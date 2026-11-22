"""A colour mosaic's pixel at white in one band and within WHITE_SLACK of it in the others is drawn white
(obs_mosaic.clipped_white): ringsFA's saturated block came out 255/255/247, cream, once the solved blue gain was 0.97
(PR 611 review). Anything further from white, or not at white in any band, keeps its colour; alpha is untouched. Run:
python web/test_clipped_white.py"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "frames")); sys.path.insert(0, os.path.join(here, ".."))
import numpy as np
import obs_mosaic as om

px = [[255, 255, 247, 200],   # cream block: white
      [255, 255, 255 - om.WHITE_SLACK, 255],   # at the slack: white
      [255, 255, 255 - om.WHITE_SLACK - 1, 255],   # past it: kept
      [254, 254, 250, 255],   # no band at white: kept
      [255, 200, 120, 255],   # a clipped red over real colour: kept
      [120, 120, 120, 0]]
rgba = np.array([px], np.uint8)
got = om.clipped_white(rgba)
assert got[0, 0, :3].tolist() == [255, 255, 255] and got[0, 0, 3] == 200, got
assert got[0, 1, :3].tolist() == [255, 255, 255], got
for i in (2, 3, 4, 5):
    assert got[0, i].tolist() == px[i], (i, got[0, i])
assert rgba[0, 0, 2] == 247, "input changed in place"
same = np.array([[[10, 20, 30, 255]]], np.uint8)
assert om.clipped_white(same) is same
print("clipped white ok")
