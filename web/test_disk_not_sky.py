"""pass_scale's dark sky is never inside an airless body's disk where SPICE puts it (obs_mosaic._disk_mask, inner:
DISK_MARGIN in from the limb, so the sky by the limb still counts). Iapetus' closest flyby (049IA ORSHIRES001, 2007)
fills its frames with bright ice and dark material a tenth as bright: the dark material passed for sky (_dark_sky), the
pass's black went to its level (0.088 I/F against a sky top of 0.008) and it drew as black holes. Synthetic frames.
Run: python web/test_disk_not_sky.py"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

shape = (1024, 1024)
q = np.full((256, 256), 0.5, np.float32)         # bright ice over the whole frame (quarter size)
q[40:120, 30:200] = 0.035                        # dark material, a fourteenth as bright
radius = 3000.0                                  # the disk far wider than the frame: all of it is ground
inner = om._disk_mask(q.shape, shape, 0.0, 0.0, radius, inner=True)
outer = om._disk_mask(q.shape, shape, 0.0, 0.0, radius)
assert inner.all() and outer.all()
assert om._dark_sky(q)[40:120, 30:200].all(), "without the disk the dark material reads as sky"
assert not (om._dark_sky(q) & ~inner).any()
print("dark ground inside the disk is not sky; ok")

# a moon in the middle of the frame, sky round it: the sky by the limb (within SPICE's error) still counts
q2 = np.zeros((256, 256), np.float32)
yy, xx = np.mgrid[0:256, 0:256] * 4.0
r = 300.0
q2[(yy - 511.5) ** 2 + (xx - 511.5) ** 2 < r * r] = 0.6
inner = om._disk_mask(q2.shape, shape, 0.0, 0.0, r, inner=True)
sky = om._dark_sky(q2) & ~inner
limb = ((yy - 511.5) ** 2 + (xx - 511.5) ** 2 > (r + 4) ** 2) & ((yy - 511.5) ** 2 + (xx - 511.5) ** 2 < (r * 1.15) ** 2)
assert sky[limb].all() and inner.sum() < (np.pi * (r / 4) ** 2)
print("the sky by the limb still counts as sky; ok")

assert not om._disk_mask(q.shape, shape, 0.0, 0.0, 10.0, inner=True).any()
print("a disk narrower than SPICE's error takes nothing out; ok")
