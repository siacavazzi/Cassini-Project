"""A mosaic tile's clipped levels stay white under a gain under 1 (mosaic._gained, keep_clipped): ringsFA's saturated
block went from 255/255/255 to 255/255/247 when its blue gain fell to 0.97 (PR 611 review). Run:
python web/test_keep_clipped.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import mosaic

c = np.array([[[255, 255, 255], [100, 100, 100], [255, 120, 60]]], np.float32)
for gamma in (None, 2.2):
    got = mosaic._toned(c if gamma is None else c.astype(np.uint8), np.array([1.0, 1.0, 0.97]), np.zeros(3), gamma)
    assert (got[0, 0] == 255).all(), (gamma, got)
    assert got[0, 1, 2] < 100, (gamma, got)        # an unclipped level still takes its gain
    assert got[0, 2, 0] == 255 and got[0, 2, 1] == 120, (gamma, got)
    # a gain over 1 still raises an unclipped level, and a clipped one stays at white
    up = mosaic._toned(c, np.array([1.05, 1.05, 1.05]), np.zeros(3), gamma)
    assert up[0, 1, 0] > 100 and (np.clip(up[0, 0], 0, 255) == 255).all(), (gamma, up)
print("ok")
