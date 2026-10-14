#!/usr/bin/env python3
"""Validate independent review and export original/corrected labels; never loads a model."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def canonical_rows(rows):
    unique = {}
    for row in rows:
        old = unique.get(row['sha256'])
        if old is None or (old['folder_hand_label'] == 'not_labelled' and row['folder_hand_label'] != 'not_labelled'):
            unique[row['sha256']] = row
    return list(unique.values())


def absence_intervals(times, states, duration):
    intervals = []
    for time, state in zip(times, states):
        if state != 'A':
            continue
        end = min(duration, time + 1000)
        if intervals and intervals[-1]['end_ms'] == time:
            intervals[-1]['end_ms'] = end
        else:
            intervals.append({'start_ms': time, 'end_ms': end})
    return intervals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('ml/quality/data/manifest.jsonl'))
    parser.add_argument('--review', type=Path, default=Path('ml/hands/data/visual_review.json'))
    parser.add_argument('--output', type=Path, default=Path('ml/hands/data'))
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    rows = [json.loads(x) for x in raw.decode().splitlines()]
    review = json.loads(args.review.read_text())
    if hashlib.sha256(raw).hexdigest() != review['manifest_sha256']:
        raise ValueError('Review is for another manifest')
    clips = [r for r in canonical_rows(rows) if r['kind'] == 'video']
    if set(review['clips']) != {r['id'] for r in clips}:
        raise ValueError('Review clip identities differ from canonical videos')
    samples, summaries, intervals = [], [], []
    for row in clips:
        annotation = review['clips'][row['id']]
        states = annotation['states']
        times = list(range(0, row['duration_ms'], 1000))
        if len(states) != len(times) or not set(states) <= set('PAU'):
            raise ValueError(f"Invalid timestamp review: {row['id']}")
        aliases = [r['id'] for r in rows if r['sha256'] == row['sha256']]
        original = row['folder_hand_label']
        for time, state in zip(times, states):
            corrected = {'P': 'present', 'A': 'absent', 'U': 'unjudgeable'}[state]
            samples.append({'id': row['id'], 'sha256': row['sha256'], 'timestamp_ms': time,
                'original_folder_hand_label': original, 'reviewed_hand_presence': corrected,
                'provenance': review['provenance'], 'reviewer': review['reviewer'], 'review_version': review['version']})
        count = collections.Counter(states)
        judgeable = count['P'] + count['A']
        summary = {'id': row['id'], 'sha256': row['sha256'], 'relative_path': row['relative_path'],
            'original_folder_hand_label': original, 'reviewed_clip_label': 'mixed' if count['P'] and count['A'] else
                'present_at_judgeable_samples' if count['P'] else 'absent_at_judgeable_samples' if count['A'] else 'unjudgeable',
            'present_samples': count['P'], 'absent_samples': count['A'], 'unjudgeable_samples': count['U'],
            'judgeable_visible_ratio': count['P'] / judgeable if judgeable else None,
            'judgeable_coverage': judgeable / len(states), 'review_provenance': review['provenance'],
            'reviewer': review['reviewer'], 'review_version': review['version'], 'note': annotation['note']}
        summaries.append(summary)
        transitions = [{'after_ms': times[i - 1], 'by_ms': times[i], 'from': states[i - 1], 'to': states[i]}
            for i in range(1, len(states)) if states[i] != states[i - 1] and states[i] != 'U' and states[i - 1] != 'U']
        intervals.append({**summary, 'alias_ids_same_bytes': aliases, 'duration_ms': row['duration_ms'],
            'samples': [{'timestamp_ms': t, 'label': {'P': 'present', 'A': 'absent', 'U': 'unjudgeable'}[s]} for t, s in zip(times, states)],
            'sampled_absence_intervals': absence_intervals(times, states, row['duration_ms']),
            'entry_exit_uncertainty_brackets': transitions, 'sampling_tolerance_ms': 1000,
            'interval_convention': 'left-anchored sampled cells; not continuously reviewed exact entry/exit times'})
    args.output.mkdir(parents=True, exist_ok=True)
    for name, records in [('sample_labels.csv', samples), ('labels.csv', summaries)]:
        with (args.output / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    (args.output / 'interval_labels.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in intervals))
    counts = collections.Counter(r['reviewed_hand_presence'] for r in samples)
    coverage = {'review_version': review['version'], 'review_sha256': hashlib.sha256(args.review.read_bytes()).hexdigest(),
        'manifest_sha256': review['manifest_sha256'], 'visually_reviewed_unique_clips': len(clips),
        'timestamp_samples': len(samples), 'class_counts': dict(counts),
        'judgeable_coverage': (counts['present'] + counts['absent']) / len(samples),
        'clips_with_present_samples': sum(r['present_samples'] > 0 for r in summaries),
        'clips_with_absent_samples': sum(r['absent_samples'] > 0 for r in summaries),
        'all_absent_clips': [r['id'] for r in summaries if r['absent_samples'] and not r['present_samples']],
        'original_not_visible_clips_with_present_samples': [r['id'] for r in summaries
            if r['original_folder_hand_label'] == 'hands_not_visible' and r['present_samples'] > 0],
        'evaluation': 'not performed; these are ground-truth counts, not prediction agreement',
        'split_status': 'not frozen; original collection reserved for development/calibration pending two owner-supplied independent sets'}
    (args.output / 'label_audit.json').write_text(json.dumps(coverage, indent=2) + '\n')
    print(json.dumps(coverage, indent=2))


if __name__ == '__main__':
    main()
