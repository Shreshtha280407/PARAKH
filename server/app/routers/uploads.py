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

P6 extends this SAME machinery with a second session `target`:

  "evidence" -- exactly the protocol above (default, fully backward
    compatible with every P2.1/P2.2 caller that never sets `target` at all).
  "manifest" -- carries a P5 SignedManifestPackage envelope (see
    apps/android/core/seal/.../SealManifest.kt) through the identical
    open/chunk/complete flow instead of a second, parallel protocol. On
    complete, the envelope's Android-Keystore ECDSA signature is verified
    (server/app/manifest_verify.py) and a DeviceManifest row records the
    result. A "manifest" session is never task-scoped and never counts
    against the 120 MB evidence quota -- it is capped by its own small
    MANIFEST_MAX_BYTES ceiling instead.

`revision_id`/`client_evidence_id` (both optional, both set together by a
P6-aware client) bind a session to the exact P5 outbox row it came from:
  - An "evidence" session with a `revision_id` requires a RECEIVED/COMPLETE
    DeviceManifest to already exist for that revision, and its eventual
    complete() cross-checks the uploaded bytes' sha256/size/task binding
    against that manifest's declaration for the matching evidenceId --
    tampered, substituted, or re-ordered evidence is rejected (409) even if
    it would otherwise pass the plain size+hash check.
  - Both "evidence" and "manifest" opens are idempotent "recover" calls: an
    open, non-expired session already matching (assessment, target,
    revision_id, client_evidence_id) is returned as-is instead of duplicated,
    so a lost response to POST /uploads never orphans a second session.
  - A revision superseded by a newer one (see SealOrchestrator.
    discardAndReopen on the phone) is rejected on any further mutation --
    see _require_worker_token_for_session's revision check below.
"""
import datetime
from decimal import Decimal
from typing import Union

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs, manifest_verify, models, quota, schemas
from ..config import settings
from ..db import get_db
from ..storage import get_storage, manifest_upload_key_for, upload_key_for
from ..worker_tokens import hash_worker_token

router = APIRouter(prefix="/uploads", tags=["uploads"])

# The one storage instance the whole API shares (routers/evidence.py,
# routers/reports.py and routers/verify.py all reach it through here, and
# the test suite monkeypatches it here). get_storage() picks LocalDiskStorage
# or S3Storage from STORAGE_BACKEND -- see server/app/storage.py.
_storage = get_storage()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware_utc(dt: datetime.datetime) -> datetime.datetime:
    """SQLite drops tzinfo on round-trip (no native TIMESTAMPTZ type) even
    for columns declared DateTime(timezone=True); PostgreSQL does not. We
    always write UTC, so a naive value read back is UTC with the tzinfo
    just missing -- reattach it rather than compare naive-vs-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.timezone.utc)


def _audit(db: Session, assessment_id: int, actor_user_id: int | None, actor_role: str, action: str, details: dict | None = None) -> None:
    # Local copy of assessments._audit's exact shape (importing it directly
    # would create a cycle: assessments.py does not import uploads.py today,
    # but evidence.py imports uploads.py and is itself imported before
    # assessments.py has a chance to settle in a different ordering -- a
    # single trivial helper duplicated once here is simpler than reasoning
    # about import order across routers).
    db.add(models.AuditLog(
        assessment_id=assessment_id, actor_user_id=actor_user_id, actor_role=actor_role,
        action=action, details=details or {},
    ))


