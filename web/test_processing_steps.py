"""Settings > Processing: each pipeline step turned off on its own (calibration.stepping, the picture routes' off=)
does what it says, through the pipeline's own functions, and the cache names of pictures made with every step on are
the ones they had before. Synthetic frames. Run: python web/test_processing_steps.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import threading
import numpy as np
import obs_mosaic  # noqa: E402  (puts the repo on the path)
import reel  # noqa: E402
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import stacking  # noqa: E402

# every step on: no variant, and the cache folders keep their names (the pre-built cache stays valid)
assert cal.variant() == "" and all(cal.step(s) for s in cal.STEPS)
assert reel.version() == reel.VERSIONS["balanced"] + "-q95"
u = {"key": ("SATURN", "ISS_OBS", "N"), "repeat_gap": obs_mosaic.mosaic_benchmark.REPEAT_GAP}
assert obs_mosaic.folder(u, "/c") == f"/c/{obs_mosaic.VERSIONS['balanced']}-q{obs_mosaic.QUALITY}/SATURN_ISS_OBS_N"
# steps off: one name per set of steps whatever the order asked, unknown names ignored
with cal.stepping("align,stack,bogus"):
    assert cal.variant() == "-off-stack-align" and not cal.step("stack") and cal.step("hdr")
    assert obs_mosaic.folder(u, "/c") == f"/c/{obs_mosaic.VERSIONS['balanced']}-off-stack-align-q{obs_mosaic.QUALITY}/SATURN_ISS_OBS_N"
    assert reel.version() == reel.VERSIONS["balanced"] + "-off-stack-align-q95"
    m = cal.mode()
assert cal.variant() == ""
# the mode carries to another thread (obs_mosaic's background makers)
seen = []


def other():
    with cal.in_mode(m):
        seen.append(cal.variant())


t = threading.Thread(target=other)
t.start(); t.join()
assert seen == ["-off-stack-align"], seen

# ---------- load_aligned: calibrate, fill and align ----------
H = 128
rng = np.random.default_rng(3)
yy, xx = np.mgrid[:H, :H]


class Label:
    def __init__(self, band, t, exposure=100.0):
        self.band = band
        self.info = {"PRODUCT_ID": f"N{t}_1", "IMAGE_TIME": f"2005-02-17T05:{t:02d}:00", "FILTER_NAME": ("CL1", band),
                     "DATA_CONVERSION_TYPE": "TABLE", "INSTRUMENT_ID": "ISSNA", "TARGET_NAME": "ENCELADUS",
                     "EXPOSURE_DURATION": exposure, "GAIN_MODE_ID": "12 ELECTRONS PER DN", "INSTRUMENT_MODE_ID": "FULL",
                     "path": f"nac_data/N{t}_1.png"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        m = np.ones((H, H), bool)
        m[40:44] = False   # four lines lost in downlink
        return m

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return made[self.info["path"]][1]


made = {}
for t, (band, dx) in enumerate((("RED", 0), ("GRN", 6), ("BL1", 12))):
    disk = (yy - 64) ** 2 + (xx - 50 - dx) ** 2 < 25 ** 2   # the body moves 6 px between channels
    iof = 0.0005 + rng.normal(0, 0.0003, (H, H))
    iof[disk] += 0.4
    png = np.clip(iof / 0.5 * 254, 0, 254).astype(np.uint8)
    png[40:44] = 0
    made[f"nac_data/N{t}_1.png"] = (Label(band, t), png, iof)
stacking.load_stacked = lambda path, window=120, max_frames=5, count=False: (made[path][0], made[path][1].copy(), 1)
cal.calibrate = lambda png, info, image=None: next(v[2] for v in made.values() if v[0].info is info)
cal.ds.imread = lambda path, flags=None: made[path][1]


def run(off=""):
    with cal.stepping(off):
        return color_image.load_aligned(list(made))


imgs, valid, _, rep = run()
assert rep["calibrated"] and "off" not in rep["aligned"] and "filled" not in rep, rep
assert not valid[40:44].any()   # lost lines stay out of the picture's coverage either way
imgs, valid, _, rep = run("calibrate")
assert not rep["calibrated"], rep
imgs, valid, _, rep = run("align")
assert rep["aligned"] == ["off"] * 3, rep
imgs, valid, _, rep = run("fill")
assert rep.get("filled") is False
print("load_aligned: calibrate, align, fill ok")

# ---------- stacking: plain stack and HDR ----------
asked = []
repeats = {"a.png": [("a.png", 100.0), ("b.png", 100.0), ("c.png", 10.0)]}
labels = {p: Label("CL2", i, e) for i, (p, e) in enumerate(repeats["a.png"])}
for p, lb in labels.items():
    lb.info["path"] = p
    made[p] = (lb, np.full((H, H), 100, np.uint8), np.full((H, H), 0.1, np.float32))
stacking.find_repeats = lambda path, window=120, max_frames=5: asked.append(max_frames) or [p for p, _ in repeats[path]][:max_frames]
stacking.lh.label = lambda p, as_png=True: labels[p]
stacking.ic.find_shift = lambda a, b, r: None
cal.saturated = lambda codes, info, image=None: np.zeros(codes.shape, bool)
stacking.cal = cal
_, _, n = stacking.load_hdr("a.png")
assert n == 3, n                                   # every exposure of the bracket
with cal.stepping("hdr"):
    _, _, n = stacking.load_hdr("a.png")
    assert n == 2, n                               # only the identical ones: a plain stack
with cal.stepping("stack"):
    _, _, n = stacking.load_hdr("a.png")
    assert n == 1 and asked[-1] == 1, (n, asked)   # the frame alone
print("load_hdr: hdr, stack ok")
print("ok")
