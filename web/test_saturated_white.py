"""What the camera saturated is drawn white in mosaic tiles and movie frames, as in a one frame picture
(calibration.draw_saturated). A tile is drawn on its pass's shared scale (color_image.load_aligned with scale ->
calibration.load_channels) from its exposures merged in I/F (stacking.load_hdr): where a long exposure saturated, a
shorter one's measurement is used (also next to that one's own saturated core); where every exposure saturated, the pixel keeps a clipped value that sits below
the brightness round it, and was drawn one flat gray (250EN_ENCELSPOL001's crescent, 212SA_STORMW010's rings). Now
load_hdr returns those pixels (clipped) and they are drawn white, on the shared scale and on a picture's own.
Synthetic frames: a body whose bright side saturates the long exposure and whose core saturates the short one too.
Fails on the code before it (the core drawn gray, darker than the side round it).
Run: python web/test_saturated_white.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import stacking  # noqa: E402

H = 128
yy, xx = np.mgrid[:H, :H]
r2 = (yy - 64) ** 2 + (xx - 64) ** 2
# the scene's I/F: dark sky, a body of 1.0, its bright side 5.0, and a core of 50
scene = np.full((H, H), 0.02, np.float32)
scene[r2 < 40 ** 2] = 1.0
side = (r2 < 40 ** 2) & (xx > 70)
scene[side] = 5.0
core = (r2 < 40 ** 2) & (xx > 90)
scene[core] = 50.0
side &= ~core
EXPOSURES = {"long.png": 100.0, "short.png": 10.0}


def codes_of(path):
    # the camera's 8 bit codes: I/F times the exposure, clipped at the top (254 and over is saturated, cal.saturated)
    return np.clip(scene * EXPOSURES[path], 0, 255).astype(np.uint8)


class Label:
    def __init__(self, path):
        self.info = {"path": path, "EXPOSURE_DURATION": EXPOSURES[path], "GAIN_MODE_ID": "12",
                     "INSTRUMENT_MODE_ID": "FULL", "IMAGE_TIME": "2016-11-27T09:12:36", "PRODUCT_ID": path}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return np.ones((H, H), bool)

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return cv2.cvtColor(codes_of(self.info["path"]), cv2.COLOR_GRAY2BGR)


labels = {p: Label(p) for p in EXPOSURES}
stacking.find_repeats = lambda path, window=120, max_frames=5: ["long.png", "short.png"][:max_frames]
stacking.lh.label = lambda p, as_png=True: labels[p]
stacking.ic.find_shift = lambda a, b, r: (0.0, 0.0)
stacking.places = lambda ids: {i: (0.0, 0.0, 1.0e5) for i in ids}
stacking.ds.imread = lambda path, flags=None: codes_of(path)
cal.calibrate = lambda codes, info, image=None: codes.astype(np.float32) / np.float32(info["EXPOSURE_DURATION"])
cal.ds.lut8 = lambda: False   # cal.saturated as it is for 8 bit frames: codes at 254 and over

# ---------- stacking.load_hdr: a shorter exposure where the long one saturated; clipped where every one did ----------
_, iof, n = stacking.load_hdr("long.png")   # as before, without clipped
_, iof2, n2, clipped = stacking.load_hdr("long.png", clipped=True)
assert n == n2 == 2 and np.array_equal(iof, iof2)
# the short exposure's, also next to its own saturated core (left out of the average there, but it measured it)
assert np.allclose(iof[side], 5.0, atol=0.11), np.unique(iof[side])
assert np.allclose(iof[core], 2.55), np.unique(iof[core])   # every exposure saturated: the first frame's clipped value
assert np.array_equal(clipped, core), (clipped.sum(), core.sum())
_, _, _, valid, clipped = stacking.load_hdr("long.png", valid=True, clipped=True)
assert valid.all() and np.array_equal(clipped, core)
print("load_hdr ok")

# ---------- calibration.load_channels on a shared scale: saturated pixels white ----------
scale = {"blacks": [0.05], "white": 8.0, "gamma": 2.2, "shoulder": cal.SHOULDER}
img = labels["long.png"].resize_image()
plain = cal.load_channels([labels["long.png"]], [img], iofs=[iof], scale=scale)[0][..., 0]
drawn = cal.load_channels([labels["long.png"]], [img], iofs=[iof], scale=scale, saturated=[clipped])[0][..., 0]
assert np.array_equal(plain[~core], drawn[~core])   # the rest as before
assert drawn[core].min() == 255 and plain[core].max() < 200, (plain[core].max(), drawn[core].min())
assert np.median(plain[side]) > plain[core].max()   # the bug: the core darker than the side round it
print("load_channels ok")

# ---------- color_image.load_aligned: a mosaic tile (hdr, shared scale) and a picture of its own ----------
color_image.calibrate = True
imgs, valid, _, report = color_image.load_aligned(["long.png"], hdr=True, scale=scale)
tile = imgs[0][..., 0]
assert report["calibrated"] and report["stacked"] == [2], report
assert tile[core].min() == 255, tile[core].min()
assert report["saturated_share"] == round(float(core.mean()), 4), report
assert tile[side].max() < 255 and np.median(tile[side]) > 150, np.median(tile[side])
imgs, _, _, report = color_image.load_aligned(["long.png"], hdr=True)
own = imgs[0][..., 0]
assert own[core].min() == 255, own[core].min()
print("load_aligned ok")

# ---------- a frame with nothing saturated: byte for byte as before ----------
scene[side | core] = 1.0
_, iof, _, clipped = stacking.load_hdr("long.png", clipped=True)
assert not clipped.any()
a = cal.load_channels([labels["long.png"]], [img], iofs=[iof], scale=scale)[0]
b = cal.load_channels([labels["long.png"]], [img], iofs=[iof], scale=scale, saturated=[clipped])[0]
assert np.array_equal(a, b)
print("nothing saturated ok")
print("ok")