def _require_worker_token_for_session(
    session_id: int,
    x_worker_token: str | None,
    db: Session,
    lock: bool = False,
    require_draft: bool = False,
) -> models.UploadSession:
    """lock=True takes a row lock (SELECT ... FOR UPDATE) on the session for
    the rest of the caller's transaction -- required before any mutation
    (chunk append, complete) so two concurrent requests for the same session
    serialize instead of both reading the pre-mutation state and double-
    applying it (see put_chunk/complete_upload). require_draft=True (also
    only for mutations) enforces evidence-locking: once an assessment has
    been submitted, nothing may be added to it, even a session opened
    before the submit -- and (P6) rejects any further mutation of a session
    whose revision has since been superseded by a newer one."""
    upload = db.get(models.UploadSession, session_id, with_for_update=lock)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload session not found")
    assessment = db.get(models.Assessment, upload.assessment_id)
    if (
        assessment.worker_token_status != "active"
        or not x_worker_token
        or hash_worker_token(x_worker_token) != assessment.worker_token_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    # P7: a reopened (needs_reassessment) assessment may still mutate a
    # session that belongs to its CURRENT open revision -- see
    # open_upload_session's matching check, which is what actually decides
    # whether a *new* session may be opened in the first place. This only
    # widens which already-open sessions may be chunked/completed; it never
    # lets a session opened under a now-superseded revision proceed (the
    # revision-superseded check right below still applies).
    if require_draft and assessment.status not in ("draft", "needs_reassessment"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"assessment is '{assessment.status}'; evidence can no longer be added")
    if (
        require_draft
        and upload.target == "evidence"
        and upload.revision_id
        and assessment.current_revision_id
        and upload.revision_id != assessment.current_revision_id
    ):
        # Only evidence sessions can be "superseded" -- a manifest session is
        # what *establishes* a revision as current in the first place (see
        # _complete_manifest_upload), so this must never block a brand-new
        # revision's own manifest from completing while an older revision is
        # still the recorded current_revision_id.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"revision '{upload.revision_id}' has been superseded by '{assessment.current_revision_id}'; abandon this upload",
        )
    return upload


