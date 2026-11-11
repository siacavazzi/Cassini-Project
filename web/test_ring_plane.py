"""reproject.ring_plane: where lines of sight cross a body's equator plane. Seen pole-on from far away, a sky place r
reference px from the body's centre is on the ring plane r * km_px km out, and on the rings between RING_INNER and
RING_OUTER; seen edge-on it never crosses in front of Cassini at a ring radius off the plane's line.
Run: python web/test_ring_plane.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import reproject as rp

D = 2.0e6        # km from Cassini
KM = 50.0        # km per reference px


def view(rot):
    c = np.array([D, 0.0, 0.0])
    ch = c / np.linalg.norm(c)
    north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
    north /= np.linalg.norm(north)
    return {"c": c, "ch": ch, "north": north, "east": np.cross(north, ch), "rot": np.array(rot, float),
            "radii": np.array([60268.0, 60268.0, 54364.0]), "sun": np.array([1.0, 0.0, 0.0])}


# pole-on: the body's z axis along the line of sight (J2000 x)
pole = view([[0, 1, 0], [0, 0, 1], [1, 0, 0]])
x = np.array([0.0, 1000.0, 2000.0, 2600.0, 3000.0])
y = np.zeros_like(x)
r, on = rp.ring_plane(pole, x, y, KM)
assert np.allclose(r, np.abs(x) * KM, rtol=2e-3), r
assert on.tolist() == [False, False, True, True, False], on   # 0, 50,000 (inside C ring), 100,000, 130,000, 150,000 km
r2, _ = rp.ring_plane(pole, np.zeros(3), np.array([1500.0, -1500.0, 2000.0]), KM)
assert np.allclose(r2, [75000, 75000, 100000], rtol=2e-3), r2

# seen from 10 degrees over the ring plane: a sky place y px north of the body's centre is on the plane y * km_px /
# sin(10 deg) km out (foreshortened rings). A sky place's y runs south (sky_to_surface: y = -north): y < 0 is north of
# the centre, the rings' far side, behind the disk's outline (not on the rings); y > 0 the near side, in front of it
e = np.radians(10.0)


def tilted():
    c = 100 * D * np.array([np.cos(e), 0.0, -np.sin(e)])   # (far, so the sight lines are near parallel)
    ch = c / np.linalg.norm(c)
    north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
    north /= np.linalg.norm(north)
    return {"c": c, "ch": ch, "north": north, "east": np.cross(north, ch), "rot": np.eye(3),
            "radii": np.array([60268.0, 60268.0, 54364.0]), "sun": np.array([1.0, 0.0, 0.0])}


v = tilted()
ys = np.array([-400.0, -300.0, 300.0, 400.0])   # px: 20,000 and 15,000 km on the sky, far side and near side
r3, on3 = rp.ring_plane(v, np.zeros(4), ys, KM)
want = np.abs(ys) * KM / np.sin(e)
assert np.allclose(r3, want, rtol=0.03), (r3, want)
# (far side behind the disk: never; near side, in front of it: on the rings where the radius is)
assert on3.tolist() == [False, False] + [rp.RING_INNER <= w <= rp.RING_OUTER for w in want[2:]], (on3, want)
print("ring plane: ok")
