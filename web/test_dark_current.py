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
# (the full resolution maps; a SUM4 frame's are their 4x4 block sums, as cisscal makes them)
full_params = (np.cumsum(rng.uniform(0, 60, (8, L, L)), axis=0) - 20).repeat(4, 1).repeat(4, 2) / 16
full_params += rng.uniform(-0.5, 0.5, full_params.shape)
params = full_params.reshape(8, L, 4, L, 4).sum(axis=(2, 4))
write_cube(f"{root}/darkcurrent/nac_dark_parameters.full.cub", full_params)
write_cube(f"{root}/darkcurrent/wac_dark_parameters.full.cub", full_params)
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

open(f"{root}/darkcurrent/WAC_hotpix2006.9_140219.tab", "w").write(open(f"{root}/darkcurrent/NAC_hotpix2006.9_140219.tab").read())
# the NAC's lists are left out by default (they over-predict its hot pixels), the WAC's are used
assert dc.readout(INFO)[-1] == ""
assert dc.readout({**INFO, "INSTRUMENT_ID": "ISSWA"})[-1] == "WAC_hotpix2006.9_140219.tab"
smooth = dc.dark_dn(INFO)
assert smooth is not None and smooth.max() < 2 * np.median(smooth)    # the NAC's maps taken through a 3x3 median
dc._parameters.cache_clear(); dc._dark.cache_clear()
dc.HOT_PIXEL_CAMERAS = ("ISSNA", "ISSWA")     # the rest checks cisscal's own model, on the NAC maps as they are
dc.SMOOTH_MAP_CAMERAS = ()
r = dc.readout(INFO)
assert r is not None and r[-1] == "NAC_hotpix2006.9_140219.tab"                   # the nearest epoch
assert dc.readout({**INFO, "IMAGE_TIME": "2013-300T00:00:00"})[-1] == "NAC_hotpix2014.3_171204.tab"
assert dc.readout({**INFO, "READOUT_CYCLE_INDEX": "UNKNOWN"}) is None
assert dc.readout({**INFO, "GAIN_MODE_ID": "95ELECTRONSPERDN"}) == r                    # as label_handler gives it
assert dc.readout({**INFO, "INSTRUMENT_DATA_RATE": "-999.0"}) == r                 # an odd rate is taken as 24 pps
assert dc.readout({**INFO, "INSTRUMENT_DATA_RATE": "243.5"})[7] == 32
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
    """makedarkarray and the DN conversion as cisscal writes them, line by line, on the full resolution maps with
    the hot pixels in, summed over 4x4 blocks"""
    p = full_params.astype(np.float32).astype(np.float64)
    for y, x, curve in dc._hot_pixels(f"{root}/darkcurrent/{r[-1]}"):
        p[:, y, x] = curve
    p = p.reshape(8, L, 4, L, 4).sum(axis=(2, 4))
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

# cisscal's WAC_hotpix2014.3 and 2015.7 lists have NaN at 1200 s for some pixels: the time is skipped, and the dark
# (whose FFT down each column would carry one NaN into the whole column) stays finite
open(f"{root}/darkcurrent/WAC_hotpix2015.7_171204.tab", "w").write(
    open(f"{root}/darkcurrent/NAC_hotpix2006.9_140219.tab").read().replace("123459.      4.00000", "NaN          4.00000")
    .replace("123459.      -1.0000", "NaN          -1.0000"))