def _status_payload(db: Session, session: models.UploadSession) -> schemas.UploadSessionOut:
    assessment = db.get(models.Assessment, session.assessment_id)
    pack = db.get(models.QualificationPack, assessment.pack_id)
    total_remaining = pack.final_evidence_budget_bytes - quota.assessment_bytes_committed(db, assessment.id)
    task_remaining = None
    if session.assessment_task_id is not None:
        task = db.get(models.AssessmentTask, session.assessment_task_id)
        task_remaining = task.budget_bytes - quota.task_bytes_committed(db, task.id)
    return schemas.UploadSessionOut(
        id=session.id,
        assessment_id=session.assessment_id,
        assessment_task_id=session.assessment_task_id,
        target=session.target,
        kind=session.kind,
        mime=session.mime,
        claimed_size_bytes=session.claimed_size_bytes,
        received_bytes=session.received_bytes,
        next_chunk_index=session.next_chunk_index,
        status=session.status,
        opened_at=session.opened_at,
        expires_at=session.expires_at,
        revision_id=session.revision_id,
        client_evidence_id=session.client_evidence_id,
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
    if (
        assessment.worker_token_status != "active"
        or not x_worker_token
        or hash_worker_token(x_worker_token) != assessment.worker_token_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    # P7: a targeted reassessment reopens specific tasks on the SAME
    # assessment (status 'needs_reassessment') rather than requiring a new
    # Assessment -- see models.AssessmentRevision/ReassessmentRequest. The
    # active (status='open') AssessmentRevision row is the sole source of
    # truth for which tasks may receive NEW evidence in that state; every
    # other task stays locked even though the assessment itself accepts
    # uploads again.
    active_revision = None
    if assessment.status == "needs_reassessment":
        active_revision = (
            db.query(models.AssessmentRevision)
            .filter_by(assessment_id=assessment.id, revision_number=assessment.revision_number, status="open")
            .one_or_none()
        )
        if active_revision is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no open reassessment revision for this assessment")
    elif assessment.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"assessment is '{assessment.status}'; evidence can no longer be added")

    if active_revision is not None and body.target == "evidence":
        reopened = active_revision.reopened_task_codes or []
        if body.task_code not in reopened:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"task {body.task_code} was not reopened for reassessment (reopened: {reopened}); it is locked",
            )

    # Serialize all quota reservations / recovery lookups for this
    # assessment: without this lock, two concurrent POSTs can each read
    # "fits"/"no existing session" before either commits, so both succeed
    # even though combined they shouldn't (check-then-act race). Locking the
    # assessment (not just the task) closes the same race across *different*
    # tasks too, since the 120 MB total budget is shared across all five.
    db.execute(select(models.Assessment).where(models.Assessment.id == assessment.id).with_for_update())

    # Note: no upfront "is this revision superseded?" check here -- a
    # manifest-target session is exactly what ESTABLISHES a revision as
    # current (see _complete_manifest_upload), so a brand-new revision's own
    # manifest must always be allowed to open/complete even while an older
    # revision is still assessment.current_revision_id. An evidence-target
    # session with a stale revision_id is rejected naturally below (no
    # received/complete manifest will be found for it once superseded), and
    # any already-open stale session is rejected on its next mutation by
    # _require_worker_token_for_session's target="evidence"-scoped check.

    # P6 "begin or recover": an open, non-expired session already covering
    # this exact revision/item is returned as-is rather than duplicated.
    # Pre-P6 callers never set revision_id, so this never fires for them.
    if body.revision_id:
        existing = (
            db.query(models.UploadSession)
            .filter_by(
                assessment_id=assessment.id, target=body.target, revision_id=body.revision_id,
                client_evidence_id=body.client_evidence_id, status="open",
            )
            .filter(models.UploadSession.expires_at > _utcnow())
            .one_or_none()
        )
        if existing is not None:
            db.commit()
            return _status_payload(db, existing)

    if body.target == "manifest":
        if body.claimed_size_bytes > manifest_verify.MANIFEST_MAX_BYTES:
            raise HTTPException(409, f"manifest exceeds the {manifest_verify.MANIFEST_MAX_BYTES}-byte ceiling")
        session = models.UploadSession(
            assessment_id=assessment.id,
            target="manifest",
            claimed_size_bytes=body.claimed_size_bytes,
            storage_key="",
            revision_id=body.revision_id,
            expires_at=_utcnow() + datetime.timedelta(minutes=settings.upload_session_ttl_minutes),
        )
        db.add(session)
        db.flush()
        session.storage_key = manifest_upload_key_for(assessment.id, session.id)
    else:
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

        if body.revision_id:
            # Enforce manifest-before-evidence ordering server-side too (P5's
            # own outbox always commits the manifest at priority 0, but a
            # client bug or a malicious caller must not be able to smuggle
            # evidence in ahead of a verified manifest to declare for it).
            manifest = (
                db.query(models.DeviceManifest)
                .filter_by(assessment_id=assessment.id, revision_id=body.revision_id)
                .filter(models.DeviceManifest.status.in_(("received", "complete")))
                .one_or_none()
            )
            if manifest is None:
                raise HTTPException(
                    409, "manifest has not been received/verified yet for this revision -- upload it first"
                )

        session = models.UploadSession(
            assessment_id=assessment.id,
            assessment_task_id=task.id,
            target="evidence",
            kind=body.kind,
            mime=body.mime,
            claimed_size_bytes=body.claimed_size_bytes,
            storage_key="",
            revision_id=body.revision_id,
            client_evidence_id=body.client_evidence_id,
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
    body = await request.body()
    return _put_chunk(session_id, chunk_index, body, x_worker_token, db)


def _put_chunk(
    session_id: int,
    chunk_index: int,
    body: bytes,
    x_worker_token: str | None,
    db: Session,
) -> schemas.ChunkAck:
    """Synchronous core of PUT /chunks/{index} -- split out from the async
    route handler (which only needs to await request.body() first) so it's
    directly callable with raw bytes from tests proving real concurrency
    with two independent DB sessions/threads."""
    session = _require_worker_token_for_session(session_id, x_worker_token, db, lock=True, require_draft=True)

    if session.status != "open":
        raise HTTPException(409, f"upload session is {session.status}, not open")
    if _aware_utc(session.expires_at) <= _utcnow():
        session.status = "expired"
        db.commit()
        raise HTTPException(409, "upload session has expired; open a new one")

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
    session.last_rejection_reason = None
    db.commit()
    db.refresh(session)
    return schemas.ChunkAck(
        chunk_index=chunk_index, received_bytes=session.received_bytes,
        next_chunk_index=session.next_chunk_index, status=session.status,
    )


@router.post("/{session_id}/complete", response_model=Union[schemas.UploadReceipt, schemas.ManifestReceipt])
def complete_upload(
    session_id: int,
    body: schemas.UploadCompleteRequest,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    session = _require_worker_token_for_session(session_id, x_worker_token, db, lock=True, require_draft=True)
    if session.target == "manifest":
        return _complete_manifest_upload(db, session, body)
    return _complete_evidence_upload(db, session, body)


def _maybe_complete_manifest(db: Session, manifest: models.DeviceManifest, assessment: models.Assessment) -> None:
    """Flip a DeviceManifest to 'complete' once every item it declares has a
    matching, verified EvidenceItem. This is the ONLY gate that lets
    submit_assessment move a P6-synced assessment out of 'draft' (or, P7,
    resubmit a targeted-reassessment revision out of 'needs_reassessment')
    -- see routers/assessments.py::submit_assessment.

    P7: an item whose client_evidence_id already has a verified EvidenceItem
    from an EARLIER revision is "inherited" (the phone re-declared an
    unchanged task's evidence by reference instead of re-uploading already-
    vault-deleted bytes -- see docs/gates/P7.md section 3). Two things are
    enforced here that were not needed before versioned resubmission
    existed: the inherited declaration must exactly match what was actually
    verified (sha256 + byte count), and it must not smuggle NEW evidence
    into a task the active revision never reopened.
    """
    if manifest.status == "complete":
        return

    active_revision = (
        db.query(models.AssessmentRevision)
        .filter_by(assessment_id=assessment.id, revision_id=manifest.revision_id)
        .one_or_none()
    )
    reopened = set(active_revision.reopened_task_codes) if active_revision and active_revision.reopened_task_codes else None

    for item in manifest.declared_items:
        task = db.query(models.AssessmentTask).filter_by(
            assessment_id=assessment.id, task_code=item["task_code"]
        ).one_or_none()
        if task is None:
            return
        found = db.query(models.EvidenceItem).filter_by(
            assessment_task_id=task.id, client_evidence_id=item["evidence_id"],
        ).one_or_none()
        if found is None:
            return  # not every declared item has arrived/verified yet -- try again later

        is_inherited = found.revision_id is not None and found.revision_id != manifest.revision_id
        if is_inherited:
            mismatched = [
                field for field, ok in (
                    ("sha256", found.sha256 == item["sha256"]),
                    ("byte count", found.declared_size_bytes == item["bytes"]),
                    ("assistance snapshot", found.assistance == item.get("assistance")),
                ) if not ok
            ]
            if mismatched:
                reason = (
                    f"inherited item {item['evidence_id']} for task {item['task_code']} does not match the "
                    f"previously verified evidence (mismatched: {', '.join(mismatched)})"
                )
                manifest.status = "rejected"
                manifest.rejection_reason = reason
                _audit(
                    db, assessment.id, actor_user_id=None, actor_role="system",
                    action="manifest_rejected_inherited_mismatch",
                    details={"client_evidence_id": item["evidence_id"], "task_code": item["task_code"], "mismatched": mismatched},
                )
                db.commit()
                return
        elif reopened is not None and item["task_code"] not in reopened:
            # A genuinely new upload (same revision as this manifest, not
            # inherited) for a task the active revision never reopened --
            # the server-side lock, independent of the UI affordance.
            reason = f"task {item['task_code']} was not reopened for reassessment; new evidence is not allowed"
            manifest.status = "rejected"
            manifest.rejection_reason = reason
            _audit(
                db, assessment.id, actor_user_id=None, actor_role="system",
                action="manifest_rejected_locked_task",
                details={"client_evidence_id": item["evidence_id"], "task_code": item["task_code"]},
            )
            db.commit()
            return

    manifest.status = "complete"
    manifest.verified_at = _utcnow()
    _audit(
        db, assessment.id, actor_user_id=None, actor_role="system", action="sync_package_complete",
        details={"revision_id": manifest.revision_id, "item_count": manifest.item_count},
    )
    db.commit()


def _complete_evidence_upload(db: Session, session: models.UploadSession, body: schemas.UploadCompleteRequest) -> schemas.UploadReceipt:
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

    # Turn the received chunks into one directly readable object before
    # anything hashes, serves or ffmpegs it. A no-op on local disk (append
    # already built the file in place); on S3 this coalesces the staged
    # per-chunk objects into the single object EvidenceItem.storage_key
    # will point at. Idempotent, so a replayed complete() is safe.
    _storage.finalize(session.storage_key, content_type=session.mime)

    server_sha256 = _storage.sha256(session.storage_key)
    if server_sha256 != body.client_sha256.lower():
        raise HTTPException(
            409, f"hash mismatch: server computed {server_sha256}, client declared {body.client_sha256}"
        )

    task = db.get(models.AssessmentTask, session.assessment_task_id)
    assessment = db.get(models.Assessment, task.assessment_id)

    # P6: once a session is bound to a sealed revision, never trust its own
    # declared kind/mime/task alone -- cross-check against the already
    # signature-verified manifest's declaration for this exact evidenceId.
    manifest = None
    if session.revision_id:
        manifest = (
            db.query(models.DeviceManifest)
            .filter_by(assessment_id=assessment.id, revision_id=session.revision_id)
            .filter(models.DeviceManifest.status.in_(("received", "complete")))
            .one_or_none()
        )
        if manifest is None:
            raise HTTPException(409, "manifest has not been received/verified yet for this revision")
        declared = next(
            (i for i in manifest.declared_items if i["evidence_id"] == session.client_evidence_id), None
        )
        if declared is None:
            session.last_rejection_reason = "evidenceId not declared in the verified manifest"
            db.commit()
            raise HTTPException(409, session.last_rejection_reason)
        mismatched = [
            field for field, ok in (
                ("sha256", declared["sha256"] == server_sha256),
                ("byte count", declared["bytes"] == session.received_bytes),
                ("task binding", declared["task_code"] == task.task_code),
            ) if not ok
        ]
        if mismatched:
            session.last_rejection_reason = (
                f"evidence does not match the verified manifest's declaration for this item "
                f"(mismatched: {', '.join(mismatched)})"
            )
            _audit(
                db, assessment.id, actor_user_id=None, actor_role="system", action="evidence_manifest_mismatch",
                details={"client_evidence_id": session.client_evidence_id, "mismatched": mismatched},
            )
            db.commit()
            raise HTTPException(409, session.last_rejection_reason)

    device_captured_at = None
    if manifest is not None and declared.get("captured_at_millis") is not None:
        device_captured_at = datetime.datetime.fromtimestamp(
            declared["captured_at_millis"] / 1000, tz=datetime.timezone.utc
        )

    evidence = models.EvidenceItem(
        assessment_task_id=task.id,
        kind=session.kind,
        mime=session.mime,
        declared_size_bytes=session.received_bytes,
        storage_key=session.storage_key,
        sha256=server_sha256,
        revision_id=session.revision_id,
        client_evidence_id=session.client_evidence_id,
        device_captured_at=device_captured_at,
        assistance=declared.get("assistance") if manifest is not None else None,
        quality_check_status=(declared["assistance"]["status"].lower()
                              if manifest is not None and declared.get("assistance") else "not_run"),
    )
    if evidence.kind == "video":
        # Distinguishes "a thumbnail job is queued" from the model default
        # "not_applicable" (which means "this kind never gets one" --
        # true for photos, not yet true for a video whose job hasn't run).
        evidence.thumbnail_status = "queued"
    evidence.metadata_status = "queued"
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
    session.last_rejection_reason = None

    # One atomic commit: EvidenceItem + task/assessment byte counters +
    # session completion + job enqueue all land together or not at all --
    # a crash between a separate evidence-commit and a separate job-commit
    # would otherwise leave evidence stored with no verification ever queued.
    jobs.enqueue(db, "verify_evidence", {"evidence_item_id": evidence.id}, commit=False)
    if evidence.kind == "video":
        jobs.enqueue(db, "generate_thumbnail", {"evidence_item_id": evidence.id}, commit=False)
    jobs.enqueue(db, "extract_metadata", {"evidence_item_id": evidence.id}, commit=False)
    db.commit()
    db.refresh(evidence)
    db.refresh(session)

    if manifest is not None:
        _maybe_complete_manifest(db, manifest, assessment)

    return schemas.UploadReceipt(
        session_id=session.id, evidence_id=evidence.id, sha256=evidence.sha256,
        byte_count=evidence.declared_size_bytes, mime=evidence.mime, kind=evidence.kind,
        storage_status="stored", completed_at=session.completed_at,
    )


def _manifest_receipt(session: models.UploadSession, manifest: models.DeviceManifest) -> schemas.ManifestReceipt:
    return schemas.ManifestReceipt(
        session_id=session.id, manifest_id=manifest.id, assessment_id=manifest.assessment_id,
        revision_id=manifest.revision_id, sha256=manifest.sha256, item_count=manifest.item_count,
        declared_total_bytes=manifest.declared_total_bytes,
        status="rejected" if manifest.status == "rejected" else "received",
        rejection_reason=manifest.rejection_reason, received_at=manifest.received_at,
    )


def _complete_manifest_upload(db: Session, session: models.UploadSession, body: schemas.UploadCompleteRequest) -> schemas.ManifestReceipt:
    if session.status == "completed":
        manifest = db.get(models.DeviceManifest, session.manifest_id)
        return _manifest_receipt(session, manifest)
    if session.status != "open":
        raise HTTPException(409, f"upload session is {session.status}, cannot complete")

    if session.received_bytes != session.claimed_size_bytes:
        raise HTTPException(
            409, f"size mismatch: received {session.received_bytes} bytes, declared {session.claimed_size_bytes}"
        )

    _storage.finalize(session.storage_key, content_type="application/json")

    server_sha256 = _storage.sha256(session.storage_key)
    if server_sha256 != body.client_sha256.lower():
        raise HTTPException(
            409, f"hash mismatch: server computed {server_sha256}, client declared {body.client_sha256}"
        )

    assessment = db.get(models.Assessment, session.assessment_id)
    # The manifest envelope is small (bounded by MANIFEST_MAX_BYTES, a JSON
    # metadata document, never media bytes) -- unlike evidence files, there
    # is no "never load a whole file into memory" constraint for it; that
    # rule exists for the Android client's own evidence files, not this.
    envelope_bytes = _storage.read(session.storage_key)

    existing = (
        db.query(models.DeviceManifest)
        .filter_by(assessment_id=assessment.id, revision_id=session.revision_id)
        .one_or_none()
    )

    try:
        parsed = manifest_verify.parse_and_verify_envelope(envelope_bytes, session.revision_id)
    except manifest_verify.ManifestVerificationError as e:
        reason = str(e)
        manifest_row = existing or models.DeviceManifest(
            assessment_id=assessment.id, revision_id=session.revision_id,
            idempotency_key=f"{assessment.id}:{session.revision_id}",
            canonical_json="", sha256=server_sha256, signature_b64="", algorithm="",
            signer_key_id="", signer_public_key_b64="", declared_items=[],
        )
        manifest_row.status = "rejected"
        manifest_row.rejection_reason = reason
        db.add(manifest_row)
        db.flush()
        session.status = "completed"
        session.manifest_id = manifest_row.id
        session.completed_at = _utcnow()
        session.last_rejection_reason = reason
        _audit(
            db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_rejected",
            details={"reason": reason, "revision_id": session.revision_id},
        )
        db.commit()
        raise HTTPException(409, f"manifest rejected: {reason}")

    if existing is not None:
        if existing.sha256 == parsed.sha256_hex:
            # Identical retry (lost acknowledgement) -- idempotent success,
            # never a second row for the same (assessment, revision).
            session.status = "completed"
            session.manifest_id = existing.id
            session.completed_at = _utcnow()
            session.last_rejection_reason = None
            db.commit()
            return _manifest_receipt(session, existing)
        raise HTTPException(409, "a different manifest already exists for this revision")

    if assessment.client_assessment_id and assessment.client_assessment_id != parsed.manifest_assessment_id:
        # Trust-on-first-use violation on the OTHER identifier space: a
        # manifest signed for a different local draft is trying to land on
        # this server-side assessment row. See Assessment.client_assessment_id's
        # docstring in models.py.
        reason = "manifest's local assessment id does not match this assessment's previously-pinned client id"
        manifest_row = models.DeviceManifest(
            assessment_id=assessment.id, revision_id=session.revision_id,
            idempotency_key=parsed.idempotency_key, canonical_json=parsed.canonical_bytes.decode("utf-8"),
            sha256=parsed.sha256_hex, signature_b64=parsed.signature_b64, algorithm=parsed.algorithm,
            signer_key_id=parsed.signer_key_id, signer_public_key_b64=parsed.signer_public_key_b64,
            status="rejected", rejection_reason=reason, item_count=len(parsed.items),
            declared_total_bytes=parsed.assessment_total_bytes, declared_items=parsed.items,
        )
        db.add(manifest_row)
        db.flush()
        session.status = "completed"
        session.manifest_id = manifest_row.id
        session.completed_at = _utcnow()
        session.last_rejection_reason = reason
        _audit(
            db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_rejected_client_id_mismatch",
            details={"revision_id": session.revision_id},
        )
        db.commit()
        raise HTTPException(409, f"manifest rejected: {reason}")

    if assessment.device_public_key_b64 and assessment.device_public_key_b64 != parsed.signer_public_key_b64:
        # Trust-on-first-use violation: a different signing key is trying to
        # continue this assessment's evidence history. Reject outright --
        # see Assessment.device_public_key_b64's docstring in models.py.
        reason = "signer public key does not match this assessment's previously-pinned device key"
        manifest_row = models.DeviceManifest(
            assessment_id=assessment.id, revision_id=session.revision_id,
            idempotency_key=parsed.idempotency_key, canonical_json=parsed.canonical_bytes.decode("utf-8"),
            sha256=parsed.sha256_hex, signature_b64=parsed.signature_b64, algorithm=parsed.algorithm,
            signer_key_id=parsed.signer_key_id, signer_public_key_b64=parsed.signer_public_key_b64,
            status="rejected", rejection_reason=reason, item_count=len(parsed.items),
            declared_total_bytes=parsed.assessment_total_bytes, declared_items=parsed.items,
        )
        db.add(manifest_row)
        db.flush()
        session.status = "completed"
        session.manifest_id = manifest_row.id
        session.completed_at = _utcnow()
        session.last_rejection_reason = reason
        _audit(
            db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_rejected_key_mismatch",
            details={"revision_id": session.revision_id},
        )
        db.commit()
        raise HTTPException(409, f"manifest rejected: {reason}")

    # P7: the active revision's FULL evidence snapshot -- inherited items
    # included -- must fit the pinned budgets, independent of
    # quota.check_quota (which only ever sees genuinely NEW bytes actively
    # being uploaded; an inherited item is never re-uploaded, so it would
    # otherwise escape budget enforcement entirely). Checked against the
    # same pinned numbers every per-item upload already uses.
    pack = db.get(models.QualificationPack, assessment.pack_id)
    if parsed.assessment_total_bytes > pack.final_evidence_budget_bytes:
        reason = (
            f"declared total {parsed.assessment_total_bytes} bytes exceeds the assessment's "
            f"{pack.final_evidence_budget_bytes}-byte budget"
        )
        manifest_row = models.DeviceManifest(
            assessment_id=assessment.id, revision_id=session.revision_id,
            idempotency_key=parsed.idempotency_key, canonical_json=parsed.canonical_bytes.decode("utf-8"),
            sha256=parsed.sha256_hex, signature_b64=parsed.signature_b64, algorithm=parsed.algorithm,
            signer_key_id=parsed.signer_key_id, signer_public_key_b64=parsed.signer_public_key_b64,
            status="rejected", rejection_reason=reason, item_count=len(parsed.items),
            declared_total_bytes=parsed.assessment_total_bytes, declared_items=parsed.items,
        )
        db.add(manifest_row)
        db.flush()
        session.status = "completed"
        session.manifest_id = manifest_row.id
        session.completed_at = _utcnow()
        session.last_rejection_reason = reason
        _audit(
            db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_rejected_budget_exceeded",
            details={"revision_id": session.revision_id, "declared_total_bytes": parsed.assessment_total_bytes},
        )
        db.commit()
        raise HTTPException(409, f"manifest rejected: {reason}")
    task_templates_by_code = {
        t.task_code: t for t in db.query(models.TaskTemplate).filter_by(pack_id=assessment.pack_id).all()
    }
    for task_code, total_bytes in parsed.task_totals.items():
        template = task_templates_by_code.get(task_code)
        if template is not None and total_bytes > template.budget_bytes:
            reason = f"task {task_code} declared total {total_bytes} bytes exceeds its {template.budget_bytes}-byte budget"
            manifest_row = models.DeviceManifest(
                assessment_id=assessment.id, revision_id=session.revision_id,
                idempotency_key=parsed.idempotency_key, canonical_json=parsed.canonical_bytes.decode("utf-8"),
                sha256=parsed.sha256_hex, signature_b64=parsed.signature_b64, algorithm=parsed.algorithm,
                signer_key_id=parsed.signer_key_id, signer_public_key_b64=parsed.signer_public_key_b64,
                status="rejected", rejection_reason=reason, item_count=len(parsed.items),
                declared_total_bytes=parsed.assessment_total_bytes, declared_items=parsed.items,
            )
            db.add(manifest_row)
            db.flush()
            session.status = "completed"
            session.manifest_id = manifest_row.id
            session.completed_at = _utcnow()
            session.last_rejection_reason = reason
            _audit(
                db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_rejected_budget_exceeded",
                details={"revision_id": session.revision_id, "task_code": task_code, "declared_total_bytes": total_bytes},
            )
            db.commit()
            raise HTTPException(409, f"manifest rejected: {reason}")

    # New assistance is bound to the actual server revision number. Inherited
    # snapshots are compared byte-for-value with the original verified item in
    # _maybe_complete_manifest; they retain their historical revision identity.
    for item in parsed.items:
        assistance = item.get("assistance")
        if assistance and item.get("processing") != "INHERITED" and assistance["revisionNumber"] != assessment.revision_number:
            raise HTTPException(409, "assistance revision number does not match active assessment revision")

    manifest_row = models.DeviceManifest(
        assessment_id=assessment.id, revision_id=parsed.revision_id,
        idempotency_key=parsed.idempotency_key, canonical_json=parsed.canonical_bytes.decode("utf-8"),
        sha256=parsed.sha256_hex, signature_b64=parsed.signature_b64, algorithm=parsed.algorithm,
        signer_key_id=parsed.signer_key_id, signer_public_key_b64=parsed.signer_public_key_b64,
        status="received", item_count=len(parsed.items), declared_total_bytes=parsed.assessment_total_bytes,
        declared_items=parsed.items, verified_at=_utcnow(),
    )
    db.add(manifest_row)
    db.flush()

    active_revision = (
        db.query(models.AssessmentRevision)
        .filter_by(assessment_id=assessment.id, revision_number=assessment.revision_number, status="open")
        .one_or_none()
    )
    if active_revision is not None:
        # Always the LATEST attempt's revision_id for this revision_number
        # -- a pre-submit discard/reseal (still draft) can legitimately
        # produce more than one revision_id for the same revision_number
        # before anything is ever submitted; only the newest one matters.
        active_revision.revision_id = parsed.revision_id

    if not assessment.device_public_key_b64:
        assessment.device_public_key_b64 = parsed.signer_public_key_b64
    if not assessment.client_assessment_id:
        assessment.client_assessment_id = parsed.manifest_assessment_id
    # Supersede any other in-flight (non-complete) manifest for this
    # assessment under a DIFFERENT, older revision -- a discard/reseal on
    # the phone generates a fresh revisionId; that old sync, if it never
    # finished, is now void (see SealOrchestrator.discardAndReopen).
    db.query(models.DeviceManifest).filter(
        models.DeviceManifest.assessment_id == assessment.id,
        models.DeviceManifest.id != manifest_row.id,
        models.DeviceManifest.status == "received",
    ).update({"status": "superseded"})
    assessment.current_revision_id = parsed.revision_id
    if parsed.declared_match_result is not None:
        assessment.declared_match_result = parsed.declared_match_result
    if parsed.declared_coverage_fraction is not None:
        assessment.declared_coverage_fraction = Decimal(str(parsed.declared_coverage_fraction))
    if parsed.declared_gap_task_codes is not None:
        assessment.declared_gap_task_codes = parsed.declared_gap_task_codes
    if parsed.declared_match_reasons is not None:
        assessment.declared_match_reasons = parsed.declared_match_reasons

    session.status = "completed"
    session.manifest_id = manifest_row.id
    session.completed_at = _utcnow()
    session.last_rejection_reason = None

    _audit(
        db, assessment.id, actor_user_id=None, actor_role="system", action="manifest_received",
        details={"revision_id": manifest_row.revision_id, "item_count": manifest_row.item_count, "sha256": manifest_row.sha256},
    )
    db.commit()
    db.refresh(manifest_row)
    db.refresh(session)

    return _manifest_receipt(session, manifest_row)
