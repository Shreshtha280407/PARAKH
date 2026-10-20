#!/usr/bin/env python3
"""Encode captured UI and code-native artwork for GitHub-friendly delivery."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/assets/readme'
FRAMES=Path('/tmp/parakh-readme-artwork')

def ffmpeg(*args):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-threads','2',*map(str,args)],check=True)

def gif(source,dest,fps,width,colors):
    filt=f'fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors={colors}:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4'
    ffmpeg('-i',source,'-vf',filt,'-loop','0','-y',dest)

def frames_gif(name,framerate):
    filt='scale=1100:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=160[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4'
    ffmpeg('-framerate',framerate,'-i',FRAMES/name/'%03d.png','-vf',filt,'-loop','0','-y',OUT/('hero.gif' if name=='hero' else 'worker-journey.gif'))

def still(p):
    filters=['-vf','crop=iw:ih-168:0:120'] if p.name.startswith('app-') else []
    ffmpeg('-i',p,*filters,'-c:v','libwebp','-quality','88','-y',p.with_suffix('.webp'))

jobs=[]
with ThreadPoolExecutor(max_workers=3) as pool:
    if '--stills-only' not in sys.argv:
        jobs.append(pool.submit(frames_gif,'hero','8'))
        jobs.append(pool.submit(frames_gif,'worker','1/3'))
    for name in ([] if '--stills-only' in sys.argv else ['assessor-review','live-product-tour']):
        src=OUT/(name+'.webm')
        jobs.append(pool.submit(gif,src,OUT/(name+'.gif'),4,900,112))
        jobs.append(pool.submit(ffmpeg,'-i',src,'-vf','scale=1200:-2','-c:v','libx264','-crf','27','-preset','slow','-pix_fmt','yuv420p','-movflags','+faststart','-an','-y',OUT/(name+'.mp4')))
    for p in OUT.glob('*.png'):jobs.append(pool.submit(still,p))
    for job in jobs:job.result()
print('Media encoding complete')
