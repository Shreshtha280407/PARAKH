"""server/app/outcome.py -- the computed §4.4 outcome engine. Pure logic,
no DB/HTTP needed: builds minimal stand-ins for the (RubricItem,
PerformanceCriterion, NOS) rows and AssessmentCriterionScore objects
compute_outcome actually reads.
"""
from decimal import Decimal
from types import SimpleNamespace

from server.app.outcome import compute_outcome

THRESHOLD = 50


def _rubric_item(marks: str, critical: bool = False):
    return SimpleNamespace(marks=Decimal(marks), critical=critical)


def _pc(full_id: str):
    return SimpleNamespace(id=full_id, full_id=full_id)


def _nos(code: str, title: str = "Title"):
    return SimpleNamespace(id=code, code=code, title=title)


def _score(level: int, status: str = "DEMONSTRATED", marks_awarded: str | None = None, scored: bool = True):
    marks = Decimal(marks_awarded) if marks_awarded is not None else None
    return SimpleNamespace(
        score_level=level, evidence_status=status, marks_awarded=marks,
        scored_at="2026-01-01" if scored else None, revision_number=1,
    )


def _row(nos_code: str, pc_id: str, marks: str, critical: bool = False):
    return (_rubric_item(marks, critical), _pc(pc_id), _nos(nos_code))


def test_single_nos_fully_competent_recommends_certification():
    rows = [_row("N1", "PC1", "50.00"), _row("N1", "PC2", "50.00")]
    scores = {"PC1": _score(3, marks_awarded="50.00"), "PC2": _score(3, marks_awarded="50.00")}
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "RECOMMEND_CERTIFICATION"
    assert result.achieved_nos_codes == ["N1"]
    assert result.gap_nos_codes == []


def test_all_nos_below_threshold_is_not_yet_competent():
    rows = [_row("N1", "PC1", "100.00"), _row("N2", "PC2", "100.00")]
    scores = {"PC1": _score(1, marks_awarded="33.33"), "PC2": _score(1, marks_awarded="33.33")}
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "NOT_YET_COMPETENT"


def test_some_but_not_all_nos_competent_is_partially_competent():
    rows = [
        _row("N1", "PC1", "100.00"),
        _row("N2", "PC2", "100.00"), _row("N2", "PC3", "200.00"),
    ]
    scores = {
        "PC1": _score(3, marks_awarded="100.00"),  # N1 fully competent (100%)
        "PC2": _score(3, marks_awarded="100.00"), "PC3": _score(0, marks_awarded="0.00"),  # N2: 100/300 = 33% < 50%
    }
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "PARTIALLY_COMPETENT"
    assert result.achieved_nos_codes == ["N1"]
    assert result.gap_nos_codes == ["N2"]


def test_critical_pc_below_level_2_forces_not_yet_competent_regardless_of_percent():
    """rubric.json's own rule, verbatim: 'level < 2 -> that NOS cannot be
    marked competent, regardless of overall NOS %.' Even a perfect-looking
    NOS percent must not hide a critical safety failure."""
    rows = [_row("N1", "PC1", "50.00", critical=True), _row("N1", "PC2", "50.00")]
    scores = {"PC1": _score(1, marks_awarded="16.67"), "PC2": _score(3, marks_awarded="50.00")}
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "NOT_YET_COMPETENT"
    assert "PC1" in result.critical_violation_pc_ids
    nos1 = next(n for n in result.nos_results if n.nos_code == "N1")
    assert nos1.critical_violation is True
    assert nos1.competent is False


def test_critical_pc_at_level_2_is_fine():
    rows = [_row("N1", "PC1", "50.00", critical=True), _row("N1", "PC2", "50.00")]
    scores = {"PC1": _score(2, marks_awarded="33.33"), "PC2": _score(3, marks_awarded="50.00")}
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "RECOMMEND_CERTIFICATION"
    assert result.critical_violation_pc_ids == []


def test_unscored_pc_is_insufficient_evidence_not_silently_competent():
    """Missing/unscored criteria must never accidentally count as competent."""
    rows = [_row("N1", "PC1", "100.00")]
    scores: dict = {}  # never scored at all
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "INSUFFICIENT_EVIDENCE"
    nos1 = result.nos_results[0]
    assert nos1.has_insufficient_evidence is True
    assert nos1.competent is False
    assert nos1.marks_awarded == Decimal("0.00")


