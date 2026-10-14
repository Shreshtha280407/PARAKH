"""Computed outcome engine -- master-plan section 4.4's rule table, applied
only from pinned pack data (see docs/gates/P7.md section 2 for exactly
which pinned number is reused, and why no second/official NSQF threshold is
invented: qp.json's only pinned percentage, minimum_aggregate_passing_percent,
is reused consistently at both the overall and per-NOS scope -- which is
literally what rubric.json's own rules.pass_thresholds text already says to
do, not an invention).

Pure aggregation over scores a human assessor already recorded -- this
module never assigns, infers, or overrides a PC score itself. See
docs/evidence_status_model.md and schemas.COMPETENCY_PROFILE_DISCLAIMER:
decision support only, the assessor's own final call (routers/reports.py's
sign_off) always has the last word, including overriding this computed
value with a written reason.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Outcome = Literal[
    "RECOMMEND_CERTIFICATION",
    "PARTIALLY_COMPETENT",
    "NOT_YET_COMPETENT",
    "INSUFFICIENT_EVIDENCE",
]


@dataclass
class NosOutcome:
    nos_code: str
    nos_title: str
    marks_awarded: Decimal
    marks_possible: Decimal
    percent: float
    meets_threshold: bool
    critical_violation: bool
    has_insufficient_evidence: bool
    competent: bool


@dataclass
class ComputedOutcome:
    outcome: Outcome
    nos_results: list[NosOutcome] = field(default_factory=list)
    achieved_nos_codes: list[str] = field(default_factory=list)
    gap_nos_codes: list[str] = field(default_factory=list)
    insufficient_evidence_nos_codes: list[str] = field(default_factory=list)
    critical_violation_pc_ids: list[str] = field(default_factory=list)


def compute_outcome(rows, scores: dict, minimum_aggregate_passing_percent: int) -> ComputedOutcome:
    """rows: the (RubricItem, PerformanceCriterion, NOS) tuples from
    routers.scoring._rubric_rows -- every mandatory (task-evidenced) PC for
    this pack. scores: {pc_id: AssessmentCriterionScore}, exactly as built
    by every existing caller of _rubric_rows."""
    by_nos: dict[int, dict] = {}
    for item, pc, nos in rows:
        bucket = by_nos.setdefault(nos.id, {
            "nos_code": nos.code, "nos_title": nos.title,
            "awarded": Decimal("0.00"), "possible": Decimal("0.00"),
            "critical_violation": False, "insufficient_evidence": False,
            "critical_violation_pc_ids": [],
        })
        bucket["possible"] += item.marks
        score = scores.get(pc.id)

        if score is None or score.scored_at is None:
            bucket["insufficient_evidence"] = True
            continue
        if score.evidence_status == "NOT_OBSERVABLE":
            bucket["insufficient_evidence"] = True
            continue

        awarded = score.marks_awarded or Decimal("0.00")
        bucket["awarded"] += awarded
        if item.critical and score.evidence_status == "DEMONSTRATED" and score.score_level < 2:
            bucket["critical_violation"] = True
            bucket["critical_violation_pc_ids"].append(pc.full_id)

    nos_results: list[NosOutcome] = []
    all_critical_violations: list[str] = []
    for bucket in by_nos.values():
        percent = float(bucket["awarded"] / bucket["possible"] * 100) if bucket["possible"] else 0.0
        meets_threshold = percent >= minimum_aggregate_passing_percent
        competent = meets_threshold and not bucket["critical_violation"] and not bucket["insufficient_evidence"]
        nos_results.append(NosOutcome(
            nos_code=bucket["nos_code"], nos_title=bucket["nos_title"],
            marks_awarded=bucket["awarded"], marks_possible=bucket["possible"],
            percent=round(percent, 2), meets_threshold=meets_threshold,
            critical_violation=bucket["critical_violation"],
            has_insufficient_evidence=bucket["insufficient_evidence"],
            competent=competent,
        ))
        all_critical_violations.extend(bucket["critical_violation_pc_ids"])

    achieved = [n.nos_code for n in nos_results if n.competent]
    gap = [n.nos_code for n in nos_results if not n.competent]
    insufficient = [n.nos_code for n in nos_results if n.has_insufficient_evidence]
    total = len(nos_results)

    # Priority order mirrors rubric.json's own critical_pc rule ("regardless
    # of overall NOS %", i.e. the safety veto dominates everything else)
    # followed by the master-plan 4.4 table's own row order.
    if all_critical_violations:
        outcome: Outcome = "NOT_YET_COMPETENT"
    elif insufficient and len(achieved) < total:
        outcome = "INSUFFICIENT_EVIDENCE"
    elif total > 0 and len(achieved) == total:
        outcome = "RECOMMEND_CERTIFICATION"
    elif achieved:
        outcome = "PARTIALLY_COMPETENT"
    else:
        outcome = "NOT_YET_COMPETENT"

    return ComputedOutcome(
        outcome=outcome, nos_results=nos_results, achieved_nos_codes=achieved,
        gap_nos_codes=gap, insufficient_evidence_nos_codes=insufficient,
        critical_violation_pc_ids=all_critical_violations,
    )
