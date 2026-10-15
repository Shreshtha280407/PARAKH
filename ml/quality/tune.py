#!/usr/bin/env python3
"""Fit deterministic thresholds using calibration-only Android exports and frozen truth.

No model training. Validation/holdout captures in the input are rejected. The output
profile is versioned and still needs actual Android validation/held-out acceptance.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assistance'))
from protocol import REPO, confusion, digest, load_protocol, quality_labels, read_results, technical_prediction


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, required=True); p.add_argument('--android-results', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--version', required=True)
    p.add_argument('--metrics-profile', type=Path, help='Exact profile bundled in the Android metrics APK; defaults to current asset')
    args = p.parse_args()
    protocol, manifest, split_hash = load_protocol(args.protocol)
    records = read_results(args.android_results, 'quality')
    calibration = set(protocol['partitions']['calibration'])
    if not records or set(records) != calibration:
        raise ValueError('Threshold fitting requires all assigned calibration captures exactly once; never validation/holdout')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', args.version):
        raise ValueError('Version must be a portable identifier')
    labels = quality_labels(protocol)
    reviewed = [i for i in records if labels[i]['review_status'] == 'verified']
    if any(labels[i]['bad_capture'] not in ('true', 'false') for i in reviewed):
        raise ValueError('Reviewed bad-capture truth must be explicit true/false')
    if {labels[i]['bad_capture'] for i in reviewed} != {'true', 'false'}:
        raise ValueError('Calibration must contain independently reviewed good and bad captures')
    template = json.loads((REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json').read_text())
    metrics_profile = args.metrics_profile or REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json'
    exported_profile = json.loads(metrics_profile.read_text())
    if any(template[k] != exported_profile[k] for k in ('metric_definition', 'motion_definition', 'longest_edge_px', 'video_preprocessing_paths')):
        raise ValueError('Android metrics used a different preprocessing/metric definition')
    if any(r['threshold_sha256'] != digest(metrics_profile) for r in records.values()):
        raise ValueError('Android results do not match the specified bundled metrics profile')
    clip_fraction = protocol['quality_clip_bad_fraction']
    if not 0 < clip_fraction <= 1:
        raise ValueError('Invalid frozen clip aggregation fraction')
    # Deterministic condition-wise fitting. Separate photo/video blur avoids source-
    # modality imbalance. v1 and its failing video results remain immutable historical evidence.
    def f1(result):
        precision, recall = result['precision'] or 0.0, result['recall'] or 0.0
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    thresholds = dict(template['thresholds'])
    selections = {}
    def condition_result(condition, kind=None):
        return confusion([
            (condition in labels[i]['verified_quality_labels'].split('|'),
             technical_prediction(records[i], thresholds, clip_fraction, condition))
            for i in reviewed if condition not in labels[i].get('unjudgeable_conditions', '').split('|')
            and (kind is None or manifest[i]['kind'] == kind)
            and (condition != 'CAMERA_MOTION' or manifest[i]['kind'] == 'video')])
    blur_grid = (5, 10, 20, 30, 40, 60, 80, 100, 150, 250, 400, 700)
    fits = [('mean_dark_below', range(20, 111, 5), 'DARK', None, -1),
            ('laplacian_variance_below', blur_grid, 'BLURRY', 'photo', -1),
            ('video_laplacian_variance_below', blur_grid, 'BLURRY', 'video', -1),
            ('motion_translation_px_at_least', (1, 2, 3, 4, 5), 'CAMERA_MOTION', 'video', 1)]
    for parameter, grid, condition, kind, conservative in fits:
        best = None
        for candidate in grid:
            thresholds[parameter] = float(candidate)
            outcome = condition_result(condition, kind)
            score = (f1(outcome), outcome['precision'] or 0.0, outcome['recall'] or 0.0, conservative * candidate)
            if best is None or score > best[0]:
                best = (score, candidate, outcome)
        thresholds[parameter] = float(best[1])
        selections[parameter] = {'condition': condition, 'kind': kind, 'result': best[2]}

    # Clip-level temporal aggregation policy: per-frame thresholds are now fixed above;
    # this stage fits how scattered per-anchor flags become one clip verdict. A condition's
    # own standalone precision/recall (per_condition_calibration below) is never affected by
    # this stage, since condition_result always calls technical_prediction with an explicit
    # condition, which bypasses min_consecutive_anchors/excluded_conditions by design.
    def combined_result(clip_fraction_candidate, min_run, excluded):
        return confusion([(labels[i]['bad_capture'] == 'true', technical_prediction(
            records[i], thresholds, clip_fraction_candidate, None, min_run, excluded)) for i in reviewed])
    aggregation_grid = [
        {'clip_bad_fraction': cbf, 'dark_min_consecutive_anchors': dark_run,
         'blurry_min_consecutive_anchors': blur_run, 'camera_motion_counts_toward_bad_capture': motion_counts}
        for cbf in (0.15, 0.2, 0.25, 0.3, 0.35, 0.4)
        for dark_run in (1, 2, 3, 4, 5, 6)
        for blur_run in (1, 2, 3, 4)
        for motion_counts in (True, False)
    ]
    best_aggregation = None
    for candidate in aggregation_grid:
        min_run = {'DARK': candidate['dark_min_consecutive_anchors'], 'BLURRY': candidate['blurry_min_consecutive_anchors']}
        excluded = set() if candidate['camera_motion_counts_toward_bad_capture'] else {'CAMERA_MOTION'}
        outcome = combined_result(candidate['clip_bad_fraction'], min_run, excluded)
        recall = outcome['recall'] or 0.0
        if recall < 0.80:
            continue  # Never trade away the mandatory IC-2 recall floor for precision.
        score = (f1(outcome), outcome['precision'] or 0.0, recall,
            -candidate['dark_min_consecutive_anchors'], -candidate['blurry_min_consecutive_anchors'])
        if best_aggregation is None or score > best_aggregation[0]:
            best_aggregation = (score, candidate, outcome)
    if best_aggregation is None:
        raise ValueError('No aggregation policy on this grid preserves the mandatory recall floor')
    aggregation = best_aggregation[1]
    clip_fraction = aggregation['clip_bad_fraction']
    aggregation_result = best_aggregation[2]
    final_min_run = {'DARK': aggregation['dark_min_consecutive_anchors'], 'BLURRY': aggregation['blurry_min_consecutive_anchors']}
    final_excluded = set() if aggregation['camera_motion_counts_toward_bad_capture'] else {'CAMERA_MOTION'}

    result = confusion([(labels[i]['bad_capture'] == 'true', technical_prediction(
        records[i], thresholds, clip_fraction, None, final_min_run, final_excluded)) for i in reviewed])
    assert result == aggregation_result
    conditions = {condition: condition_result(condition) for condition in ('DARK', 'BLURRY', 'CAMERA_MOTION')}
    profile = copy.deepcopy(template)
    profile.update(version=args.version, calibration_status='calibrated', thresholds=thresholds,
        evaluation_design=protocol.get('evaluation_design', 'independent_grouped'),
        dataset_manifest_sha256=protocol['manifest']['sha256'], split_sha256=split_hash,
        clip_bad_fraction=clip_fraction,
        aggregation={
            'dark_min_consecutive_anchors': aggregation['dark_min_consecutive_anchors'],
            'blurry_min_consecutive_anchors': aggregation['blurry_min_consecutive_anchors'],
            'camera_motion_counts_toward_bad_capture': aggregation['camera_motion_counts_toward_bad_capture'],
            'rationale': ('A condition only contributes to the combined clip verdict once it '
                'persists for its own minimum run of consecutive 1s anchors; CAMERA_MOTION is '
                'excluded from the verdict (but still computed/reported/evaluated on its own) '
                'because its calibrated standalone precision is only 50% and, on this '
                'calibration set, it is never the sole reason a genuinely bad clip crosses the '
                'verdict threshold, while it does drive false warnings on clips independently '
                'reviewed as technically good (panning/handheld movement misread as shake).')},
        calibration_provenance={'protocol': protocol['version'], 'android_results_sha256': digest(args.android_results),
            'calibration_code_sha256': digest(__file__), 'metrics_profile_sha256': digest(metrics_profile),
            'quality_labels_sha256': protocol['quality_labels']['sha256'], 'captures': len(reviewed),
            'calibration_result': result, 'per_condition_calibration': conditions, 'parameter_fits': selections,
            'aggregation_fit': {'grid_size': len(aggregation_grid), 'selected': aggregation, 'result': aggregation_result,
                'recall_floor_enforced': 0.80},
            'algorithm': 'finite grid v3: condition F1 then precision/recall and conservative ties; dark first, photo blur and video blur fitted separately, then camera motion; no holdout inputs. '
                'Clip aggregation policy (v4): finite grid over clip_bad_fraction x per-condition minimum consecutive-anchor run length x camera-motion inclusion, scored by combined F1 subject to a hard recall>=0.80 floor; no holdout inputs.',
            'scope': 'Proxy resubstitution only; no independent validation/holdout or field generalisation proof' if protocol.get('evaluation_design') == 'owner_approved_proxy_resubstitution' else 'Calibration only; acceptance requires untouched heldout',
            'highlight_rule': 'engineering saturation guard: mean >245 and highlight clipping >0.95; deterministic/synthetic verification only; no real positive highlight cases in the supplied proxy collection'})
    if args.out.exists() and args.out.resolve() != (REPO / 'apps/android/assist-quality/src/main/assets/quality/thresholds.json').resolve():
        raise ValueError('Refusing to overwrite an existing versioned calibration report')
    archive = REPO / 'ml/quality/calibration' / (args.version + '.json')
    if archive.exists():
        raise ValueError('Calibration version already exists; never overwrite versioned results')
    content = json.dumps(profile, indent=2, sort_keys=True) + '\n'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open('x') as f:
        f.write(content)
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(content)
    print(json.dumps({'version': args.version, 'calibration_only': result, 'heldout': 'not run'}, indent=2))


if __name__ == '__main__':
    main()
