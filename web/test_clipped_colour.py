"""Mosaic colour pictures (obs_mosaic.colour_picture) with a band clipped: a clipped pixel takes the picture's own
hue (clipped_hue: read on its bright part where no band clipped), paled toward white, at the brightness that keeps
every band at or over what it read, so a patch where red clipped and green did not keeps the colour round it instead
of turning pink (North Pole map movie, 175SA NPOLMAP001, red saturated over 70% of the disk), a patch clipped in every
band is the body's colour at the top of the scale, not white (SOI 2004, 000RI RINGPHOTM001), and no band's own
clipping edge draws a rim. Bands that do not clip are drawn as before, byte for byte. Synthetic planes.
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

hue = lambda c: c / c.max()
order = lambda c: c[0] >= c[1] >= c[2]

# the right half a quarter brighter: red clips there, green and blue do not; the right half keeps the left's colour
# (its order of bands, paler), never under what green and blue read, and is not pink (red over green by more than left)
r2, g2, b2 = r.copy(), g.copy(), b.copy()
r2[:, 100:] = 255; g2[:, 100:] = 209; b2[:, 100:] = 139   # 1.25 times as bright: red past white
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r2, g2, b2)).astype(float)
left, right = a[100, 30, :3], a[100, 170, :3]
assert order(left) and order(right), (left, right)
assert right[1] >= 209 - 2 and right[2] >= 139 - 2, right
assert right[0] - right[1] <= left[0] - left[1], (left, right)
print("a band clipped where another is not keeps the colour round it, paler (%s, %s); ok" % (left, right))

# every band clipped on the right: the left's colour at the top of the scale, not white
r5, g5, b5 = r.copy(), g.copy(), b.copy()
r5[:, 100:] = 255; g5[:, 100:] = 255; b5[:, 100:] = 255
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r5, g5, b5)).astype(int)
c = a[100, 170, :3]
assert c[0] >= 245 and order(c) and c[0] - c[2] >= 20, c
print("a patch clipped in every band keeps the picture's hue at white (%s); ok" % (c,))

# a third of the picture clipped (Saturn 2011, 150SA NHEMMOVIE001): the clipped part is at the top of the scale in the
# picture's hue and meets green's clipping edge without a step (no green or yellow patch along it)
r3 = np.full((200, 200), 150.0); g3 = np.full((200, 200), 150.0); b3 = np.full((200, 200), 165.0)
r3[:, 140:] = 255; g3[:, 140:] = 255; b3[:, 140:] = 215
g3[:, 140:170] = 235   # green just under its clipping here
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r3, g3, b3)).astype(int)
for x in (150, 160, 190):
    c = a[100, x, :3]
    assert c.max() >= 240 and abs(int(c[0]) - int(c[1])) <= 8, (x, c)
assert np.abs(a[100, 168, :3] - a[100, 172, :3]).max() < 25, (a[100, 168, :3], a[100, 172, :3])
print("a picture partly clipped is at white in the picture's hue (%s, %s); ok" % (a[100, 150, :3], a[100, 190, :3]))

# most of the picture clipped in red (175SA NPOLMAP001): the clipped part takes the bluish gray of the part that is
# not, paled, never red over blue (pink)
r4 = r3.copy(); g4 = g3.copy(); b4 = b3.copy()
r4[:, 60:] = 255; g4[:, 60:] = 255; b4[:, 60:] = 215; g4[:, 60:110] = 235
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r4, g4, b4)).astype(int)
c = a[100, 100, :3]
assert c[0] <= c[2] + 2, c
print("a band clipped over most of the picture takes the hue of the rest (%s); ok" % (c,))
