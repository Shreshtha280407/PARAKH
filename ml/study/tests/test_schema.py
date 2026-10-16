import json
import shutil

import pytest

from ml.study.common import RATING_FIELDS, REFERENCE_FIELDS, digest, read_csv, read_jsonl, write_csv, write_json, write_jsonl
from ml.study.validate_dataset import validate


def test_full_contract_and_provenance(dataset):
    counts = validate(dataset, check_reproducible=True)
    assert counts["packages"] == 20
    assert counts["rating_records"] == 14280
    assert counts["critical_pcs"] == 26
    assert counts["safety_evidence_omitted_packages"] == ["SIM-016"]


def test_source_hash_tampering_detected(dataset, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(dataset, data)
    manifest = json.loads((data / "dataset_manifest.json").read_text())
    manifest["source_sha256"]["server/app/outcome.py"] = "0" * 64
    write_json(data / "dataset_manifest.json", manifest)
    with pytest.raises(ValueError, match="source provenance"):
        validate(data)


def test_artifact_hash_tampering_detected(dataset, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(dataset, data)
    with (data / "packages.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="artifact hash"):
        validate(data)


def refresh_hash(data, name):
    manifest = json.loads((data / "dataset_manifest.json").read_text())
    manifest["artifact_sha256"][name] = digest(data / name)
    write_json(data / "dataset_manifest.json", manifest)


@pytest.mark.parametrize("change,pattern", [("unknown_pc", "reference PC"), ("unknown_nos", "metadata drift"),
                                           ("unknown_task", "metadata drift"), ("anchor", "anchor drift"),
                                           ("critical", "critical flag"), ("missing_reference", "reference PC"),
                                           ("scored_na", "applicability/status"), ("unscored_zero", "missing level")])
def test_reference_schema_rejects_corruption(dataset, tmp_path, change, pattern):
    data = tmp_path / "data"
    shutil.copytree(dataset, data)
    rows = read_csv(data / "expected_pc_levels.csv", reference=True)
    if change == "unknown_pc": rows[0]["pc"] = "CON/N0602.PC999"
    if change == "unknown_nos": rows[0]["nos"] = "UNKNOWN"
    if change == "unknown_task": rows[0]["task"] = "T6"
    if change == "anchor": rows[0]["anchors_json"] = "{}"
    if change == "critical": rows[0]["critical"] = "false"
    if change == "missing_reference": rows.pop()
    if change == "scored_na":
        row = next(r for r in rows if r["evidence_status"] == "NOT_APPLICABLE_IN_MVP")
        row["evidence_status"], row["level"] = "DEMONSTRATED", 3
    if change == "unscored_zero":
        row = next(r for r in rows if r["evidence_status"] == "NOT_OBSERVABLE")
        row["level"] = 0
    write_csv(data / "expected_pc_levels.csv", rows, REFERENCE_FIELDS)
    refresh_hash(data, "expected_pc_levels.csv")
    with pytest.raises(ValueError, match=pattern):
        validate(data)


@pytest.mark.parametrize("change,pattern", [("missing_rater", "rating identity"), ("false_media", "misrepresented"),
                                           ("private_field", "package schema"), ("unknown_task", "task reference"),
                                           ("wrong_quality", "fictional evidence quality")])
def test_package_evidence_rating_contracts(dataset, tmp_path, change, pattern):
    data = tmp_path / "data"
    shutil.copytree(dataset, data)
    if change == "missing_rater":
        name = "simulated_ratings.csv"
        rows = read_csv(data / name)
        write_csv(data / name, [r for r in rows if r["rater"] != "SIM_RATER_03"], RATING_FIELDS)
    elif change in ("false_media", "wrong_quality"):
        name = "evidence_manifest.jsonl"
        rows = read_jsonl(data / name)
        if change == "false_media": rows[0]["media_available"] = True
        else: rows[0]["quality_warning_scenario"] = "FABRICATED_DETECTION"
        write_jsonl(data / name, rows)
    else:
        name = "packages.jsonl"
        rows = read_jsonl(data / name)
        if change == "private_field": rows[0]["phone"] = "FORBIDDEN_FIELD"
        else: rows[0]["task_references"][0]["task"] = "T6"
        write_jsonl(data / name, rows)
    refresh_hash(data, name)
    with pytest.raises(ValueError, match=pattern):
        validate(data)


def minimal_row(**changes):
    row = {"package": "P", "pc": "PC", "nos": "NOS", "task": "T", "rater": "R", "condition": "manual",
           "evidence_status": "DEMONSTRATED", "level": 1, "scenario": "test", "simulation_seed": 42, "policy": "baseline", "synthetic": "true"}
    return dict(row, **changes)


@pytest.mark.parametrize("level", [-1, 4, 1.5, "NaN", "inf", "", "01", " 1"])
def test_csv_invalid_levels(tmp_path, level):
    path = tmp_path / "bad.csv"
    write_csv(path, [minimal_row(level=level)], RATING_FIELDS)
    with pytest.raises(ValueError, match="integer level"):
        read_csv(path)


def test_duplicate_csv_and_blank_not_observable(tmp_path):
    path = tmp_path / "bad.csv"
    row = minimal_row()
    write_csv(path, [row, row], RATING_FIELDS)
    with pytest.raises(ValueError, match="duplicate identity"):
        read_csv(path)
    write_csv(path, [minimal_row(evidence_status="NOT_OBSERVABLE", level=None)], RATING_FIELDS)
    assert read_csv(path)[0]["level"] is None
    write_csv(path, [minimal_row(evidence_status="NOT_OBSERVABLE", level=0)], RATING_FIELDS)
    with pytest.raises(ValueError, match="missing level"):
        read_csv(path)


@pytest.mark.parametrize("text", ["package,pc\nP,PC\n", "package,package\nP,P\n", "", ",\n", 'package,pc\n"unterminated',
                                  ",".join(RATING_FIELDS) + "\nP,too,few\n"])
def test_corrupt_csv(tmp_path, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        read_csv(path)


def test_csv_invalid_encoding_and_empty_data(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="corrupt CSV"):
        read_csv(path)
    write_csv(path, [], RATING_FIELDS)
    with pytest.raises(ValueError, match="empty CSV"):
        read_csv(path)


@pytest.mark.parametrize("content", ['{"id":1,"id":2}', '{"level":NaN}', '{"level":Infinity}', '[]', '{}\n\n'])
def test_invalid_jsonl_objects(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_text(content)
    with pytest.raises(ValueError, match="invalid JSONL"):
        read_jsonl(path)
