#!/usr/bin/env python3
"""Generate fictional, metadata-only packages from the pinned CON/Q0602 pack."""
import argparse
import random
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.study.common import (HERE, MARKER, REFERENCE_FIELDS, SCENARIOS, VERSION, canonical,
                             digest, fixed_status, load_pack, source_hashes, write_csv,
                             write_json, write_jsonl)
from ml.study.outcome_adapter import derive_outcome


def generate(out_dir=HERE / "data", *, seed=42, count=20):
    if count <= 0 or count % 4:
        raise ValueError("count must be positive and divisible by four for balanced scenarios")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pack, rng = load_pack(), random.Random(seed)
    tasks, catalog = pack["tasks"]["tasks"], pack["catalog"]
    packages, references, evidence = [], [], []
    critical_pcs = [pc for pc, i in catalog.items() if i["critical"] and not fixed_status(i)]
    for index in range(count):
        package = f"SIM-{index + 1:03d}"
        scenario_index, variant = divmod(index, count // 4)
        scenario = SCENARIOS[scenario_index]
        omitted_task = tasks[variant % len(tasks)]["id"] if scenario == "incomplete_evidence" else None
        violation_pc = critical_pcs[variant % len(critical_pcs)] if scenario == "major_faults" else None
        package_rows, task_refs = [], []
        for pc, item in catalog.items():
            status = fixed_status(item)
            ambiguity = round(rng.uniform(0.05, 0.8), 4)
            if status is None:
                incomplete = scenario == "incomplete_evidence" and (
                    item["task"] == omitted_task or rng.random() < 0.12)
                status = "NOT_OBSERVABLE" if incomplete else "DEMONSTRATED"
            level = None
            if status == "DEMONSTRATED":
                if scenario == "major_faults":
                    level = rng.choices([0, 1, 2], [0.4, 0.45, 0.15])[0]
                elif scenario == "minor_faults":
                    level = rng.choices([1, 2, 3], [0.04, 0.61, 0.35])[0]
                    if item["critical"]:
                        level = max(2, level)
                else:
                    level = rng.choices([2, 3], [0.18 + variant * 0.03, 0.82 - variant * 0.03])[0]
                if pc == violation_pc:
                    level = variant % 2
            row = {"package": package, "pc": pc, "nos": item["nos"], "task": item["task"],
                   "evidence_status": status, "level": level, "scenario": scenario,
                   "marks": item["marks"], "critical": str(item["critical"]).lower(),
                   "evidence_pathway": item["evidence_pathway"],
                   "mvp_applicability": item["mvp_applicability"],
                   "anchors_json": canonical(item["anchors"]), "ambiguity": ambiguity,
                   "reference_kind": "synthetic_reference", "synthetic": "true"}
            package_rows.append(row)
        for task in tasks:
            task_id = task["id"]
            fixture = f"synthetic-fixture://{VERSION}/{package}/{task_id}"
            task_rows = [r for r in package_rows if r["task"] == task_id]
            missing = sum(r["evidence_status"] == "NOT_OBSERVABLE" for r in task_rows)
            evidence_id = f"{package}-{task_id}-META"
            evidence.append({
                "package": package, "task": task_id, "evidence_id": evidence_id,
                "fixture_reference": fixture, "media_kind": rng.choice(["photo", "video"]),
                "media_available": False, "evidence_availability": "METADATA_ONLY",
                "reviewability_status": "NO_MEDIA_TO_REVIEW",
                "scenario_availability": "OMITTED" if task_id == omitted_task else "PRESENT_IN_FICTION",
                "scenario_reviewability": "MISSING" if task_id == omitted_task else "UNCLEAR" if missing else "CLEAR",
                "quality_warning_scenario": "OMITTED_EVIDENCE" if task_id == omitted_task else "UNCLEAR_VIEW" if missing else None,
                "expected_evidence_status_by_pc": {r["pc"]: r["evidence_status"] for r in task_rows},
                "synthetic": True, "provenance": MARKER,
            })
            task_refs.append({"task": task_id, "title": task["title"], "nos": task["nos"],
                              "evidence_metadata_refs": [evidence_id], "fixture_reference": fixture})
        outcome = derive_outcome(package_rows, pack)
        packages.append({
            "package": package, "synthetic": True, "provenance": MARKER, "scenario": scenario,
            "qp_code": pack["qp"]["qp_code"], "qp_version": pack["qp"]["version"],
            "rubric_id": pack["rubric"]["rubric_id"], "rubric_status": pack["rubric"]["status"],
            "rubric_disclaimer": pack["rubric"]["rules"]["disclaimer"],
            "generator": {"version": VERSION, "seed": seed},
            "worker_declaration": {"synthetic": True, "statement": "Fictional worker declaration for software testing only.",
                                   "scenario_profile": scenario, "variant": variant + 1},
            "task_references": task_refs,
            "pc_expectations": [{"pc": r["pc"], "evidence_status": r["evidence_status"],
                                 "scenario_expected_level": r["level"], "critical": r["critical"] == "true"}
                                for r in package_rows],
            "expected_outcome": outcome.outcome,
            "critical_violation_pcs": outcome.critical_violation_pc_ids,
            "omitted_evidence_task": omitted_task,
            "scenario_description": "Fictional assessment record; no electrical work or recording occurred.",
        })
        references.extend(package_rows)
    write_jsonl(out_dir / "packages.jsonl", packages)
    write_csv(out_dir / "expected_pc_levels.csv", references, REFERENCE_FIELDS)
    write_jsonl(out_dir / "evidence_manifest.jsonl", evidence)
    manifest = {
        "schema_version": 1, "generator_version": VERSION, "seed": seed, "count": count,
        "synthetic": True, "provenance": MARKER, "reference_kind": "synthetic_reference",
        "qp_code": pack["qp"]["qp_code"], "qp_version": pack["qp"]["version"],
        "rubric_id": pack["rubric"]["rubric_id"], "rubric_status": pack["rubric"]["status"],
        "rubric_disclaimer": pack["rubric"]["rules"]["disclaimer"],
        "scenario_counts": dict(Counter(p["scenario"] for p in packages)),
        "source_sha256": source_hashes(),
        "artifact_sha256": {name: digest(out_dir / name) for name in (
            "packages.jsonl", "expected_pc_levels.csv", "evidence_manifest.jsonl")},
        "clock_policy": "No event timestamps: fictional metadata only; no wall clock or UUIDs.",
        "media_policy": "No media files, media hashes, upload receipts or signatures exist.",
    }
    write_json(out_dir / "dataset_manifest.json", manifest)
    return packages, references, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out-dir", type=Path, default=HERE / "data")
    args = parser.parse_args()
    packages, reference, _ = generate(args.out_dir, seed=args.seed, count=args.count)
    print(f"{MARKER}: {len(packages)} packages, {len(reference)} reference rows")


if __name__ == "__main__":
    main()