def test_not_observable_is_insufficient_evidence_distinct_from_demonstrated_zero():
    """NOT_OBSERVABLE (assessor explicitly couldn't see it in the evidence)
    must be distinguishable from a DEMONSTRATED, genuinely poor (level 0)
    performance -- the former is a capture/evidence problem (reassessment
    candidate), the latter is a real competency gap."""
    rows = [_row("N1", "PC1", "100.00")]
    scores_not_observable = {"PC1": _score(0, status="NOT_OBSERVABLE", marks_awarded="0.00")}
    result_a = compute_outcome(rows, scores_not_observable, THRESHOLD)
    assert result_a.outcome == "INSUFFICIENT_EVIDENCE"

    scores_demonstrated_zero = {"PC1": _score(0, status="DEMONSTRATED", marks_awarded="0.00")}
    result_b = compute_outcome(rows, scores_demonstrated_zero, THRESHOLD)
    assert result_b.outcome == "NOT_YET_COMPETENT"
    assert result_b.insufficient_evidence_nos_codes == []


def test_not_applicable_in_mvp_counts_as_scored_zero_marks_not_insufficient_evidence():
    rows = [_row("N1", "PC1", "50.00"), _row("N1", "PC2", "50.00")]
    scores = {
        "PC1": _score(3, marks_awarded="50.00"),
        "PC2": _score(0, status="NOT_APPLICABLE_IN_MVP", marks_awarded="0.00"),
    }
    result = compute_outcome(rows, scores, THRESHOLD)
    nos1 = result.nos_results[0]
    assert nos1.has_insufficient_evidence is False
    assert nos1.percent == 50.0


def test_fractional_marks_use_precise_decimal_arithmetic():
    """70/11 style equal-split marks (rubric.json's own marks_note) must
    not get silently truncated -- use real Decimal, round only for display."""
    rows = [_row("N1", "PC1", "6.36")]
    scores = {"PC1": _score(3, marks_awarded="6.36")}
    result = compute_outcome(rows, scores, THRESHOLD)
    nos1 = result.nos_results[0]
    assert nos1.marks_possible == Decimal("6.36")
    assert nos1.percent == 100.0


def test_most_nos_below_threshold_is_not_yet_competent_even_with_one_achieved():
    """1 of 5 mandatory NOS competent, 4 below threshold -- a strict
    majority failing is NOT_YET_COMPETENT, not PARTIALLY_COMPETENT (the
    master-plan 4.4 table's "most NOS below threshold" row; a lone
    achieved NOS must not mask an overall failing picture)."""
    rows = [
        _row("N1", "PC1", "100.00"),
        _row("N2", "PC2", "100.00"),
        _row("N3", "PC3", "100.00"),
        _row("N4", "PC4", "100.00"),
        _row("N5", "PC5", "100.00"),
    ]
    scores = {
        "PC1": _score(3, marks_awarded="100.00"),  # N1: 100% -- competent
        "PC2": _score(1, marks_awarded="33.33"),  # N2-N5: 33% < 50% -- not competent
        "PC3": _score(1, marks_awarded="33.33"),
        "PC4": _score(1, marks_awarded="33.33"),
        "PC5": _score(1, marks_awarded="33.33"),
    }
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "NOT_YET_COMPETENT"
    assert result.achieved_nos_codes == ["N1"]
    assert len(result.gap_nos_codes) == 4


def test_exactly_half_nos_below_threshold_stays_partially_competent():
    """An even split (not a strict majority failing) must NOT trip the
    "most NOS failing" rule -- this is the boundary the fix must not
    overreach past."""
    rows = [
        _row("N1", "PC1", "100.00"), _row("N2", "PC2", "100.00"),
        _row("N3", "PC3", "100.00"), _row("N4", "PC4", "100.00"),
    ]
    scores = {
        "PC1": _score(3, marks_awarded="100.00"),
        "PC2": _score(3, marks_awarded="100.00"),
        "PC3": _score(1, marks_awarded="33.33"),
        "PC4": _score(1, marks_awarded="33.33"),
    }
    result = compute_outcome(rows, scores, THRESHOLD)
    assert result.outcome == "PARTIALLY_COMPETENT"
    assert len(result.achieved_nos_codes) == 2
    assert len(result.gap_nos_codes) == 2
