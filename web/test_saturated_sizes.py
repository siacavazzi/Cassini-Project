"""A color set whose frames are stored at different sizes (a summed 512 px frame among 1024 px ones, the Jupiter set
N1356864915_2 + N1356865196_2 + N1356864947_2; c32, N1353557510_1 + N1353557402_1 + N1353557567_1, whose summed
frame is the saturated one) with a saturated pixel in one channel: each channel's saturated mask is put on the
channels' grid before the fill (color_image.load_aligned, calibration.fill_saturated). It used to stop with "operands
could not be broadcast together with shapes (1024,1024) (512,512)" (#241), which load_aligned took for an alignment
failure: the set came out aligned "failed" and was drawn grey. Synthetic frames through color_image.load_aligned.
Run: python web/test_saturated_sizes.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import stacking  # noqa: E402

H = 256
rng = np.random.default_rng(3)
yy, xx = np.mgrid[:H, :H]
disk = (yy - 128) ** 2 + (xx - 128) ** 2 < 80 ** 2
BODY = {"RED": 0.5, "GRN": 0.45, "BL1": 0.4}


class Label:
    def __init__(self, band, t, side):
        self.side = side
        self.info = {"PRODUCT_ID": f"N{t}_2", "IMAGE_TIME": f"2000-350T10:{t:02d}:00", "FILTER_NAME": f"(CL1,{band})",
                     "DATA_CONVERSION_TYPE": "TABLE", "INSTRUMENT_ID": "ISSNA", "TARGET_NAME": "JUPITER",
                     "path": f"nac_data/N{t}_2.png"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return np.ones((H, H), bool)

    def export(self):
        return self.info["path"]


def run(summed, saturated):
    """summed: the band stored at half size; saturated: the band saturated on the body's bright side"""
    made = {}
    for t, band in enumerate(("RED", "GRN", "BL1")):
        side = H // 2 if band == summed else H
        iof = (0.001 + rng.normal(0, 0.0003, (H, H)) + np.where(disk, BODY[band], 0)).astype(np.float32)
        shown = np.clip(iof / 0.6 * 254, 0, 254).astype(np.uint8)
        if band == saturated:
            shown[disk & (xx > 150)] = 255
        codes = shown[::H // side, ::H // side]
        made[f"nac_data/N{t}_2.png"] = (Label(band, t, side), np.dstack([shown] * 3), iof, codes)
    stacking.load_stacked = lambda path, window=120, max_frames=5, count=False, valid=False: \
        (made[path][0], made[path][1], 1) + ((made[path][0].valid_mask(),) if valid else ())
    cal.calibrate = lambda png, info, image=None: next(v[2] for v in made.values() if v[0].info is info)
    cal.ds.imread = lambda path, flags=None: made[path][3]
    with cal.looking("balanced"):
        imgs, valid, lbl, report = color_image.load_aligned(list(made))
    print("summed %s, saturated %s: aligned %s" % (summed, saturated, report["aligned"]))
    assert report["calibrated"] and len(imgs) == 3 and all(im.shape[:2] == (H, H) for im in imgs), report
    assert "failed" not in report["aligned"] and not report.get("grey"), report     # not taken for a failed alignment
    red, blue = (imgs[i][..., 0].astype(int) for i in (0, 2))
    side = disk & (xx > 160) & (xx < 200)
    print("  bright side red - blue %d (filled, not clipped)" % np.median(red[side] - blue[side]))
    assert np.median(red[side] - blue[side]) >= 0


cal.saturated = lambda codes, info, image=None: np.asarray(codes if image is None else image) >= 255
run("GRN", "RED")      # the Jupiter set: a summed frame with nothing saturated among full ones
run("BL1", "BL1")      # c32: the summed frame is the saturated one
run("GRN", "GRN")
print("ok")
