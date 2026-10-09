"""Resumable evidence upload protocol.

Chosen protocol: ORDERED SEQUENTIAL CHUNKS. A session tracks
next_chunk_index (starting at 0) and received_bytes. A client:

  1. POST /uploads -- declares task_code, kind, mime and the total size it
     intends to upload. The server validates MIME/kind/size, checks task +
     120 MB total quota, and RESERVES that quota for the session's lifetime
     (see server/app/quota.py) before returning a session id.
  2. PUT /uploads/{id}/chunks/{chunk_index} -- raw bytes body, one call per
     chunk, STRICTLY IN ORDER. chunk_index must equal the session's current
     next_chunk_index, or be one less than it (an already-received chunk,
     replayed after the client never saw the ack -- treated as a no-op
     success rather than an error, so retries are safe). Anything else
     (skipping ahead, or far behind) is 409 Conflict.
  3. GET /uploads/{id} -- resume/status: received_bytes, next_chunk_index,
     so a client that lost its local state (app restart, etc.) knows
     exactly where to continue.
  4. POST /uploads/{id}/complete -- client declares its own SHA-256 as a
     cross-check; the server independently streams the stored bytes through
     SHA-256 itself and NEVER trusts the client value alone. The EvidenceItem
     is only created, atomically, once byte count AND both hashes match.
     Retrying complete() after a successful completion returns the exact
     same receipt -- it does not create a second EvidenceItem.

All four endpoints require the X-Worker-Token for the assessment that owns
the session's task (see docs/worker_capability_tokens.md) -- there is no
worker login, so this opaque per-assessment token is what stands in for
"only this worker's device may upload to this assessment".
"""
import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import jobs, models, quota, schemas
from ..config import settings
from ..db import get_db
from ..storage import LocalDiskStorage, extension_for_mime, upload_key_for
from ..worker_tokens import hash_worker_token

router = APIRouter(prefix="/uploads", tags=["uploads"])

