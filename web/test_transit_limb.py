"""
Transit movie fixes (spot check 10):
1. obs_mosaic._limb_centre finds a lit disk drawn off SPICE's place (Dione 25 px off in 153DI MUTUALEVE002), and
   gives None when SPICE's place is right.
2. obs_mosaic._shade_rgb dims a colour picture by an exposure gain under 1 the same in every band where one band is
   near white (Rhea clipped in GRN, 154RH): no hue where the body is white; and keeps white white.
Run: python web/test_transit_limb.py
"""
import os, sys
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames")]
import numpy as np
import obs_mosaic as om

H = W = 400
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
c = (210.0 - 9, 200.0 + 24)
d = np.hypot(xx - c[0], yy - c[1])
# a gibbous disk: lit on the left, a soft terminator, a dim night side, on a faint background glow
lit = np.clip(0.5 - (xx - c[0]) / 40.0, 0, 1)
g = np.where(d <= 45, 40 + 190 * lit, 0) + 20 * np.exp(-((xx - 120) ** 2 + (yy - 210) ** 2) / 2e4)
g = g.astype(np.float32)
off = om._limb_centre(g, (210.0, 200.0), 45.0)
assert off is not None and abs(off[0] + 9) <= 1.5 and abs(off[1] - 24) <= 1.5, off
print("disk 9 px left and 24 px down of SPICE's place found at", off, "ok")
assert om._limb_centre(g, c, 45.0) is None
print("at SPICE's place: None ok")

px = np.zeros((4, 6, 4), np.uint8)
px[..., 3] = 255
px[0, :, :3] = [226, 246, 204]   # GRN near clipping, the others just under it
px[1, :, :3] = [255, 255, 255]   # white
px[2, :, :3] = [120, 110, 100]   # a mid tone
out = om._shade_rgb(px, 0.5, 2.2)
a = out[0, 0, :3].astype(float); b = px[0, 0, :3].astype(float)
la, lb = (a / 255) ** 2.2, (b / 255) ** 2.2
assert np.ptp(la / lb) < 0.02, (a, b)
assert (out[1, 0, :3] == 255).all()
assert (out[2, 0, :3] < px[2, 0, :3]).all()
print("gain 0.5:", b, "->", a, "(same share in every band), white stays", out[1, 0, :3], "ok")
