"""Recommendation sign-off and reassessment -- see docs/gates/P2_2.md
section 3. decide_assessment never auto-certifies: it only records a human
assessor's recommended/needs_reassessment call. reassess preserves the
original assessment untouched (all its tasks, evidence, scores, and any
signed report stay exactly as they were) and issues a brand-new Assessment
with a fresh worker capability token for a second attempt.
"""
import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..reviewer_identity import identity

from .. import models, schemas
from ..auth import require_assessor
from ..db import get_db

router = APIRouter(prefix="/assessments", tags=["decisions"])


class DecisionIn(BaseModel):
    decision: Literal["recommended", "needs_reassessment"]
    notes: str | None = None


@router.post("/{assessment_id}/decision", response_model=schemas.AssessmentOut)
def decide_assessment(
    assessment_id: int,
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.AssessmentOut:
    from .assessments import _assessment_out, _audit

    assessment = db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update()).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if assessment.status != "in_review":
        raise HTTPException(status.HTTP_409_CONFLICT, f"cannot decide: assessment is '{assessment.status}', not 'in_review'")

    assessment.status = body.decision
    assessment.decision = body.decision
    assessment.decision_notes = body.notes
    assessment.decided_by_id = user.id
    assessment.decided_at = datetime.datetime.now(datetime.timezone.utc)
    assessment.decision_reviewer_identity = identity(user)
    _audit(
        db, assessment.id, actor_user_id=user.id, actor_role=user.role, action="decided",
        details={"decision": body.decision, "reason": body.notes, "revision_number": assessment.revision_number,
                 "reviewer_identity": identity(user)},
    )
    db.commit()
    db.refresh(assessment)
    return _assessment_out(db, assessment)


@router.post("/{assessment_id}/reassess", response_model=schemas.AssessmentCreatedOut, status_code=201)
def reassess(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.AssessmentCreatedOut:
    from .assessments import _audit, _created_out, _new_assessment

    original = db.get(models.Assessment, assessment_id)
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if original.status != "needs_reassessment":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot reassess: assessment is '{original.status}', not 'needs_reassessment'",
        )

    new_assessment, raw_token = _new_assessment(
        db, original.worker_id, original.pack_id, actor_user_id=user.id, actor_role=user.role,
        reassessment_of_id=original.id,
    )
    _audit(
        db, original.id, actor_user_id=user.id, actor_role=user.role, action="reassessment_initiated",
        details={"new_assessment_id": new_assessment.id},
    )
    db.commit()
    db.refresh(new_assessment)
    return _created_out(new_assessment, raw_token)
