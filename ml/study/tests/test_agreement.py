"""Hand calculations plus independent sklearn/statsmodels oracles, no copied algorithm."""
import itertools
import math
import random

import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score
from statsmodels.stats.inter_rater import fleiss_kappa as library_fleiss

from ml.study.agreement import (METRICS, Summary, analyze, cluster_draw, fleiss_kappa, metrics,
                                percentile, population_sd, prepare, quadratic_weighted_kappa, sum_draw)


def fixture(matrix, references=None, packages=None, assisted=None):
    ratings, refs = [], []
    for i, levels in enumerate(matrix):
        base = {"package": packages[i] if packages else f"P{i}", "pc": f"PC{i}",
                "nos": "NOS", "task": "TASK", "scenario": "fixture", "evidence_status": "DEMONSTRATED"}
        if references is not None and references[i] is not None:
            refs.append(dict(base, level=references[i]))
        for condition, values in (("manual", levels), ("rubric_assisted", assisted[i] if assisted else levels)):
            for rater, level in enumerate(values):
                ratings.append(dict(base, rater=f"R{rater}", condition=condition, level=level))
    return ratings, refs


def test_perfect_agreement_every_metric():
    rows, reference = fixture([[v] * 3 for v in range(4)], list(range(4)))
    result = analyze(rows, reference, bootstrap=10)
    for condition in ("manual", "rubric_assisted"):
        m = result["metrics"][condition]
        assert m["mean_pairwise_qwk"] == m["fleiss_kappa"] == 1
        assert m["exact_agreement_pct"] == 100
        assert m["mean_rating_sd"] == m["mae"] == 0


def test_complete_disagreement_hand_calculation():
    rows, refs = fixture([[0, 1, 3], [0, 1, 3]], [1, 1])
    m = analyze(rows, refs, bootstrap=0)["metrics"]["manual"]
    assert m["mean_pairwise_qwk"] == 0
    assert m["fleiss_kappa"] == pytest.approx(-0.5)
    assert m["exact_agreement_pct"] == 0
    assert m["mean_rating_sd"] == pytest.approx(math.sqrt(14) / 3)
    assert m["mae"] == 1


def test_partial_disagreement_hand_calculation():
    # Pi=1/3 for both rows. Pooled p=(1/3,1/3,1/3,0), Pe=1/3.
    rows, refs = fixture([[0, 0, 1], [1, 2, 2]], [0, 2])
    m = analyze(rows, refs, bootstrap=0)["metrics"]["manual"]
    assert m["fleiss_kappa"] == pytest.approx(0)
    assert m["exact_agreement_pct"] == 0
    assert m["mean_rating_sd"] == pytest.approx(math.sqrt(2) / 3)
    assert m["mae"] == pytest.approx(1 / 3)
    assert quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 3, 2]) == pytest.approx(0.8)


@pytest.mark.parametrize("a,b", [([0, 1, 2, 3], [3, 2, 1, 0]),
                                ([0, 1, 2, 3], [1, 2, 3, 3]),
                                ([0, 0, 2, 3, 1], [0, 1, 2, 2, 3])])
def test_qwk_against_sklearn(a, b):
    assert quadratic_weighted_kappa(a, b) == pytest.approx(cohen_kappa_score(a, b, labels=[0, 1, 2, 3], weights="quadratic"), abs=1e-12)


@pytest.mark.parametrize("table", [ [[3, 0, 0, 0], [0, 3, 0, 0], [0, 0, 3, 0]],
                                      [[2, 1, 0, 0], [0, 1, 2, 0], [0, 0, 0, 3]],
                                      [[1, 1, 0, 1], [0, 2, 1, 0], [1, 0, 1, 1]] ])
def test_fleiss_against_statsmodels(table):
    assert fleiss_kappa(table) == pytest.approx(library_fleiss(np.array(table), method="fleiss"), abs=1e-12)


