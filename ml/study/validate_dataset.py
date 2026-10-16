#!/usr/bin/env python3
"""Strict D3 schema, pack identity, missingness and source/artifact provenance checks."""
import argparse
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.study.common import (CONDITIONS, HERE, LIMITATION, MARKER, RATERS, RATING_FIELDS,
                             REFERENCE_FIELDS, SCENARIOS, VERSION, canonical, digest,
                             fixed_status, load_pack, read_csv, read_jsonl, source_hashes,
                             strict_json, validate_score_record)
from ml.study.outcome_adapter import derive_outcome

DATA_FILES = ("packages.jsonl", "expected_pc_levels.csv", "evidence_manifest.jsonl",
              "simulated_ratings.csv", "dataset_manifest.json")
PACKAGE_KEYS = {"package", "synthetic", "provenance", "scenario", "qp_code", "qp_version", "rubric_id",
                "rubric_status", "rubric_disclaimer", "generator", "worker_declaration", "task_references",
                "pc_expectations", "expected_outcome", "critical_violation_pcs", "omitted_evidence_task", "scenario_description"}
EVIDENCE_KEYS = {"package", "task", "evidence_id", "fixture_reference", "media_kind", "media_available",
                 "evidence_availability", "reviewability_status", "scenario_availability", "scenario_reviewability",
                 "quality_warning_scenario", "expected_evidence_status_by_pc", "synthetic", "provenance"}
