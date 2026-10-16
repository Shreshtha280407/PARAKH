#!/usr/bin/env python3
"""Simulated raters: baseline has no programmed condition effect; identical is a control."""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.study.common import (BASE_FIELDS, CONDITIONS, HERE, MARKER, RATERS, RATING_FIELDS,
                             digest, read_csv, write_csv, write_json)

POLICY = {
    "baseline": "Same parameters in both conditions; independent condition-specific draws; no assistance effect.",
    "identical": "Same parameters and random draws in both conditions; zero-difference control.",
    "severity": dict(zip(RATERS, [-0.18, 0.0, 0.18])),
    "one_step_probability": "0.10 + 0.38 * ambiguity; multiply by 0.55 on critical PCs",
    "large_disagreement_probability": "0.04 conditional on a scoring perturbation",
    "unobservable_decision_probability": "0.035 * ambiguity on demonstrated PCs only",
    "missing_policy": "Reference NOT_OBSERVABLE, declaration-only and fixed not-applicable stay unscored.",
    "leakage_boundary": "Simulator consumes scenario levels to create controlled errors; analysis never corrects ratings using references.",
}


def simulate(reference=HERE / "data/expected_pc_levels.csv", out=None, *, seed=42, policy="baseline"):
    if policy not in ("baseline", "identical"):
        raise ValueError("unknown simulation policy")
    reference = Path(reference)
    out = Path(out) if out else reference.with_name("simulated_ratings.csv")
    records = read_csv(reference, reference=True)
    rows = []
    for record in sorted(records, key=lambda r: (r["package"], r["pc"])):
        ambiguity = float(record["ambiguity"])
        if not 0 <= ambiguity <= 1:
            raise ValueError("ambiguity must be in [0, 1]")
        for condition in CONDITIONS:
            for rater in RATERS:
                condition_key = condition if policy == "baseline" else "shared"
                key = f"{seed}|{record['package']}|{record['pc']}|{rater}|{condition_key}"
                rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(), "big"))
                row = {field: record[field] for field in BASE_FIELDS}
                if record["evidence_status"] == "DEMONSTRATED":
                    if rng.random() < 0.035 * ambiguity:
                        row["evidence_status"], row["level"] = "NOT_OBSERVABLE", None
                    else:
                        probability = (0.10 + 0.38 * ambiguity) * (0.55 if record["critical"] == "true" else 1)
                        if rng.random() < probability:
                            direction = 1 if rng.random() < 0.5 + POLICY["severity"][rater] else -1
                            delta = 2 if rng.random() < 0.04 else 1
                            row["level"] = max(0, min(3, row["level"] + direction * delta))
                row.update(rater=rater, condition=condition, simulation_seed=seed,
                           policy=policy, synthetic="true")
                rows.append(row)
    write_csv(out, rows, RATING_FIELDS)
    manifest_path = reference.with_name("dataset_manifest.json")
    if manifest_path.exists() and out.parent.resolve() == reference.parent.resolve() and out.name == "simulated_ratings.csv":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["simulation"] = {"seed": seed, "policy": policy, "parameters": POLICY,
                                  "raters": list(RATERS), "conditions": list(CONDITIONS)}
        manifest["artifact_sha256"][out.name] = digest(out)
        write_json(manifest_path, manifest)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=HERE / "data/expected_pc_levels.csv")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--policy", choices=("baseline", "identical"), default="baseline")
    args = parser.parse_args()
    rows = simulate(args.reference, args.out, seed=args.seed, policy=args.policy)
    print(f"{MARKER}: {len(rows)} simulated rating records ({args.policy})")


if __name__ == "__main__":
    main()