dc._hot_lists.cache_clear()
late = {**INFO, "INSTRUMENT_ID": "ISSWA", "IMAGE_TIME": "2015-200T00:00:00"}
assert dc.readout(late)[-1] == "WAC_hotpix2015.7_171204.tab"
hot = dc._hot_pixels(f"{root}/darkcurrent/WAC_hotpix2015.7_171204.tab")
assert len(hot) == 2 and all(np.isfinite(c).all() for _, _, c in hot)
dc._parameters.cache_clear(); dc._dark.cache_clear()
d = dc.dark_dn(late)
assert d is not None and np.isfinite(d).all(), "NaN in the WAC dark"
assert d[int(482 / 4), int(213 / 4)] > 50 * np.median(d)                           # the hot pixel still in
print("NaN in a hot pixel list ok")

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
# a partial downlink can keep a line's pixel count but garble its prefix (N1413937500_2's line 129: -8,155 DN): that
# line is left out of the fit, which otherwise tilts the bias by tens of DN down the frame
garbled = prefix.copy()
garbled[128, 12:14] = np.frombuffer(np.array([-32694], ">i2").tobytes(), np.uint8)
garbled[128, 22:24] = np.frombuffer(np.array([220], ">i2").tobytes(), np.uint8)
open(os.path.join(data, "nac_data", fid + ".prefix.gz"), "wb").write(gzip.compress(garbled.tobytes()))
assert np.abs(cal.overclock_bias(info) - lines_bias).max() < 0.6, np.abs(cal.overclock_bias(info) - lines_bias).max()
open(os.path.join(data, "nac_data", fid + ".prefix.gz"), "wb").write(gzip.compress(prefix.tobytes()))
with cal.stepping("flat,hotpix"):
    on = cal.calibrate(codes, info)
    with cal.stepping("flat,dark,hotpix"):
        off = cal.calibrate(codes, info)
hot = (int(482 / 4), int(213 / 4))
print("hot pixel over the frame: dark on", round(float(on[hot] / np.median(on)), 3),
      "off", round(float(off[hot] / np.median(off)), 3))
assert abs(on[hot] / np.median(on) - 1) < 0.05 < off[hot] / np.median(off) - 1    # the hot pixel gone
assert np.std(on[5:-5].mean(axis=1)) / np.median(on) < 0.005                        # no ramp down the frame
with cal.stepping("flat,dark"):                     # the hotpix step alone repairs it too
    assert abs(cal.calibrate(codes, info)[hot] / np.median(on) - 1) < 0.05
assert cal.variant() == ""
with cal.stepping("hotpix"):
    assert cal.variant() == "-off-hotpix"

# repair_hot: the listed pixels of a SUM4 frame, drawn 4x4 by resize_image, put back to the sky; a sky pixel that
# isn't listed, and a listed one that isn't hot, left alone
sky = np.random.default_rng(5).normal(100, 2, (1024, 1024)).astype(np.float32)
img = sky.copy()
img[480:484, 212:216] = 900                    # listed (213, 482): hot
img[84:88, 96:100] = 50                         # listed (98, 87): darker than the sky round it, so not hot here
img[600:604, 300:304] = 900                     # not listed: a star
assert dc.repair_hot(img, INFO) in (1, 2)       # (213, 482), and (37, 647) if its sky is above its 3x3's median
assert abs(img[480:484, 212:216].mean() - 100) < 2 and (img[84:88, 96:100] == 50).all() and (img[600:604, 300:304] == 900).all()
full = sky.copy()
full[482, 213] = 900
assert dc.repair_hot(full, {**INFO, "LINES": "1024", "INSTRUMENT_MODE_ID": "FULL"}) >= 1 and abs(full[482, 213] - 100) < 8
assert (full[481, 212:215] == sky[481, 212:215]).all()      # only the pixel itself

# the defect maps measured from the archive: dots that stay put while the scene moves, found and repaired
rng = np.random.default_rng(9)
frames = []
for n in range(12):
    f = rng.normal(60, 3, (256, 256)).astype(np.float32)
    f[rng.integers(0, 256, 40), rng.integers(0, 256, 40)] += 80         # stars, somewhere else in every frame
    f[150, 150] += 60                                                   # hot
    f[160, 170] -= 40                                                   # dead
    frames.append(f)
found = {tuple(r) for r in dc.defects(frames)}
assert (150, 150, 1) in found and (160, 170, -1) in found and len(found) < 6, found
np.savez(os.path.join(root, "hot_maps.npz"), **{dc.map_key("ISSNA", "SUM4", 2006 * 12 + 8, 1): np.array(sorted(found), np.int16),
                                                dc.map_key("ISSNA", "SUM4", 2006 * 12 + 6, 3): np.zeros((0, 3), np.int16)})
