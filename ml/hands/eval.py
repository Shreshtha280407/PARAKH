#!/usr/bin/env python3
"""Actual Android predictions versus independently reviewed timestamps on frozen splits."""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assistance'))
from protocol import REPO, confusion, digest, load_protocol, partition_ids, read_results


def gap_filled(samples, interval):
    """Mirrors Kotlin HandSmoothing.gapFilled exactly: an ANALYSED/no-hand sample is treated as
    present only when both immediate interval-spaced neighbours were ANALYSED/present. Never
    fills a failed/unjudgeable (None) sample or across one. Returns {timestamp_ms: bool|None}."""
    raw = {s['timestamp_ms']: (s['hand_present'] if s['state'] == 'ANALYSED' else None) for s in samples}
    if len(raw) < 2:
        return raw
    return {t: (v if v is not False else (True if raw.get(t - interval) is True and raw.get(t + interval) is True else v))
            for t, v in raw.items()}


def verify_gap_filled_aggregation(record, interval):
    filled = gap_filled(record['samples'], interval)
    valid = [v for v in filled.values() if v is not None]
    expected_ratio = sum(valid) / len(valid) if valid else None
    actual_ratio = record.get('visible_ratio_gap_filled')
    if (expected_ratio is None) != (actual_ratio is None) or (expected_ratio is not None and abs(expected_ratio - actual_ratio) > 1e-9):
        raise ValueError('Actual Android gap-filled visible-ratio aggregation parity failed')
    cells = []
    for s in record['samples']:
        t = s['timestamp_ms']
        if filled.get(t) is not False:
            continue
        start, end = t, min(t + interval, record['duration_ms'])
        if cells and cells[-1]['end_ms'] == start:
            cells[-1]['end_ms'] = end
        else:
            cells.append({'start_ms': start, 'end_ms': end})
    if cells != record.get('hands_not_visible_intervals_gap_filled'):
        raise ValueError('Actual Android gap-filled absence-interval aggregation parity failed')


def verify_aggregation(record, interval):
    samples = record['samples']
    valid = [s for s in samples if s['state'] == 'ANALYSED']
    expected_ratio = sum(s['hand_present'] for s in valid) / len(valid) if valid else None
    if (expected_ratio is None) != (record['visible_ratio'] is None) or (expected_ratio is not None and abs(expected_ratio - record['visible_ratio']) > 1e-12):
        raise ValueError('Actual Android visible-ratio aggregation parity failed')
    cells = []
    for s in samples:
        if s['state'] != 'ANALYSED' or s['hand_present'] is not False:
            continue
        start, end = s['timestamp_ms'], min(s['timestamp_ms'] + interval, record['duration_ms'])
        if cells and cells[-1]['end_ms'] == start:
            cells[-1]['end_ms'] = end
        else:
            cells.append({'start_ms': start, 'end_ms': end})
    if cells != record['hands_not_visible_intervals']:
        raise ValueError('Actual Android absence-interval aggregation parity failed')


