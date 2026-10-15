#!/usr/bin/env python3
"""Freeze reviewed grouped assignments only after class/session coverage and leakage checks."""
import argparse
import csv
import datetime
import json
import tempfile
from pathlib import Path
from protocol import REPO, digest, load_protocol, quality_labels


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True); p.add_argument('--quality-labels', type=Path, required=True)
    p.add_argument('--hand-sample-labels', type=Path, required=True); p.add_argument('--assignments', type=Path, required=True)
    p.add_argument('--near-duplicates', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--version', required=True); p.add_argument('--clip-bad-fraction', type=float, default=0.2)
    p.add_argument('--design', choices=['independent_grouped', 'owner_approved_proxy_resubstitution'], default='independent_grouped')
    p.add_argument('--owner-scope-amendment', type=Path)
    args = p.parse_args()
    if args.out.exists():
        raise ValueError('Never overwrite a frozen split; version the full protocol if justified')
    if args.design == 'owner_approved_proxy_resubstitution' and not args.owner_scope_amendment:
        raise ValueError('Explicit documented owner scope is required for proxy-only calibration/evaluation')
    manifest = [json.loads(x) for x in args.manifest.read_text().splitlines()]
    by_id = {r['id']: r for r in manifest}
    with args.assignments.open(newline='') as f:
        assignments = list(csv.DictReader(f))
    if len(assignments) != len({r['id'] for r in assignments}):
        raise ValueError('Duplicate assignment rows')
    partitions = {key: [] for key in ('calibration', 'validation', 'heldout')}
    groups = {}
    hash_partition = {}
    for row in assignments:
        if not row.get('group') or not row.get('provenance') or row['partition'] not in partitions:
            raise ValueError('Every capture needs explicit conservative group and grouping provenance')
        partitions[row['partition']].append(row['id']); groups[row['id']] = row['group']
        digest_value = by_id[row['id']]['sha256']
        if digest_value in hash_partition:
            raise ValueError('A duplicate/derivative was assigned independently')
        hash_partition[digest_value] = row['partition']
    for candidate in json.loads(args.near_duplicates.read_text()):
        a = hash_partition[by_id[candidate['a']]['sha256']]; b = hash_partition[by_id[candidate['b']]['sha256']]
        if a != b:
            raise ValueError('Unresolved near-duplicate candidate crosses partitions; visually adjudicate before freezing')
    with args.quality_labels.open(newline='') as f:
        quality_rows = list(csv.DictReader(f))
    quality = {r['id']: r for r in quality_rows}
    with args.hand_sample_labels.open(newline='') as f:
        hands = list(csv.DictReader(f))
    for split, identities in partitions.items():
        if not identities:
            if args.design == 'owner_approved_proxy_resubstitution' and split in ('validation', 'heldout'):
                continue
            raise ValueError('Three independent partitions are required; request missing captures before freezing')
        if args.design == 'owner_approved_proxy_resubstitution' and split != 'calibration':
            raise ValueError('Owner-approved proxy design keeps all captures in calibration, with no holdout claim')
        for kind in ('photo', 'video'):
            available = [quality[i] for i in identities if by_id[i]['kind'] == kind and quality[i]['review_status'] == 'verified']
            if {r['bad_capture'] for r in available} != {'true', 'false'}:
                raise ValueError(f'{split}/{kind} lacks independently reviewed good and bad technical evidence')
            conditions = {v for r in available for v in r['verified_quality_labels'].split('|') if v}
            needed = {'DARK', 'BLURRY'} | ({'CAMERA_MOTION'} if kind == 'video' else set())
            if not needed <= conditions:
                raise ValueError(f'{split}/{kind} lacks required condition coverage: {needed - conditions}')
        class_values = {r['reviewed_hand_presence'] for r in hands if r['id'] in identities} - {'unjudgeable'}
        if class_values != {'present', 'absent'}:
            raise ValueError(f'{split} lacks both independent hand classes')
    def source(path):
        return {'path': path.resolve().relative_to(REPO).as_posix(), 'sha256': digest(path)}
    value = {'version': args.version, 'state': 'frozen', 'frozen_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'evaluation_design': args.design,
        'owner_scope_amendment': source(args.owner_scope_amendment) if args.owner_scope_amendment else None,
        'manifest': source(args.manifest), 'quality_labels': source(args.quality_labels), 'hand_sample_labels': source(args.hand_sample_labels),
        'assignments': source(args.assignments), 'near_duplicate_candidates': source(args.near_duplicates),
        'quality_clip_bad_fraction': args.clip_bad_fraction, 'partitions': partitions, 'groups': groups,
        'original_collection_ids': [r['id'] for r in assignments if r['group'] == 'drive-proxy-original-collection'],
        'scope': 'owner-approved technical Q2; semantic target framing unsupported',
        'selection_policy': 'grouped reviewed coverage; one partition per scene/session/duplicate group; no tuning or reshuffling against final holdout'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True) + '\n'
    with tempfile.NamedTemporaryFile('w', dir=args.out.parent, prefix='.protocol-check-', suffix='.json', delete=False) as f:
        f.write(content); temporary = Path(f.name)
    try:
        checked, _, _ = load_protocol(temporary)
        quality_labels(checked)
        with args.out.open('x') as f:
            f.write(content)
    finally:
        temporary.unlink()
    print('Frozen:', args.out, digest(args.out), {key: len(v) for key, v in partitions.items()})


if __name__ == '__main__':
    main()
