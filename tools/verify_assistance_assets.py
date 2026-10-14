#!/usr/bin/env python3
"""Validate bundled assistance provenance/configuration, optionally APK packaging and acceptance readiness."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL = REPO / 'apps/android/assist-hands/src/main/assets/hands'
QUALITY = REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json'


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--require-calibrated', action='store_true')
    p.add_argument('--apk', type=Path, action='append', default=[]); args = p.parse_args()
    metadata = json.loads((MODEL / 'model.json').read_text())
    asset = MODEL / 'hand_landmarker.task'
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert digest == metadata['sha256'] and asset.stat().st_size == metadata['bytes']
    assert metadata['origin'] == 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
    assert metadata['license'] == 'Apache-2.0' and 'Apache License' in (MODEL / 'LICENSE.txt').read_text()
    assert metadata['dependency'] in (REPO / 'apps/android/assist-hands/build.gradle.kts').read_text()
    assert metadata['delegate'] == 'CPU' and metadata['num_hands'] == 2 and metadata['sample_interval_ms'] in (500, 1000)
    assert all(0 <= metadata[k] <= 1 for k in ('min_detection_confidence', 'min_presence_confidence', 'min_tracking_confidence'))
    with zipfile.ZipFile(asset) as z:
        assert set(z.namelist()) == {'hand_detector.tflite', 'hand_landmarks_detector.tflite'}
        assert all(z.getinfo(name).file_size > 100_000 for name in z.namelist())
    profile = json.loads(QUALITY.read_text())
    assert profile['metric_definition'] == 'luma77-150-29-laplacian4-interior-population-v1'
    assert profile['motion_definition'] == 'tile9-centered-mad-translation-radius4-patch12-neighbour1-v2'
    assert profile['longest_edge_px'] == 320
    t = profile['thresholds']
    assert 0 <= t['mean_dark_below'] <= t['mean_bright_above'] <= 255
    assert 0 <= t['highlight_fraction_above'] <= 1 and t['laplacian_variance_below'] >= 0 and t['video_laplacian_variance_below'] >= 0
    assert 0 < t['motion_translation_px_at_least'] <= 6
    for apk in args.apk:
        with zipfile.ZipFile(apk) as z:
            packaged = z.read('assets/hands/hand_landmarker.task')
            assert hashlib.sha256(packaged).hexdigest() == digest
            assert z.getinfo('assets/hands/hand_landmarker.task').compress_type == zipfile.ZIP_STORED
            assert z.read('assets/hands/model.json') == (MODEL / 'model.json').read_bytes()
            assert z.read('assets/quality/thresholds.json') == QUALITY.read_bytes()
            stamp = json.loads(z.read('assets/assistance-source.json'))
            assert '+assistance-tree-sha256:' in stamp['source_version']
        print(f'{apk.name}: bundled model/profile/source stamp valid; APK={apk.stat().st_size} bytes')
    print('Official model origin/hash, licence evidence, pinned dependency and config structure validated')
    if profile['calibration_status'] != 'calibrated':
        print('Q2 calibration: BLOCKED; development profile cannot produce accepted quality advice')
        if args.require_calibrated:
            raise SystemExit(1)
    elif args.require_calibrated:
        assert profile['split_sha256'] and profile['dataset_manifest_sha256'] and profile['calibration_provenance']
        sys.path.insert(0, str(REPO / 'ml/assistance'))
        from protocol import load_protocol, quality_labels
        protocol, _, protocol_hash = load_protocol(REPO / 'ml/quality/data/splits.json')
        quality_labels(protocol)
        assert protocol_hash == profile['split_sha256']
        assert protocol['manifest']['sha256'] == profile['dataset_manifest_sha256']
        assert hashlib.sha256((REPO / 'ml/hands/data/splits.json').read_bytes()).hexdigest() == protocol_hash
        assert (REPO / 'ml/quality/calibration' / (profile['version'] + '.json')).read_bytes() == QUALITY.read_bytes()
        assert profile['calibration_provenance']['calibration_code_sha256'] == hashlib.sha256((REPO / 'ml/quality/tune.py').read_bytes()).hexdigest()
        calibration_root = REPO / 'ml/quality/calibration'
        assert profile['calibration_provenance']['android_results_sha256'] == hashlib.sha256((calibration_root / (profile['version'] + '-android-metrics.jsonl')).read_bytes()).hexdigest()
        assert profile['calibration_provenance']['metrics_profile_sha256'] == hashlib.sha256((calibration_root / (profile['version'] + '-metrics-profile.json')).read_bytes()).hexdigest()
        amendment = protocol.get('owner_scope_amendment')
        if amendment:
            assert hashlib.sha256((REPO / amendment['path']).read_bytes()).hexdigest() == amendment['sha256']
        print('Frozen label/manifest/protocol hashes match the calibrated profile; proxy reuse is not held-out acceptance')


if __name__ == '__main__':
    main()
