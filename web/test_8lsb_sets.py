"""C9: a color set with a frame that can't be calibrated (8LSB: only the low 8 bits were sent) keeps its other two
channels calibrated as a two-filter picture, instead of every channel falling back to its own stretch.
Synthetic frames through color_image.load_aligned. Run: python web/test_8lsb_sets.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import stacking  # noqa: E402

H = 256
rng = np.random.default_rng(9)
yy, xx = np.mgrid[:H, :H]
disk = (yy - 128) ** 2 + (xx - 128) ** 2 < 60 ** 2
BODY = {"RED": 0.08, "GRN": 0.05, "BL1": 0.03}   # a dark red-brown moon, in I/F


class Label:
    def __init__(self, band, conversion, t):
        self.band = band
        self.info = {"PRODUCT_ID": f"N{t}_1", "IMAGE_TIME": f"2004-06-11T19:{t:02d}:00", "FILTER_NAME": ("CL1", band),
                     "DATA_CONVERSION_TYPE": conversion, "INSTRUMENT_ID": "ISSNA", "TARGET_NAME": "PHOEBE",
                     "path": f"nac_data/N{t}_1.png"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return np.ones((H, H), bool)

    def export(self):
        return self.info["path"]


def iof_of(band):
    im = 0.0005 + rng.normal(0, 0.0003, (H, H))
    im[disk] += BODY[band]
    return im


def frames(conversions):
    out = {}
    for t, (band, conv) in enumerate(zip(("RED", "GRN", "BL1"), conversions)):
        iof = iof_of(band)
        png = np.clip(iof / 0.1 * 254, 0, 254).astype(np.uint8)
        out[f"nac_data/N{t}_1.png"] = (Label(band, conv, t), png, iof)
    return out


def run(conversions):
    made = frames(conversions)
    stacking.load_stacked = lambda path, window=120, max_frames=5, count=False: (made[path][0], made[path][1], 1)
    # 8LSB frames can't be unstretched (calibration.unstretch); the others come back as their I/F
    cal.calibrate = lambda png, info, image=None: None if info["DATA_CONVERSION_TYPE"] == "8LSB" else \
        next(v[2] for v in made.values() if v[0].info is info)
    cal.ds.imread = lambda path, flags=None: made[path][1]
    return color_image.load_aligned(list(made))


for look in ("balanced", "classic"):
    with cal.looking(look):
        imgs, valid, lbl, report = run(["TABLE", "TABLE", "TABLE"])
        assert len(imgs) == 3 and report["calibrated"] and "dropped" not in report, report
        imgs, valid, lbl, report = run(["TABLE", "TABLE", "8LSB"])
        print(look, "report", {k: report[k] for k in ("calibrated", "dropped")})
        assert report["calibrated"] and report["dropped"] == ["N2_1"], report and len(imgs) == 2
        # the two kept channels are on one scale: red stays brighter than green, as the camera measured
        r, g = (float(np.mean(im[disk][..., 0] if im.ndim == 3 else im[disk])) for im in imgs)
        print(look, "body red", round(r, 1), "green", round(g, 1))
        assert r > g * 1.1
        # one good channel left is not a color picture: the old fallback (each frame its own stretch)
        imgs, valid, lbl, report = run(["TABLE", "8LSB", "8LSB"])
        assert len(imgs) == 3 and not report["calibrated"] and "dropped" not in report
print("ok")
