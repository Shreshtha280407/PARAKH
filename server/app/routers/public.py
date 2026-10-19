"""Explicit public projection. Never serialize privileged assessment models."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..abuse import source, throttle
from ..db import get_db
from ..report_outcomes import decision_for

router = APIRouter(prefix="/public", tags=["public summaries"])


def summary(db, assessment, *, reports=None, private=False):
    report = (reports.get(assessment.id) if reports is not None else
              db.query(models.SignedReport).filter_by(assessment_id=assessment.id).one_or_none())
    finalized = assessment.status in ("recommended", "not_recommended")
    eligible = report is not None and finalized and report.revision_number == assessment.revision_number
    publish = eligible and (private or assessment.public_outcome_consent)
    # No inference from signing to a positive result. Without explicit outcome
    # consent, neither positive nor adverse decisions/IDs enter public browsing.
    workflow = decision_for(report.final_recommendation) if eligible else assessment.status
    if finalized and not private and not assessment.public_outcome_consent:
        workflow = "finalized"
    return schemas.PublicAssessmentOut(
        id=assessment.id,
        candidate_display_name=assessment.worker.display_name if assessment.public_name_consent else f"Candidate #{assessment.id}",
        pack_code=assessment.pack.qp_code, pack_name=assessment.pack.qp_name, submitted_at=assessment.submitted_at,
        status=workflow, tasks_completed=sum(t.status == "evidence_added" for t in assessment.tasks),
        tasks_total=len(assessment.tasks), review_status="signed_off" if publish else workflow,
        revision_number=assessment.revision_number, report_available=bool(publish),
        report_id=report.report_uid if publish else None, outcome=report.final_recommendation if publish else None,
        report_issued_at=report.signed_at if publish else None,
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
    response.headers["Cache-Control"] = "no-store"
    rows = visible(db)
    if before_id is not None:
        rows = rows.filter(models.Assessment.id < before_id)
    assessments = rows.order_by(models.Assessment.id.desc()).limit(limit).all()
    reports = {r.assessment_id: r for r in db.query(models.SignedReport)
               .filter(models.SignedReport.assessment_id.in_([a.id for a in assessments])).all()} if assessments else {}
    return [summary(db, a, reports=reports) for a in assessments]


@router.get("/reports", response_model=list[schemas.PublicAssessmentOut])
def list_signed_reports(request: Request, response: Response, before_id: int | None = Query(None, gt=0),
                        limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    """Consent-aware directory; possession of an ID still permits /verify/{id}."""
    throttle(db, "public-global", 600, 60)
    throttle(db, "public:" + source(request), 240, 60)
    response.headers["Cache-Control"] = "no-store"
    rows = visible(db).join(models.SignedReport, models.SignedReport.assessment_id == models.Assessment.id).filter(
        models.Assessment.public_outcome_consent.is_(True),
        models.Assessment.status.in_(("recommended", "not_recommended")),
        models.SignedReport.revision_number == models.Assessment.revision_number,
    )
    if before_id is not None:
        rows = rows.filter(models.Assessment.id < before_id)
    assessments = rows.order_by(models.Assessment.id.desc()).limit(limit).all()
    reports = {r.assessment_id: r for r in db.query(models.SignedReport).filter(
        models.SignedReport.assessment_id.in_([a.id for a in assessments])).all()} if assessments else {}
    return [summary(db, a, reports=reports) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=schemas.PublicAssessmentOut)
def get_public(assessment_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    throttle(db, "public-global", 600, 60)
    throttle(db, "public:" + source(request), 240, 60)
    assessment = visible(db).filter(models.Assessment.id == assessment_id).one_or_none()
    if not assessment:
        raise HTTPException(404, "public assessment not found")
    return summary(db, assessment)
