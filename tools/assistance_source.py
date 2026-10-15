#!/usr/bin/env python3
"""Non-secret, reproducible source identity for assistance APKs and device reports."""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def source_files():
    roots = [REPO / 'apps/android/assist-quality', REPO / 'apps/android/assist-hands', REPO / 'apps/android/assist-benchmark',
             REPO / 'ml/assistance', REPO / 'ml/quality', REPO / 'ml/hands']
    # Dataset/review/protocol/evaluation hashes are recorded separately. Generated reports
    # must not change executable-source identity, otherwise recording a run would itself
    # make the tested source appear stale. Bundled model/config/threshold assets are included.
    files = [p for root in roots for p in root.rglob('*') if p.is_file() and not p.is_symlink() and
             not any(x in p.parts for x in ('build', '__pycache__', '.gradle')) and p.suffix != '.md' and
             not (root.is_relative_to(REPO / 'ml') and p.relative_to(root).parts[0] in ('data', 'reports', 'calibration'))]
    files += [REPO / p for p in ('apps/android/settings.gradle.kts', 'apps/android/build.gradle.kts',
        'apps/android/gradle/libs.versions.toml', 'tools/assistance_source.py', 'tools/assistance_device.py')]
    return sorted(files)


def source_version():
    digest = hashlib.sha256()
    for p in source_files():
        digest.update(p.relative_to(REPO).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(p.read_bytes()).digest())
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    return base + '+assistance-tree-sha256:' + digest.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path)
    parser.add_argument('--snapshot-dir', type=Path); args = parser.parse_args()
    value = source_version()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'source_version': value}, indent=2) + '\n')
    else:
        print(value)
    if args.snapshot_dir:
        if args.snapshot_dir.resolve().is_relative_to(REPO):
            raise ValueError('Source snapshots must remain outside Git')
        args.snapshot_dir.mkdir(parents=True, exist_ok=True)
        files = source_files()
        with (args.snapshot_dir / 'source-files.json').open('x') as f:
            json.dump({'source_version': value, 'files': {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}, f, indent=2)
            f.write('\n')
        with tarfile.open(args.snapshot_dir / 'assistance-sources.tar.gz', 'x:gz') as archive:
            for p in files:
                archive.add(p, arcname=p.relative_to(REPO).as_posix(), recursive=False)