def transition_metrics(truth, predictions, interval):
    expected, observed = [], []
    times = sorted(truth)
    for a, b in zip(times, times[1:]):
        if b - a != interval or truth[a] == 'unjudgeable' or truth[b] == 'unjudgeable':
            continue
        if truth[a] != truth[b]:
            expected.append((b, truth[b]))
        left, right = predictions.get(a), predictions.get(b)
        if left and right and left['state'] == right['state'] == 'ANALYSED' and left['hand_present'] != right['hand_present']:
            observed.append((b, 'present' if right['hand_present'] else 'absent'))
    unmatched = set(range(len(expected))); errors = []
    for time, direction in observed:
        candidates = [i for i in unmatched if expected[i][1] == direction and abs(expected[i][0] - time) <= interval]
        if candidates:
            chosen = min(candidates, key=lambda i: (abs(expected[i][0] - time), i)); unmatched.remove(chosen)
            errors.append(abs(expected[chosen][0] - time))
    return {'manual_transitions': len(expected), 'predicted_transitions_in_judgeable_adjacent_cells': len(observed),
        'matched_within_one_sampling_step': len(errors), 'unmatched_manual_transitions': len(unmatched),
        'unmatched_predicted_transitions': len(observed) - len(errors), 'tolerance_ms': interval,
        'matched_boundary_mean_absolute_error_ms': statistics.mean(errors) if errors else None,
        'boundary_definition': 'first sampled state after change; true continuous boundary lies in prior/current sample bracket; clip edges are not observed transitions'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path); p.add_argument('--android-results', type=Path, required=True)
    p.add_argument('--partition', choices=['development', 'proxy', 'calibration', 'validation', 'heldout'], required=True)
    p.add_argument('--manifest', type=Path, default=REPO / 'ml/quality/data/manifest.jsonl')
    p.add_argument('--hand-labels', type=Path, default=REPO / 'ml/hands/data/sample_labels.csv')
    p.add_argument('--model-manifest', type=Path, default=REPO / 'apps/android/assist-hands/src/main/assets/hands/model.json')
    p.add_argument('--smoothing', choices=['raw', 'gap_filled'], default='raw',
        help='gap_filled reinterprets an isolated ANALYSED/no-hand sample bracketed by ANALYSED/present '
             'neighbours as present (never fills a failed/unjudgeable sample); raw is the original per-sample value')
    p.add_argument('--out', type=Path, required=True); args = p.parse_args()
    if args.out.exists():
        raise ValueError('Preserve previous evaluation; choose a new report version')
    if args.partition == 'development':
        if args.protocol:
            raise ValueError('Development review is separate from frozen acceptance partitions')
        rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
        unique = {}
        for row in rows:
            old = unique.get(row['sha256'])
            if old is None or (old['folder_hand_label'] == 'not_labelled' and row['folder_hand_label'] != 'not_labelled'):
                unique[row['sha256']] = row
        manifest = {r['id']: r for r in unique.values()}
        selected = {i for i, r in manifest.items() if r['kind'] == 'video'}
        labels_path = args.hand_labels
        protocol_hash = None
        protocol = {'version': 'development-only-unfrozen-not-acceptance'}
    else:
        if not args.protocol:
            raise ValueError('Acceptance partitions require the frozen grouped protocol')
        protocol, manifest, protocol_hash = load_protocol(args.protocol)
        selected = {i for i in partition_ids(protocol, args.partition) if manifest[i]['kind'] == 'video'}
        labels_path = REPO / protocol['hand_sample_labels']['path']
    model = json.loads(args.model_manifest.read_text())
    records = read_results(args.android_results, 'hands')
    if not selected <= records.keys():
        raise ValueError('Missing requested clip predictions; no silent denominator change')
    with labels_path.open(newline='') as f:
        truth_rows = [r for r in csv.DictReader(f) if r['id'] in selected]
    truth = {}
    for row in truth_rows:
        key = (row['id'], int(row['timestamp_ms']))
        if key in truth or row['sha256'] != manifest[row['id']]['sha256']:
            raise ValueError('Duplicate or mismatched hand truth')
        truth[key] = row['reviewed_hand_presence']
    pairs = []; clips = []; excluded = 0; missing = 0; predicted_valid = 0; unlabelled = []; android_requested = 0
    for identity in sorted(selected):
        record = records[identity]
        if record['model_sha256'] != model['sha256'] or record['configuration_sha256'] != digest(args.model_manifest):
            raise ValueError('Actual Android model/configuration differs from evaluated release')
        predictions = {s['timestamp_ms']: s for s in record['samples']}
        android_requested += len(record['samples'])
        if len(predictions) != len(record['samples']):
            raise ValueError('Duplicate inference timestamps')
        verify_aggregation(record, model['sample_interval_ms'])
        smoothed = gap_filled(record['samples'], model['sample_interval_ms']) if args.smoothing == 'gap_filled' else None
        if smoothed is not None:
            verify_gap_filled_aggregation(record, model['sample_interval_ms'])
        reviewed_times = {time for i, time in truth if i == identity}
        for time in sorted(set(predictions) - reviewed_times):
            unlabelled.append({'id': identity, 'timestamp_ms': time, 'reference_duration_ms': manifest[identity]['duration_ms'],
                'android_duration_ms': record['duration_ms'], 'reason': 'outside independently reviewed timestamp grid; no truth invented'})
        clip_pairs = []; true_visible = []; predicted_visible = []; matched_truth = []; intersection = union = 0
        for time in range(0, manifest[identity]['duration_ms'], model['sample_interval_ms']):
            label = truth.get((identity, time))
            if label is None:
                raise ValueError('Missing independently reviewed timestamp label')
            if label == 'unjudgeable':
                excluded += 1; continue
            if label not in ('present', 'absent'):
                raise ValueError('Unknown hand truth status')
            sample = predictions.get(time)
            prediction = smoothed.get(time) if smoothed is not None else (sample['hand_present'] if sample and sample['state'] == 'ANALYSED' else None)
            if prediction is None:
                missing += 1
            else:
                predicted_valid += 1
            target = label == 'present'
            clip_pairs.append((target, prediction)); pairs.append((target, prediction)); true_visible.append(target)
            if prediction is not None:
                predicted_visible.append(prediction)
                matched_truth.append(target)
                # 1s cells; failed/unknown cells excluded from interval comparison, never invented absent.
                cell_ms = min(model['sample_interval_ms'], manifest[identity]['duration_ms'] - time)
                intersection += cell_ms * int(not target and not prediction); union += cell_ms * int(not target or not prediction)
        correct = sum(prediction is not None and target == prediction for target, prediction in clip_pairs)
        denominator = len(clip_pairs)
        clips.append({'id': identity, 'judgeable_samples': denominator, 'agreement': correct / denominator if denominator else None,
            'actual_android_visible_ratio_all_analysable_samples': record['visible_ratio'],
            'aggregation_parity': 'PASS',
            'transitions': transition_metrics({t: v for (i, t), v in truth.items() if i == identity}, predictions, model['sample_interval_ms']),
            'manual_visible_ratio': statistics.mean(true_visible) if true_visible else None,
            'predicted_visible_ratio_on_matched_valid_cells': statistics.mean(predicted_visible) if predicted_visible else None,
            'manual_visible_ratio_on_matched_valid_cells': statistics.mean(matched_truth) if matched_truth else None,
            'visible_ratio_absolute_error_on_matched_valid_cells': abs(statistics.mean(predicted_visible) - statistics.mean(matched_truth)) if matched_truth else None,
            'absence_cell_iou_on_matched_valid_cells': intersection / union if union else None,
            'absence_interval_tolerance_ms': model['sample_interval_ms'],
            'analysed_sample_coverage': sum(p is not None for _, p in clip_pairs) / denominator if denominator else 0})
    result = confusion(pairs); matrix = result['confusion']; total = len(pairs)
    agreement = (matrix['tp'] + matrix['tn']) / total if total else None
    specificity_denominator = matrix['tn'] + matrix['fp'] + matrix['unavailable_negative']
    report = {'partition': args.partition, 'smoothing': args.smoothing, 'protocol_version': protocol['version'], 'protocol_sha256': protocol_hash,
        'android_results_sha256': digest(args.android_results), 'configuration_sha256': digest(args.model_manifest),
        'hand_labels_sha256': digest(labels_path),
        'model_sha256': model['sha256'], 'unique_clips': len(selected), 'judgeable_timestamp_samples': total,
        'requested_android_timestamp_samples': android_requested, 'independently_reviewed_timestamp_samples': len(truth),
        'unlabelled_android_timestamp_samples': len(unlabelled), 'unlabelled_samples': unlabelled,
        'judgeable_truth_coverage_over_android_requested': total / android_requested if android_requested else 0,
        'judgeable_fraction_of_reviewed_truth': total / len(truth) if truth else 0,
        'excluded_unjudgeable_truth_samples': excluded, 'failed_or_missing_predictions_on_judgeable_truth': missing,
        'analysable_prediction_coverage_on_judgeable_truth': predicted_valid / total if total else 0,
        'confusion': matrix, 'agreement': agreement, 'sensitivity': result['recall'],
        'specificity': matrix['tn'] / specificity_denominator if specificity_denominator else None,
        'clip_mean_agreement': statistics.mean([r['agreement'] for r in clips if r['agreement'] is not None]) if clips else None,
        'clips': clips, 'hands_numeric_gate': ('NOT_APPLICABLE: proxy/development data is not held-out acceptance' if args.partition in ('proxy', 'development')
            else 'PASS' if (agreement or 0) >= 0.90 else 'FAIL'),
        'limits': 'Frames within a clip/session are correlated. Clip count is not inflated by samples. Proxy coverage and one held-out session do not establish broad device/trade performance. Sampled intervals have up to one sampling-step boundary uncertainty.'}
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('partition', 'unique_clips', 'judgeable_timestamp_samples', 'agreement', 'sensitivity', 'specificity', 'hands_numeric_gate')}, indent=2))


if __name__ == '__main__':
    main()
