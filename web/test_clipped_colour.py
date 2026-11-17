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

# a band the camera saturated on the bright part of a body, drawn white there (calibration.saturated_code: a patch with
# an edge), in a resampled plane whose clipped area's rim blends that white with what the band read. With its tile's
# saturation map (sat: how much of it is the white drawn over the light it saturated on) the band is floored at that light, not at its white, and keeps the
# body's colour; without one it is floored at white, as before. GRN saturated over a fifth of Rhea in 154RH
# MUTUALEVE002, where RED read 230, came out a lime-green patch
import cv2  # noqa: E402
gam = 1.5
ramp = np.tile(np.linspace(0.25, 1.0, 200, dtype=np.float32), (200, 1))   # linear brightness of a neutral body
enc = lambda v: np.clip(np.power(np.clip(v, 0, 1), 1 / gam) * 255 + 0.5, 0, 255)
r5, g5, b5 = enc(ramp), enc(0.95 * ramp), enc(0.85 * ramp)
sat = ramp > 0.8                       # GRN saturated where red still reads 220-ish: drawn at 255
level = np.where(sat, enc(0.95 * ramp), 0).astype(np.uint8)   # the light it saturated on (its own clip)
g5 = np.where(sat, 255.0, g5)
g5 = np.round(cv2.GaussianBlur(g5.astype(np.float32), (0, 0), 0.7))   # resampled: the rim blends 255 with the band's readings
ps = planes(r5, g5, b5)
dec = lambda v: np.power(v.astype(np.float32) / 255, gam)
excess = np.where(level > 0, np.maximum(dec(g5) - dec(level), 0), 0).astype(np.float32)   # (om._sat_excess)
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], ps, sat=[None, excess, None]).astype(int)
old = om.colour_picture(u, p, ["RED", "GRN", "BL1"], ps).astype(int)
inside, outside = a[100, 170:195, :3], a[100, 100:140, :3]
assert (outside[:, 0] > outside[:, 1]).all(), outside[::8]
assert (inside[:, 1] <= inside[:, 0] + 1).all(), inside[::5]
assert (old[100, 170:195, 1] > old[100, 170:195, 0] + 1).any(), old[100, 170:195:5, :3]
print("a band saturated on a body's bright part, floored at the light it saturated on, keeps the body's colour (%s, "
      "red over green as round it %s; floored at its white: %s); ok" % (inside[10], outside[20], old[100, 180, :3]))

# a mosaic (its sat composed with its picture, obs_mosaic._filter_excess: mark): a thin saturated ring blended into the
# canvas under CLIP_FROM (269RI HIPHASEFB001's F ring: BL1 and GRN saturated, RED not) is clipped by its excess and
# takes the colour round it, not cyan; without mark (a movie frame) the excess never marks a pixel clipped
r6 = np.full((200, 200), 120.0); g6 = np.full((200, 200), 118.0); b6 = np.full((200, 200), 110.0)
ring = slice(98, 101)
r6[ring] = 177; g6[ring] = 225; b6[ring] = 230
ex_g = np.zeros((200, 200), np.float32); ex_b = np.zeros((200, 200), np.float32)
ex_g[ring] = dec(np.full((3, 200), 225.0)) - dec(np.full((3, 200), 176.0))
ex_b[ring] = dec(np.full((3, 200), 230.0)) - dec(np.full((3, 200), 166.0))
a = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r6, g6, b6), sat=[None, ex_g, ex_b], mark=True).astype(int)
old = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r6, g6, b6)).astype(int)
movie = om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes(r6, g6, b6), sat=[None, ex_g, ex_b]).astype(int)
c, o, rest = a[99, 100, :3], old[99, 100, :3], a[50, 100, :3]
assert c[0] >= c[1] - 2 and c[1] >= c[2] - 2, (c, rest)
assert o[2] > o[0] + 20, o
assert (movie == old).all()
print("a thin saturated ring in a mosaic keeps the colour round it (%s, round it %s; before %s); ok" % (c, rest, o))