def test_each_metric_independent_random_oracles():
    rng = random.Random(72)
    matrix = [[rng.randrange(4) for _ in range(3)] for _ in range(100)]
    reference = [rng.randrange(4) for _ in matrix]
    rows, refs = fixture(matrix, reference)
    actual = analyze(rows, refs, bootstrap=0)["metrics"]["manual"]
    array = np.array(matrix)
    expected_qwk = np.mean([cohen_kappa_score(array[:, a], array[:, b], weights="quadratic", labels=[0, 1, 2, 3]) for a, b in itertools.combinations(range(3), 2)])
    counts = np.stack([(array == level).sum(axis=1) for level in range(4)], axis=1)
    assert actual["mean_pairwise_qwk"] == pytest.approx(expected_qwk, abs=1e-12)
    assert actual["fleiss_kappa"] == pytest.approx(library_fleiss(counts), abs=1e-12)
    assert actual["exact_agreement_pct"] == pytest.approx(100 * np.mean(np.all(array == array[:, :1], axis=1)))
    assert actual["mean_rating_sd"] == pytest.approx(np.std(array, axis=1, ddof=0).mean())
    assert actual["mae"] == pytest.approx(np.abs(array - np.array(reference)[:, None]).mean())


def test_missing_rater_uses_joint_complete_set():
    rows, refs = fixture([[0, 0, 0], [1, 1, 1], [2, 2, 2]], [0, 1, 2])
    rows.pop()
    result = analyze(rows, refs, bootstrap=0)
    assert result["audit"]["retained_complete_scored_items"] == 2
    assert result["audit"]["excluded_items_by_reason"]["incomplete_rater_group_in_either_condition"] == 1
    assert result["audit"]["missing_rater_slots_by_condition"]["rubric_assisted"] == 1
    assert result["metrics"]["manual"] == result["metrics"]["rubric_assisted"]


def test_unobservable_and_fixed_status_exclusions():
    rows, refs = fixture([[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 3, 3]], [0, 1, 2, 3])
    for row in rows:
        if row["pc"] == "PC0":
            row["evidence_status"], row["level"] = "NOT_OBSERVABLE", None
        if row["pc"] == "PC1":
            row["evidence_status"], row["level"] = "NOT_APPLICABLE_IN_MVP", None
    result = analyze(rows, refs, bootstrap=0)
    assert result["audit"]["retained_complete_scored_items"] == 2
    assert result["audit"]["excluded_items_by_reason"] == {"fixed_unscored_status_in_either_condition": 1, "not_observable_in_either_condition": 1}
    assert result["metrics"]["manual"]["mae"] == 0


def test_one_rater_only_mae_is_available():
    rows, refs = fixture([[0], [2]], [1, 2])
    result = analyze(rows, refs, bootstrap=5)
    assert result["metrics"]["manual"]["mae"] == 0.5
    for key in METRICS.keys() - {"mae"}:
        assert result["metrics"]["manual"][key] is None


def test_explicit_roster_catches_wholly_absent_rater():
    rows, refs = fixture([[0, 0], [1, 1]], [0, 1])
    result = analyze(rows, refs, bootstrap=0, expected_raters=["R0", "R1", "R2"])
    assert result["audit"]["retained_complete_scored_items"] == 0
    assert result["audit"]["missing_rater_slots_by_condition"] == {"manual": 2, "rubric_assisted": 2}


def test_degenerate_kappa_not_misleading_zero():
    rows, refs = fixture([[3, 3, 3], [3, 3, 3]], [3, 3])
    result = analyze(rows, refs, bootstrap=10)
    m = result["metrics"]["manual"]
    assert m["mean_pairwise_qwk"] is m["fleiss_kappa"] is None
    assert m["exact_agreement_pct"] == 100
    assert m["mean_rating_sd"] == 0
    assert result["ci95"]["fleiss_kappa"]["low"] is None
    assert result["ci95"]["fleiss_kappa"]["undefined_replicates"] == 10


