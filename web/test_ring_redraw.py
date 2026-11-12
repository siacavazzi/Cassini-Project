"""Saturn's ring passes are redrawn as at the pass's epoch (reproject.ring_field, obs_mosaic.ring_redraw): a tile's
picture taken while Cassini sat elsewhere shows each place of the ring plane where the epoch's view shows the same
place. ISS_00ARI_COMPHIDRK001 (2004-10-28, at periapsis) saw the rings' ellipse a quarter flatter by its last pointing
than at its first; tiles put on the body's centre stepped 10 to 30 px at every seam. Checked here on views made up
from vectors, no SPICE: the field is none between a view and itself, carries every place of the plane to the same
radius, keeps the disk in front of the rings as taken, and a shear along the arcs is not read as a squeeze.
Run: python web/test_ring_redraw.py"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import reproject as rp  # noqa: E402


def view(elev_deg, dist=1.2e6, az_deg=0.0):
    """Cassini dist km from Saturn, elev_deg above the ring plane (body-fixed = J2000 here, z the pole)."""
    e, a = math.radians(elev_deg), math.radians(az_deg)
    cas = dist * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    c = -cas   # Cassini to Saturn
    ch = c / np.linalg.norm(c)
    north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
    north /= np.linalg.norm(north)
    east = np.cross(north, ch)
    return {"c": c, "ch": ch, "north": north, "east": east, "rot": np.eye(3),
            "radii": np.array([60268.0, 60268.0, 54364.0]), "sun": np.array([1.0, 0.0, 0.0])}


KM_PX = 60.0
y, x = np.mgrid[-1200:1200:40, -2600:2600:40].astype(float)

# a view and itself: no shift, and the plane is there in front of Cassini
v = view(8.0)
dx, dy, w = rp.ring_field(v, v, x, y, KM_PX)
assert w.sum() > 0 and np.abs(dx[w > 0]).max() < 1e-6 and np.abs(dy[w > 0]).max() < 1e-6
print("a view against itself moves nothing; ok")

# Cassini 2 degrees higher (the ellipse opens up): each place lands on the same radius in the other view
e, f = view(8.0), view(10.0, dist=1.15e6, az_deg=3.0)
dx, dy, w = rp.ring_field(e, f, x, y, KM_PX)
r_e, on_e = rp.ring_plane(e, x, y, KM_PX)
r_f, on_f = rp.ring_plane(f, x + dx, y + dy, KM_PX)
both = (w > 0) & on_e & on_f
assert both.sum() > 200, both.sum()
assert np.abs(r_e[both] - r_f[both]).max() < 1.0, np.abs(r_e[both] - r_f[both]).max()
assert np.hypot(dx, dy)[both].max() > 20   # (the change is real: tens of px, which no one shift takes out)
spread = np.hypot(dx - np.median(dx[both]), dy - np.median(dy[both]))[both]
assert np.percentile(spread, 95) > 5, np.percentile(spread, 95)
print("a place of the ring plane lands on the same radius in the other view; ok")

# the disk in front of the rings at the epoch stays as taken; rings the frame saw behind the disk are holes
keep, hole = rp.ring_masks(e, f, x, y, x + dx, y + dy, KM_PX)
_, hit = rp.sky_to_surface(e, x, y, KM_PX)
assert keep[hit & ~on_e].all()
assert not (hole & keep).any()
print("the disk stays as taken, and nothing is both kept and a hole; ok")

# a shear along the arcs (dx growing with y) squeezes nothing; field_stretch read it as a squeeze
gy, gx = np.mgrid[0:20, 0:20].astype(np.float32) * 16
sx, sy, ww = (0.6 * gy).astype(np.float32), np.zeros_like(gy), np.ones_like(gy)
assert rp.field_stretch(sx, sy, ww, 16) > 0.5
assert rp.field_squeeze(sx, sy, ww, 16) < 0.5, rp.field_squeeze(sx, sy, ww, 16)
# a true squeeze is one
assert rp.field_squeeze((-0.7 * gx).astype(np.float32), sy, ww, 16) > 0.5
print("a shear along the arcs is not a squeeze, a squeeze is; ok")

# warp_rings: kept places as taken, holes empty, the rest drawn from the shifted place
img = np.zeros((64, 64, 4), np.uint8)
img[:, 32:] = (200, 100, 50, 255)
img[:, :32] = (10, 20, 30, 255)
z = np.zeros((5, 5), np.float32)
keepm = np.zeros((64, 64), bool)
keepm[:8] = True
holem = np.zeros((64, 64), bool)
holem[-8:] = True
out = rp.warp_rings(img, z + 16, z, z + 1, 16, keepm, holem)
assert (out[:8] == img[:8]).all()
assert (out[-8:, :, 3] == 0).all()
assert tuple(out[20, 20]) == (200, 100, 50, 255), out[20, 20]   # (drawn from 16 px to the right)
print("warp_rings keeps, empties and redraws; ok")

# a redrawn tile's ring plane is the pass's middle frame's (ring_at), which SPICE may not have placed (no distance,
# fr[7] == 0): its view is still worked out from its time, never a KeyError that failed the pass's layout
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402
calls = []
om._ets, om._with_kernels = (lambda ids: {i: 1.0e8 for i in ids}), (lambda t: calls.append(t) or True)
rp.sky_view = lambda target, et: {"et": et}
u = {"key": ["SATURN", "ISS_TEST", "W", 0], "z": 1.0e6,
     "frames": [[0, "W1_1", 0, 100.0, 0, 0, 0, 1.0e6], [1, "W2_1", 0, 200.0, 0, 0, 0, 0], [2, "W3_1", 0, 300.0, 0, 0, 0, 1.0e6]]}
view = om._sky_views(u)
assert view("W2_1") == {"et": 1.0e8} and calls[-1] == 200.0
assert view("W9_9") is None
print("a frame SPICE did not place still has its view; ok")
