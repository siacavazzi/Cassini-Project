#!/usr/bin/env python3
"""steady_video.py --code --cache --out DIR OBS: the movie of a pass's frames as the window plays it (movie_webp,
centred, steadied at the default smoothing), every frame saved as PNG into DIR."""
import argparse, os, sys, io
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("--out"); ap.add_argument("--size", type=int, default=512); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache); a.out = os.path.abspath(a.out)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server, obs_mosaic as om, calibration
from PIL import Image
os.makedirs(a.out, exist_ok=True)
with calibration.looking("balanced"):
    for u in om.units(*a.obs.split(":")):
        if u.get("kind") != "movie": continue
        for i, fr in enumerate(u["frames"]):
            got = om.movie_webp(fr[1], a.size, a.cache, ahead=0, wait=True, steady=om.STEADY_SMOOTH)
            if got and got[0]:
                Image.open(io.BytesIO(got[0])).convert("RGB").save(os.path.join(a.out, f"{'_'.join(map(str, u['key']))}_{i:04d}.png"))
        print("done", u["key"], flush=True)
