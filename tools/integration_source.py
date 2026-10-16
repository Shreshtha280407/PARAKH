#!/usr/bin/env python3
"""Non-secret source stamp for the production assistance integration APK."""
import argparse
import hashlib
import json
from pathlib import Path

from assistance_source import source_version

ROOT = Path(__file__).resolve().parents[1]


def render():
    digest = hashlib.sha256()
    roots = ["apps/android/app/src", "apps/android/core/seal/src", "server/app", "server/alembic", "apps/dashboard/src", "contracts"]
    files = [p for r in roots for p in (ROOT / r).rglob("*") if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts]
    files += [ROOT / p for p in ["apps/android/app/build.gradle.kts", "apps/android/app/proguard-rules.pro", "apps/dashboard/package.json", "tools/integration_source.py"]]
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {"source_version": source_version(), "integration_source_sha256": digest.hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(render(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    else:
        print(result, end="")