def test_one_undefined_pair_makes_mean_unavailable():
    rows, _ = fixture([[0, 0, 1], [0, 0, 2]])
    result = analyze(rows, bootstrap=0)
    assert result["pairwise_qwk"]["manual"]["R0 / R1"] is None
    assert result["metrics"]["manual"]["mean_pairwise_qwk"] is None


def test_no_common_packages_and_missing_condition():
    rows, refs = fixture([[0, 1, 2], [1, 2, 3]], [1, 2])
    for row in rows:
        if row["condition"] == "rubric_assisted":
            row["package"] += "other"
    result = analyze(rows, refs, bootstrap=5)
    assert result["audit"]["common_packages"] == []
    assert all(x is None for x in result["metrics"]["manual"].values())
    assert result["ci95"]["mae"]["unavailable_reason"]
    result = analyze([r for r in rows if r["condition"] == "manual"], refs, bootstrap=0)
    assert result["audit"]["common_packages"] == []


def test_missing_reference_and_unscored_reference():
    rows, refs = fixture([[0, 1, 2], [1, 2, 3], [1, 1, 2]], [None, 2, 2])
    refs[-1]["evidence_status"], refs[-1]["level"] = "NOT_OBSERVABLE", None
    result = analyze(rows, refs, bootstrap=0)
    assert result["audit"]["mae_excluded_items_missing_reference"] == 1
    assert result["audit"]["mae_excluded_items_unscored_reference"] == 1
    assert result["metrics"]["manual"]["mae"] == pytest.approx(2 / 3)
    assert analyze(rows, bootstrap=0)["metrics"]["manual"]["mae"] is None


def test_reordering_is_exactly_invariant():
    rows, refs = fixture([[0, 0, 1], [1, 2, 2], [2, 3, 3]], [0, 1, 3])
    expected = analyze(rows, refs, bootstrap=25)
    random.Random(19).shuffle(rows)
    refs.reverse()
    assert analyze(rows, refs, bootstrap=25) == expected


def test_repeated_cluster_draw_is_not_deduplicated():
    rows, refs = fixture([[0, 0, 0], [0, 1, 2], [3, 3, 3]], [0, 1, 3], packages=["A", "B", "B"])
    packages, roster, contributions, _ = prepare(rows, refs)
    # Two draws of B include both of B's PCs twice; A contributes nothing.
    draws = [("draw-0", "B"), ("draw-1", "B")]
    summary = sum_draw(contributions, draws, "manual", len(roster))
    assert summary.n == 4
    assert summary.mae_n == 12
    assert metrics(summary, 3)["exact_agreement_pct"] == 50
    literal = []
    literal_refs = []
    for draw_id, package in draws:
        literal += [dict(r, package=draw_id) for r in rows if r["package"] == package]
        literal_refs += [dict(r, package=draw_id) for r in refs if r["package"] == package]
    expanded = analyze(literal, literal_refs, bootstrap=0)["metrics"]["manual"]
    for key, value in metrics(summary, 3).items():
        assert expanded[key] == pytest.approx(value) if value is not None else expanded[key] is None
    found_repeat = False
    for seed in range(20):
        draw = cluster_draw(packages, random.Random(seed))
        assert len({identity for identity, _ in draw}) == len(packages)
        found_repeat |= len({package for _, package in draw}) < len(packages)
    assert found_repeat


def test_bootstrap_hand_enumerated_mae_interval():
    # Manual MAE=0 for A/B. Assisted errors=0 for A, 3 for B.
    # Every paired size-2 cluster draw gives difference 0, 1.5 or 3.
    rows, refs = fixture([[0, 0, 0], [0, 0, 0]], [0, 0], assisted=[[0, 0, 0], [3, 3, 3]])
    result = analyze(rows, refs, bootstrap=200, seed=42)
    assert result["differences"]["mae"] == 1.5
    assert result["ci95"]["mae"]["low"] == 0
    assert result["ci95"]["mae"]["high"] == 3
    assert result["ci95"]["mae"]["defined_replicates"] == 200


