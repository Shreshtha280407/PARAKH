"""P7: task-specific reassessment requests + the versioned-resubmission
read surface. See docs/gates/P7.md section 3.

Distinct from the pre-existing POST /assessments/{id}/reassess
(routers/decisions.py), which creates a brand-new Assessment and is kept
unchanged for the "start over completely" case. This router instead
reopens SPECIFIC tasks on the SAME assessment -- the master-plan 4.4 "per
task, reason + what to capture" loop -- building on the exact P6
upload/manifest/revision_id machinery (see routers/uploads.py) rather than
a parallel protocol.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from .. import models, schemas
from ..auth import require_assessor
from ..db import get_db
from ..reviewer_identity import identity
from .assessments import _assessor_or_worker_token

router = APIRouter(prefix="/assessments/{assessment_id}", tags=["reassessment"])


def _audit(db: Session, assessment_id: int, actor_user_id: int | None, actor_role: str, action: str, details: dict | None = None) -> None:
    db.add(models.AuditLog(
        assessment_id=assessment_id, actor_user_id=actor_user_id, actor_role=actor_role,
        action=action, details=details or {},
    ))


def _request_out(req: models.ReassessmentRequest, revision_number: int) -> schemas.ReassessmentRequestOut:
    return schemas.ReassessmentRequestOut(
        id=req.id, assessment_id=req.assessment_id, revision_number=revision_number,
        task_codes=req.task_codes, reason=req.reason, capture_instructions=req.capture_instructions,
        # Keep the legacy integer wire contract for already-installed Android
        # clients. Zero explicitly denotes a reviewer without an account; the
        # real declaration/verification lives in the private identity snapshot.
        requested_by_id=req.requested_by_id if req.requested_by_id is not None else 0,
        requested_at=req.requested_at, status=req.status,
        fulfilled_at=req.fulfilled_at,
    )


@router.post("/reassessment-requests", response_model=schemas.ReassessmentRequestOut, status_code=201)
def create_reassessment_request(
    assessment_id: int,
    body: schemas.ReassessmentRequestIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.ReassessmentRequestOut:
    """Assessor/admin only. Reopens exactly the requested tasks under a new
    revision; every other task's v1 evidence/scores are untouched. Only one
    reassessment request may be pending at a time (the server-side source
    of truth for 'which tasks are reopened' would otherwise be ambiguous
    while a prior request's revision is still unresolved)."""
    assessment = db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update()).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if assessment.status not in ("in_review", "submitted"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot request reassessment: assessment is '{assessment.status}', not 'in_review' or 'submitted'",
        )

    existing_task_codes = {t.task_code for t in assessment.tasks}
    unknown = set(body.task_codes) - existing_task_codes
    if unknown:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown task codes: {sorted(unknown)}")

    pending = (
        db.query(models.ReassessmentRequest)
        .filter_by(assessment_id=assessment_id, status="pending")
        .one_or_none()
    )
    if pending is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "a reassessment request is already pending for this assessment")

    new_revision_number = assessment.revision_number + 1
    revision = models.AssessmentRevision(
        assessment_id=assessment.id, revision_number=new_revision_number,
        reopened_task_codes=list(body.task_codes), status="open",
    )
    db.add(revision)
    db.flush()

    reassessment_request = models.ReassessmentRequest(
        assessment_id=assessment.id, revision_id=revision.id, task_codes=list(body.task_codes),
        reason=body.reason.strip(), capture_instructions=body.capture_instructions.strip(),
        requested_by_id=user.id,
        reviewer_identity=identity(user),
    )
    db.add(reassessment_request)

    # P7: every PC whose task is being reopened must be genuinely
    # re-reviewed before a final sign-off -- never silently carried
    # forward from v1. The old score/marks stay exactly as they were
    # (clear provenance for the dashboard); only the flag changes.
    affected_pc_ids = {
        pc.id for pc in db.query(models.PerformanceCriterion)
        .join(models.NOS, models.PerformanceCriterion.nos_id == models.NOS.id)
        .filter(models.NOS.task_code.in_(body.task_codes))
        .all()
    }
    if affected_pc_ids:
        db.query(models.AssessmentCriterionScore).filter(
            models.AssessmentCriterionScore.assessment_id == assessment.id,
            models.AssessmentCriterionScore.pc_id.in_(affected_pc_ids),
        ).update({"needs_review": True}, synchronize_session=False)

    assessment.status = "needs_reassessment"
    assessment.revision_number = new_revision_number
    assessment.decision_reviewer_identity = identity(user)
    assessment.decision = "needs_reassessment"
    assessment.decision_notes = body.reason.strip()
    assessment.decided_at = models.utcnow()
    assessment.decided_by_id = user.id
    _audit(
        db, assessment.id, actor_user_id=user.id, actor_role=user.role, action="reassessment_requested",
        details={"task_codes": body.task_codes, "reason": body.reason, "revision_number": new_revision_number,
                 "affected_revision_number": new_revision_number - 1, "reviewer_identity": identity(user)},
    )
    db.commit()
    db.refresh(reassessment_request)
    return _request_out(reassessment_request, new_revision_number)


