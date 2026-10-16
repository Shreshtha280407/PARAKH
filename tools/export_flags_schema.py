#!/usr/bin/env python3
"""Export the strict assistance shape; semantic/binding rules run in assistance.py."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.app.assistance import AssistanceSnapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema = AssistanceSnapshot.model_json_schema()
    schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:kaushalpramaan:assistance:1",
                   "description": "Signed on-device advisory snapshot. Cross-field intervals, coverage, status and evidence binding also require semantic validation; see docs/evidence_quality_result.md."})
    rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    path = ROOT / "contracts/flags.schema.json"
    if args.check:
        if not path.exists() or path.read_text() != rendered:
            raise SystemExit("flags.schema.json is stale; run tools/export_flags_schema.py")
        print("flags.schema.json is up to date")
    else:
        path.write_text(rendered)


if __name__ == "__main__":
    main()
