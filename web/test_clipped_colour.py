"""Mosaic colour pictures (obs_mosaic.colour_picture) with a band clipped where another is not: the clipped band is
filled from the bands that are not (calibration.fill_saturated, read near each pixel), so a patch where red clipped
and green did not keeps the colour round it instead of turning pink (North Pole map movie, 175SA NPOLMAP001, red
saturated over 70% of the disk). Bands that do not clip are drawn as before, byte for byte. Synthetic planes.
Run: python web/test_clipped_colour.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obs_mosaic as om  # noqa: E402

u = {"key": ("SATURN", "TEST", "W", 0)}
p = {"display_scale": {"gamma": 1.5}}


def planes(r, g, b):
    return [np.dstack([np.full((200, 200), v, np.uint8) if np.isscalar(v) else v.astype(np.uint8)] * 3
                      + [np.full((200, 200), 255, np.uint8)]) for v in (r, g, b)]


# nothing clipped: as before
r = np.full((200, 200), 230.0); g = np.full((200, 200), 180.0); b = np.full((200, 200), 120.0)
def without(ps):
    keep, om.CLIP_FROM = om.CLIP_FROM, 256
    try:
        return om.colour_picture(u, p, ["RED", "GRN", "BL1"], ps)
    finally:
        om.CLIP_FROM = keep
assert np.array_equal(om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r, g, b)), without(planes(r, g, b)))

# the right half a quarter brighter: red clips there, green and blue do not; the right half keeps the left's colour
r2, g2, b2 = r.copy(), g.copy(), b.copy()
r2[:, 100:] = 255; g2[:, 100:] = 209; b2[:, 100:] = 139   # 1.25 times as bright: red past white
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r2, g2, b2)).astype(float)
left, right = a[100, 30, :3], a[100, 170, :3]
hue = lambda c: c / c.max()
old = without(planes(r2, g2, b2)).astype(float)[100, 170, :3]
now, then = np.abs(hue(left) - hue(right)).max(), np.abs(hue(left) - hue(old)).max()
assert now < then / 2 and now < 0.06, (left, right, old)
print("a band clipped where another is not keeps the colour round it (%s, %s; before %s); ok" % (left, right, old))

# a third of the picture clipped (Saturn 2011, 150SA NHEMMOVIE001): the only place every band reads is the dim part,
# so the ratio the fill reads there drew the clipped part under the bands' own clipped values, green where red alone
# clipped. A clipped band is never drawn under what it read: the bright part stays warm, as bright as its red and
# green read, and meets green's clipping edge without a step
r3 = np.full((200, 200), 150.0); g3 = np.full((200, 200), 150.0); b3 = np.full((200, 200), 165.0)
r3[:, 140:] = 255; g3[:, 140:] = 255; b3[:, 140:] = 215
g3[:, 140:170] = 235   # green just under its clipping here
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r3, g3, b3)).astype(int)
for x in (150, 160, 190):
    c = a[100, x, :3]
    assert c[0] >= 240 and c[0] >= c[1] >= c[2], (x, c)
assert np.abs(a[100, 168, :3] - a[100, 172, :3]).max() < 25, (a[100, 168, :3], a[100, 172, :3])
print("a picture partly clipped stays as bright as its clipped bands read (%s, %s); ok" % (a[100, 150, :3], a[100, 190, :3]))

# most of the picture clipped (the North Pole map movie, 175SA NPOLMAP001: RED saturated over about 70% of the disk):
# too little of red is left to say how bright it was, so its fill takes the colour round it whole, as before the floor
r4 = r3.copy(); g4 = g3.copy(); b4 = b3.copy()
r4[:, 60:] = 255; g4[:, 60:] = 255; b4[:, 60:] = 215; g4[:, 60:110] = 235
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r4, g4, b4)).astype(int)
c = a[100, 100, :3]
assert c[0] < c[1], c
print("a band clipped over most of the picture is filled from the others alone (%s); ok" % (c,))
