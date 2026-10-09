#!/usr/bin/env python3
"""Export the FastAPI app's OpenAPI schema to contracts/openapi.json.

Deterministic: sorted keys, fixed indentation, trailing newline -- so two
runs against the same code produce a byte-identical file and `git diff`
(or CI's freshness check, see .github/workflows/ci.yml) shows real API
changes only, never reordering noise.

Usage: python tools/export_openapi.py [--check]
  --check: exit 1 if contracts/openapi.json would change (CI uses this
           instead of overwriting the committed file).
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server.app.main import app  # noqa: E402

OUT_PATH = REPO_ROOT / "contracts" / "openapi.json"


def render() -> str:
    schema = app.openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed file is stale, don't write")
    args = ap.parse_args()

    rendered = render()

    if args.check:
        if not OUT_PATH.exists():
            print(f"{OUT_PATH} does not exist -- run without --check to generate it")
            sys.exit(1)
        current = OUT_PATH.read_text()
        if current != rendered:
            print(f"{OUT_PATH} is stale -- run `python tools/export_openapi.py` and commit the result")
            sys.exit(1)
        print(f"{OUT_PATH} is up to date")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(rendered)
    print(f"wrote {OUT_PATH} ({len(rendered)} bytes)")


if __name__ == "__main__":
    main()
