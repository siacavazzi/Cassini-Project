#!/usr/bin/env python3
"""full.py --code WT/web/frames --cache DIR --out FILE.png --size PX TARGET:OBS:CAM : the finished mosaic at a large size."""
import argparse, os, sys
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("--out"); ap.add_argument("--size", type=int, default=4096); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache); a.out = os.path.abspath(a.out)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration
from PIL import Image
t, o, c = a.obs.split(":")
with calibration.looking("balanced"):
    for i, u in enumerate(om.units(t, o, c)):
        if u.get("kind") not in ("mosaic", "mosaic_movie"):
            continue
        n = len(u["frames"]) - 1
        im = om.so_far(u, n, a.cache, out=min(a.size, om.CANVAS))[0]
        if im is not None:
            p = a.out.replace(".png", f"_{i}.png")
            (im if isinstance(im, Image.Image) else Image.fromarray(im)).save(p)
            print(p, flush=True)
