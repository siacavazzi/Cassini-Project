"""Spot check 7, fix D: the dark sky's one-code smoothing (calibration.smooth_sky, the "skysmooth" step) leaves a faint
glow's slope a slope. A plume's fan a few codes over the sky was smoothed between its one-code contours into flat
terraces (ISS_279EN_PLUME001_PIE N1876460140_1: Enceladus's plume a stack of blocks); the flat sky beside it is still
smoothed as before. Synthetic 8-bit codes. Run: python web/test_sky_glow.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402

rng = np.random.default_rng(3)
N = 1024
yy, xx = np.mgrid[:N, :N].astype(np.float32)
# a fan rising 8 codes over 250 px towards its root, on a sky of 14 codes with 2 Hz bands of half a code
fan = 8.0 * np.clip(1 - np.hypot(xx - 300, (yy - 900) * 0.5) / 250, 0, 1)
bands = 0.5 * np.sin(yy * 2 * np.pi / 45)
true = 14 + fan + bands
codes = np.floor(true + rng.normal(0, 0.3, (N, N))).astype(np.uint8)
iof = codes.astype(np.float32) - bands   # calibrate took each line's 2 Hz level off (twohzsky)
true = true - bands
sky = np.ones((N, N), bool)    # the dark sky of cisscal_noise.dark_sky: the fan's faint part is in it
out = cal.smooth_sky(iof, codes, sky)


def terraces(img, rows, cols):
    """How far the picture sits off the true slope over a patch, once both are blurred past the grain (3 px): flat
    terraces between one-code steps sit up to half a code off it"""
    import cv2
    d = cv2.GaussianBlur(img.astype(np.float32) - true, (0, 0), 3)[rows, cols]
    return float(np.std(d))


patch = (slice(600, 760), slice(240, 360))   # on the fan's slope
flat = (slice(50, 250), slice(700, 900))      # plain sky
fan_after = terraces(out, *patch)
print("fan: off its slope", round(terraces(iof, *patch), 3), "->", round(fan_after, 3))
# on the fan the result stays on its slope (smoothed over SKY_SMOOTH alone it sat in terraces)
assert fan_after < 0.02, fan_after
# the flat sky is smoothed as before: its grain goes
print("sky: grain", round(float(iof[flat].std()), 3), "->", round(float(out[flat].std()), 3))
assert out[flat].std() < 0.6 * iof[flat].std()
# and its mean stays
assert abs(float(out[flat].mean()) - float(iof[flat].mean())) < 0.05
print("ok")
