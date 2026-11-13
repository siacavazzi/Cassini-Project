"""A pixel the camera saturated is drawn, on a mosaic's shared scale (calibration.load_channels with scale), as bright as
the light it saturated on (calibration.saturated_code): white where that light reaches white (a crescent, a ring arc,
a disk in exposures made for the rings, as test_saturated_white.py has it), but about as bright as a faint glow when
a long exposure saturated on one far under the mosaic's white. The Grand Finale high-phase ring mosaics (269RI
HIPHASEFB001, 260RI HIPHASEFA001) drew the glow under Saturn, where a 38 s BL1 and a 6.8 s GRN saturated at I/F
0.0009-0.001 and RED read 0.0013, as a cyan and blue blob, and a 3.8 s RED saturated at 0.0015 as a white block.
Synthetic frames. Fails on the code before it (the glow's saturated patch drawn 255).
Run: python web/test_saturated_glow.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402  (puts the repo on the path)
import calibration as cal  # noqa: E402

H = 160
yy, xx = np.mgrid[:H, :H]
r2 = (yy - 80) ** 2 + (xx - 80) ** 2
scale = {"blacks": [0.0], "white": 1.0, "gamma": 2.2, "shoulder": cal.SHOULDER}


def drawn(iof, full):
    plain = cal.load_channels([None], [None], iofs=[iof], scale=scale)[0][..., 0]
    now = cal.load_channels([None], [None], iofs=[iof], scale=scale, saturated=[full])[0][..., 0]
    return plain, now


# a faint glow, 0.02 of white, whose middle the camera saturated at 0.025: drawn as bright as the glow round it
glow = (0.02 * np.exp(-r2 / (2 * 45.0 ** 2))).astype(np.float32)
full = glow >= 0.016
iof = np.minimum(glow, 0.016)
plain, now = drawn(iof, full)
ring = (~full) & (np.sqrt(r2) < np.sqrt(r2[full]).max() + 3)
assert np.array_equal(plain[~full], now[~full])   # the rest as before
assert now[full].max() <= plain[ring].max() + 2 and now[full].min() >= plain[full].max(), (now[full].max(), plain[ring].max())
print("a glow saturated far under white is drawn as bright as the glow round it (%d, round it %d); ok"
      % (now[full].max(), plain[ring].max()))

# ringlets a long exposure clipped among bright ringlets, the clip far over the glow's but under white (195RI
# HIPHASEC001: 143-245 of 255): white as before, not flat gray bands among white ones
rings = np.where((xx // 4) % 2 == 0, 0.22, 0.08).astype(np.float32)
rings[:, 76:84] = 0.5
full = rings >= 0.25
_, now = drawn(np.minimum(rings, 0.25), full)
assert now[full].min() == 255, now[full].min()
print("ringlets clipped well over a glow's level are white; ok")

# a body as bright as white, its bright side saturated: white, as before
body = np.where(r2 < 50 ** 2, 0.8, 0.002).astype(np.float32)
body[(r2 < 50 ** 2) & (xx > 100)] = 3.0
full = body > 1.5
iof = np.minimum(body, 0.9)
_, now = drawn(iof, full)
assert now[full].min() == 255, now[full].min()
print("a body saturated at white is white; ok")

# two patches in one frame: each its own level
iof = (0.001 + 0.02 * np.exp(-((yy - 30) ** 2 + (xx - 30) ** 2) / (2 * 30.0 ** 2))).astype(np.float32)
full = iof >= 0.016             # a glow's patch, saturated on its middle
iof = np.minimum(iof, 0.016)
full[100:140, 100:140] = False
full[100:140, 100:140] = True   # a lit body's
iof[95:145, 95:145] = 0.85
iof[100:140, 100:140] = 0.9
_, now = drawn(iof, full)
assert now[30, 30] < 80 and now[120, 120] == 255, (now[30, 30], now[120, 120])
print("each saturated patch at its own level (%d, %d); ok" % (now[30, 30], now[120, 120]))

# a colour mosaic of the glow, two bands saturated where the third read the glow: near gray, not cyan
glow = (0.03 * np.exp(-r2 / (2 * 45.0 ** 2))).astype(np.float32)
bands = []
for clip in (None, 0.022, 0.018):   # RED read it all; GRN and BL1 saturated on its middle
    full = np.zeros(glow.shape, bool) if clip is None else glow >= clip
    picture = cal.load_channels([None], [None], iofs=[np.minimum(glow, clip or 1.0)], scale=scale, saturated=[full])[0]
    bands.append(np.dstack([picture[..., 0]] * 3 + [np.full(glow.shape, 255, np.uint8)]))
u = {"key": ("SATURN", "TEST", "W", 0)}
p = {"display_scale": {"gamma": 2.2}}
rgb = om.colour_picture(u, p, ["RED", "GRN", "BL1"], bands)[80, 80, :3].astype(int)
assert rgb.max() < 120 and rgb.max() - rgb.min() < 25, rgb
print("a colour glow saturated in two bands stays near gray (%s); ok" % (rgb,))

# a sunlit crescent a long exposure saturated, far under white, against its night side and the sky (250EN ENCELSPOL001):
# brighter than anything round it says, white as before
moon = np.where(r2 < 50 ** 2, 0.0005, 0.0002).astype(np.float32)
crescent = (r2 < 50 ** 2) & (xx > 110)
full = crescent.copy()
iof = np.where(crescent, 0.01, moon).astype(np.float32)
_, now = drawn(iof, full)
assert now[full].min() == 255, now[full].min()
print("a crescent with an edge saturated under white is white; ok")