@router.get("/reassessment-requests", response_model=list[schemas.ReassessmentRequestOut])
def list_reassessment_requests(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.ReassessmentRequestOut]:
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    revisions_by_id = {
        r.id: r.revision_number
        for r in db.query(models.AssessmentRevision).filter_by(assessment_id=assessment_id).all()
    }
    rows = (
        db.query(models.ReassessmentRequest)
        .filter_by(assessment_id=assessment_id)
        .order_by(models.ReassessmentRequest.id)
        .all()
    )
    return [_request_out(r, revisions_by_id.get(r.revision_id, 1)) for r in rows]


@router.get("/revisions", response_model=list[schemas.AssessmentRevisionOut])
def list_revisions(
    assessment_id: int,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> list[schemas.AssessmentRevisionOut]:
    """v1/v2/... revision history -- both the assessor dashboard and the
    worker app need this (same dual auth as GET /assessments/{id})."""
    rows = (
        db.query(models.AssessmentRevision)
        .filter_by(assessment_id=assessment_id)
        .order_by(models.AssessmentRevision.revision_number)
        .all()
    )
    return [
        schemas.AssessmentRevisionOut(
            revision_number=r.revision_number, revision_id=r.revision_id,
            reopened_task_codes=r.reopened_task_codes, status=r.status,
            created_at=r.created_at, submitted_at=r.submitted_at,
        )
        for r in rows
    ]


@router.get("/worker-updates", response_model=schemas.WorkerUpdatesOut)
def get_worker_updates(
    assessment_id: int,
    since: int = 0,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> schemas.WorkerUpdatesOut:
    """Durable, idempotent snapshot for the worker app to poll: the latest
    PENDING reassessment request (if any), current status, and report
    availability. A deliberate, documented departure from the master
    plan's literal 'GET /workers/me/updates?since=' shape -- see
    docs/gates/P7.md section 3 for why (no worker login/session concept
    exists to make 'me' meaningful; this is scoped by the same
    per-assessment capability token every other worker-facing endpoint
    already uses). `since` is advisory only (lets a caller skip re-fetching
    unchanged `pending_reassessment_request` details); the response always
    reflects current DB state, so a replayed/duplicate poll is always safe.
    """
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    pending = (
        db.query(models.ReassessmentRequest)
        .filter_by(assessment_id=assessment_id, status="pending")
        .order_by(models.ReassessmentRequest.id.desc())
        .first()
    )
    revision_number_out = assessment.revision_number
    pending_out = None
    latest_event_id = 0
    if pending is not None:
        pending_out = _request_out(pending, revision_number_out)
        latest_event_id = pending.id

    report = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if report is not None:
        report_status: schemas.ReportStatus = "available"
        latest_event_id = max(latest_event_id, report.id + 10_000_000)  # disjoint id space from reassessment_requests
    elif assessment.status in ("recommended", "needs_reassessment"):
        report_status = "pending"
    else:
        report_status = "none"

    return schemas.WorkerUpdatesOut(
        assessment_id=assessment_id, assessment_status=assessment.status,
        revision_number=revision_number_out, pending_reassessment_request=pending_out,
        report_status=report_status, latest_event_id=latest_event_id,
    )
