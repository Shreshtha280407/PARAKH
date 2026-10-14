#!/usr/bin/env python3
"""Validate and export direct visual review, never infer quality truth from folders/scores."""
import csv
import json
from pathlib import Path
from protocol import REPO, digest


def main():
    root = REPO / 'ml/quality/data'
    raw = [json.loads(x) for x in (root / 'manifest.jsonl').read_text().splitlines()]
    unique = {}
    for row in raw:
        old = unique.get(row['sha256'])
        if old is None or (old['folder_hand_label'] == 'not_labelled' and row['folder_hand_label'] != 'not_labelled'):
            unique[row['sha256']] = row
    by_id = {r['id']: r for r in unique.values()}
    rows = []
    for kind, filename, key in [('photo', 'photo_visual_review.json', 'photos'), ('video', 'video_visual_review.json', 'videos')]:
        review = json.loads((root / filename).read_text())
        if review['manifest_sha256'] != digest(root / 'manifest.jsonl'):
            raise ValueError('Review manifest changed; preserve/version the review')
        for entry in review[key]:
            source = by_id[entry['id']]
            if source['kind'] != kind or source['sha256'] != entry['sha256'] or source['folder_quality_label'] != entry['original_quality_label']:
                raise ValueError('Review identity/type/original category mismatch')
            if not entry['provenance'] or not entry['review_note']:
                raise ValueError('Independent review provenance is required')
            labels = set(entry['verified_quality_labels'])
            if not labels <= {'DARK', 'OVEREXPOSED', 'BLURRY', 'CAMERA_MOTION'}:
                raise ValueError('Unsupported quality label')
            if entry['review_status'] == 'verified':
                if not isinstance(entry['bad_capture'], bool) or entry['bad_capture'] != bool(labels):
                    raise ValueError('Reviewed defect labels and bad-capture truth disagree')
            elif entry['review_status'] != 'unjudgeable' or entry['bad_capture'] != 'unjudgeable':
                raise ValueError('Invalid unknown review state')
            rows.append({**entry, 'kind': kind})
    if len(rows) != len(by_id) or {r['id'] for r in rows} != set(by_id):
        raise ValueError('Every unique capture needs exactly one review, including ambiguous captures')
    fields = ['id', 'sha256', 'kind', 'original_quality_label', 'verified_quality_labels', 'unjudgeable_conditions',
              'review_status', 'bad_capture', 'provenance', 'review_note']
    with (root / 'labels.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for row in rows:
            output = {k: row[k] for k in fields}
            for k in ('verified_quality_labels', 'unjudgeable_conditions'):
                output[k] = '|'.join(row[k])
            output['bad_capture'] = str(row['bad_capture']).lower()
            writer.writerow(output)
    print(f'Validated/exported {len(rows)} unique reviewed captures; ambiguous truth retained')


if __name__ == '__main__':
    main()
