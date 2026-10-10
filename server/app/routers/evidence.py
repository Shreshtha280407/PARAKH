"""Secure evidence content/thumbnail serving. See docs/gates/P2_2.md
section 5. Range requests (video scrubbing) are handled by Starlette's
FileResponse, which implements RFC 7233 natively -- no hand-rolled Range
parsing needed. Deliberately NO CV/AI inference anywhere in this file --
see docs/evidence_quality_result.md for the stable not_run/queued/
completed/unavailable contract a future phase could wire up against.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from . import uploads  # the one storage singleton lives at uploads._storage; tests monkeypatch it there
from .assessments import _assessor_or_worker_token

router = APIRouter(prefix="/assessments/{assessment_id}/evidence", tags=["evidence"])


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
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> FileResponse:
    """Dual auth, same as GET /assessments/{id} -- assessor/admin JWT, or
    this assessment's own (active) worker token."""
    evidence = _evidence_for_assessment(db, assessment_id, evidence_id)
    path = uploads._storage.path_for(evidence.storage_key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence file is missing from storage")
    return FileResponse(path, media_type=evidence.mime)


@router.get("/{evidence_id}/thumbnail")
def get_evidence_thumbnail(
    assessment_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> FileResponse:
    """Photos serve their own bytes directly (no separate thumbnail job --
    see models.EvidenceItem.thumbnail_status's 'not_applicable' default).
    Videos serve the ffmpeg-extracted frame once the background job
    completes; while queued, or if ffmpeg extraction failed/is unavailable,
    this is a graceful 404 (never a 500) so the dashboard can show a
    pending/placeholder state instead of crashing."""
    evidence = _evidence_for_assessment(db, assessment_id, evidence_id)

    if evidence.kind == "photo":
        path = uploads._storage.path_for(evidence.storage_key)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence file is missing from storage")
        return FileResponse(path, media_type=evidence.mime)

    if evidence.thumbnail_status != "completed" or not evidence.thumbnail_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no thumbnail available (status: {evidence.thumbnail_status})")
    path = uploads._storage.path_for(evidence.thumbnail_key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thumbnail file is missing from storage")
    return FileResponse(path, media_type="image/jpeg")
