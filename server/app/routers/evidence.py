"""Secure evidence content/thumbnail serving. See docs/gates/P2_2.md
section 5. Deliberately NO CV/AI inference anywhere in this file -- see
docs/evidence_quality_result.md for the stable not_run/queued/completed/
unavailable contract a future phase could wire up against.

Range requests (video scrubbing) are served two ways, by backend:

  * LocalDiskStorage -- Starlette's FileResponse, which implements RFC 7233
    natively. Unchanged from P2.2; no hand-rolled Range parsing involved.
  * S3Storage -- there is no local file to hand to FileResponse, so the
    object is PROXIED through this endpoint as a ranged stream (see
    _ranged_stream_response). Deliberately a proxy rather than a redirect
    to a presigned URL: a presigned URL is a bearer credential in a query
    string that would escape this module's authorization check entirely,
    land in browser history, logs and Referer headers, and stay valid for
    its whole TTL regardless of whether the assessor still has access to
    the assessment.

Either way the authorization model is identical and unchanged: an
assessor/admin JWT, or this assessment's own active worker token.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..storage import LocalDiskStorage, Storage
from . import uploads  # the one storage singleton lives at uploads._storage; tests monkeypatch it there
from .assessments import _assessor_or_worker_token

router = APIRouter(prefix="/assessments/{assessment_id}/evidence", tags=["evidence"])

# Private assessment evidence must never land in a shared/CDN cache -- it
# is authorized per request, per assessment (and, on Vercel, reaches the
# browser through a same-origin rewrite that would otherwise be eligible
# for edge caching).
_PRIVATE_CACHE = {"Cache-Control": "private, no-store", "Accept-Ranges": "bytes"}

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Single byte range -> inclusive (start, end), or None to serve the
    whole object. Only the single-range form is honoured, which is all any
    browser/video player actually sends; a multi-range request degrades to
    a normal 200 full response rather than being mis-served."""
    match = _RANGE_RE.match(header.strip())
    if not match or size == 0:
        return None
    raw_start, raw_end = match.groups()
    if raw_start == "":
        if raw_end == "":
            return None
        # "bytes=-N" -- the final N bytes.
        length = min(int(raw_end), size)
        if length == 0:
            return None
        return size - length, size - 1
    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    return start, min(end, size - 1)


def _ranged_stream_response(
    storage: Storage, key: str, media_type: str, range_header: str | None
) -> Response:
    """RFC 7233 ranged streaming for any backend without a local file.
    Streams in bounded blocks -- a 100 MB video is never buffered whole."""
    size = storage.size(key)
    requested = _parse_range(range_header, size) if range_header else None

    if requested is None:
        return StreamingResponse(
            storage.open_stream(key), media_type=media_type,
            headers={**_PRIVATE_CACHE, "Content-Length": str(size)},
        )

    start, end = requested
    if start >= size or start > end:
        # RFC 7233: unsatisfiable range must say so, and say how big the
        # object actually is -- players rely on this to recover.
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={**_PRIVATE_CACHE, "Content-Range": f"bytes */{size}"},
        )

    return StreamingResponse(
        storage.open_stream(key, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            **_PRIVATE_CACHE,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )


def _serve(key: str, media_type: str, request: Request, missing_detail: str) -> Response:
    """Backend-agnostic private object serving."""
    storage = uploads._storage

    if isinstance(storage, LocalDiskStorage):
        # Unchanged P2.2 path: a real file, Range handled by Starlette.
        path = storage.path_for(key)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, missing_detail)
        return FileResponse(path, media_type=media_type, headers=_PRIVATE_CACHE)

    if not storage.exists(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, missing_detail)
    return _ranged_stream_response(storage, key, media_type, request.headers.get("range"))


def _evidence_for_assessment(db: Session, assessment_id: int, evidence_id: int) -> models.EvidenceItem:
    evidence = db.get(models.EvidenceItem, evidence_id)
    if evidence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence not found")
    task = db.get(models.AssessmentTask, evidence.assessment_task_id)
    if task is None or task.assessment_id != assessment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence not found on this assessment")
    return evidence


@router.get("/{evidence_id}/content")
def get_evidence_content(
    assessment_id: int,
    evidence_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> Response:
    """Dual auth, same as GET /assessments/{id} -- assessor/admin JWT, or
    this assessment's own (active) worker token."""
    evidence = _evidence_for_assessment(db, assessment_id, evidence_id)
    return _serve(
        evidence.storage_key, evidence.mime, request,
        "evidence file is missing from storage",
    )


@router.get("/{evidence_id}/thumbnail")
def get_evidence_thumbnail(
    assessment_id: int,
    evidence_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> Response:
    """Photos serve their own bytes directly (no separate thumbnail job --
    see models.EvidenceItem.thumbnail_status's 'not_applicable' default).
    Videos serve the ffmpeg-extracted frame once the background job
    completes; while queued, or if ffmpeg extraction failed/is unavailable,
    this is a graceful 404 (never a 500) so the dashboard can show a
    pending/placeholder state instead of crashing."""
    evidence = _evidence_for_assessment(db, assessment_id, evidence_id)

    if evidence.kind == "photo":
        return _serve(
            evidence.storage_key, evidence.mime, request,
            "evidence file is missing from storage",
        )

    if evidence.thumbnail_status != "completed" or not evidence.thumbnail_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no thumbnail available (status: {evidence.thumbnail_status})")
    return _serve(
        evidence.thumbnail_key, "image/jpeg", request,
        "thumbnail file is missing from storage",
    )