MANIFEST_KEYS = {"artifact_sha256", "clock_policy", "count", "generator_version", "media_policy", "provenance",
                 "qp_code", "qp_version", "reference_kind", "rubric_disclaimer", "rubric_id", "rubric_status",
                 "scenario_counts", "schema_version", "seed", "simulation", "source_sha256", "synthetic"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_regeneration(data, manifest):
    from ml.study.generate_demo_data import generate
    from ml.study.simulate_ratings import simulate
    with tempfile.TemporaryDirectory(prefix="parakh-d3-data-") as directory:
        target = Path(directory)
        generate(target, seed=manifest["seed"], count=manifest["count"])
        simulate(target / "expected_pc_levels.csv", seed=manifest["simulation"]["seed"],
                 policy=manifest["simulation"]["policy"])
        for name in DATA_FILES:
            require((data / name).read_bytes() == (target / name).read_bytes(), f"deterministic regeneration differs: {name}")


def validate(data=HERE / "data", *, out=None, check_reproducible=False):
    data = Path(data)
    manifest = strict_json((data / "dataset_manifest.json").read_text(encoding="utf-8"))
    pack = load_pack()
    catalog, tasks = pack["catalog"], pack["tasks"]["tasks"]
    require(set(manifest) == MANIFEST_KEYS, "manifest schema mismatch")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            manifest["generator_version"] == VERSION, "unknown schema/generator version")
    require(manifest["synthetic"] is True and manifest["provenance"] == MARKER and
            manifest["reference_kind"] == "synthetic_reference", "synthetic provenance missing")
    require(type(manifest["seed"]) is int and type(manifest["count"]) is int and
            manifest["count"] > 0 and manifest["count"] % 4 == 0, "invalid seed/count")
    require(manifest["source_sha256"] == source_hashes(), "source provenance hash mismatch")
    expected_artifacts = set(DATA_FILES) - {"dataset_manifest.json"}
    require(set(manifest["artifact_sha256"]) == expected_artifacts, "artifact manifest incomplete or has unexpected paths")
    for name, sha in manifest["artifact_sha256"].items():
        require(sha == digest(data / name), f"artifact hash mismatch: {name}")
    simulation = manifest["simulation"]
    from ml.study.simulate_ratings import POLICY
    require(simulation["parameters"] == POLICY and simulation["policy"] in ("baseline", "identical") and
            simulation["raters"] == list(RATERS) and simulation["conditions"] == list(CONDITIONS) and
            type(simulation["seed"]) is int, "invalid simulation contract")
    for key, actual in (("qp_code", pack["qp"]["qp_code"]), ("qp_version", pack["qp"]["version"]),
                        ("rubric_id", pack["rubric"]["rubric_id"]), ("rubric_status", pack["rubric"]["status"]),
                        ("rubric_disclaimer", pack["rubric"]["rules"]["disclaimer"])):
        require(manifest[key] == actual, f"manifest {key} drift")
    packages = read_jsonl(data / "packages.jsonl")
    evidence = read_jsonl(data / "evidence_manifest.jsonl")
    references = read_csv(data / "expected_pc_levels.csv", reference=True)
    ratings = read_csv(data / "simulated_ratings.csv")
    require(all(set(r) == set(REFERENCE_FIELDS) for r in references), "reference CSV schema mismatch")
    require(all(set(r) == set(RATING_FIELDS) for r in ratings), "rating CSV schema mismatch")
    package_ids = {f"SIM-{i + 1:03d}" for i in range(manifest["count"])}
    require(len(packages) == len(package_ids) and {p["package"] for p in packages} == package_ids,
            "package count/identities invalid")
    scenario_counts = Counter(p["scenario"] for p in packages)
    require(scenario_counts == Counter({s: manifest["count"] // 4 for s in SCENARIOS}) and
            dict(scenario_counts) == manifest["scenario_counts"], "scenario distribution invalid")
    package_by_id = {p["package"]: p for p in packages}
    reference_by_key = {(r["package"], r["pc"]): r for r in references}
    require(set(reference_by_key) == {(p, pc) for p in package_ids for pc in catalog}, "missing or unknown reference PC/package")
    for row in references:
        item = catalog[row["pc"]]
        for key in ("nos", "task", "marks", "evidence_pathway", "mvp_applicability"):
            require(row[key] == (item[key] if item[key] is not None else ""), f"reference pack metadata drift: {row['pc']} {key}")
        require(row["critical"] == str(item["critical"]).lower(), "critical flag drift")
        require(row["anchors_json"] == canonical(item["anchors"]), "anchor drift")
        require(row["reference_kind"] == "synthetic_reference" and row["synthetic"] == "true", "reference provenance missing")
        require(row["scenario"] == package_by_id[row["package"]]["scenario"], "reference scenario mismatch")
        ambiguity = float(row["ambiguity"])
        require(math.isfinite(ambiguity) and 0 <= ambiguity <= 1, "invalid ambiguity")
        fixed = fixed_status(item)
        require(row["evidence_status"] == fixed if fixed else row["evidence_status"] in ("DEMONSTRATED", "NOT_OBSERVABLE"),
                "invalid reference applicability/status")
    task_by_id = {t["id"]: t for t in tasks}
    evidence_by_id = {e["evidence_id"]: e for e in evidence}
    require(len(evidence_by_id) == len(evidence) == len(packages) * len(tasks), "duplicate/missing evidence records")
    for package in packages:
        pid = package["package"]
        require(set(package) == PACKAGE_KEYS and package["synthetic"] is True and package["provenance"] == MARKER,
                "package schema/provenance mismatch")
        for key in ("qp_code", "qp_version", "rubric_id", "rubric_status", "rubric_disclaimer"):
            require(package[key] == manifest[key], f"package {key} drift")
        require(package["generator"] == {"version": VERSION, "seed": manifest["seed"]}, "package generator drift")
        require(package["scenario_description"] == "Fictional assessment record; no electrical work or recording occurred.",
                "invalid synthetic scenario description")
        declaration = package["worker_declaration"]
        require(set(declaration) == {"synthetic", "statement", "scenario_profile", "variant"} and
                declaration["synthetic"] is True and declaration["scenario_profile"] == package["scenario"] and
                declaration["statement"] == "Fictional worker declaration for software testing only." and
                type(declaration["variant"]) is int and 1 <= declaration["variant"] <= manifest["count"] // 4,
                "invalid synthetic declaration")
        refs = package["task_references"]
        require(len(refs) == len(tasks) and {t["task"] for t in refs} == set(task_by_id), "missing/unknown task reference")
        rows = [reference_by_key[pid, pc] for pc in catalog]
        expected = [{"pc": r["pc"], "evidence_status": r["evidence_status"],
                     "scenario_expected_level": r["level"], "critical": r["critical"] == "true"} for r in rows]
        for pc in package["pc_expectations"]:
            require(set(pc) == {"pc", "evidence_status", "scenario_expected_level", "critical"} and
                    type(pc["critical"]) is bool, "invalid package PC schema")
            validate_score_record({"evidence_status": pc["evidence_status"], "level": pc["scenario_expected_level"]})
        require(package["pc_expectations"] == expected, "package/reference values differ")
        outcome = derive_outcome(rows, pack)
        require(package["expected_outcome"] == outcome.outcome and package["critical_violation_pcs"] == outcome.critical_violation_pc_ids,
                "outcome disagrees with production engine")
        if package["scenario"] == "major_faults":
            require(bool(outcome.critical_violation_pc_ids), "major scenario lacks critical failure")
        if package["scenario"] == "incomplete_evidence":
            require(package["omitted_evidence_task"] in task_by_id and
                    any(r["evidence_status"] == "NOT_OBSERVABLE" for r in rows), "incomplete scenario lacks missing evidence")
        else:
            require(package["omitted_evidence_task"] is None, "unexpected omitted task")
        for task_ref in refs:
            task = task_by_id[task_ref["task"]]
            eid = f"{pid}-{task['id']}-META"
            fixture = f"synthetic-fixture://{VERSION}/{pid}/{task['id']}"
            require(task_ref == {"task": task["id"], "title": task["title"], "nos": task["nos"],
                                 "evidence_metadata_refs": [eid], "fixture_reference": fixture}, "task reference metadata mismatch")
            require(eid in evidence_by_id, "missing evidence metadata reference")
            e = evidence_by_id[eid]
            require(set(e) == EVIDENCE_KEYS and e["package"] == pid and e["task"] == task["id"] and
                    e["fixture_reference"] == fixture, "evidence schema/identity mismatch")
            require(e["synthetic"] is True and e["provenance"] == MARKER and e["media_available"] is False and
                    e["evidence_availability"] == "METADATA_ONLY" and e["reviewability_status"] == "NO_MEDIA_TO_REVIEW" and
                    e["media_kind"] in ("photo", "video"), "metadata-only evidence misrepresented")
            task_rows = [r for r in rows if r["task"] == task["id"]]
            missing = any(r["evidence_status"] == "NOT_OBSERVABLE" for r in task_rows)
            omitted = package["omitted_evidence_task"] == task["id"]
            require(e["expected_evidence_status_by_pc"] == {r["pc"]: r["evidence_status"] for r in task_rows}, "evidence status relationship mismatch")
            require(e["scenario_availability"] == ("OMITTED" if omitted else "PRESENT_IN_FICTION") and
                    e["scenario_reviewability"] == ("MISSING" if omitted else "UNCLEAR" if missing else "CLEAR") and
                    e["quality_warning_scenario"] == ("OMITTED_EVIDENCE" if omitted else "UNCLEAR_VIEW" if missing else None),
                    "inconsistent fictional evidence quality")
            if omitted:
                require(all(r["evidence_status"] in ("NOT_OBSERVABLE", "NOT_APPLICABLE_IN_MVP") for r in task_rows),
                        "omitted evidence was scored")
    expected_rating_keys = {(p, pc, r, c) for p in package_ids for pc in catalog for r in RATERS for c in CONDITIONS}
    require({(r["package"], r["pc"], r["rater"], r["condition"]) for r in ratings} == expected_rating_keys,
            "missing/unknown rating identity or rater")
    for row in ratings:
        reference = reference_by_key[row["package"], row["pc"]]
        require(all(row[k] == reference[k] for k in ("nos", "task", "scenario")), "rating metadata mismatch")
        require(row["synthetic"] == "true" and row["policy"] == simulation["policy"] and
                row["simulation_seed"] == str(simulation["seed"]), "rating simulation provenance mismatch")
        if reference["evidence_status"] != "DEMONSTRATED":
            require(row["evidence_status"] == reference["evidence_status"] and row["level"] is None, "unscored reference became scored")
        else:
            require(row["evidence_status"] in ("DEMONSTRATED", "NOT_OBSERVABLE"), "invalid rater status decision")
    if check_reproducible:
        check_regeneration(data, manifest)
    counts = {
        "packages": len(packages), "distinct_tasks": len(tasks), "task_references": len(packages) * len(tasks),
        "distinct_pcs": len(catalog), "task_linked_pcs": len(pack["rubric"]["items"]),
        "reference_rows": len(references), "reference_status_counts": dict(sorted(Counter(r["evidence_status"] for r in references).items())),
        "reference_level_distribution": dict(sorted(Counter(r["level"] for r in references if r["level"] is not None).items())),
        "raters": len(RATERS), "conditions": len(CONDITIONS), "rating_records": len(ratings),
        "rating_status_counts": dict(sorted(Counter(r["evidence_status"] for r in ratings).items())),
        "rating_level_distribution": {c: dict(sorted(Counter(r["level"] for r in ratings if r["condition"] == c and r["level"] is not None).items())) for c in CONDITIONS},
        "scenarios": dict(scenario_counts), "critical_pcs": sum(i["critical"] for i in catalog.values()),
        "critical_violation_packages": [p["package"] for p in packages if p["critical_violation_pcs"]],
        "unobservable_critical_reference_rows": sum(r["critical"] == "true" and r["evidence_status"] == "NOT_OBSERVABLE" for r in references),
        "safety_evidence_omitted_packages": [p["package"] for p in packages if p["omitted_evidence_task"] == tasks[0]["id"]],
        "expected_outcome_distribution": dict(sorted(Counter(p["expected_outcome"] for p in packages).items())),
    }
    if out:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# D3 synthetic dataset validation", "", f"**{LIMITATION}**", "",
                 manifest["rubric_disclaimer"], f"Rubric status: {manifest['rubric_status']}.", "",
                 "Validation: **PASS** (strict schemas, complete identities, source/artifact hashes, pinned anchors/marks, evidence semantics and production outcomes).", "",
                 "Reproducibility: **PASS — byte-identical regeneration of every dataset artifact**." if check_reproducible else "Reproducibility: NOT RUN in this invocation.", "",
                 f"Generator `{VERSION}`, seed {manifest['seed']}; simulation `{simulation['policy']}`, seed {simulation['seed']}.",
                 f"QP {manifest['qp_code']} v{manifest['qp_version']}; rubric `{manifest['rubric_id']}`.", "",
                 "## Counts and missing data", "", "```json", json.dumps(counts, indent=2, sort_keys=True), "```", "",
                 "All 119 QP PCs are represented per package: 71 task-linked (one fixed not-applicable), plus 48 declaration/notes only. Each declaration-only row has blank task, marks and level, and empty anchors. The 70 assessable PCs can be demonstrated or not observable. Blank CSV levels and JSON null values are never level 0. A demonstrated zero represents an observed deficient scenario outcome.", "",
                 "There is exactly one metadata-only fixture reference per package/task; no media file exists. `media_available=false` and `NO_MEDIA_TO_REVIEW` apply throughout. Fictional availability/reviewability fields are scenario inputs, never capture/upload/signature verification results. No private Q2/Q3 media is accessed.", "",
                 "## Source and artifact SHA-256", "", "```json", json.dumps({"source_sha256": manifest["source_sha256"], "artifact_sha256": manifest["artifact_sha256"]}, indent=2, sort_keys=True), "```", "",
                 "Source version is the explicit generator version plus the recorded content hashes, independent of checkout directory, clock and Git commit. Hashes refer to actual committed-pack and generated text files, never nonexistent media.", "",
                 "## Boundaries", "", "Synthetic reference values are controlled scenario expectations, not expert gold. No real assessor study, physical assessment collection, P10 device benchmark or offline product demonstration was performed by this pipeline. Original physical D3/D5 requirements remain unfulfilled. The draft rubric still requires trade-expert sign-off. P10 may reuse these fixtures only with the synthetic provenance visible.", ""]
        out.write_text("\n".join(lines), encoding="utf-8")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--out", type=Path, default=HERE / "reports/dataset_validation.md")
    parser.add_argument("--check-reproducible", action="store_true")
    args = parser.parse_args()
    try:
        counts = validate(args.data_dir, out=args.out, check_reproducible=args.check_reproducible)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"dataset validation failed: {exc}\n")
    print(f"PASS {MARKER}: {counts['packages']} packages, {counts['rating_records']} ratings")


if __name__ == "__main__":
    main()
