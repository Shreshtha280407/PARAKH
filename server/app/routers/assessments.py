import datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import (
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    _MUTATING_METHODS,
    decode_access_token,
    require_assessor,
)
from ..db import get_db
from ..worker_tokens import generate_worker_token, hash_worker_token

router = APIRouter(prefix="/assessments", tags=["assessments"])

_bearer = HTTPBearer(auto_error=False)


def _assessor_or_worker_token(
    assessment_id: int,
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> models.Assessment:
    """GET /assessments/{id} (and the evidence/report endpoints that reuse
    this dependency) is read by both workers (their own progress, via the
    capability token issued at creation) and assessors (review, via JWT --
    Bearer header for API clients, or the dashboard's session cookie) --
    see docs/worker_capability_tokens.md."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    token = creds.credentials if creds is not None else access_token_cookie
    if token is not None:
        if creds is None and request.method in _MUTATING_METHODS:
            # Cookie path on a mutating request -- same CSRF double-submit
            # check as auth.get_current_user (Bearer requests skip this,
            # a cross-site page can't attach a custom header).
            if not csrf_cookie or not x_csrf_token or csrf_cookie != x_csrf_token:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
        claims = decode_access_token(token)
        user = db.get(models.User, int(claims["sub"]))
        # Re-verify against the live DB row, not just the JWT claim -- a
        # user deleted or demoted after the token was issued must lose
        # access immediately rather than whenever the token happens to
        # expire (see auth.get_current_user, same pattern).
        if user is not None and user.role == claims.get("role") and user.role in ("assessor", "admin"):
            return assessment

    if (
        assessment.worker_token_status == "active"
        and x_worker_token
        and hash_worker_token(x_worker_token) == assessment.worker_token_hash
    ):
        return assessment

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "requires an assessor/admin bearer token or this assessment's X-Worker-Token")


def _new_assessment(
    db: Session, worker_id: int, pack_id: int, actor_user_id: int | None, actor_role: str,
    reassessment_of_id: int | None = None,
) -> tuple[models.Assessment, str]:
    """Shared by create_assessment and decisions.reassess -- both produce a
    brand-new Assessment with the fixed five tasks (in pack order, never
    worker-chosen) and a fresh worker capability token."""
    raw_token, token_hash = generate_worker_token()
    assessment = models.Assessment(
        worker_id=worker_id, pack_id=pack_id, worker_token_hash=token_hash,
        reassessment_of_id=reassessment_of_id,
    )
    db.add(assessment)
    db.flush()

    templates = (
        db.query(models.TaskTemplate)
        .filter_by(pack_id=pack_id)
        .order_by(models.TaskTemplate.task_order)
        .all()
    )
    for t in templates:
        db.add(models.AssessmentTask(
            assessment_id=assessment.id,
            task_code=t.task_code,
            budget_bytes=t.budget_bytes,
        ))

    _audit(
        db, assessment.id, actor_user_id=actor_user_id, actor_role=actor_role, action="created",
        details={"reassessment_of_id": reassessment_of_id} if reassessment_of_id else {},
    )
    return assessment, raw_token


def _created_out(assessment: models.Assessment, raw_token: str) -> schemas.AssessmentCreatedOut:
    return schemas.AssessmentCreatedOut(
        id=assessment.id,
        worker_id=assessment.worker_id,
        pack_id=assessment.pack_id,
        status=assessment.status,
        worker_token=raw_token,
        tasks=[
            schemas.AssessmentTaskOut(task_code=t.task_code, budget_bytes=t.budget_bytes, bytes_used=t.bytes_used, status=t.status)
            for t in assessment.tasks
        ],
    )


@router.post("", response_model=schemas.AssessmentCreatedOut, status_code=201)
def create_assessment(body: schemas.AssessmentCreate, db: Session = Depends(get_db)) -> schemas.AssessmentCreatedOut:
    """Open to any caller (the worker app has no login) -- the response
    carries a fresh, unguessable capability token that every subsequent
    worker-side call on this assessment must present. See
    docs/worker_capability_tokens.md."""
    worker = db.get(models.User, body.worker_id)
    if worker is None or worker.role != "worker":
        raise HTTPException(404, "worker not found")
    pack = db.get(models.QualificationPack, body.pack_id)
    if pack is None:
        raise HTTPException(404, "pack not found")

    assessment, raw_token = _new_assessment(db, worker.id, pack.id, actor_user_id=None, actor_role="system")
    db.commit()
    db.refresh(assessment)
    return _created_out(assessment, raw_token)


def _audit(db: Session, assessment_id: int, actor_user_id: int | None, actor_role: str, action: str, details: dict | None = None) -> None:
    db.add(models.AuditLog(
        assessment_id=assessment_id, actor_user_id=actor_user_id, actor_role=actor_role,
        action=action, details=details or {},
    ))


def _assessment_out(db: Session, assessment: models.Assessment) -> schemas.AssessmentOut:
    assessment = db.get(
        models.Assessment, assessment.id,
        options=[joinedload(models.Assessment.tasks).joinedload(models.AssessmentTask.evidence_items)],
    )
    pack = db.get(models.QualificationPack, assessment.pack_id)
    worker_user = db.get(models.User, assessment.worker_id)
    return schemas.AssessmentOut(
        id=assessment.id,
        worker_id=assessment.worker_id,
        worker_name=worker_user.display_name,
        pack_id=assessment.pack_id,
        pack_code=pack.qp_code,
        pack_name=pack.qp_name,
        status=assessment.status,
        assessor_id=assessment.assessor_id,
        total_bytes_used=assessment.total_bytes_used,
        total_budget_bytes=pack.final_evidence_budget_bytes,
        created_at=assessment.created_at,
        submitted_at=assessment.submitted_at,
        decision=assessment.decision,
        decision_notes=assessment.decision_notes,
        reassessment_of_id=assessment.reassessment_of_id,
        tasks=[
            schemas.AssessmentTaskOut(
                task_code=t.task_code,
                budget_bytes=t.budget_bytes,
                bytes_used=t.bytes_used,
                status=t.status,
                evidence=[schemas.EvidenceReceiptOut.model_validate(e) for e in t.evidence_items],
            )
            for t in assessment.tasks
        ],
    )


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> schemas.AssessmentOut:
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    return _assessment_out(db, assessment)


@router.post("/{assessment_id}/submit", response_model=schemas.AssessmentOut)
def submit_assessment(
    assessment_id: int,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.AssessmentOut:
    """The worker app calls this once it's done capturing evidence for all
    five tasks -- moves draft -> submitted and LOCKS further evidence
    uploads (see routers/uploads.py's require_draft checks). Worker-token
    authenticated, same as uploads -- there is no worker login."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if (
        assessment.worker_token_status != "active"
        or not x_worker_token
        or hash_worker_token(x_worker_token) != assessment.worker_token_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    if assessment.status != models.AssessmentStatus.draft.value:
        raise HTTPException(status.HTTP_409_CONFLICT, f"cannot submit: assessment is '{assessment.status}', not 'draft'")

    assessment.status = models.AssessmentStatus.submitted.value
    assessment.submitted_at = datetime.datetime.now(datetime.timezone.utc)
    _audit(db, assessment.id, actor_user_id=None, actor_role="worker", action="submitted")
    db.commit()
    db.refresh(assessment)
    return _assessment_out(db, assessment)


@router.post("/{assessment_id}/start-review", response_model=schemas.AssessmentOut)
def start_review(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.AssessmentOut:
    """An assessor picks a submitted assessment off the queue -- moves
    submitted -> in_review and claims it (assessor_id)."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if assessment.status != models.AssessmentStatus.submitted.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"cannot start review: assessment is '{assessment.status}', not 'submitted'"
        )

    assessment.status = models.AssessmentStatus.in_review.value
    assessment.assessor_id = user.id
    _audit(db, assessment.id, actor_user_id=user.id, actor_role=user.role, action="review_started")
    db.commit()
    db.refresh(assessment)
    return _assessment_out(db, assessment)


@router.get("/{assessment_id}/rubric", response_model=list[schemas.RubricItemOut])
def get_assessment_rubric(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.RubricItemOut]:
    """Assessor/admin only -- the 0-3 anchors for this assessment's pack,
    for the dashboard's assessment-review page."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    rows = (
        db.query(models.RubricItem, models.PerformanceCriterion)
        .join(models.PerformanceCriterion, models.RubricItem.pc_id == models.PerformanceCriterion.id)
        .join(models.NOS, models.PerformanceCriterion.nos_id == models.NOS.id)
        .filter(models.NOS.pack_id == assessment.pack_id)
        .all()
    )
    return [
        schemas.RubricItemOut(
            pc_full_id=pc.full_id, rubric_version=item.rubric_version, marks=item.marks,
            critical=item.critical, anchors=item.anchors, disclaimer=item.disclaimer,
            evidence_hint=item.evidence_hint,
        )
        for item, pc in rows
    ]
