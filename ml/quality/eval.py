#!/usr/bin/env python3
"""Evaluate actual Android quality exports on one frozen partition, proving threshold parity."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assistance'))
from protocol import REPO, capture_flags, confusion, digest, load_protocol, partition_ids, quality_labels, read_results, technical_prediction


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, required=True); p.add_argument('--android-results', type=Path, required=True)
    p.add_argument('--thresholds', type=Path, default=REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json')
    p.add_argument('--partition', choices=['proxy', 'validation', 'heldout'], required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise ValueError('Preserve previous evaluation; choose a new report version')
    protocol, manifest, split_hash = load_protocol(args.protocol)
    profile = json.loads(args.thresholds.read_text())
    if profile['calibration_status'] != 'calibrated' or profile['split_sha256'] != split_hash:
        raise ValueError('Calibrated profile must reference these exact frozen splits')
    records = read_results(args.android_results, 'quality'); labels = quality_labels(protocol)
    identities = set(partition_ids(protocol, args.partition))
    required = {i for i in identities if labels[i]['review_status'] == 'verified'}
    if not required <= records.keys():
        raise ValueError('Missing requested Android results; no silent dropping from holdout')
    clip_fraction = profile.get('clip_bad_fraction', protocol['quality_clip_bad_fraction'])
    aggregation = profile.get('aggregation')
    min_consecutive_anchors = {'DARK': aggregation['dark_min_consecutive_anchors'],
        'BLURRY': aggregation['blurry_min_consecutive_anchors']} if aggregation else None
    excluded_conditions = (set() if aggregation.get('camera_motion_counts_toward_bad_capture') else {'CAMERA_MOTION'}) if aggregation else None
    pairs, details = [], []
    for identity in sorted(required):
        record = records[identity]
        if record['threshold_sha256'] != digest(args.thresholds) or not record['threshold_calibrated']:
            raise ValueError('Android did not execute the exact calibrated threshold profile')
        expected = capture_flags(record, profile['thresholds'])
        actual = [{flag['condition'] for flag in sample['flags']} for sample in record['samples']]
        if actual != [flags for _, flags, _ in expected]:
            raise ValueError('Kotlin/reference threshold flag parity failed')
        truth = labels[identity]['bad_capture'] == 'true'
        prediction = technical_prediction(record, profile['thresholds'], clip_fraction, None,
            min_consecutive_anchors, excluded_conditions)
        pairs.append((truth, prediction))
        details.append({'id': identity, 'kind': manifest[identity]['kind'], 'original_category': manifest[identity]['folder_quality_label'],
            'truth': truth, 'prediction': prediction, 'verified_conditions': labels[identity]['verified_quality_labels'],
            'motion_analysed_pairs': record['motion_analysed_pairs'], 'motion_requested_pairs': record['motion_requested_pairs']})
    aggregate = confusion(pairs)
    report = {'partition': args.partition, 'protocol_version': protocol['version'], 'protocol_sha256': split_hash,
        'android_results_sha256': digest(args.android_results), 'threshold_sha256': digest(args.thresholds),
        'unique_captures': len(required), 'unjudgeable_or_unreviewed_captures': len(identities - required),
        'aggregate': aggregate,
        'by_kind': {kind: confusion([(r['truth'], r['prediction']) for r in details if r['kind'] == kind]) for kind in ('photo', 'video')},
        'by_original_category': {category: confusion([(r['truth'], r['prediction']) for r in details if r['original_category'] == category])
            for category in sorted({r['original_category'] for r in details})},
        'by_verified_condition': {condition: confusion([
            (condition in labels[i]['verified_quality_labels'].split('|'),
             technical_prediction(records[i], profile['thresholds'], protocol['quality_clip_bad_fraction'], condition))
            for i in sorted(required) if condition not in labels[i].get('unjudgeable_conditions', '').split('|')
            and (condition != 'CAMERA_MOTION' or manifest[i]['kind'] == 'video')])
            for condition in ('DARK', 'BLURRY', 'CAMERA_MOTION')},
        'semantic_framing': 'unsupported, outside owner-approved revised scope; original categories retained',
        'capture_weighting': 'one photo or unique clip is one capture; aggregate is descriptive, not independent extracted frames',
        'limits': 'Proxy data, small sample and correlated scene/session coverage; no trade or entry/mid-device acceptance inferred',
        'details': details,
        'quality_numeric_gate': ('NOT_APPLICABLE: owner-approved proxy functional scope; no independent heldout claim' if args.partition == 'proxy'
            else 'PASS' if (aggregate['precision'] or 0) >= 0.85 and (aggregate['recall'] or 0) >= 0.80 else 'FAIL')}
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('partition', 'unique_captures', 'aggregate', 'quality_numeric_gate')}, indent=2))


if __name__ == '__main__':
    main()
