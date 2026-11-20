"""Synthetic check of a filter's turn against its pointing's reference (obs_mosaic.filter_turn_of, used by _filter_turn
before C8): a cratered moon drawn twice, the second turned by a degree or two and moved a few px, as Mimas 167MI's GRN
and UV3 frames are against its clear frame. The turn is found with its sign (+x side down), and turning the second
back by it (_subpixel, as _tile does) leaves no turn; a frame that is not turned gives none, nor do sky or ringlets
(detail one way only). Run:
python web/test_filter_turn.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2
import numpy as np
import obs_mosaic as om

S = 1024
rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
body = np.zeros((S, S), np.float32)
disk = (xx - 600) ** 2 + (yy - 380) ** 2 < 640 ** 2
body[disk] = 150
for _ in range(400):
    cx, cy, r = rng.uniform(0, S), rng.uniform(0, S), rng.uniform(4, 30)
    d = np.hypot(xx - cx, yy - cy)
    body += np.where(d < r, -40 * (1 - d / r), 0) + np.where((d >= r) & (d < 1.3 * r), 35, 0)
body = cv2.GaussianBlur(np.clip(body, 0, 255) * disk, (0, 0), 1.0) + rng.normal(0, 2, (S, S)).astype(np.float32)


def rgba(g):
    g = np.clip(g, 0, 255).astype(np.uint8)
    return np.dstack([g, g, g, np.full_like(g, 255)])


def turned(theta, dx, dy):
    # (cv2's angle is counter-clockwise on the screen: a picture whose +x side is turned down by theta is turned by -theta)
    m = cv2.getRotationMatrix2D(((S - 1) / 2, (S - 1) / 2), -theta, 1.0)
    m[:, 2] += (dx, dy)
    return cv2.warpAffine(body, m, (S, S), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


ref = rgba(body)
s = {"offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]}
for theta, dx, dy in ((1.4, 6.0, -3.0), (-2.2, -4.0, 9.0), (0.0, 5.0, 2.0)):
    mine = rgba(turned(theta, dx, dy))
    got, blocks = om.filter_turn_of(s, ref, dict(s), mine)
    assert got is not None and abs(got - theta) < 0.08, (theta, got, blocks)
    back = om._subpixel(mine, 0.0, 0.0, got, ((S - 1) / 2, (S - 1) / 2))
    again, _ = om.filter_turn_of(s, ref, dict(s), back)
    assert again is not None and abs(again) < 0.08, (theta, got, again)

# two frames of featureless sky (their own noise each) give no turn
got, why = om.filter_turn_of(s, rgba(rng.normal(20, 2, (S, S)).astype(np.float32)), dict(s),
                             rgba(rng.normal(20, 2, (S, S)).astype(np.float32)))
assert got is None, (got, why)
# ringlets (detail one way only) turned against each other give no turn: a block of them matches anywhere along them
rings = (120 + 60 * np.sin(np.hypot(xx + 3000, yy - 500) / 3.0) + rng.normal(0, 2, (S, S))).astype(np.float32)
m = cv2.getRotationMatrix2D(((S - 1) / 2, (S - 1) / 2), -2.0, 1.0)
got, why = om.filter_turn_of(s, rgba(rings), dict(s), rgba(cv2.warpAffine(rings, m, (S, S), borderMode=cv2.BORDER_REFLECT)))
assert got is None, (got, why)
print("ok")
