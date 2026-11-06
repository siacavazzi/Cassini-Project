"""A gain under 1 (a movie frame's exposure gain, a luminance base's band gain) leaves white white: a clipped pixel
is at least as bright as white, so dimmed it drew a floor as a value (the 2006 backlit Saturn movie, 028RG
HIPHASE002: the sun's saturated glare a flat grey blob at exposure gain 0.7, white in the frames round it)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import obs_mosaic as om  # noqa: E402

v = np.arange(256, dtype=np.uint8)
part = np.dstack([np.tile(v, (4, 1))] * 3 + [np.full((4, 256), 255, np.uint8)])
dim = om._shade(part, {"gain": 0.7, "gamma": 2.2})[0, :, 0].astype(int)
assert dim[255] == 255, dim[255]                       # clipped white stays white
assert dim[128] < 128 - 15 and dim[200] < 200 - 10, (dim[128], dim[200])   # the rest is dimmed as before
assert np.all(np.diff(dim) >= 0), "not monotonic"       # eased in, no fold
bright = om._shade(part, {"gain": 1.3, "gamma": 2.2})[0, :, 0].astype(int)
assert bright[128] > 128 and bright[255] == 255
print("a gain under 1 dims the picture and leaves white white (128 -> %d, 200 -> %d, 255 -> %d); ok" % (dim[128], dim[200], dim[255]))
