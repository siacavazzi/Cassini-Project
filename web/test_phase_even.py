"""image_correction.phase_correlate: cv2.phaseCorrelate pads each side to an optimal DFT size, and where that is odd its
peak comes out half a pixel off (a 364-row square, padded to 375, matched with itself measured 0.5 px down; every
stabilization link of Enceladus' 279EN PLUME001 movie was half a pixel off each way, 48 px of drift over 288 frames).
phase_correlate pads to an even size first. Run: python web/test_phase_even.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import image_correction  # noqa: E402

rng = np.random.default_rng(3)
for h, w in ((364, 289), (369, 288), (372, 646), (407, 369), (128, 128), (201, 200)):
    a = cv2.GaussianBlur(rng.random((h + 40, w + 40)).astype(np.float32), (0, 0), 3)
    win = cv2.createHanningWindow((w, h), cv2.CV_32F)
    base = a[20:20 + h, 20:20 + w]
    for dx, dy in ((0, 0), (3, 7), (-5, 2)):
        moved = a[20 - dy:20 - dy + h, 20 - dx:20 - dx + w]
        (gx, gy), _ = image_correction.phase_correlate(base, moved, win)
        assert abs(gx - dx) < 0.3 and abs(gy - dy) < 0.3, (h, w, dx, dy, gx, gy)
    # find_shift on the same picture twice: no move
    bgr = cv2.cvtColor(np.clip(base * 255 * 4, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    s = image_correction.find_shift(bgr, bgr.copy())
    assert s is None or (abs(s[0]) < 1e-6 and abs(s[1]) < 1e-6), (h, w, s)
print("ok")
