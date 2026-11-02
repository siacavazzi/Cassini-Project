"""The "darksky" step: what the dark model leaves in the frame's own dark sky (its column stripes and the glow round
the frame's edges) taken out too, dark_current.sky_residual. Synthetic frames. Run: python web/test_dark_sky.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import calibration as cal  # noqa: E402
import dark_current as dc  # noqa: E402

H = 512
rng = np.random.default_rng(7)
yy, xx = np.mgrid[:H, :H]
edge = np.minimum(np.minimum(yy, H - 1 - yy), np.minimum(xx, H - 1 - xx))
glow = 2.0 * np.exp(-edge / 50.0)                              # the sky 2 DN brighter at the frame's edges
stripes = rng.normal(0, 1.0, H)                                # a DN from column to column
disc = (yy - 250) ** 2 + (xx - 140) ** 2 < 90 ** 2              # a moon
plume = 3.0 * np.exp(-((yy - 250) ** 2 + (xx - 300) ** 2) / (2 * 30 ** 2))   # a faint plume in the middle


def frame(level=0.0):
    img = level + glow + stripes[None, :] + plume + rng.normal(0, 1.0, (H, H))
    img[disc] += 400.0
    for y, x in rng.integers(4, H - 4, (60, 2)):
        img[y - 1:y + 2, x - 1:x + 2] += 300.0
    return img


img = frame()
left = dc.sky_residual(img)
assert left is not None
after = img - left
sky = ~disc & (plume < 0.1)
rim = lambda a: float(np.median(a[:12, 240:480]) - np.median(a[200:220, 380:420]))
assert rim(img) > 1.0 and abs(rim(after)) < 0.25, (rim(img), rim(after))
# the column stripes go
cols = lambda a: np.array([np.median(a[380:500, c][sky[380:500, c]]) for c in range(40, H - 40)])
hp = lambda c: c - np.convolve(c, np.ones(31) / 31, "same")
assert np.std(hp(cols(after))[20:-20]) < 0.35 * np.std(hp(cols(img))[20:-20]), (np.std(hp(cols(img))), np.std(hp(cols(after))))
# the moon and the plume in the middle stay: the step takes away no more there than the stripes
assert abs(float(np.mean(left[200:300, 120:160]) - np.mean(stripes[120:160]))) < 0.3
assert abs(float(np.mean(left[240:260, 290:310]) - np.mean(stripes[290:310]))) < 0.3

# a lit frame (Venus, a sky Saturn lights), a frame with no sky, a frame that does not cut into blocks: nothing
assert dc.sky_residual(frame(level=100.0)) is None
assert dc.sky_residual(np.zeros((100, 100))) is None

# the step: in STEPS after "dark", on by default, its own cache name when off
assert cal.STEPS.index("darksky") == cal.STEPS.index("dark") + 1 and cal.step("darksky")
with cal.stepping("darksky"):
    assert not cal.step("darksky") and cal.step("dark") and cal.variant() == "-off-darksky"
print("dark sky ok")
