"""Human assessor scoring -- see docs/evidence_status_model.md for the
evidence_status axis and docs/gates/P2_2.md section 2 for the full
contract. Scoring never auto-derives a pass/fail: GET
/competency-profile is explicitly decision support only, the actual
recommendation is a separate human action (routers/decisions.py).
"""
import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import models, outcome as outcome_module, schemas
from ..auth import require_assessor
from ..db import get_db
from ..reviewer_identity import identity

router = APIRouter(prefix="/assessments", tags=["scoring"])


def _rubric_rows(db: Session, pack_id: int):
    """All TASK_EVIDENCE_PATHWAY PCs (the ones with a rubric item) for this
    assessment's pack, each PC's full_id, and its NOS -- same join as
    routers/assessments.py's get_assessment_rubric."""
    return (
        db.query(models.RubricItem, models.PerformanceCriterion, models.NOS)
        .join(models.PerformanceCriterion, models.RubricItem.pc_id == models.PerformanceCriterion.id)
        .join(models.NOS, models.PerformanceCriterion.nos_id == models.NOS.id)
        .filter(models.NOS.pack_id == pack_id)
        .all()
    )


def _score_out(score: models.AssessmentCriterionScore) -> schemas.CriterionScoreOut:
    return schemas.CriterionScoreOut(
        pc_full_id=score.pc.full_id,
        score_level=score.score_level,
        evidence_status=score.evidence_status,
        assessor_comment=score.assessor_comment,
        marks_awarded=score.marks_awarded,
        rubric_version=score.rubric_version,
        assessor_id=score.assessor_id,
        scored_at=score.scored_at,
        version=score.version,
        revision_number=score.revision_number,
        needs_review=score.needs_review,
    )


@router.get("/{assessment_id}/review", response_model=list[schemas.CriterionReviewItemOut])
def get_review(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.CriterionReviewItemOut]:
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    rows = _rubric_rows(db, assessment.pack_id)
    existing = {
        s.pc_id: s
        for s in db.query(models.AssessmentCriterionScore).options(joinedload(models.AssessmentCriterionScore.pc))
        .filter_by(assessment_id=assessment_id).all()
    }
    tasks = {t.task_code: t.title for t in db.query(models.TaskTemplate).filter_by(pack_id=assessment.pack_id).all()}
    return [
        schemas.CriterionReviewItemOut(
            pc_full_id=pc.full_id, rubric_version=item.rubric_version, marks=item.marks,
            criterion_text=pc.text, task_code=nos.task_code, task_title=tasks.get(nos.task_code, nos.title),
            nos_code=nos.code, nos_title=nos.title,
            critical=item.critical, anchors=item.anchors, disclaimer=item.disclaimer,
            evidence_hint=item.evidence_hint,
            score=_score_out(existing[pc.id]) if pc.id in existing else None,
        )
        for item, pc, nos in rows
    ]


