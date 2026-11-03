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
