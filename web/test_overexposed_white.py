"""Check the white of frames exposed past full well on purpose (calibration.unsaturated_white, Sam's taste call 24, B):
a picture whose label forecasts over 100% of full well, with under 5% of it really saturated, takes its white from what
the camera did not saturate, at most 4 times under the white it had, and every other picture keeps its white.
Run: python web/test_overexposed_white.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calibration as cal  # noqa: E402

assert (cal.OVEREXPOSED, cal.OVEREXPOSED_SATURATED, cal.OVEREXPOSED_GAIN) == (100.0, 0.05, 4.0)
# the label's forecast
assert cal.expected_maximum({"EXPECTED_MAXIMUM": "(909.44397,1405.6)"}) == 909.44397
assert cal.expected_maximum({"EXPECTED_MAXIMUM": '"(101.228996, 150.0)"'}) == 101.228996
assert cal.expected_maximum({"EXPECTED_MAXIMUM": "(UNK,UNK)"}) is None and cal.expected_maximum({}) is None
assert cal.overexposed({"EXPECTED_MAXIMUM": "(100.154999,120.0)"}) and not cal.overexposed({"EXPECTED_MAXIMUM": "(100.0,120.0)"})
assert not cal.overexposed({"EXPECTED_MAXIMUM": "(57.5,63.3)"}) and not cal.overexposed({"EXPECTED_MAXIMUM": "(UNK,UNK)"})

rng = np.random.default_rng(24)
y, x = np.mgrid[0:1024, 0:1024].astype(np.float32)


def scene(plume, sliver=6):
    """A blown-out crescent (I/F 1.0, `sliver` px thick, saturated), a plume over it at `plume` of that, dark sky."""
    r = np.hypot(x - 512, y - 600)
    iof = 0.0005 * rng.standard_normal((1024, 1024)).astype(np.float32)
    iof += plume * np.exp(-((x - 512) / 60) ** 2) * np.exp(-np.maximum(540 - y, 0) / 120) * (y < 540)
    blown = (np.abs(r - 60) < sliver / 2) & (y > 600)
    iof[blown] = 1.0
    return iof, blown


iof, blown = scene(0.01)
assert 0 < blown.mean() < 0.01
white = float(iof.max()) / cal.MAX_STRETCH              # as _balanced_scale sets it: the blown-out sliver's
levels, margin = [0.0], 0.002
# the plume at 1% of the crescent: the white comes down by the full 4 times and no more
got = cal.unsaturated_white([iof], levels, margin, white, [blown])
assert abs(got - white / cal.OVEREXPOSED_GAIN) < 1e-9, (got, white)
# a brighter thing beside it (40% of the white): the white is that thing's, under 4 times
bright, blown2 = scene(0.4 * white)
got = cal.unsaturated_white([bright], levels, margin, white, [blown2])
assert white / cal.OVEREXPOSED_GAIN < got < 0.5 * white, (got, white)
# never over the white given, whatever is left
assert cal.unsaturated_white([np.full((1024, 1024), 5.0, np.float32)], levels, margin, white, [blown]) == white
# nothing saturated, no mask, or 5% and more of the picture saturated: the white stays
assert cal.unsaturated_white([iof], levels, margin, white, [np.zeros_like(blown)]) == white
assert cal.unsaturated_white([iof], levels, margin, white, [None]) == white
wide = np.zeros_like(blown); wide[:60] = True           # 5.9% of the picture
assert cal.unsaturated_white([iof], levels, margin, white, [wide]) == white
# the pixels round a saturated one are left out with it: a bright ring of bleed 3 px wide round the sliver sets nothing
bleed = iof.copy()
import cv2  # noqa: E402
ring = (cv2.dilate(blown.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0) & ~blown
bleed[ring] = 0.8
assert abs(cal.unsaturated_white([bleed], levels, margin, white, [blown]) - white / cal.OVEREXPOSED_GAIN) < 1e-9
# a set: the saturated pixels of any channel are left out of every channel, and the brightest channel sets the white
g = cal.unsaturated_white([iof, bright], [0.0, 0.0], margin, white, [blown, blown2])
assert abs(g - cal.unsaturated_white([bright], levels, margin, white, [blown2])) < 0.02 * white
print(f"overexposed on purpose: white {white:.3f} -> {cal.unsaturated_white([iof], levels, margin, white, [blown]):.3f} "
      f"(at most {cal.OVEREXPOSED_GAIN:g} times), others unchanged: ok")
