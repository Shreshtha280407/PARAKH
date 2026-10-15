#!/usr/bin/env python3
"""Generate tiny synthetic Android-test videos; no private dataset inputs."""
import subprocess
from pathlib import Path

out = Path(__file__).resolve().parents[2] / 'apps/android/assist-benchmark/src/androidTest/assets/fixtures'
out.mkdir(parents=True, exist_ok=True)
landscape = out / 'synthetic-landscape.mp4'
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30:duration=2',
    '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '28', '-g', '30',
    '-pix_fmt', 'yuv420p', '-map_metadata', '-1', str(landscape)], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(landscape), '-map', '0:v:0', '-c', 'copy',
    '-metadata:s:v:0', 'rotate=90', str(out / 'synthetic-rotation90.mp4')], check=True)
for p in sorted(out.glob('*.mp4')):
    print(p.name, p.stat().st_size)
