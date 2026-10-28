"""Synthetic check of surface reprojection for north-up tiles (reproject.sky_field, warp_sky): a moon seen from
Cassini at the same time moves nothing; turned by an angle, the point under the disk's middle moves R sin(angle)
across the sky (east-west, none north-south), the sky stays put (weight 0 off the body), the limb stays one edge,
and a tile redrawn with the field lands its surface where it was at the epoch. Run: python web/test_sky_field.py"""
import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import reproject as rp

R, D, KM = 500.0, 100000.0, 0.5   # radius km, distance km, km per reference pixel


def view(turn, sun=(-1.0, 0.0, 0.0)):
    c = np.array([D, 0.0, 0.0])
    ch = c / D
    north = np.array([0.0, 0.0, 1.0])
    east = np.cross(north, ch)
    a = math.radians(turn)
    rot = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1.0]])
    s = np.array(sun) / np.linalg.norm(sun)
    return {"c": c, "ch": ch, "north": north, "east": east, "rot": rot, "radii": np.array([R, R, R]), "sun": rot @ s}


ys, xs = np.mgrid[-1200:1201:16, -1200:1201:16].astype(np.float64)
dx, dy, w = rp.sky_field(view(0), view(0), xs, ys, KM)
assert np.abs(dx).max() < 1e-6 and np.abs(dy).max() < 1e-6, "same view, nothing moves"
assert w[75, 75] == 1 and w[0, 0] == 0, "the body moves, the sky not"
turn = 1.0
dx, dy, w = rp.sky_field(view(0), view(turn), xs, ys, KM)
mid = (ys == 0) & (xs == 0)
want = R * math.sin(math.radians(turn)) / KM
print("middle moves", dx[mid], dy[mid], "want", want)
assert abs(abs(dx[mid][0]) - want) < 0.05 * want and abs(dy[mid][0]) < 0.05, (dx[mid], dy[mid])
off = np.hypot(xs, ys) > R / KM + 2
assert np.all(dx[off] == 0) and np.all(dy[off] == 0) and np.all(w[off] == 0), "off the body nothing moves"

# a tile redrawn: a spot on the surface at the middle at the epoch is drawn at the middle again
img = np.zeros((2401, 2401, 4), np.uint8)
img[..., 3] = 255
img[..., :3] = 40
cx = 1200 + int(round(dx[mid][0]))
img[1195:1206, cx - 5:cx + 6, :3] = 250   # where the turned picture shows the spot
out = rp.warp_sky(img, dx, dy, w, 16)
ys2, xs2 = np.nonzero(out[..., 0] > 150)
print("spot redrawn at", xs2.mean() - 1200, ys2.mean() - 1200)
assert abs(xs2.mean() - 1200) < 1 and abs(ys2.mean() - 1200) < 1
# the limb: a bright disk (night side too) turned, redrawn, keeps one edge where it was (no second limb inside)
r = R / KM
yy, xx = np.mgrid[0:2401, 0:2401] - 1200.0
disk = np.zeros((2401, 2401, 4), np.uint8)
disk[..., 3] = 255
disk[..., :3] = np.where(np.hypot(xx, yy) <= r, 200, 0)[..., None]
ep, vw = view(0), view(5.0, sun=(0, 1.0, 0))
dx, dy, w = rp.sky_field(ep, vw, xs, ys, KM)
out = rp.warp_sky(disk, dx, dy, w, 16)
row = out[1200, :, 0].astype(int)
inside = row[1200 - int(r) + 3:1200 + int(r) - 3]
print("limb row: darkest inside the disk", inside.min())
assert inside.min() > 150, "no dark band inside the limb"
assert row[1200 - int(r) - 4] < 20 and row[1200 + int(r) + 4] < 20, "the sky stays dark"
# the shift fades toward the limb (to a fraction of the middle's in the outer 1%) and is none on the night side
# (the epoch lit from +y body-fixed: half the disk dark)
assert np.abs(dx[(w > 0) & (np.hypot(xs, ys) > 0.99 * r)]).max() < 0.15 * np.abs(dx[mid]).max(), "fades at the limb"
ep2 = view(0, sun=(0, 1.0, 0))
dx2, _, _ = rp.sky_field(ep2, vw, xs, ys, KM)
on, hit2 = rp.sky_to_surface(ep2, xs, ys, KM)
lit = (on / R) @ ep2["sun"]
assert np.all(dx2[hit2 & (lit <= 0)] == 0) and np.abs(dx2[hit2 & (lit > 0.3)]).min() > 0, "the night side keeps its place"
# fast: a 1448 px tile at the disk's middle in well under a second
import time
big = np.zeros((1448, 1448, 4), np.uint8)
gy, gx = np.mgrid[0:1448 + 16:16, 0:1448 + 16:16].astype(np.float64)
t0 = time.time()
fx_, fy_, fw_ = rp.sky_field(ep, vw, gx - 724, gy - 724, KM)
rp.warp_sky(big, fx_, fy_, fw_, 16)
took = time.time() - t0
print("1448 px tile", round(took, 3), "s")
assert took < 0.8, took
print("sky field: ok")
