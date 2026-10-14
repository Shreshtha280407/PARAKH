#!/usr/bin/env python3
"""Verify metrics on actual Android-decoded/exported grayscale, plus Kotlin threshold parity."""
import argparse
import json
import sys
from pathlib import Path
from reference import assert_metrics, image_metrics
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assistance'))
from protocol import REPO, capture_flags, digest


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--results', type=Path, required=True)
    p.add_argument('--gray-dir', type=Path, required=True)
    p.add_argument('--thresholds', type=Path, default=REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json')
    args = p.parse_args()
    rows = [json.loads(x) for x in args.results.read_text().splitlines()]
    run = next(r for r in rows if r.get('type') == 'run')
    profile = json.loads(args.thresholds.read_text()); checked = 0; threshold_records = 0
    for row in rows:
        if row.get('module') != 'quality':
            continue
        if row['threshold_sha256'] != digest(args.thresholds):
            raise ValueError('Exports use a different threshold/profile version')
        if row['duration_ms'] is None and row['samples'] and row['samples'][0]['metrics']:
            m = row['samples'][0]['metrics']
            raw = (args.gray_dir / f"{run['run_id']}-{row['id']}.gray").read_bytes()
            assert_metrics(m, image_metrics(raw, m['width'], m['height'])); checked += 1
        expected = [flags for _, flags, _ in capture_flags(row, profile['thresholds'])]
        actual = [{f['condition'] for f in s['flags']} for s in row['samples']]
        if profile['calibration_status'] == 'calibrated':
            if expected != actual:
                raise ValueError('Actual Kotlin/reference threshold parity mismatch')
            threshold_records += 1
        elif any(actual):
            raise ValueError('Uncalibrated Android profile emitted quality advice')
    if not checked:
        raise ValueError('No actual Android photo exports to verify')
    print(json.dumps({'android_photo_gray_metric_parity_passed': checked,
        'calibrated_kotlin_reference_threshold_records': threshold_records,
        'calibration_status': profile['calibration_status'],
        'limits': 'Gray-export parity verifies calculations on Android preprocessing. EXIF/rotation/resize are separately instrumented. No held-out accuracy implied.'}, indent=2))


if __name__ == '__main__':
    main()
