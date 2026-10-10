"""Worker capability token rotation/revocation -- see docs/gates/P2_2.md
section 6. Closes part of docs/worker_capability_tokens.md's "deliberately
deferred" boundaries list (rotation and revocation now exist; expiry and
device-loss recovery flows still don't, that doc is updated accordingly).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_assessor
from ..db import get_db
from ..worker_tokens import generate_worker_token
from .assessments import _audit

router = APIRouter(prefix="/assessments", tags=["worker-tokens"])


@router.post("/{assessment_id}/worker-token/rotate", response_model=schemas.WorkerTokenOut)
def rotate_worker_token(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.WorkerTokenOut:
    """Invalidates the current token immediately (the old raw value stops
    working the instant this commits -- its hash is simply overwritten) and
    issues a fresh one, returned once, exactly like at creation. Use when a
    worker's device is lost or a token may have leaked."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    raw_token, token_hash = generate_worker_token()
    assessment.worker_token_hash = token_hash
    assessment.worker_token_status = "active"
    _audit(db, assessment_id, actor_user_id=user.id, actor_role=user.role, action="token_rotated")
    db.commit()
    return schemas.WorkerTokenOut(assessment_id=assessment_id, worker_token=raw_token, status="active")


@router.post("/{assessment_id}/worker-token/revoke", response_model=schemas.WorkerTokenOut)
def revoke_worker_token(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.WorkerTokenOut:
    """No new token is issued -- every worker-token-authenticated endpoint
    (uploads, submit, GET, report download) rejects it from this point on,
    regardless of whether the hash would otherwise still match."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    assessment.worker_token_status = "revoked"
    _audit(db, assessment_id, actor_user_id=user.id, actor_role=user.role, action="token_revoked")
    db.commit()
    return schemas.WorkerTokenOut(assessment_id=assessment_id, worker_token=None, status="revoked")
