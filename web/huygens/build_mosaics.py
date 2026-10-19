#!/usr/bin/env python3
"""
Turn Karkoschka's DISR landing-site mosaics into a brightness-matched pyramid
for the replay.

The archive's EXTRAS/MOSAICS/MOSIACS_PNG holds twelve 1250x1600 16-bit mosaics,
north up, centred on the landing site (column 625, row 800 counted from the
bottom), named by scale in m/pixel (1, 2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60).
Each file was scaled to 16 bits on its own, so the brightness of one scale does
not match the next. This script fits a gain and offset from every scale to the
next coarser one where they overlap (60 m is the reference), applies one shared
stretch, and writes:

  mosaics/<s>m.png      8-bit, same size and placement as the source
  mosaics/mosaics.json  scale, size and landing-site pixel of each level

project_frames.py places the frames on this pyramid and renders the descent.

Usage:
  python web/huygens/build_mosaics.py --src <MOSIACS_PNG dir> --out <replay dir>
"""

import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image

SCALES = [60, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1]  # m/pixel, coarse to fine
W, H = 1250, 1600
CX, CY = 624.0, H - 800.0  # landing site, 0-based, rows counted from the top


def load(src, s):
    return np.array(Image.open(os.path.join(src, f"{s}.PNG"))).astype(np.float64)


def sample(img, s, gx, gy):
    """Sample a mosaic of scale s (m/px) at ground coords gx (east), gy (north) in m.
    Returns values and a mask of points inside the mosaic."""
    mx = (CX + gx / s).astype(np.float32)
    my = (CY - gy / s).astype(np.float32)
    inside = (mx >= 0) & (mx <= W - 1) & (my >= 0) & (my <= H - 1)
    v = cv2.remap(img.astype(np.float32), mx, my, cv2.INTER_LINEAR,
                  borderMode=cv2.BORDER_REPLICATE)
    return v, inside


def match_levels(src):
    """Gain/offset for every level so it matches the 60 m mosaic's brightness."""
    imgs = {s: load(src, s) for s in SCALES}
    fit = {60: (1.0, 0.0)}
    for coarse, fine in zip(SCALES, SCALES[1:]):
        f = imgs[fine]
        # the fine mosaic, blurred to the coarse resolution, against the coarse mosaic
        k = coarse / fine
        fb = cv2.GaussianBlur(f, (0, 0), 0.5 * k) if k > 1 else f
        ys, xs = np.mgrid[0:H:4, 0:W:4]
        gx = (xs - CX) * fine
        gy = (CY - ys) * fine
        cv, inside = sample(imgs[coarse], coarse, gx, gy)
        a = fb[ys, xs][inside]
        b = cv[inside]
        A = np.vstack([a, np.ones_like(a)]).T
        g, o = np.linalg.lstsq(A, b, rcond=None)[0]
        gc, oc = fit[coarse]
        fit[fine] = (gc * g, gc * o + oc)
    out = {s: imgs[s] * fit[s][0] + fit[s][1] for s in SCALES}
    return out, fit


def stretch_params(levels):
    v = levels[60]
    lo, hi = np.percentile(v, [0.5, 99.5])
    return lo, hi


def to8(v, lo, hi, gamma=0.85):
    x = np.clip((v - lo) / (hi - lo), 0, 1) ** gamma
    return (x * 255 + 0.5).astype(np.uint8)


def write_pyramid(levels, fit, out):
    lo, hi = stretch_params(levels)
    d = os.path.join(out, "mosaics")
    os.makedirs(d, exist_ok=True)
    meta = {"source": "DISR V1.3 EXTRAS/MOSAICS (E. Karkoschka), brightness-matched to the 60 m level",
            "north_up": True, "landing_px": [CX, CY], "width": W, "height": H,
            "stretch": {"lo": lo, "hi": hi, "gamma": 0.85}, "levels": []}
    for s in SCALES:
        Image.fromarray(to8(levels[s], lo, hi)).save(os.path.join(d, f"{s}m.png"), optimize=True)
        meta["levels"].append({"m_per_px": s, "file": f"mosaics/{s}m.png",
                               "extent_m": [W * s, H * s], "gain": fit[s][0], "offset": fit[s][1]})
    json.dump(meta, open(os.path.join(d, "mosaics.json"), "w"), indent=1)
    return lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    levels, fit = match_levels(a.src)
    lo, hi = write_pyramid(levels, fit, a.out)
    for s in SCALES:
        print(f"{s:3d} m/px  gain {fit[s][0]:.4f}  offset {fit[s][1]:9.1f}")


if __name__ == "__main__":
    main()