dc._hot_maps.cache_clear()
assert dc.map_key("ISSNA", "SUM4", 2006 * 12 + 8, 1) == "ISSNA_SUM4_2006-09_1"
assert [dc.exposure_band(t) for t in (1, 2, 46, 60, 220)] == [None, 0, 1, 2, 3]
assert dc.hot_map(INFO) is not None and len(dc.hot_map(INFO)) == len(found)    # 46 s: band 1, September's, 2 months off
assert len(dc.hot_map({**INFO, "EXPOSURE_DURATION": "100000"})) == 0           # band 2 has none: the longer band 3 first
assert len(dc.hot_map({**INFO, "EXPOSURE_DURATION": "220000"})) == 0           # its own band, July
assert dc.hot_map({**INFO, "IMAGE_TIME": "2007-001T00:00:00"}) is None
# a defect that turned hot late in July is only in August's map: a July frame takes its band's maps of June to August
np.savez(os.path.join(root, "hot_maps.npz"), **{dc.map_key("ISSNA", "SUM4", 2006 * 12 + 6, 1): np.array([[10, 10, 1]], np.int16),
                                                dc.map_key("ISSNA", "SUM4", 2006 * 12 + 7, 0): np.array([[20, 20, 1]], np.int16),
                                                dc.map_key("ISSNA", "SUM4", 2006 * 12 + 7, 2): np.array([[40, 40, 1]], np.int16),
                                                dc.map_key("ISSNA", "SUM4", 2006 * 12 + 9, 1): np.array([[30, 30, 1]], np.int16)})
dc._hot_maps.cache_clear()
assert sorted(map(tuple, dc.hot_map(INFO))) == [(10, 10, 1), (20, 20, 1)]       # July, and August's shorter band; not a longer band, not October
np.savez(os.path.join(root, "hot_maps.npz"), **{dc.map_key("ISSNA", "SUM4", 2006 * 12 + 8, 1): np.array(sorted(found), np.int16),
                                                dc.map_key("ISSNA", "SUM4", 2006 * 12 + 6, 3): np.zeros((0, 3), np.int16)})
dc._hot_maps.cache_clear()
img = sky.copy()
img[600:604, 600:604] = 300                                         # native (150, 150)
img[640:644, 680:684] = 20                                          # native (160, 170)
dc.repair_hot(img, INFO)
assert abs(img[600:604, 600:604].mean() - 100) < 8 and abs(img[640:644, 680:684].mean() - 100) < 8
with cal.stepping("dark"):
    assert cal.variant() == "-off-dark"

# a hot pixel that has cooled since its list: the dark step takes its list curve out (the WAC's lists), so it lands
# below the sky, a black pinhole; repaired from the pixels round it where the dark stood out (dark_spots), left alone
# otherwise (a listed pixel darker than the sky with no more dark taken out than round it is just noise there)
low = sky.copy()
low[84:88, 96:100] = 20
dc.repair_hot(low, INFO)
assert (low[84:88, 96:100] == 20).all()
spots = np.zeros((L, L), bool)
spots[87 // 4, 98 // 4] = True                # listed (98, 87), at the SUM4 frame's own size
dc.repair_hot(low, INFO, spots)
assert abs(low[84:88, 96:100].mean() - 100) < 8
# and through calibrate: a WAC frame whose listed pixel gathered no more than the sky comes out at the sky, not black
wac = {**info, "INSTRUMENT_ID": "ISSWA", "GAIN_MODE_ID": "29 ELECTRONS PER DN", "FILTER_NAME": "(\"CL1\",\"CL2\")"}
dc._parameters.cache_clear(); dc._dark.cache_clear()
wdark = dc.dark_dn(wac)
smooth = wdark.copy()
smooth[int(482 / 4), int(213 / 4)] = np.median(wdark[int(482 / 4) - 2:int(482 / 4) + 3, int(213 / 4) - 2:int(213 / 4) + 3])
wdn = 900 + lines_bias[:, None] + smooth        # the pixel gathered only the dark round it
wcodes = np.searchsorted(mids, wdn).astype(np.uint8)
hot = (int(482 / 4), int(213 / 4))
with cal.stepping("flat,hotpix"):
    pinhole = cal.calibrate(wcodes, wac)
with cal.stepping("flat"):
    repaired = cal.calibrate(wcodes, wac)
print("cooled listed WAC pixel over the sky: hotpix off", round(float(pinhole[hot] / np.median(pinhole)), 3),
      "on", round(float(repaired[hot] / np.median(repaired)), 3))
assert pinhole[hot] < 0.5 * np.median(pinhole) and abs(repaired[hot] / np.median(repaired) - 1) < 0.05
print("ok")
