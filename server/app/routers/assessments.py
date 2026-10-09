from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, quota, schemas
from ..db import get_db

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", response_model=schemas.AssessmentOut, status_code=201)
def create_assessment(body: schemas.AssessmentCreate, db: Session = Depends(get_db)) -> models.Assessment:
    worker = db.get(models.User, body.worker_id)
    if worker is None or worker.role != "worker":
        raise HTTPException(404, "worker not found")
    pack = db.get(models.QualificationPack, body.pack_id)
    if pack is None:
        raise HTTPException(404, "pack not found")

    assessment = models.Assessment(worker_id=worker.id, pack_id=pack.id)
    db.add(assessment)
    db.flush()

    # Fixed five tasks, in pack order -- never substituted, never worker-chosen.
    templates = (
        db.query(models.TaskTemplate)
        .filter_by(pack_id=pack.id)
        .order_by(models.TaskTemplate.task_order)
        .all()
    )
    for t in templates:
        db.add(models.AssessmentTask(
            assessment_id=assessment.id,
            task_code=t.task_code,
            budget_bytes=t.budget_bytes,
        ))

    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)) -> models.Assessment:
    assessment = db.get(
        models.Assessment, assessment_id,
        options=[joinedload(models.Assessment.tasks)],
    )
    if assessment is None:
        raise HTTPException(404, "assessment not found")
    return assessment


@router.post("/{assessment_id}/evidence", response_model=schemas.EvidenceItemOut, status_code=201)
def add_evidence_metadata(
    assessment_id: int, body: schemas.EvidenceItemCreate, db: Session = Depends(get_db)
) -> models.EvidenceItem:
    """Records evidence METADATA only (kind/mime/declared size) -- no bytes.
    Counts against the same task + 120 MB quota the upload-session endpoint
    checks, so budgets can't be double-spent across the two paths."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "assessment not found")
    task = db.query(models.AssessmentTask).filter_by(
        assessment_id=assessment_id, task_code=body.task_code
    ).one_or_none()
    if task is None:
        raise HTTPException(404, f"task {body.task_code} not found on this assessment")

    pack = db.get(models.QualificationPack, assessment.pack_id)
    try:
        quota.check_quota(db, task, body.declared_size_bytes, pack.final_evidence_budget_bytes)
    except quota.QuotaExceeded as e:
        raise HTTPException(409, str(e)) from e

    item = models.EvidenceItem(
        assessment_task_id=task.id,
        kind=body.kind,
        mime=body.mime,
        declared_size_bytes=body.declared_size_bytes,
    )
    db.add(item)
    task.bytes_used += body.declared_size_bytes
    task.status = "evidence_added"
    assessment.total_bytes_used += body.declared_size_bytes
    db.commit()
    db.refresh(item)
    return item
