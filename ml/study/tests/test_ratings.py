from collections import Counter

from ml.study.agreement import analyze
from ml.study.common import CONDITIONS, RATERS, read_csv
from ml.study.simulate_ratings import POLICY, simulate


def test_same_roster_and_items_both_conditions(dataset):
    rows = read_csv(dataset / "simulated_ratings.csv")
    assert len(rows) == 20 * 119 * 3 * 2
    assert set(r["rater"] for r in rows) == set(RATERS)
    assert set(r["condition"] for r in rows) == set(CONDITIONS)
    keys = {c: {(r["package"], r["pc"], r["rater"]) for r in rows if r["condition"] == c} for c in CONDITIONS}
    assert keys["manual"] == keys["rubric_assisted"]
    assert all(0 <= r["level"] <= 3 if r["evidence_status"] == "DEMONSTRATED" else r["level"] is None for r in rows)


def test_fixed_and_unobservable_statuses_preserved(dataset):
    references = {(r["package"], r["pc"]): r for r in read_csv(dataset / "expected_pc_levels.csv", reference=True)}
    rows = read_csv(dataset / "simulated_ratings.csv")
    for row in rows:
        reference = references[row["package"], row["pc"]]
        if reference["evidence_status"] != "DEMONSTRATED":
            assert row["evidence_status"] == reference["evidence_status"]
            assert row["level"] is None


def test_baseline_has_variation_and_no_programmed_assistance(dataset):
    rows = read_csv(dataset / "simulated_ratings.csv")
    assert all(r["policy"] == "baseline" and r["simulation_seed"] == "42" for r in rows)
    assert sorted(POLICY["severity"].values()) == [-0.18, 0, 0.18]
    reference = read_csv(dataset / "expected_pc_levels.csv", reference=True)
    result = analyze(rows, reference, bootstrap=0)
    assert result["metrics"]["manual"]["exact_agreement_pct"] < 100
    # The canonical baseline actually worsens some assisted metrics; no positive gate.
    assert result["differences"]["mean_pairwise_qwk"] < 0
    deltas = Counter()
    by_ref = {(r["package"], r["pc"]): r for r in reference}
    for row in rows:
        if row["level"] is not None:
            deltas[row["level"] - by_ref[row["package"], row["pc"]]["level"]] += 1
    assert all(deltas[d] > 0 for d in (-2, -1, 0, 1, 2))


def test_identical_policy_is_zero_difference_control(dataset, tmp_path):
    path = tmp_path / "identical.csv"
    simulate(dataset / "expected_pc_levels.csv", path, policy="identical")
    result = analyze(read_csv(path), read_csv(dataset / "expected_pc_levels.csv", reference=True), bootstrap=30)
    for key, difference in result["differences"].items():
        assert difference == 0
        assert result["ci95"][key]["low"] == result["ci95"][key]["high"] == 0


def test_ratings_deterministic_and_seed_sensitive(dataset, tmp_path):
    same, different = tmp_path / "same.csv", tmp_path / "different.csv"
    simulate(dataset / "expected_pc_levels.csv", same)
    simulate(dataset / "expected_pc_levels.csv", different, seed=43)
    assert same.read_bytes() == (dataset / "simulated_ratings.csv").read_bytes()
    assert same.read_bytes() != different.read_bytes()
