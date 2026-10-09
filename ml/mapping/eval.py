#!/usr/bin/env python3
"""Run the CON/Q0602 declaration matcher against a labelled declaration set
and report agreement with the recorded expected_match labels.

Usage: python ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set ml/mapping/data/labelled_60.jsonl

P1 exit test only requires the first 20 labelled declarations to run without
errors (no exceptions / no malformed record). The >= 90% full-set agreement
gate against all 60 is at IC-1 (2026-10-17), once thresholds.json has been
tuned on real worker declarations -- see labelled_60.jsonl's header comment
for why this fixture is currently synthetic.

--mode harness (default) requires every record in --set to carry
"harness_marker": "HARNESS_ONLY_NOT_FIELD_VALIDATION" and always prints a
synthetic-data banner; it will never claim an IC-1 gate result. --mode field
requires the OPPOSITE -- zero records may carry that marker -- and is the
only mode allowed to report an IC-1 gate PASS/FAIL. Mixing the two, or
asking for --mode field against a harness-marked file (or vice versa),
refuses to run. This makes "launder synthetic data as field validation" a
hard error instead of a copy-paste mistake.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from matcher import load_rules, match  # noqa: E402

HARNESS_MARKER = "HARNESS_ONLY_NOT_FIELD_VALIDATION"
IC1_GATE = 0.90


def load_declarations(path: Path):
    records = []
    with path.open() as f:
        for lineno, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON — {e}") from e
    return records


def agreement(records, predictions):
    n = len(records)
    hits = sum(1 for r, p in zip(records, predictions) if r.get("expected_match") == p["match_result"])
    return hits, n


def check_marker_consistency(records, mode: str, dataset: Path):
    marked = [r.get("id", "?") for r in records if r.get("harness_marker") == HARNESS_MARKER]
    unmarked = [r.get("id", "?") for r in records if r.get("harness_marker") != HARNESS_MARKER]

    if mode == "harness":
        if unmarked:
            print(f"REFUSING TO RUN: --mode harness requires every record in {dataset} to carry "
                  f"\"harness_marker\": \"{HARNESS_MARKER}\". {len(unmarked)} record(s) do not: "
                  f"{', '.join(unmarked[:10])}{' ...' if len(unmarked) > 10 else ''}")
            print("If this is real field-collected, expert-labelled data, re-run with --mode field.")
            sys.exit(1)
    elif mode == "field":
        if marked:
            print(f"REFUSING TO RUN: --mode field requires NO record in {dataset} to carry the "
                  f"\"{HARNESS_MARKER}\" marker — {len(marked)} record(s) do: "
                  f"{', '.join(marked[:10])}{' ...' if len(marked) > 10 else ''}.")
            print("This dataset contains harness-only synthetic declarations and cannot be used "
                  "to claim IC-1 field-validation agreement. Re-run with --mode harness, or use a "
                  "real field-collected dataset with no harness_marker field at all.")
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True, type=Path, help="mapping/ directory")
    ap.add_argument("--set", required=True, type=Path, dest="dataset", help="labelled declarations .jsonl")
    ap.add_argument("--mode", choices=["harness", "field"], default="harness",
                     help="harness (default): synthetic smoke-test data only, never claims the IC-1 gate. "
                          "field: real field-collected data only, may report IC-1 PASS/FAIL.")
    args = ap.parse_args()

    rules = load_rules(args.rules)
    records = load_declarations(args.dataset)
    check_marker_consistency(records, args.mode, args.dataset)

    print(f"loaded {len(records)} labelled declarations from {args.dataset}  [mode={args.mode}]")
    if args.mode == "harness":
        print("=" * 72)
        print(f"  {HARNESS_MARKER}")
        print("  This is synthetic smoke-test data. Numbers below are a code-correctness")
        print("  check only -- NOT field validation, NOT an IC-1 expert-agreement result,")
        print("  and must never be reported as either. See ml/mapping/data/README.md.")
        print("=" * 72)

    predictions = []
    errors = []
    for i, rec in enumerate(records):
        try:
            predictions.append(match(rec, rules))
        except Exception as e:  # noqa: BLE001 — surfaced as a P1-gate failure either way
            errors.append((i, rec.get("id", f"#{i}"), repr(e)))
            predictions.append({"match_result": None})

    first20 = records[:20], predictions[:20]
    hits20, n20 = agreement(*first20)
    hits_all, n_all = agreement(records, predictions)

    if args.mode == "harness":
        print(f"match-agreement (first 20 labelled declarations): {hits20 / n20:.3f} ({hits20}/{n20}) "
              f"[harness smoke test, not a gate]")
        print(f"match-agreement (all {n_all}, informational only — harness data, not field data): "
              f"{hits_all / n_all:.3f} ({hits_all}/{n_all})")
        print(f"The real IC-1 gate (>= {IC1_GATE:.0%} agreement) can only be evaluated with "
              f"--mode field against real field-collected, expert-labelled declarations.")
    else:
        rate = hits_all / n_all if n_all else 0.0
        verdict = "PASS" if rate >= IC1_GATE else "FAIL"
        print(f"match-agreement (all {n_all}, field-validated data): {rate:.3f} ({hits_all}/{n_all})")
        print(f"IC-1 gate (>= {IC1_GATE:.0%}): {verdict}")

    if errors:
        print(f"{len(errors)} error(s):")
        for i, rec_id, err in errors:
            print(f"  record {i} ({rec_id}): {err}")
        sys.exit(1)

    print(f"0 errors across {len(records)} declarations")


if __name__ == "__main__":
    main()
