#!/usr/bin/env python3
"""Score a documented 20-capture P8 field run without upgrading reused calibration data.

Each JSONL row: captureId, expected (bad/good), newUnseen (bool),
labelledBeforeAnalysis (bool), productCapture (bool), deviceModel,
androidVersion, runId, sourceRevision, assistance (the real signed snapshot).
No media or worker details are read or copied. Pending/failed inference is
NOT VERIFIED for that capture, never interpreted as a negative prediction.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.app.assistance import AssistanceSnapshot


def evaluate(rows):
    if len(rows) != 20 or sum(r.get("expected") == "bad" for r in rows) != 10 or sum(r.get("expected") == "good" for r in rows) != 10:
        raise ValueError("exactly ten independently labelled bad and ten good captures required")
    if len({r["captureId"] for r in rows}) != 20:
        raise ValueError("capture IDs must be unique")
    snapshots = [AssistanceSnapshot.model_validate(r["assistance"]) for r in rows]
    if len({s.mediaSha256 for s in snapshots}) != 20:
        raise ValueError("twenty byte-distinct captures required; scene independence still needs manual review")
    results = []
    for row, snapshot in zip(rows, snapshots):
        eligible = all(row.get(k) is True for k in ("newUnseen", "labelledBeforeAnalysis", "productCapture")) and all(
            isinstance(row.get(k), str) and row[k] for k in ("deviceModel", "androidVersion", "runId", "sourceRevision"))
        analysed = snapshot.status in ("COMPLETED", "PARTIAL")
        # This counts what the actual worker UI warns about, including disclosed raw
        # quality intervals and gap-filled hand observations, not a cherry-picked metric.
        warned = bool(snapshot.flags) if analysed else None
        results.append({"captureId": row["captureId"], "expected": row["expected"], "warned": warned,
                        "status": snapshot.status, "eligibleFieldCapture": eligible,
                        "deviceModel": row.get("deviceModel"), "sourceRevision": row.get("sourceRevision"),
                        "correct": None if warned is None else warned == (row["expected"] == "bad")})
    bad = [r for r in results if r["expected"] == "bad"]
    good = [r for r in results if r["expected"] == "good"]
    eligible = all(r["eligibleFieldCapture"] and r["warned"] is not None for r in results)
    bad_count = sum(r["warned"] is True for r in bad)
    good_false = sum(r["warned"] is True for r in good)
    return {"badCaptures": {"correctlyFlagged": bad_count, "total": 10, "required": ">=8", "verdict": ("PASS" if bad_count >= 8 else "FAIL") if eligible else "NOT VERIFIED"},
            "goodCaptures": {"falseWarnings": good_false, "total": 10, "required": "<=1", "verdict": ("PASS" if good_false <= 1 else "FAIL") if eligible else "NOT VERIFIED"},
            "captures": results, "independentFieldRunEligible": eligible,
            "limits": "Self-reported capture/run provenance requires independent review. Reused/calibration or unfinished captures cannot pass field acceptance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate([json.loads(line) for line in args.captures.read_text().splitlines() if line.strip()]) if args.captures else {
        "badCaptures": {"verdict": "NOT VERIFIED", "reason": "No new 10-bad field run supplied"},
        "goodCaptures": {"verdict": "NOT VERIFIED", "reason": "No new 10-good field run supplied"}, "captures": []}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "captures"}, indent=2))


if __name__ == "__main__":
    main()
