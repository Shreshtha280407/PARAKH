#!/usr/bin/env python3
"""Regenerate small privacy-safe metric fixtures (never private dataset derivatives)."""
import argparse
import base64
import random
from pathlib import Path
from reference import image_metrics


def contents() -> str:
    rng = random.Random(20423)
    fixtures = [('tiny', 1, 2, bytes([0, 255])), ('constant', 9, 7, bytes([120] * 63)),
                ('clipping', 4, 4, bytes([0, 16, 17, 235, 234, 255, 150, 1] * 2))]
    for i in range(12):
        width, height = 5 + i, 4 + i
        fixtures.append((f'random-{i}', width, height, bytes(rng.randrange(256) for _ in range(width * height))))
    fixtures.append(('gradient', 12, 10, bytes(x * 15 + y * 3 for y in range(10) for x in range(12))))
    lines = ['id\twidth\theight\tgray_base64\tmean_luma\tdark_fraction\thighlight_fraction\tlaplacian_variance']
    for name, w, h, values in fixtures:
        metrics = image_metrics(values, w, h)
        lines.append('\t'.join(map(str, [name, w, h, base64.b64encode(values).decode(), metrics['mean_luma'],
            metrics['dark_clip_fraction'], metrics['highlight_clip_fraction'], metrics['laplacian_variance']])))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    target = Path(__file__).parent / 'fixtures/golden_metrics.tsv'
    expected = contents()
    if args.check:
        if target.read_text() != expected:
            raise SystemExit('Golden fixture regeneration differs')
        print('16 privacy-safe golden vectors reproducible')
    else:
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(expected)
