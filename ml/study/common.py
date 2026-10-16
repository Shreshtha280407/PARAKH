"""Versioned study contracts, strict serialization, and pinned pack access.

Runtime uses only the standard library. CSV blanks mean None, never level 0.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERSION = "d3-synthetic-v1"
MARKER = "SYNTHETIC_ENGINEERING_VALIDATION_ONLY"
LIMITATION = (
    "This report uses synthetic packages, synthetic reference scores and simulated raters. "
    "It validates the software and statistics only. It is not evidence of agreement "
    "improvement among real assessors."
)
SCENARIOS = ("strong", "minor_faults", "major_faults", "incomplete_evidence")
CONDITIONS = ("manual", "rubric_assisted")
RATERS = ("SIM_RATER_01", "SIM_RATER_02", "SIM_RATER_03")
STATUSES = ("DEMONSTRATED", "NOT_OBSERVABLE", "NOT_APPLICABLE_IN_MVP",
            "DECLARATION_OR_ASSESSOR_NOTE")
BASE_FIELDS = ["package", "pc", "nos", "task", "evidence_status", "level", "scenario"]
REFERENCE_FIELDS = BASE_FIELDS + ["marks", "critical", "evidence_pathway", "mvp_applicability",
                                  "anchors_json", "ambiguity", "reference_kind", "synthetic"]
RATING_FIELDS = BASE_FIELDS + ["rater", "condition", "simulation_seed", "policy", "synthetic"]
SOURCE_FILES = [
    "packs/ae-con-q0602/qp.json", "packs/ae-con-q0602/rubric.json",
    "packs/ae-con-q0602/tasks.json", "packs/ae-con-q0602/coverage_matrix.json",
    "server/app/outcome.py", "server/app/routers/scoring.py",
] + [f"ml/study/{name}" for name in (
    "common.py", "outcome_adapter.py", "generate_demo_data.py", "simulate_ratings.py",
    "agreement.py", "validate_dataset.py", "reproduce.py", "requirements-test.txt",
)]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: digest(ROOT / name) for name in SOURCE_FILES}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    Path(path).write_text("".join(canonical(r) + "\n" for r in rows), encoding="utf-8")


def strict_json(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def read_jsonl(path):
    rows = []
    for line, text in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = strict_json(text)
            if not isinstance(row, dict):
                raise ValueError("expected an object")
            rows.append(row)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path}:{line}: invalid JSONL: {exc}") from exc
    return rows


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path, *, reference=False):
    """Reject corrupt/duplicate records; permit absent rater records for audited exclusion.

    Generic statistical fixtures may use their own item IDs. The dataset validator
    additionally enforces every identity and metadata field against the pinned pack.
    """
    required = set(BASE_FIELDS + ([] if reference else ["rater", "condition"]))
    result, seen = [], set()
    try:
        with Path(path).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames
            if not header or len(set(header)) != len(header) or not required <= set(header):
                raise ValueError("missing or duplicate CSV columns")
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"line {reader.line_num}: wrong column count")
                for key in required - {"task", "level"}:
                    if not row[key] or row[key] != row[key].strip():
                        raise ValueError(f"line {reader.line_num}: blank/whitespace {key}")
                status, level = row["evidence_status"], row["level"]
                if status not in STATUSES:
                    raise ValueError(f"line {reader.line_num}: invalid evidence_status {status}")
                if status == "DEMONSTRATED":
                    if level not in ("0", "1", "2", "3"):
                        raise ValueError(f"line {reader.line_num}: DEMONSTRATED needs integer level 0–3")
                    row["level"] = int(level)
                else:
                    if level != "":
                        raise ValueError(f"line {reader.line_num}: {status} must have a missing level")
                    row["level"] = None
                key = (row["package"], row["pc"])
                if not reference:
                    if row["condition"] not in CONDITIONS:
                        raise ValueError(f"line {reader.line_num}: unknown condition")
                    key += (row["rater"], row["condition"])
                if key in seen:
                    raise ValueError(f"line {reader.line_num}: duplicate identity {key}")
                seen.add(key)
                result.append(row)
    except (csv.Error, UnicodeError) as exc:
        raise ValueError(f"{path}: corrupt CSV: {exc}") from exc
    if not result:
        raise ValueError(f"{path}: empty CSV")
    return result


def load_pack():
    pack_dir = ROOT / "packs/ae-con-q0602"
    pack = {name: json.loads((pack_dir / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("qp", "rubric", "tasks", "coverage_matrix")}
    rubric = {x["pc_id"]: x for x in pack["rubric"]["items"]}
    catalog = {}
    for coverage in pack["coverage_matrix"]["rows"]:
        pc = coverage["pc_id"]
        item = rubric.get(pc)
        catalog[pc] = {
            "pc": pc, "nos": coverage["nos"],
            "task": item["tasks"][0] if item else "",
            "marks": str(item["marks"]) if item else None,
            "critical": item["critical"] if item else False,
            "evidence_pathway": coverage["status"],
            "mvp_applicability": coverage["mvp_applicability"],
            "anchors": item["anchors"] if item else {},
        }
    pack["catalog"] = catalog
    return pack


def fixed_status(item):
    if item["evidence_pathway"] == "DECLARATION_OR_ASSESSOR_NOTE":
        return "DECLARATION_OR_ASSESSOR_NOTE"
    if item["mvp_applicability"] == "NOT_APPLICABLE_IN_MVP":
        return "NOT_APPLICABLE_IN_MVP"
    return None


def validate_score_record(row):
    """Shared in-memory contract, including the library-level analysis API."""
    status, level = row["evidence_status"], row["level"]
    if status not in STATUSES:
        raise ValueError(f"invalid evidence_status {status}")
    if status == "DEMONSTRATED":
        if type(level) is not int or level not in range(4):
            raise ValueError("DEMONSTRATED needs integer level 0–3")
    elif level is not None:
        raise ValueError(f"{status} must have a missing level")
