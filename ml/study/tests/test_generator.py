from collections import Counter
import json

import pytest

from ml.study.common import SCENARIOS, fixed_status, load_pack, read_csv, read_jsonl
from ml.study.generate_demo_data import generate
from ml.study.outcome_adapter import derive_outcome


def test_twenty_unique_balanced_packages(dataset):
    packages = read_jsonl(dataset / "packages.jsonl")
    assert [p["package"] for p in packages] == [f"SIM-{i:03d}" for i in range(1, 21)]
    assert Counter(p["scenario"] for p in packages) == {s: 5 for s in SCENARIOS}
    assert len({json.dumps(p["pc_expectations"], sort_keys=True) for p in packages}) == 20


def test_tasks_come_from_pack(dataset):
    tasks = load_pack()["tasks"]["tasks"]
    for package in read_jsonl(dataset / "packages.jsonl"):
        assert [(t["task"], t["title"], t["nos"]) for t in package["task_references"]] == [(t["id"], t["title"], t["nos"]) for t in tasks]


def test_all_119_pcs_and_71_rubric_pcs(dataset):
    pack = load_pack()
    reference = read_csv(dataset / "expected_pc_levels.csv", reference=True)
    assert len(reference) == 20 * 119
    assert len(pack["rubric"]["items"]) == 71
    for row in reference:
        item = pack["catalog"][row["pc"]]
        assert row["nos"] == item["nos"]
        assert row["task"] == item["task"]
        assert row["critical"] == str(item["critical"]).lower()
        assert json.loads(row["anchors_json"]) == item["anchors"]
        if row["evidence_status"] == "DEMONSTRATED":
            assert type(row["level"]) is int and 0 <= row["level"] <= 3
        else:
            assert row["level"] is None
        if fixed_status(item):
            assert row["evidence_status"] == fixed_status(item)


def test_missing_evidence_is_not_observed_zero(dataset):
    reference = read_csv(dataset / "expected_pc_levels.csv", reference=True)
    assert any(r["level"] == 0 and r["evidence_status"] == "DEMONSTRATED" for r in reference)
    assert any(r["evidence_status"] == "NOT_OBSERVABLE" and r["critical"] == "true" for r in reference)
    omitted = [r for r in reference if r["package"] == "SIM-016" and r["task"] == "T1"]
    assert len(omitted) == 17
    assert all(r["evidence_status"] == "NOT_OBSERVABLE" and r["level"] is None for r in omitted)


def test_synthetic_and_metadata_only(dataset):
    packages = read_jsonl(dataset / "packages.jsonl")
    evidence = read_jsonl(dataset / "evidence_manifest.jsonl")
    assert len(evidence) == 100
    for record in evidence:
        assert record["media_available"] is False
        assert record["reviewability_status"] == "NO_MEDIA_TO_REVIEW"
        assert record["fixture_reference"].startswith("synthetic-fixture://")
        assert not any(key in record for key in ("sha256", "path", "uploaded", "signed", "verified"))
    for package in packages:
        assert package["synthetic"] is True
        assert "Fictional" in package["worker_declaration"]["statement"]
        assert not ({"name", "phone", "email", "government_id", "biometric"} & set(package))
        assert "not an official SSC" in package["rubric_disclaimer"]


def test_reference_outcomes_and_critical_failures(dataset):
    references = read_csv(dataset / "expected_pc_levels.csv", reference=True)
    for package in read_jsonl(dataset / "packages.jsonl"):
        rows = [r for r in references if r["package"] == package["package"]]
        actual = derive_outcome(rows)
        assert actual.outcome == package["expected_outcome"]
        if package["scenario"] in ("strong", "minor_faults"):
            assert actual.outcome == "RECOMMEND_CERTIFICATION"
        elif package["scenario"] == "major_faults":
            assert actual.outcome == "NOT_YET_COMPETENT"
            assert actual.critical_violation_pc_ids
        else:
            assert actual.outcome == "INSUFFICIENT_EVIDENCE"
            assert not actual.critical_violation_pc_ids


def test_outcome_adapter_rounding_and_missing_distinction(dataset):
    pack = load_pack()
    base = [r for r in read_csv(dataset / "expected_pc_levels.csv", reference=True) if r["package"] == "SIM-001"]
    # All demonstrated levels 3, not-applicable unscored: same denominator as backend.
    for row in base:
        if row["evidence_status"] == "DEMONSTRATED":
            row["level"] = 3
    result = derive_outcome(base)
    t4 = next(n for n in result.nos_results if n.nos_code == "CON/N0603")
    assert t4.percent == round((70.01 - 5.0) / 70.01 * 100, 2)
    critical = next(r for r in base if pack["catalog"][r["pc"]]["critical"])
    critical["evidence_status"], critical["level"] = "NOT_OBSERVABLE", None
    assert derive_outcome(base).outcome == "INSUFFICIENT_EVIDENCE"
    critical["evidence_status"], critical["level"] = "DEMONSTRATED", 0
    assert derive_outcome(base).outcome == "NOT_YET_COMPETENT"


def test_adapter_refuses_incomplete_or_duplicate_records(dataset):
    rows = [r for r in read_csv(dataset / "expected_pc_levels.csv", reference=True) if r["package"] == "SIM-001"]
    with pytest.raises(ValueError, match="all pinned"):
        derive_outcome(rows[1:])
    with pytest.raises(ValueError, match="duplicate"):
        derive_outcome(rows + [rows[0]])


@pytest.mark.parametrize("count", [0, -4, 3, 21])
def test_invalid_count(tmp_path, count):
    with pytest.raises(ValueError, match="divisible"):
        generate(tmp_path, count=count)
