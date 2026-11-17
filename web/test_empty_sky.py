"""The sky test (calibration._sky) on a frame of empty sky measured at full depth: its noise centred on the sky's level,
a few stars setting the 99.9th percentile, so SKY_CUT of it ran through the noise's middle and half the sky was taken
for lit (N1637448980_1, N1444023957_1: a gray floor with line stripes, where the 8-bit codes had drawn black). Now the
whole noise is sky; a frame with a body, or with a glow well above its noise, keeps its sky as before.
Synthetic frames. Run: python web/test_empty_sky.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import calibration as cal  # noqa: E402

N = 1024
rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)


def old_sky(iofs):
    sky = np.ones(iofs[0].shape, dtype=bool)
    for iof in iofs:
        sky &= iof < 0.05 * np.percentile(iof, 99.9)
    return sky


def stars(img, n=60, peak=0.3):
    for _ in range(n):
        i, j = rng.integers(2, N - 2, 2)
        img[i - 1:i + 2, j - 1:j + 2] += peak
    return img


checks = 0
# 1. empty sky: noise of 0.004 round 0.0005 and stars: nearly all of it sky (the old cut took about half)
empty = stars(rng.normal(0.0005, 0.004, (N, N)).astype(np.float32))
new, old = cal._sky([empty]).mean(), old_sky([empty]).mean()
assert old < 0.7 and new > 0.97, (old, new)
print(f"empty sky: sky {old:.2f} -> {new:.2f}")
checks += 1

# 2. the same sky from its 8-bit codes (its noise squeezed into a few levels, all under the cut, as N1444023957_1's
# were: 1st to 99th percentile -0.0039 to -0.0013): as before
squeezed = stars(np.round(rng.normal(-0.0028, 0.0006, (N, N)) / 0.0007).astype(np.float32) * 0.0007)
assert np.array_equal(cal._sky([squeezed]), old_sky([squeezed]))
checks += 1

# 3. a body (a disk at 0.3) over that noise: the sky as before
body = empty.copy()
body[np.hypot(xx - 400, yy - 500) < 250] += 0.3
assert np.array_equal(cal._sky([body]), old_sky([body]))
checks += 1

# 4. a glow (a ring's, up to 0.05) over a dark sky with a body: the glow well above the noise stays lit, as before
glow = empty + 0.05 * np.exp(-((yy - 700) / 120) ** 2).astype(np.float32)
glow[np.hypot(xx - 200, yy - 200) < 150] += 0.5
assert np.array_equal(cal._sky([glow]), old_sky([glow]))
checks += 1

# 5. two channels: sky only where both are
assert cal._sky([empty, body]).sum() <= cal._sky([body]).sum()
checks += 1
print(f"{checks} checks ok")
