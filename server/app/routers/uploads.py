"""POST /uploads: open a session and check task budget + the 120 MB total
quota BEFORE any bytes are accepted. Chunk PUT / complete endpoints are
intentionally not implemented yet -- see master plan p.12 for the full
contract this is a slice of, and docs/P2_SCOPE.md for why.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, quota, schemas
from ..db import get_db

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=schemas.UploadSessionOut, status_code=201)
def open_upload_session(body: schemas.UploadSessionCreate, db: Session = Depends(get_db)) -> schemas.UploadSessionOut:
    assessment = db.get(models.Assessment, body.assessment_id)
    if assessment is None:
        raise HTTPException(404, "assessment not found")
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
        claimed_size_bytes=body.claimed_size_bytes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    task_remaining = task.budget_bytes - quota.task_bytes_committed(db, task.id)
    total_remaining = pack.final_evidence_budget_bytes - quota.assessment_bytes_committed(db, assessment.id)
    return schemas.UploadSessionOut(
        id=session.id,
        assessment_task_id=session.assessment_task_id,
        claimed_size_bytes=session.claimed_size_bytes,
        status=session.status,
        opened_at=session.opened_at,
        task_bytes_remaining=task_remaining,
        total_bytes_remaining=total_remaining,
    )


@router.get("/{upload_id}", response_model=schemas.UploadSessionOut)
def get_upload_session(upload_id: int, db: Session = Depends(get_db)) -> schemas.UploadSessionOut:
    session = db.get(models.UploadSession, upload_id)
    if session is None:
        raise HTTPException(404, "upload session not found")
    task = db.get(models.AssessmentTask, session.assessment_task_id)
    pack = db.get(models.QualificationPack, db.get(models.Assessment, task.assessment_id).pack_id)
    task_remaining = task.budget_bytes - quota.task_bytes_committed(db, task.id)
    total_remaining = pack.final_evidence_budget_bytes - quota.assessment_bytes_committed(db, task.assessment_id)
    return schemas.UploadSessionOut(
        id=session.id,
        assessment_task_id=session.assessment_task_id,
        claimed_size_bytes=session.claimed_size_bytes,
        status=session.status,
        opened_at=session.opened_at,
        task_bytes_remaining=task_remaining,
        total_bytes_remaining=total_remaining,
    )
