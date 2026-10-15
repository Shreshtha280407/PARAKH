#!/usr/bin/env python3
"""Report the v3 clip-aggregation policy's effect on the frozen calibration partition.

This is NOT an Android/reference parity report: it does not require (and cannot claim) a
device execution of the literal v3 asset file, because v3 changes only the clip-level
aggregation policy, not any per-frame metric/threshold value Android computes. Per-frame
DARK/BLURRY/CAMERA_MOTION thresholds are byte-identical to v2, whose Android/reference
parity is already verified (preserved, unchanged evidence). Re-verifying literal on-device
execution of the v3 asset requires a connected device and is explicitly NOT VERIFIED here.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assistance'))
from protocol import REPO, capture_flags, confusion, digest, load_protocol, quality_labels, read_results, technical_prediction


def main():
    protocol_path = REPO / 'ml/quality/data/splits.json'
    android_results_path = REPO / 'ml/quality/calibration/quality-proxy-v2-android-metrics.jsonl'
    thresholds_path = REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json'
    out_path = REPO / 'ml/quality/reports/quality-proxy-v3-calibration.json'
    if out_path.exists():
        raise ValueError('Preserve previous evaluation; choose a new report version')

    protocol, manifest, split_hash = load_protocol(protocol_path)
    profile = json.loads(thresholds_path.read_text())
    if profile['calibration_status'] != 'calibrated' or profile['split_sha256'] != split_hash:
        raise ValueError('Calibrated profile must reference these exact frozen splits')
    records = read_results(android_results_path, 'quality')
    labels = quality_labels(protocol)
    required = set(protocol['partitions']['calibration'])
    required = {i for i in required if labels[i]['review_status'] == 'verified'}

    clip_fraction = profile['clip_bad_fraction']
    aggregation = profile['aggregation']
    min_run = {'DARK': aggregation['dark_min_consecutive_anchors'], 'BLURRY': aggregation['blurry_min_consecutive_anchors']}
    excluded = set() if aggregation['camera_motion_counts_toward_bad_capture'] else {'CAMERA_MOTION'}

    pairs, details = [], []
    for identity in sorted(required):
        record = records[identity]
        truth = labels[identity]['bad_capture'] == 'true'
        prediction = technical_prediction(record, profile['thresholds'], clip_fraction, None, min_run, excluded)
        pairs.append((truth, prediction))
        details.append({'id': identity, 'kind': manifest[identity]['kind'], 'original_category': manifest[identity]['folder_quality_label'],
            'truth': truth, 'prediction': prediction, 'verified_conditions': labels[identity]['verified_quality_labels'],
            'motion_analysed_pairs': record['motion_analysed_pairs'], 'motion_requested_pairs': record['motion_requested_pairs']})
    aggregate = confusion(pairs)
    report = {
        'report_kind': 'calibration_only_resubstitution_NOT_android_reference_parity',
        'parity_status': 'NOT_VERIFIED: requires a connected device executing the literal quality-proxy-v3 asset; '
            'per-frame DARK/BLURRY/CAMERA_MOTION thresholds are byte-identical to the already-parity-verified v2 '
            'asset, only the clip aggregation policy changed (pure post-processing over already-verified per-sample flags)',
        'partition': 'proxy', 'protocol_version': protocol['version'], 'protocol_sha256': split_hash,
        'android_results_sha256': digest(android_results_path), 'threshold_sha256': digest(thresholds_path),
        'unique_captures': len(required),
        'aggregate': aggregate,
        'by_kind': {kind: confusion([(r['truth'], r['prediction']) for r in details if r['kind'] == kind]) for kind in ('photo', 'video')},
        'by_original_category': {category: confusion([(r['truth'], r['prediction']) for r in details if r['original_category'] == category])
            for category in sorted({r['original_category'] for r in details})},
        'aggregation_policy': aggregation,
        'clip_bad_fraction': clip_fraction,
        'semantic_framing': 'unsupported, outside owner-approved revised scope; original categories retained',
        'limits': 'Proxy data, small sample and correlated scene/session coverage; no trade or entry/mid-device acceptance inferred. '
            'Aggregation policy fitted on this same calibration set (resubstitution), not an independent holdout.',
        'details': details,
        'quality_numeric_gate': 'PASS' if (aggregate['precision'] or 0) >= 0.85 and (aggregate['recall'] or 0) >= 0.80 else 'FAIL',
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'unique_captures': len(required), 'aggregate': aggregate,
        'by_kind': report['by_kind'], 'quality_numeric_gate': report['quality_numeric_gate']}, indent=2))


if __name__ == '__main__':
    main()
