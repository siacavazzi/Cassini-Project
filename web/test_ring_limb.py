"""obs_mosaic.limb_place and ring_pair_shift on made-up geometry: a disk whose lit limb stands 6 px over the model's
(a haze) and a tile drawn 3 px out along the limb's normal; two ring tiles whose ringlets sit 4 px apart across the
rings. Each measure finds what was put in, within a fraction of a pixel.
Run: python web/test_ring_limb.py"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

T = 400

# --- limb: SPICE's disk of radius R round the canvas origin, lit everywhere; the picture's disk is R + HAZE, and the
# tile's content is drawn OUT px further out along the limb's normal at its middle (its pointing off)
R, HAZE, OUT = 1000.0, 6.0, 3.0


def disk(x, y, fid):
    hit = np.hypot(x, y) < R
    return hit, np.where(hit, 1.0, 0.0)


ang = math.radians(30)
cx, cy = R * math.cos(ang), R * math.sin(ang)
t = {"n": 0, "id": "f0", "offset": [cx, cy], "box": [-T / 2, -T / 2, T, T]}
yy, xx = np.mgrid[0:T, 0:T]
gx, gy = xx + cx - T / 2 - OUT * math.cos(ang), yy + cy - T / 2 - OUT * math.sin(ang)
r = np.hypot(gx, gy)
lit = np.clip((R + HAZE - r) + 0.5, 0, 1) * 200 + 5
im = np.zeros((T, T, 4), np.uint8)
im[..., :3] = lit[..., None].astype(np.uint8)
im[..., 3] = 255
o, n, count = om.limb_place(disk, t, im)
print("limb: stands out", round(o, 2), "normal", np.round(n, 3), "samples", count)
assert abs(o - (HAZE + OUT)) < 0.6, o
assert abs(n[0] - math.cos(ang)) < 0.05 and abs(n[1] - math.sin(ang)) < 0.05, n

# --- rings: radius = distance from the origin in km (KM km a px), on the rings between 74,490 and 140,220 km; a
# radial pattern of ringlets; tile b's picture drawn with its ringlets SHIFT px further out than tile a's
KM, SHIFT = 60.0, 4.0
rng = np.random.default_rng(5)
prof = np.convolve(rng.random(4000), np.ones(9) / 9, mode="same")   # 50 km bins of ringlet brightness


def rings(x, y, fid):
    rad = np.hypot(x, y) * KM
    return rad, (rad > 74490) & (rad < 140220)


def ring_tile(n, at, out_px):
    x0, y0 = at[0] - T / 2, at[1] - T / 2
    gx, gy = np.meshgrid(np.arange(T) + x0, np.arange(T) + y0)
    rad = (np.hypot(gx, gy) - out_px) * KM
    v = np.interp(rad / 50.0, np.arange(len(prof)), prof) * 200 + 20
    im = np.zeros((T, T, 4), np.uint8)
    im[..., :3] = v[..., None].astype(np.uint8)
    im[..., 3] = 255
    return {"n": n, "id": f"r{n}", "filter": "CL", "offset": list(at), "box": [-T / 2, -T / 2, T, T]}, im


u = {"key": ("SATURN", "OBS", "W", 0), "z": 1.0}
mid = 1800.0
a, ima = ring_tile(1, (mid, 0.0), 0.0)
b, imb = ring_tile(2, (mid + 150.0, 40.0), SHIFT)
move, how = om.ring_pair_shift(u, rings, a, ima, b, imb)
print("rings: move", np.round(move, 2), how)
# (b's ringlets sit SHIFT px out: b moves back in by that much, across the rings, about along -x here)
across = move[0] * how["normal"][0] + move[1] * how["normal"][1]
assert abs(across + SHIFT) < 0.5, across
print("ring and limb: ok")