_storage = LocalDiskStorage(settings.evidence_dir)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware_utc(dt: datetime.datetime) -> datetime.datetime:
    """SQLite drops tzinfo on round-trip (no native TIMESTAMPTZ type) even
    for columns declared DateTime(timezone=True); PostgreSQL does not. We
    always write UTC, so a naive value read back is UTC with the tzinfo
    just missing -- reattach it rather than compare naive-vs-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.timezone.utc)


def _require_worker_token_for_session(
    session_id: int,
    x_worker_token: str | None,
    db: Session,
) -> models.UploadSession:
    upload = db.get(models.UploadSession, session_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload session not found")
    task = db.get(models.AssessmentTask, upload.assessment_task_id)
    assessment = db.get(models.Assessment, task.assessment_id)
    if not x_worker_token or hash_worker_token(x_worker_token) != assessment.worker_token_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    return upload


def _status_payload(db: Session, session: models.UploadSession) -> schemas.UploadSessionOut:
    task = db.get(models.AssessmentTask, session.assessment_task_id)
    pack = db.get(models.QualificationPack, db.get(models.Assessment, task.assessment_id).pack_id)
    task_remaining = task.budget_bytes - quota.task_bytes_committed(db, task.id)
    total_remaining = pack.final_evidence_budget_bytes - quota.assessment_bytes_committed(db, task.assessment_id)
    return schemas.UploadSessionOut(
        id=session.id,
        assessment_task_id=session.assessment_task_id,
        kind=session.kind,
        mime=session.mime,
        claimed_size_bytes=session.claimed_size_bytes,
        received_bytes=session.received_bytes,
        next_chunk_index=session.next_chunk_index,
        status=session.status,
        opened_at=session.opened_at,
        expires_at=session.expires_at,
        task_bytes_remaining=task_remaining,
        total_bytes_remaining=total_remaining,
    )


@router.post("", response_model=schemas.UploadSessionOut, status_code=201)
def open_upload_session(
    body: schemas.UploadSessionCreate,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.UploadSessionOut:
    assessment = db.get(models.Assessment, body.assessment_id)
    if assessment is None:
        raise HTTPException(404, "assessment not found")
    if not x_worker_token or hash_worker_token(x_worker_token) != assessment.worker_token_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    task = db.query(models.AssessmentTask).filter_by(
        assessment_id=body.assessment_id, task_code=body.task_code
    ).one_or_none()
    if task is None:
        raise HTTPException(404, f"task {body.task_code} not found on this assessment")

    pack = db.get(models.QualificationPack, assessment.pack_id)
    try:
        quota.check_quota(db, task, body.claimed_size_bytes, pack.final_evidence_budget_bytes)
    except quota.QuotaExceeded as e:
        raise HTTPException(409, str(e)) from e

    session = models.UploadSession(
        assessment_task_id=task.id,
        kind=body.kind,
        mime=body.mime,
        claimed_size_bytes=body.claimed_size_bytes,
        storage_key="",  # set below once we have the id
        expires_at=_utcnow() + datetime.timedelta(minutes=settings.upload_session_ttl_minutes),
    )
    db.add(session)
    db.flush()
    session.storage_key = upload_key_for(assessment.id, task.task_code, session.id)
    # Defensive: guarantee an empty file to append onto. Session ids are
    # auto-increment and never reused in a real deployment, but a stray
    # leftover (a previous failed run against the same dev volume, e.g.)
    # must never silently get prepended onto this session's bytes.
    if _storage.exists(session.storage_key):
        _storage.delete(session.storage_key)
    db.commit()
    db.refresh(session)
    return _status_payload(db, session)


@router.get("/{session_id}", response_model=schemas.UploadSessionOut)
def get_upload_session(
    session_id: int,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.UploadSessionOut:
    session = _require_worker_token_for_session(session_id, x_worker_token, db)
    return _status_payload(db, session)


@router.put("/{session_id}/chunks/{chunk_index}", response_model=schemas.ChunkAck)
async def put_chunk(
    session_id: int,
    chunk_index: int,
    request: Request,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.ChunkAck:
    session = _require_worker_token_for_session(session_id, x_worker_token, db)

    if session.status != "open":
        raise HTTPException(409, f"upload session is {session.status}, not open")
    if _aware_utc(session.expires_at) <= _utcnow():
        session.status = "expired"
        db.commit()
        raise HTTPException(409, "upload session has expired; open a new one")

    body = await request.body()
    if len(body) == 0:
        raise HTTPException(422, "chunk body must not be empty")
    if len(body) > settings.upload_chunk_max_bytes:
        raise HTTPException(413, f"chunk exceeds the {settings.upload_chunk_max_bytes}-byte chunk ceiling")

    if chunk_index == session.next_chunk_index - 1:
        # Replay of an already-acked chunk (client never saw our response) -- idempotent no-op.
        return schemas.ChunkAck(
            chunk_index=chunk_index, received_bytes=session.received_bytes,
            next_chunk_index=session.next_chunk_index, status=session.status,
        )
    if chunk_index != session.next_chunk_index:
        raise HTTPException(
            409, f"out-of-order chunk: expected index {session.next_chunk_index}, got {chunk_index}"
        )
    if session.received_bytes + len(body) > session.claimed_size_bytes:
        raise HTTPException(
            409, f"chunk would exceed the session's declared total of {session.claimed_size_bytes} bytes"
        )

    _storage.append(session.storage_key, body)
    db.add(models.UploadChunk(upload_session_id=session.id, chunk_index=chunk_index, size_bytes=len(body)))
    session.received_bytes += len(body)
    session.next_chunk_index += 1
    db.commit()
    db.refresh(session)
    return schemas.ChunkAck(
        chunk_index=chunk_index, received_bytes=session.received_bytes,
        next_chunk_index=session.next_chunk_index, status=session.status,
    )


@router.post("/{session_id}/complete", response_model=schemas.UploadReceipt)
def complete_upload(
    session_id: int,
    body: schemas.UploadCompleteRequest,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.UploadReceipt:
    session = _require_worker_token_for_session(session_id, x_worker_token, db)

    if session.status == "completed":
        # Idempotent retry: same receipt, no new EvidenceItem.
        evidence = db.get(models.EvidenceItem, session.evidence_item_id)
        return schemas.UploadReceipt(
            session_id=session.id, evidence_id=evidence.id, sha256=evidence.sha256,
            byte_count=evidence.declared_size_bytes, mime=evidence.mime, kind=evidence.kind,
            storage_status="stored", completed_at=session.completed_at,
        )
    if session.status != "open":
        raise HTTPException(409, f"upload session is {session.status}, cannot complete")

    if session.received_bytes != session.claimed_size_bytes:
        raise HTTPException(
            409, f"size mismatch: received {session.received_bytes} bytes, declared {session.claimed_size_bytes}"
        )

    server_sha256 = _storage.sha256(session.storage_key)
    if server_sha256 != body.client_sha256.lower():
        raise HTTPException(
            409, f"hash mismatch: server computed {server_sha256}, client declared {body.client_sha256}"
        )

    task = db.get(models.AssessmentTask, session.assessment_task_id)
    assessment = db.get(models.Assessment, task.assessment_id)

    evidence = models.EvidenceItem(
        assessment_task_id=task.id,
        kind=session.kind,
        mime=session.mime,
        declared_size_bytes=session.received_bytes,
        storage_key=session.storage_key,
        sha256=server_sha256,
    )
    db.add(evidence)
    db.flush()

    task.bytes_used += session.received_bytes
    task.status = "evidence_added"
    assessment.total_bytes_used += session.received_bytes

    session.status = "completed"
    session.server_sha256 = server_sha256
    session.client_sha256 = body.client_sha256.lower()
    session.evidence_item_id = evidence.id
    session.completed_at = _utcnow()

    db.commit()
    db.refresh(evidence)
    db.refresh(session)

    jobs.enqueue(db, "verify_evidence", {"evidence_item_id": evidence.id})

    return schemas.UploadReceipt(
        session_id=session.id, evidence_id=evidence.id, sha256=evidence.sha256,
        byte_count=evidence.declared_size_bytes, mime=evidence.mime, kind=evidence.kind,
        storage_status="stored", completed_at=session.completed_at,
    )
