"""The shutter offset (calibration.shutter_offsets, CISSCAL's DivideByExpot): the per-sample offset file for the camera
and optics temperature, averaged over a summed pixel's samples as IDL's REBIN does, drawn out to a resized image's
width, the straight line without the files; and calibrate dividing by the exposure less the offset and the constant.
Run: python web/test_shutter_offset.py"""
import os
import sys
import tempfile
import numpy as np

root = tempfile.mkdtemp()
os.environ["CASSINI_CISSCAL"] = root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import flat_field as ff  # noqa: E402

cal.ds._lut8 = True


def write_row(path, row):
    head = (f"Object = IsisCube\n  Object = Core\n    StartByte   = 65537\n    Format      = Tile\n"
            f"    TileSamples = 1024\n    TileLines   = 1\n    Group = Dimensions\n      Samples = 1024\n"
            f"      Lines   = 1\n      Bands   = 1\n    End_Group\n    Group = Pixels\n      Type       = Real\n"
            f"      ByteOrder  = Lsb\n      Base       = 0.0\n      Multiplier = 1.0\n    End_Group\n  End_Object\n"
            f"End_Object\nEnd\n").encode().ljust(65536, b" ")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(head + np.asarray(row, "<f4").tobytes())


s = np.arange(1024)
rows = {t: 0.15 - 0.33 * s / 1023 + 0.04 * np.sin(s / 90.0) + k for k, t in ((0.0, "m10"), (-0.02, "p5"), (0.05, "p25"))}
for t, row in rows.items():
    write_row(f"{root}/offset/nacfm_so_{t}.full.cub", row)

INFO = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": '("CL1","GRN")', "GAIN_MODE_ID": "29 ELECTRONS PER DN",
        "INSTRUMENT_MODE_ID": "FULL", "EXPOSURE_DURATION": "5.0", "DATA_CONVERSION_TYPE": "12BIT",
        "BIAS_STRIP_MEAN": "12.0", "SHUTTER_STATE_ID": "ENABLED", "OPTICS_TEMPERATURE": "(6.09,1.9)",
        "TARGET_NAME": "VENUS", "IMAGE_TIME": "1999-175T20:20:51.603", "IMAGE_NUMBER": "1308947273"}

# the file for the optics temperature, as CISSCAL names it (below -5 C: m10, below 25 C: p5, else p25)
assert np.allclose(cal.shutter_offsets(INFO, 1024), rows["p5"], atol=1e-6)
assert np.allclose(cal.shutter_offsets({**INFO, "OPTICS_TEMPERATURE": "(-8.0,1.9)"}, 1024), rows["m10"], atol=1e-6)
assert np.allclose(cal.shutter_offsets({**INFO, "OPTICS_TEMPERATURE": "(26.0,1.9)"}, 1024), rows["p25"], atol=1e-6)
# a SUM2 frame: IDL's REBIN to 512 samples, the mean of each pair
assert np.allclose(cal.shutter_offsets(INFO, 512), rows["p5"].reshape(512, 2).mean(axis=1), atol=1e-6)
# an image resized wider than the camera: drawn out
wide = cal.shutter_offsets(INFO, 2048)
assert wide.shape == (2048,) and abs(wide[1000] - rows["p5"][500]) < 0.01
# the WAC's files are missing here: the straight line, as before
assert np.allclose(cal.shutter_offsets({**INFO, "INSTRUMENT_ID": "ISSWA"}, 1024), np.linspace(-0.5339, -0.6368, 1024))

# calibrate: a flat scene of DN 1000 over the bias comes out inversely proportional to the true exposure per sample,
# exposure - offset(sample) - 2.75 ms (DivideByExpot)
mids = (cal.LUT[:-1] + cal.LUT[1:]) / 2
codes = np.full((64, 1024), np.searchsorted(mids, 1012.0), np.uint8)   # the lean archive's stored code for DN 1012
iof = cal.calibrate(codes, INFO)
true = 5.0 - rows["p5"] - cal.SHUTTER_OFFSET["ISSNA"]
ratio = iof.mean(axis=0) * true
assert np.std(ratio) / np.mean(ratio) < 2e-3, np.std(ratio) / np.mean(ratio)
print("shutter offset: per sample from the file, ok")