@router.put("/{assessment_id}/review", response_model=schemas.CriterionScoreOut)
def put_score(
    assessment_id: int,
    body: schemas.CriterionScoreIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.CriterionScoreOut:
    # Locks the SAME row sign_off() locks (see routers/reports.py), in the
    # same order (assessment, then the individual score row below) --
    # otherwise a concurrent sign-off could render/sign the report from a
    # snapshot that a still-in-flight score save then overwrites a moment
    # later, or this save could land after the report was already produced
    # from a status this transaction never actually observed.
    assessment = db.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update()
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if assessment.status != "in_review":
        raise HTTPException(status.HTTP_409_CONFLICT, f"cannot score: assessment is '{assessment.status}', not 'in_review'")

    rubric_row = (
        db.query(models.RubricItem, models.PerformanceCriterion)
        .join(models.PerformanceCriterion, models.RubricItem.pc_id == models.PerformanceCriterion.id)
        .join(models.NOS, models.PerformanceCriterion.nos_id == models.NOS.id)
        .filter(models.PerformanceCriterion.full_id == body.pc_full_id)
        .filter(models.NOS.pack_id == assessment.pack_id)
        .one_or_none()
    )
    if rubric_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no rubric item for PC '{body.pc_full_id}'")
    rubric_item, pc = rubric_row

    existing = db.query(models.AssessmentCriterionScore).filter_by(
        assessment_id=assessment_id, pc_id=pc.id
    ).with_for_update().one_or_none()

    if existing is None:
        if body.expected_version != 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "expected_version must be 0 for a PC that has never been scored",
            )
    elif existing.version != body.expected_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"stale version: this score was last saved as version {existing.version}, "
            f"not {body.expected_version} -- reload /review and retry",
        )

    marks_awarded = (
        (rubric_item.marks * Decimal(body.score_level) / Decimal(3)).quantize(Decimal("0.01"))
        if body.evidence_status == "DEMONSTRATED"
        else Decimal("0.00")
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    # Captured before any mutation -- the audit entry below records exactly
    # what changed (old -> new), not just the new state, per the P6
    # requirement that the audit log show old/new score and remarks.
    old_score_level = existing.score_level if existing is not None else None
    old_evidence_status = existing.evidence_status if existing is not None else None
    old_comment = existing.assessor_comment if existing is not None else None

    if existing is None:
        existing = models.AssessmentCriterionScore(
            assessment_id=assessment_id, pc_id=pc.id, rubric_version=rubric_item.rubric_version,
            version=1,
        )
        db.add(existing)
    else:
        existing.version += 1

    existing.score_level = body.score_level
    existing.evidence_status = body.evidence_status
    existing.assessor_comment = body.assessor_comment
    existing.marks_awarded = marks_awarded
    existing.assessor_id = user.id
    existing.reviewer_identity = identity(user)
    existing.scored_at = now
    # P7: this PC has now genuinely been looked at again in the CURRENT
    # revision -- clears any stale "its task reopened, re-review me" flag
    # set by routers/reassessment.py (see AssessmentCriterionScore.needs_review's
    # docstring in models.py).
    existing.needs_review = False
    existing.revision_number = assessment.revision_number

    from .assessments import _audit  # local import: avoids a circular import at module load time

    _audit(db, assessment_id, actor_user_id=user.id, actor_role=user.role, action="scored", details={
        "reviewer_identity": identity(user), "revision_number": assessment.revision_number,
        "pc_full_id": body.pc_full_id,
        "old_score_level": old_score_level, "new_score_level": body.score_level,
        "old_evidence_status": old_evidence_status, "new_evidence_status": body.evidence_status,
        "old_assessor_comment": old_comment, "new_assessor_comment": body.assessor_comment,
    })
    db.commit()
    db.refresh(existing)
    return _score_out(existing)


def get_computed_outcome(db: Session, assessment: models.Assessment) -> outcome_module.ComputedOutcome:
    """Shared by GET /competency-profile and routers/reports.py's sign_off
    -- the exact same rows/scores feed both, so the number a report signs
    is always the same one the dashboard showed the assessor beforehand."""
    pack = db.get(models.QualificationPack, assessment.pack_id)
    rows = _rubric_rows(db, assessment.pack_id)
    scores = {
        s.pc_id: s
        for s in db.query(models.AssessmentCriterionScore).filter_by(assessment_id=assessment.id).all()
    }
    return outcome_module.compute_outcome(rows, scores, pack.minimum_aggregate_passing_percent)


@router.get("/{assessment_id}/competency-profile", response_model=schemas.CompetencyProfileOut)
def get_competency_profile(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> schemas.CompetencyProfileOut:
    """Decision support only -- see schemas.COMPETENCY_PROFILE_DISCLAIMER.
    Purely additive aggregation of whatever's been scored so far; never
    auto-certifies, never calls itself a pass/fail."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    pack = db.get(models.QualificationPack, assessment.pack_id)

    rows = _rubric_rows(db, assessment.pack_id)
    scores = {
        s.pc_id: s
        for s in db.query(models.AssessmentCriterionScore).filter_by(assessment_id=assessment_id).all()
    }

    nos_totals: dict[int, dict] = {}
    overall_awarded = Decimal("0.00")
    overall_possible = Decimal("0.00")
    pcs_scored = 0
    for item, pc, nos in rows:
        overall_possible += item.marks
        score = scores.get(pc.id)
        awarded = score.marks_awarded if score and score.scored_at is not None else Decimal("0.00")
        overall_awarded += awarded
        if score and score.scored_at is not None:
            pcs_scored += 1

        bucket = nos_totals.setdefault(nos.id, {
            "nos_code": nos.code, "nos_title": nos.title,
            "awarded": Decimal("0.00"), "possible": Decimal("0.00"),
        })
        bucket["awarded"] += awarded
        bucket["possible"] += item.marks

    overall_percent = float(overall_awarded / overall_possible * 100) if overall_possible else 0.0
    computed = outcome_module.compute_outcome(rows, scores, pack.minimum_aggregate_passing_percent)
    nos_by_code = {n.nos_code: n for n in computed.nos_results}
    return schemas.CompetencyProfileOut(
        assessment_id=assessment_id,
        overall_marks_awarded=overall_awarded,
        overall_marks_possible=overall_possible,
        overall_percent=round(overall_percent, 2),
        minimum_aggregate_passing_percent=pack.minimum_aggregate_passing_percent,
        meets_minimum_threshold=overall_percent >= pack.minimum_aggregate_passing_percent,
        pcs_scored=pcs_scored,
        pcs_total=len(rows),
        nos_breakdown=[
            schemas.NosProfileOut(
                nos_code=b["nos_code"], nos_title=b["nos_title"],
                marks_awarded=b["awarded"], marks_possible=b["possible"],
                percent=round(float(b["awarded"] / b["possible"] * 100), 2) if b["possible"] else 0.0,
                meets_threshold=nos_by_code[b["nos_code"]].meets_threshold if b["nos_code"] in nos_by_code else False,
                critical_violation=nos_by_code[b["nos_code"]].critical_violation if b["nos_code"] in nos_by_code else False,
                has_insufficient_evidence=nos_by_code[b["nos_code"]].has_insufficient_evidence if b["nos_code"] in nos_by_code else False,
                competent=nos_by_code[b["nos_code"]].competent if b["nos_code"] in nos_by_code else False,
            )
            for b in nos_totals.values()
        ],
        computed_outcome=computed.outcome,
        achieved_nos_codes=computed.achieved_nos_codes,
        gap_nos_codes=computed.gap_nos_codes,
        insufficient_evidence_nos_codes=computed.insufficient_evidence_nos_codes,
        critical_violation_pc_ids=computed.critical_violation_pc_ids,
    )
