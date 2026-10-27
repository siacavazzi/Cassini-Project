"""The dark current step (dark_current.py, calibration.calibrate's "dark" step) against cisscal's own line by line sum
(DarkCurrent::MakeManyLineDark, written out here the slow way), on synthetic dark parameter maps and a hot pixel list
in a synthetic CISSCAL folder; the readout model's line times; and the overclocked pixels' bias fit from a frame's
line prefixes. Run: python web/test_dark_current.py"""
import gzip
import os
import sys
import tempfile
import numpy as np
from scipy.interpolate import CubicSpline

root = tempfile.mkdtemp()
data = tempfile.mkdtemp()
os.environ["CASSINI_CISSCAL"] = root
os.environ["CASSINI_DATA"] = data
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import dark_current as dc  # noqa: E402

cal.ds._lut8 = True
os.makedirs(os.path.join(data, "nac_data"))
open(os.path.join(data, "nac_data", "FORMAT.txt"), "w").write("lean archive\n")


def write_cube(path, a, tile=128):
    bands, lines, samples = a.shape
    head = (f"Object = IsisCube\n  Object = Core\n    StartByte   = 65537\n    Format      = Tile\n"
            f"    TileSamples = {tile}\n    TileLines   = {tile}\n    Group = Dimensions\n      Samples = {samples}\n"
            f"      Lines   = {lines}\n      Bands   = {bands}\n    End_Group\n    Group = Pixels\n"
            f"      Type       = Real\n      ByteOrder  = Lsb\n      Base       = 0.0\n      Multiplier = 1.0\n"
            f"    End_Group\n  End_Object\nEnd_Object\nEnd\n").encode().ljust(65536, b" ")
    tiles = a.astype("<f4").reshape(bands, lines // tile, tile, samples // tile, tile).transpose(0, 1, 3, 2, 4)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(head + tiles.tobytes())


rng = np.random.default_rng(3)
L = 256
# charge at the 8 grid times: growing with time, different per pixel, a few negative at 0 s
params = np.cumsum(rng.uniform(0, 60, (8, L, L)), axis=0) - 20
write_cube(f"{root}/darkcurrent/nac_dark_parameters.sum4.cub", params)
write_cube(f"{root}/darkcurrent/wac_dark_parameters.sum4.cub", params)
open(f"{root}/darkcurrent/NAC_hotpix2006.9_140219.tab", "w").write("""PDS_VERSION_ID = PDS3
END
\\begindata
      0.00000      0.00000      0.00000      10.0000      32.0000      100.000      560.000      1200.00
      0.00000      0.00000      12.8410      12.8410      30.2700      30.2700      30.2700      30.2700
      213.000      482.000      189.614      12990.4      40637.0      110559.      123456.      123459.      4.00000
      98.0000      87.0000      99.0105      8179.26      25626.9      72210.8      123472.      123459.      -1.0000
      37.0000      647.000      191.056      8456.93      26091.1      71734.7      123469.      123462.      0.00000
""")
open(f"{root}/darkcurrent/NAC_hotpix2014.3_171204.tab", "w").write(open(f"{root}/darkcurrent/NAC_hotpix2006.9_140219.tab").read())

INFO = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": '("CL1","CB3")', "GAIN_MODE_ID": "95 ELECTRONS PER DN",
        "INSTRUMENT_MODE_ID": "SUM4", "EXPOSURE_DURATION": "46000.0", "DATA_CONVERSION_TYPE": "12BIT",
        "BIAS_STRIP_MEAN": "100.0", "SHUTTER_STATE_ID": "ENABLED", "INST_CMPRS_TYPE": "LOSSLESS",
        "INST_CMPRS_RATIO": "2.4", "INSTRUMENT_DATA_RATE": "182.783997", "READOUT_CYCLE_INDEX": "10",
        "DELAYED_READOUT_FLAG": "NO", "FLIGHT_SOFTWARE_VERSION_ID": "1.4", "TARGET_NAME": "TITAN",
        "IMAGE_TIME": "2006-182T23:23:23.444Z", "IMAGE_NUMBER": "1530489265", "LINES": str(L), "LINE_SAMPLES": str(L)}

r = dc.readout(INFO)
assert r is not None and r[-1] == "NAC_hotpix2006.9_140219.tab"                   # the nearest epoch
assert dc.readout({**INFO, "IMAGE_TIME": "2013-300T00:00:00"})[-1] == "NAC_hotpix2014.3_171204.tab"
assert dc.readout({**INFO, "READOUT_CYCLE_INDEX": "UNKNOWN"}) is None
assert dc.readout({**INFO, "GAIN_MODE_ID": "95ELECTRONSPERDN"}) == r                    # as label_handler gives it
assert dc.readout({**INFO, "INSTRUMENT_DATA_RATE": "-999.0"}) is None
t = np.array([dc.line_time(r, i + 1) for i in range(L)])
assert abs(t[0] - (46.020 + 0.68 * 255 / 256)) < 1e-9 and 46.7 < t[-1] < 50 and (np.diff(t) > 0).all()  # exposure, erase, readout
print("line times", round(t[0], 3), "...", round(t[-1], 3))


