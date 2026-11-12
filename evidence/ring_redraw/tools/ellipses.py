#!/usr/bin/env python3
"""ellipses.py --code --cache OBS IN.png OUT.png : SPICE's ring edges (A ring outer 136,770 km, B ring outer 117,580 km,
B ring inner 92,000 km) at the times of the pass's first, middle and last pointings, drawn over the finished mosaic."""
import argparse, os, sys
import numpy as np, cv2
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("obs"); ap.add_argument("inp"); ap.add_argument("out")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache); a.inp = os.path.abspath(a.inp); a.out = os.path.abspath(a.out)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration
from PIL import Image
with calibration.looking("balanced"):
    u = [u for u in om.units(*a.obs.split(":")) if u.get("kind") == "mosaic"][0]
    rings = om._ring_geometry(u)
    made = om.layout(u, len(u["frames"]) - 1, a.cache)
    p = made[0]
    tiles = [t for t in made[1] if "offset" in t]
    roots = {}
    for t in tiles:
        roots[t["n"]] = om._pointing_root(u, t["n"], roots)
    firsts = [t for t in tiles if roots[t["n"]] == t["n"]]
    im = np.asarray(Image.open(a.inp).convert("RGB")).copy()
    H, W = im.shape[:2]
    fx0, fy0, fx1, fy1 = p["footprint"]
    k = W / p["view"][0]
    print("footprint", p["footprint"], "view", p["view"], "k", k, file=sys.stderr)
    ys, xs = np.mgrid[0:H, 0:W]
    cx, cy = xs / k + fx0, ys / k + fy0
    cols = {0: (255, 80, 80), 3: (80, 255, 80), 6: (90, 160, 255)}
    for i, col in cols.items():
        t = firsts[i]
        r, on = rings(cx.ravel(), cy.ravel(), t["id"])
        r = np.where(on, r, np.nan).reshape(H, W)
        for R in (136770, 117580, 92000):
            m = np.isfinite(r) & (r >= R)
            edge = (m ^ cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)) & np.isfinite(r)
            im[edge] = col
    Image.fromarray(im).save(a.out)
    print(a.out)
