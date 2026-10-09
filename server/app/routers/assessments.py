from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import decode_access_token, require_assessor
from ..db import get_db
from ..worker_tokens import generate_worker_token, hash_worker_token

router = APIRouter(prefix="/assessments", tags=["assessments"])

_bearer = HTTPBearer(auto_error=False)


def _assessor_or_worker_token(
    assessment_id: int,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.Assessment:
    """GET /assessments/{id} is read by both workers (their own progress,
    via the capability token issued at creation) and assessors (review, via
    JWT) -- see docs/worker_capability_tokens.md."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    if creds is not None:
        claims = decode_access_token(creds.credentials)
        if claims.get("role") in ("assessor", "admin"):
            return assessment

    if x_worker_token and hash_worker_token(x_worker_token) == assessment.worker_token_hash:
        return assessment

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "requires an assessor/admin bearer token or this assessment's X-Worker-Token")


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

    raw_token, token_hash = generate_worker_token()
    assessment = models.Assessment(worker_id=worker.id, pack_id=pack.id, worker_token_hash=token_hash)
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


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> schemas.AssessmentOut:
    assessment = db.get(
        models.Assessment, assessment_id,
        options=[joinedload(models.Assessment.tasks).joinedload(models.AssessmentTask.evidence_items)],
    )
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
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
        total_bytes_used=assessment.total_bytes_used,
        total_budget_bytes=pack.final_evidence_budget_bytes,
        created_at=assessment.created_at,
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
