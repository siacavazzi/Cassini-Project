"""Ring registration on a synthetic ring system (no SPICE, no data): two overlapping tiles of rings drawn from one
radial profile through reproject.sky_to_ring, the second moved by a known amount, measured back by
obs_mosaic.ring_shift; and reproject.ring_field's masks (Saturn's disk, its shadow, the radius range). Run:
python web/test_ring_register.py"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
sys.path.insert(0, os.path.join(HERE, ".."))
import obs_mosaic as om  # noqa: E402
import reproject as rp  # noqa: E402


def view(elev_deg=20.0, dist=1.5e6, sun=(1.0, 0.3, 0.4)):
    e = np.radians(elev_deg)
    ch = np.array([np.cos(e), 0.0, -np.sin(e)])   # Cassini above the ring plane, looking down at Saturn
    c = ch * dist
    north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
    north /= np.linalg.norm(north)
    east = np.cross(north, ch)
    s = np.array(sun) / np.linalg.norm(sun)
    return {"c": c, "ch": ch, "north": north, "east": east, "rot": np.eye(3), "radii": np.array([60268.0, 60268.0, 54364.0]),
            "sun": s, "pole": np.array([0.0, 0.0, 1.0]), "sun_j2000": s}


rng = np.random.default_rng(3)
edges = np.cumsum(rng.uniform(80, 900, 400)) + 70000
levels = rng.uniform(60, 220, len(edges))


def profile(r):
    return levels[np.clip(np.searchsorted(edges, r), 0, len(levels) - 1)]


def tile(v, x0, y0, w, h, km_px, d=(0.0, 0.0)):
    """An RGBA tile whose content is the rings moved by d (it shows at x what is at x - d)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    _, r, ok = rp.sky_to_ring(v, xx + x0 - d[0], yy + y0 - d[1], km_px)
    g = np.where(ok, profile(r), 10.0)
    im = np.zeros((h, w, 4), np.uint8)
    im[..., :3] = np.clip(g, 0, 255)[..., None]
    im[..., 3] = 255
    return im


def check(v, km_px, at_q, at_t, d, label):
    q = {"n": 0, "filter": "CL1", "box": [0, 0, 640, 480]}
    t = {"n": 1, "filter": "CL1", "box": [0, 0, 640, 480]}
    a = tile(v, at_q[0], at_q[1], 640, 480, km_px)
    b = tile(v, at_t[0], at_t[1], 640, 480, km_px, d)
    shift, how = om.ring_shift(q, a, at_q, t, b, at_t, v, km_px)
    assert shift is not None, (label, how)
    normal = how.get("normal")
    err = np.subtract(shift, d)
    if normal is not None:
        err = np.dot(err, normal)   # (along the ringlets it is left as SPICE has it)
    print(f"{label}: moved {d}, measured ({shift[0]:+.2f}, {shift[1]:+.2f}) normal {normal} error {np.round(err, 2)}")
    assert np.all(np.abs(err) < 0.6), (label, shift, d, how)


v = view()
km_px = 60.0
# an ansa: one direction across the ringlets
check(v, km_px, (1700, -300), (1900, -250), (3.0, -1.5), "ansa")
# near the rings' front, where the ringlets bend: both directions
check(v, km_px, (1000, 300), (1150, 350), (-2.5, 4.0), "front")
check(v, km_px, (1000, 300), (1150, 350), (0.0, 0.0), "front, not moved")

# the masks: Saturn's disk and the sky past the rings are not ring; a ring point behind Saturn is hidden
_, r, ok = rp.sky_to_ring(v, np.array([0.0, 4000.0, 0.0]), np.array([0.0, 0.0, -3000.0]), km_px)
assert not ok[0] and not ok[1] and not ok[2], (r, ok)
# Saturn's shadow: a sun behind Saturn as seen from Cassini puts the far side of the rings in shadow
# (the sun beyond Saturn, low over the rings: its shadow falls across the near side of the rings)
gx, gy = np.meshgrid(np.arange(-2400, 2400, 8.0), np.arange(-1600, 1600, 8.0))
_, _, lit = rp.sky_to_ring(view(sun=(1.0, 0.0, 0.05)), gx, gy, km_px)
_, _, lit1 = rp.sky_to_ring(view(sun=(0.0, 1.0, 0.6)), gx, gy, km_px)
print(f"ring pixels lit: sun overhead {lit1.sum()}, sun behind Saturn {lit.sum()}")
assert lit1.sum() > lit.sum() + 500, "a shadow on the rings takes some of them out"
# the redraw: a view a degree higher moves the rings against Saturn's center; the weight is the lit rings only
gx, gy = np.meshgrid(np.arange(-2400, 2400, 16.0), np.arange(-1600, 1600, 16.0))
dx, dy, wt = rp.ring_field(v, view(elev_deg=21.0), gx, gy, km_px)
_, _, ok = rp.sky_to_ring(v, gx, gy, km_px)
assert wt.sum() > 0 and not (wt.astype(bool) & ~ok).any()
assert np.hypot(dx, dy)[wt > 0].max() > 5
same, _, _ = rp.ring_field(v, v, gx, gy, km_px)
assert np.abs(same).max() < 1e-6
fine = rp.ring_weight(v, view(elev_deg=21.0), -2400, -1600, 3200, 4800, km_px)
assert fine.shape == (3200, 4800) and 0.2 < fine.mean() / ok.mean() <= 1.0, (fine.mean(), ok.mean())
print("ring registration ok")
