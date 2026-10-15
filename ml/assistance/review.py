#!/usr/bin/env python3
"""Build private timestamp contact sheets, without model predictions or metric scores."""
import argparse
import io
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=Path('ml/quality/data/manifest.jsonl'))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    unique = {}
    for row in rows:
        old = unique.get(row['sha256'])
        if old is None or old['folder_hand_label'] == 'not_labelled':
            unique[row['sha256']] = row
    output = args.dataset_root / 'review' / 'timelines'
    output.mkdir(parents=True, exist_ok=True)
    index = []
    for number, row in enumerate(r for r in unique.values() if r['kind'] == 'video'):
        timestamps = list(range(0, row['duration_ms'], 1000))
        record = {'id': row['id'], 'sha256': row['sha256'], 'relative_path': row['relative_path'],
                  'original_hand_label': row['folder_hand_label'], 'timestamps_ms': timestamps,
                  'decoder': 'ffmpeg accurate input seek; requested timestamps; nearest decoded frame',
                  'review_pages': [], 'failed_decode_timestamps_ms': []}
        for page in range(0, len(timestamps), 12):
            times = timestamps[page:page + 12]
            canvas = Image.new('RGB', (4 * 330, ((len(times) + 3) // 4) * 278), 'white')
            draw = ImageDraw.Draw(canvas)
            for i, time_ms in enumerate(times):
                x, y = (i % 4) * 330, (i // 4) * 278
                result = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(time_ms / 1000),
                    '-i', str(args.dataset_root / 'originals' / row['relative_path']), '-frames:v', '1',
                    '-vf', 'scale=320:240:force_original_aspect_ratio=decrease',
                    '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'], capture_output=True, timeout=60)
                if result.returncode != 0 or not result.stdout:
                    record['failed_decode_timestamps_ms'].append(time_ms)
                    draw.text((x + 8, y + 80), 'REVIEW DECODE UNAVAILABLE', fill='black')
                else:
                    with Image.open(io.BytesIO(result.stdout)) as im:
                        canvas.paste(im, (x, y))
                draw.text((x + 2, y + 242), f"{row['id']} {time_ms}ms", fill='black')
                draw.text((x + 2, y + 258), row['folder_hand_label'], fill='black')
            filename = f"{number:02d}-{row['id']}-{page // 12}.jpg"
            canvas.save(output / filename, quality=90)
            record['review_pages'].append(filename)
        index.append(record)
        (output / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
        print(f"{number:02d} {row['id']} {len(timestamps)} samples", flush=True)
    (output / 'index.json').write_text(json.dumps(index, indent=2) + '\n')


if __name__ == '__main__':
    main()