def test_one_cluster_ci_is_unavailable():
    rows, refs = fixture([[0, 1, 2], [1, 2, 3]], [0, 2], packages=["A", "A"])
    result = analyze(rows, refs, bootstrap=10)
    assert result["ci95"]["mae"]["low"] is None
    assert "at least two common" in result["ci95"]["mae"]["unavailable_reason"]


@pytest.mark.parametrize("level", [-1, 4, 0.5, float("nan"), True, None])
def test_invalid_levels_in_library_api(level):
    rows, _ = fixture([[0, 1, 2]])
    rows[0]["level"] = level
    with pytest.raises(ValueError, match="integer level"):
        analyze(rows)


def test_duplicate_and_metadata_mismatch_rejected():
    rows, refs = fixture([[0, 1, 2]])
    with pytest.raises(ValueError, match="duplicate rating"):
        analyze(rows + [rows[0]])
    with pytest.raises(ValueError, match="duplicate reference"):
        analyze(rows, refs + [dict(rows[0])]*2)
    rows[-1]["nos"] = "WRONG"
    with pytest.raises(ValueError, match="inconsistent NOS"):
        analyze(rows)


@pytest.mark.parametrize("table", [[[1, 1], [0, 3]], [[-1, 3]], [[0.5, 1.5]]])
def test_invalid_fleiss_tables(table):
    with pytest.raises(ValueError):
        fleiss_kappa(table)


def test_empty_metric_inputs():
    assert quadratic_weighted_kappa([], []) is None
    assert fleiss_kappa([]) is None
    assert population_sd([]) is None
    assert population_sd([1]) is None
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([0], [])


def test_percentile_matches_numpy():
    values = [-3.2, 2.8, 7.5, 0.2, 2.1]
    for q in (0, 0.025, 0.5, 0.975, 1):
        assert percentile(values, q) == pytest.approx(np.quantile(values, q, method="linear"))


def test_outcome_category_statistics_against_library(dataset):
    from ml.study.common import CONDITIONS, RATERS, read_csv
    from ml.study.outcome_adapter import OUTCOMES, derive_outcome
    rows = read_csv(dataset / "simulated_ratings.csv")
    refs = read_csv(dataset / "expected_pc_levels.csv", reference=True)
    result = analyze(rows, refs, bootstrap=0)
    for condition in CONDITIONS:
        table = []
        exact = 0
        for package in sorted({r["package"] for r in rows}):
            outcomes = [derive_outcome([r for r in rows if r["package"] == package and r["condition"] == condition and r["rater"] == rater]).outcome for rater in RATERS]
            table.append([outcomes.count(o) for o in OUTCOMES])
            exact += len(set(outcomes)) == 1
        assert result["metrics"][condition]["outcome_fleiss_kappa"] == pytest.approx(library_fleiss(np.array(table)), abs=1e-12)
        assert result["metrics"][condition]["outcome_exact_agreement_pct"] == 100 * exact / 20


def test_incomplete_package_outcomes_excluded_jointly(dataset):
    from ml.study.common import read_csv
    rows = read_csv(dataset / "simulated_ratings.csv")
    rows = [r for r in rows if not (r["package"] == "SIM-001" and r["pc"] == "CON/N0602.PC1" and r["rater"] == "SIM_RATER_01" and r["condition"] == "manual")]
    result = analyze(rows, bootstrap=0)
    assert result["audit"]["outcome_excluded_common_packages_incomplete_pack"] == 1
    for distribution in result["audit"]["outcome_distributions"].values():
        assert sum(distribution.values()) == 19 * 3


def test_insufficient_defined_bootstrap_replicates():
    # Only one package has category variation. Its absence makes kappa undefined.
    rows, refs = fixture([[0, 0, 0], [1, 1, 1]], [0, 1])
    result = analyze(rows, refs, bootstrap=100)
    ci = result["ci95"]["fleiss_kappa"]
    assert 0 < ci["defined_replicates"] < 95
    assert ci["low"] is None and "5%" in ci["unavailable_reason"]
