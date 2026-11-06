"""A weak match checked on the edges (image_correction.checked_shift) and a channel as taken that lines up
(AS_TAKEN_SURE): ring frames through two filters whose ringlets run one way correlate too weakly for find_shift's bar
(00ASA SATSYSTEM001: peaks of 0.1 to 0.25) though moving them by the peak lines the ringlets up; frames that already
line up stand as taken instead of "not aligned"; a peak that lines the edges up worse never moves a frame.
Synthetic frames. Run: python web/test_align_checked.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import image_correction as ic  # noqa: E402

N = 1024
rng = np.random.default_rng(5)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
RADII, WIDTHS, AMPS = rng.uniform(1300, 3700, 120), rng.uniform(2, 10, 120), rng.uniform(-0.3, 0.4, 120)
MASK = np.ones((N, N), bool)


def rings(dx, dy, band, noise=0.02):
    """Ringlets seen at a low opening angle (an ellipse, so their detail runs one way), brighter in one band, with a
    different glow across the frame in each band"""
    r = np.hypot(xx - 512 - dx, (yy - 1500 - dy) * 2.5)
    img = 0.5 + sum(a * np.exp(-((r - c) / w) ** 2) for c, w, a in zip(RADII, WIDTHS, AMPS))
    img = img * (1.0 if band else 0.7) + (0.15 * xx / N if band else 0.15 * (1 - yy / N))
    img = img + rng.normal(0, noise, img.shape)
    return cv2.cvtColor(np.clip(img * 160, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


ref = rings(0, 0, 0)

# moved 9,-8 between the filters: find_shift's bar turns the peak down, the check on the edges keeps it
moved = rings(9, -8, 1)
assert ic.find_shift(ref, moved) is None
shift, how = ic._match(ref, moved, None, MASK, MASK)
assert shift is not None and "checked on edges" in how, how
assert abs(shift[1] + 8) < 1.0 and abs(shift[0] - 9) < 4.0, shift     # across the ringlets to a pixel, along them looser
print("weak ring match:", how, [round(v, 1) for v in shift])

# the same with SPICE's offset a few px off: still the frames' own match, not SPICE's
shift2, how2 = ic._match(ref, moved, (14.0, -3.0), MASK, MASK)
assert shift2 is not None and abs(shift2[1] + 8) < 1.0, (how2, shift2)
print("with SPICE near:", how2)

# a peak far from SPICE's offset is not checked (FIT_REACH): SPICE's offset alone decides, as before
far, how3 = ic.checked_shift(ref, moved, MASK, MASK, (60.0, 40.0))
assert far is None, how3

# frames that line up as taken (the same ringlets, another band): they stand as taken, never "not aligned"
same = rings(0, 0, 1)
shift4, how4 = ic._match(ref, same, None, MASK, MASK)
assert shift4 is not None and np.hypot(*shift4) < 1.0, (how4, shift4)
print("lined up:", how4)

# nothing alike (one frame blank sky): no checked match, not aligned
sky = cv2.cvtColor(np.clip(rng.normal(20, 3, (N, N)), 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
shift5, how5 = ic._match(ref, sky, None, MASK, MASK)
assert shift5 is None, (how5, shift5)
print("blank:", how5)
print("ok")