def neighborhood(tg, y, a):
    """cisscal's CubicNeighborhood: the natural spline through the 4 grid points round a"""
    a = min(max(a, tg[0]), tg[-1])
    s = max([n for n in range(len(tg)) if tg[n] < a], default=0)
    s = min(max(s, 1), len(tg) - 3)
    return float(CubicSpline(tg[s - 1:s + 3], y[s - 1:s + 3], bc_type="natural")(a))


def slow(r):
    """MakeManyLineDark and ComputeDarkDN as cisscal writes them, line by line, on the maps with the hot pixels in"""
    p = params.astype(np.float64).copy()
    for y, x, curve in dc._hot_pixels(f"{root}/darkcurrent/{r[-1]}", L):
        p[:, y, x] = curve
    t = [dc.line_time(r, i + 1) for i in range(L)]
    eye = np.eye(8)
    coef = {}                                   # the spline differences for a span, worked out once per span
    dark = np.zeros((L, L))
    for j in range(L):
        temp = p[0, j].copy()
        for k in range(j + 1):
            end = t[j - k]
            start = t[j - k - 1] if k < j else 0.0
            end = start + max(end - start, 0.0)
            if (start, end) not in coef:
                coef[start, end] = [neighborhood(dc.TGRID, eye[b], end) - neighborhood(dc.TGRID, eye[b], start)
                                    for b in range(8)]
            for b, c in enumerate(coef[start, end]):
                if c:
                    temp += c * p[b, k]
        dark[j] = temp
    med = dark.copy()
    for j in range(2, L - 2):
        med[j] = np.median(dark[j - 2:j + 3], axis=0)
    dark = np.where(med - dark > 10, med, dark)
    dn = dark / (30.27 / 0.309569)
    return np.where((dn >= 4095) | (dark >= 123700), 4095, dn)


fast = dc.dark_dn(INFO)
want = slow(r)
err = np.abs(fast - want).max()
print("dark DN", round(float(np.median(fast)), 3), "max difference to the line by line sum", err)
assert fast.shape == (L, L) and err < 1e-3 * max(1.0, np.abs(want).max())
assert fast[int(482 / 4), int(213 / 4)] > 50 * np.median(fast)                     # a hot pixel
assert dc.dark_dn({**INFO, "INSTRUMENT_ID": "ISSWA", "GAIN_MODE_ID": "29 ELECTRONS PER DN"}) is not None
print("dark ok")

# a frame of flat Titan at DN 900 over a bias of 100 plus the dark: calibrate takes both out, and the line prefixes'
# overclocked pixels give a bias that drifts down the frame
lines_bias = 100 + np.linspace(0, 6, L)
dn = 900 + lines_bias[:, None] + fast
mids = (cal.LUT[:-1] + cal.LUT[1:]) / 2
codes = np.searchsorted(mids, dn).astype(np.uint8)
fid = "N1530489265_1"
import cv2  # noqa: E402
cv2.imwrite(os.path.join(data, "nac_data", fid + ".png"), codes)
prefix = np.zeros((L, 24), np.uint8)
prefix[:, 2:4] = np.frombuffer(np.full(L, L, ">u2").tobytes(), np.uint8).reshape(L, 2)
oc = np.round(lines_bias).astype(">i2")       # sum4: both overclocks at the bias, averaged
prefix[:, 12:14] = np.frombuffer(oc.tobytes(), np.uint8).reshape(L, 2)
prefix[:, 22:24] = prefix[:, 12:14]
prefix[40:44] = 0                              # lines lost in downlink: left out of the fit
open(os.path.join(data, "nac_data", fid + ".prefix.gz"), "wb").write(gzip.compress(prefix.tobytes()))
info = {**INFO, "path": f"nac_data/{fid}.LBL"}
fit = cal.overclock_bias(info)
assert np.abs(fit - lines_bias).max() < 0.6, np.abs(fit - lines_bias).max()
assert cal.overclock_bias({**info, "INST_CMPRS_TYPE": "LOSSY"}) is None
with cal.stepping("flat"):
    on = cal.calibrate(codes, info)
    with cal.stepping("flat,dark"):
        off = cal.calibrate(codes, info)
hot = (int(482 / 4), int(213 / 4))
print("hot pixel over the frame: dark on", round(float(on[hot] / np.median(on)), 3),
      "off", round(float(off[hot] / np.median(off)), 3))
assert abs(on[hot] / np.median(on) - 1) < 0.05 < off[hot] / np.median(off) - 1    # the hot pixel gone
assert np.std(on[5:-5].mean(axis=1)) / np.median(on) < 0.005                        # no ramp down the frame
assert cal.variant() == ""
with cal.stepping("dark"):
    assert cal.variant() == "-off-dark"
print("ok")
