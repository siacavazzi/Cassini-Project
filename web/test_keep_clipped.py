"""A mosaic tile's pixel clipped in every band stays neutral under per-band gains (mosaic._gained, keep_clipped):
ringsFA's saturated block went from 255/255/255 to 255/255/247 when its blue gain fell to 0.97 (PR 611 review). It
still takes the gains' mean, so it does not stand as a white plateau over the light round it. Run:
python web/test_keep_clipped.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import mosaic

c = np.array([[[255, 255, 255], [100, 100, 100], [255, 120, 60], [254, 254, 254]]], np.float32)
for gamma in (None, 2.2):
    src = c if gamma is None else c.astype(np.uint8)
    got = mosaic._toned(src, np.array([1.0, 1.0, 0.97]), np.zeros(3), gamma)
    w = got[0, 0]
    assert w[0] == w[1] == w[2] and 245 <= w[0] < 255, (gamma, got)   # neutral, and down by the mean gain
    assert got[0, 1, 2] < got[0, 1, 0], (gamma, got)                   # an unclipped pixel takes each band's gain
    assert got[0, 2, 2] < 60 and got[0, 2, 0] == 255, (gamma, got)     # clipped in one band only: its own gains
    assert abs(float(w[0]) - float(got[0, 3].mean())) <= 2, (gamma, got)  # no step against the light next to white
    # one band: untouched by the rule
    one = mosaic._toned(src[..., :1], np.array([0.97, 0.97, 0.97]), np.zeros(3), gamma)
    assert one[0, 0, 0] < 255, (gamma, one)
print("ok")
