"""Explicit public projection. Never serialize privileged assessment models."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..abuse import source, throttle
from ..db import get_db

router = APIRouter(prefix="/public", tags=["public summaries"])


def summary(db, assessment, *, reports=None):
    report = (reports.get(assessment.id) if reports is not None else
              db.query(models.SignedReport).filter_by(assessment_id=assessment.id).one_or_none())
    return schemas.PublicAssessmentOut(
        id=assessment.id,
        candidate_display_name=assessment.worker.display_name if assessment.public_name_consent else f"Candidate #{assessment.id}",
        pack_code=assessment.pack.qp_code, pack_name=assessment.pack.qp_name, submitted_at=assessment.submitted_at,
        status=assessment.status, tasks_completed=sum(t.status == "evidence_added" for t in assessment.tasks),
        tasks_total=len(assessment.tasks), review_status="signed_off" if report else assessment.status,
        revision_number=assessment.revision_number, report_available=report is not None,
        report_id=report.report_uid if report else None, outcome=report.final_recommendation if report else None,
    )


def visible(db):
    return db.query(models.Assessment).options(joinedload(models.Assessment.worker), joinedload(models.Assessment.pack),
        joinedload(models.Assessment.tasks)).filter(models.Assessment.provenance == "candidate-v1",
        models.Assessment.submitted_at.isnot(None), models.Assessment.status != "draft")


@router.get("/assessments", response_model=list[schemas.PublicAssessmentOut])
def list_public(request: Request, response: Response, before_id: int | None = Query(None, gt=0),
                limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    throttle(db, "public-global", 600, 60)
    throttle(db, "public:" + source(request), 240, 60)
    response.headers["Cache-Control"] = "public, max-age=15"
    rows = visible(db)
    if before_id is not None:
        rows = rows.filter(models.Assessment.id < before_id)
    assessments = rows.order_by(models.Assessment.id.desc()).limit(limit).all()
    reports = {r.assessment_id: r for r in db.query(models.SignedReport)
               .filter(models.SignedReport.assessment_id.in_([a.id for a in assessments])).all()} if assessments else {}
    return [summary(db, a, reports=reports) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=schemas.PublicAssessmentOut)
def get_public(assessment_id: int, request: Request, db: Session = Depends(get_db)):
    throttle(db, "public-global", 600, 60)
    throttle(db, "public:" + source(request), 240, 60)
    assessment = visible(db).filter(models.Assessment.id == assessment_id).one_or_none()
    if not assessment:
        raise HTTPException(404, "public assessment not found")
    return summary(db, assessment)
