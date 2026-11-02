# -*- coding: utf-8 -*-
"""
Radiometric calibration of the Cassini ISS frames.

The PNGs in the dataset are not raw camera data. The PDS transform tool that made them
stretched every frame on its own so its darkest pixel became 0 and its brightest 254,
which throws away the exposure time, the gain and how sensitive each filter is. Put
three of those frames together as R, G and B and every channel is stretched to full
brightness no matter what the camera actually saw, so the colors come out wrong (and a
single cosmic ray hit can make a whole channel go dark).

This module undoes the stretch where the PNG still allows it and then follows the
CISSCAL pipeline (Porco et al. 2004, West et al. 2010, Knowles et al. 2020) as far as
the label allows:

  1. undo the PNG stretch (only possible for 8 bit "TABLE" frames, and for 12 bit
     frames whose brightest and darkest pixels are less than 254 DN apart)
  2. undo the camera's 12 -> 8 bit square root table
  3. subtract the bias: fitted down the frame from the overclocked pixels in each line's
     prefix where the archive has them (overclock_bias), else BIAS_STRIP_MEAN (as CISSCAL 4,
     also for 8-bit table frames under 12 e-/DN), and the 2 Hz noise (horizontal banding)
     line by line from the same overclocks (cisscal_noise.two_hz; the "twohz" step)
  4. subtract the dark current (dark_current.py; the "dark" step), then replace the
     anti-blooming bright/dark pixel pairs (cisscal_noise.bright_dark; the "pairs" step)
  5. correct the camera's nonlinearity (CISSCAL's linearize tables, by gain state)
  6. divide by the exposure time, corrected for the shutter offset
  7. take the flat field out: dust rings, mottle and the ground calibration's flat
     (flat_field.py, CISSCAL's own maps; the "flat" step, Settings > Processing)
     and put the detector's hot and dead pixels back to the sky round them
     (dark_current.repair_hot, the camera team's lists and maps measured from the archive;
     the "hotpix" step)
  8. scale by the gain state, the pixel summation and the sensor's decline over time
  9. divide by the filter's sensitivity to sunlight (filter_calibration.csv) and the
     distance from the sun, giving I/F

Not done: bit weights (the converter's uneven steps, under 1 DN, mostly lost in the 8-bit
archive). The 2 Hz and pixel pair steps come from CISSCAL 4.1's IDL (ISIS's cisscal leaves
them out); CISSCAL's optional image-mean 2 Hz method is not ported (its default is the
overclocks).

Frames that can't be unstretched return None and the caller keeps the old behavior.
"""
import contextlib
import contextvars
import datetime
import gzip
import json
import math
import os

import cv2
import numpy as np

import cisscal_noise as cn
import dark_current as dc
import data_source as ds
import flat_field as ff


# Inverse of the camera's 12 -> 8 bit table, from CISSCAL calib/lut/lut.tab
# (Appendix F1 of the ISS Ground Calibration Report)
LUT = np.array([
    1, 3, 5, 7, 9, 11, 14, 16, 19, 22, 25, 28, 31, 35, 38, 42, 46, 49, 53, 57, 61,
    65, 70, 74, 79, 83, 88, 93, 98, 103, 108, 113, 119, 125, 130, 136, 142, 148,
    154, 160, 166, 173, 179, 186, 193, 199, 206, 213, 221, 228, 236, 243, 251, 259,
    267, 275, 283, 291, 299, 307, 316, 324, 333, 342, 351, 360, 369, 379, 388, 398,
    407, 417, 427, 437, 447, 457, 467, 478, 488, 499, 509, 520, 531, 542, 554, 565,
    576, 588, 600, 611, 623, 635, 647, 659, 672, 684, 697, 709, 722, 735, 747, 761,
    774, 787, 801, 814, 828, 842, 856, 870, 884, 898, 912, 926, 941, 955, 970, 985,
    1000, 1015, 1030, 1045, 1061, 1076, 1092, 1108, 1124, 1140, 1156, 1172, 1188,
    1204, 1221, 1237, 1254, 1271, 1288, 1305, 1322, 1339, 1357, 1374, 1392, 1410,
    1428, 1446, 1464, 1482, 1500, 1518, 1537, 1555, 1574, 1593, 1612, 1631, 1650,
    1669, 1689, 1708, 1728, 1748, 1768, 1788, 1808, 1828, 1848, 1868, 1889, 1909,
    1930, 1951, 1971, 1993, 2014, 2035, 2057, 2078, 2100, 2121, 2143, 2165, 2187,
    2209, 2232, 2254, 2276, 2299, 2322, 2344, 2367, 2390, 2413, 2437, 2460, 2484,
    2507, 2531, 2555, 2579, 2603, 2627, 2651, 2676, 2700, 2725, 2749, 2774, 2799,
    2824, 2849, 2874, 2900, 2925, 2951, 2977, 3003, 3029, 3055, 3081, 3107, 3133,
    3160, 3186, 3213, 3239, 3266, 3293, 3321, 3348, 3375, 3403, 3430, 3458, 3486,
    3514, 3542, 3570, 3598, 3627, 3655, 3684, 3712, 3741, 3770, 3799, 3828, 3857,
    3887, 3916, 3946, 3976, 4005, 4035, 4065, 4095], dtype=np.float64)

# Gain state from GAIN_MODE_ID, and each state's gain relative to state 2 (CISSCAL
# cassimg__dntoelectrons.pro). filter_calibration.csv is for state 2.
GAIN_STATES = {"215": 0, "95": 1, "29": 2, "12": 3}
GAIN_RATIOS = {
    "ISSNA": [0.135386, 0.309569, 1.0, 2.357285],
    "ISSWA": [0.125446, 0.290637, 1.0, 2.360374],
}

# Nonlinearity (CISSCAL calib/linearize/<camera><gain state>.lut, cassimg_linearise.pro): at each tabulated DN
# (bias taken out) the factor the DN is multiplied by; between them linear, for every whole DN 0-4095
LINEARITY_TABLES = {
    "ISSNA": [
        [(0.0, 0.958), (75.0, 0.958), (221.7, 0.972), (294.2, 0.977), (366.6, 0.98), (440.4, 0.979),
         (855.1, 1.008), (1351.2, 0.957), (1522.0, 0.944), (1766.9, 0.976), (2012.0, 1.071), (2288.3, 1.13),
         (2819.3, 1.121), (3496.7, 1.068), (4096.0, 1.08)],
        [(0.0, 0.987), (121.4, 0.987), (200.3, 0.997), (281.1, 0.995), (401.4, 0.995), (801.9, 0.996),
         (1201.5, 0.997), (1439.5, 0.999), (1755.4, 1.001), (2068.9, 1.004), (2534.9, 1.008), (2997.4, 1.013),
         (3603.9, 1.02), (4096.0, 1.024)],
        [(0.0, 0.974), (34.8, 0.974), (102.7, 0.99), (203.3, 1.0), (272.0, 0.997), (407.8, 0.997), (815.1, 0.998),
         (1221.9, 0.998), (1493.0, 0.999), (1757.1, 1.003), (2165.0, 1.002), (2565.4, 1.004), (3092.6, 1.008),
         (3741.8, 1.014), (4096.0, 1.017)],
        [(0.0, 0.986), (71.6, 0.986), (212.7, 0.997), (282.8, 0.999), (354.0, 0.998), (423.4, 1.001),
         (849.8, 0.998), (1273.8, 0.998), (1415.4, 0.998), (1697.5, 0.999), (2118.3, 1.001), (2537.5, 1.002),
         (3091.9, 1.005), (3640.4, 1.009), (4096.0, 1.011)]],
    "ISSWA": [
        [(0.0, 0.885), (55.3, 0.885), (153.5, 0.957), (250.7, 0.976), (300.5, 0.977), (694.9, 0.986),
         (1167.7, 1.006), (1472.7, 0.997), (1805.8, 0.976), (2430.6, 1.047), (2844.5, 1.101), (3405.9, 1.092),
         (4096.0, 1.168)],
        [(0.0, 0.839), (30.3, 0.839), (182.4, 0.977), (257.6, 0.988), (359.6, 0.991), (765.0, 0.998),
         (1118.5, 1.001), (1619.2, 1.006), (1917.9, 1.009), (2312.8, 1.012), (2803.6, 1.017), (3384.3, 1.023),
         (4096.0, 1.029)],
        [(0.0, 0.915), (21.8, 0.915), (121.2, 0.985), (240.3, 0.994), (320.1, 0.995), (598.8, 0.997),
         (1034.9, 1.0), (1509.9, 1.002), (1827.8, 1.002), (2219.6, 1.004), (2687.7, 1.007), (3231.7, 1.01),
         (3902.4, 1.02), (4096.0, 1.02)],
        [(0.0, 0.895), (47.2, 0.895), (131.4, 0.965), (256.5, 0.989), (340.8, 0.992), (760.7, 1.0),
         (1012.1, 1.002), (1514.2, 1.005), (1848.6, 1.006), (2183.0, 1.007), (2681.0, 1.009), (3177.4, 1.011),
         (3830.6, 1.015), (4096.0, 1.016)]],
}
LINEARITY = {}


def linearity(camera, state):
    """Factor for every whole DN 0-4095 (index), for the camera and gain state (CISSCAL's Linearize)."""
    key = (camera, state)
    if key not in LINEARITY:
        dn, c = zip(*LINEARITY_TABLES[camera][state])
        LINEARITY[key] = np.interp(np.arange(4096), dn, c)
    return LINEARITY[key]


# Light collected by a summed pixel compared to a full resolution one
SUM_FACTORS = {"FULL": 1.0, "SUM2": 0.25, "SUM4": 0.0625}

# Shutter offset in ms (CISSCAL cassimg__dividebyexpot.pro): a constant from the 2013
# Rhea calibration plus a small slope across the frame, fit to offset/*fm_so_p5.
SHUTTER_OFFSET = {"ISSNA": 2.75, "ISSWA": 2.67}
SHUTTER_SLOPE = {"ISSNA": (0.1409, -0.1896), "ISSWA": (-0.5339, -0.6368)}  # first, last sample

# Sensitivity decline over the mission (Knowles et al. 2020, cassimg__sensvstime.pro)
SENSITIVITY = {"ISSNA": (1.89457e-10, 1.47036e9), "ISSWA": (9.28360e-11, 1.51463e9)}

# Orbits for the distance from the sun: semi-major axis (AU), eccentricity, a perihelion date
ORBITS = {
    "JUPITER": (5.2026, 0.0484, datetime.datetime(1999, 5, 20), 11.862),
    "SATURN": (9.5549, 0.0555, datetime.datetime(2003, 7, 26), 29.457),
}

_filters = None


def filter_table():
    global _filters
    if _filters is None:
        _filters = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filter_calibration.csv")
        with open(path) as f:
            next(f)
            for line in f:
                camera, filters, wavelength, factor, k = line.strip().split(",")
                _filters[(camera, filters)] = float(k)
    return _filters


def _value(info, key, default=None):
    value = info.get(key, default)
    if value is None:
        return default
    return str(value).replace('"', "").replace("<DEGC>", "")


def _filters_of(info):
    names = _value(info, "FILTER_NAME", "").strip("()").split(",")
    return [n.strip() for n in names]


"""
Distance between the sun and Saturn (or Jupiter, during the flyby) in AU, from a simple
Kepler orbit. Good to well under a percent, which is plenty here.
"""
def sun_distance(info):
    target = _value(info, "TARGET_NAME", "")
    time = _value(info, "IMAGE_TIME", "")
    try:
        date = datetime.datetime.strptime(time.replace("Z", "")[:17], "%Y-%jT%H:%M:%S")
    except ValueError:
        return None
    if target not in ORBITS:
        # Cassini spent the mission at Saturn, and was near Jupiter only in 2000-2001
        target = "JUPITER" if date.year < 2003 else "SATURN"
    a, e, perihelion, period = ORBITS[target]
    mean_anomaly = 2 * math.pi * ((date - perihelion).days / 365.25 / period % 1)
    E = mean_anomaly
    for _ in range(20):
        E = E - (E - e * math.sin(E) - mean_anomaly) / (1 - e * math.cos(E))
    return a * (1 - e * math.cos(E))


"""
Finds how many DN the frame spanned before it was stretched to 0-254.

A frame that spanned D DN can only have the 254 / D spaced levels round(k * 254 / D)
in its PNG, so the smallest D whose levels contain every level in the PNG is the span.
Returns None if the PNG has no gaps (the span was 254 DN or more).
"""
def recover_span(png):
    levels = np.unique(png)
    if len(levels) < 16:
        return None
    for span in range(len(levels) - 1, 254):
        # level k lands on round_half_up(k * 254 / span), done in integers so
        # halves are exact (a float tolerance let span 252 cover all 255 values)
        k = np.arange(span + 1)
        allowed = (2 * k * 254 + span) // (2 * span)
        if np.isin(levels, allowed).all():
            return span
    return None


"""
Turns a stretched PNG back into the camera's DN, or None if that can't be done.
image = optional image on the same scale as png (a resized or stacked version of it)
to convert instead of png itself
"""
def unstretch(png, info, image=None):
    conversion = _value(info, "DATA_CONVERSION_TYPE", "")
    if conversion not in ("TABLE", "12BIT"):
        return None  # 8LSB frames only kept the low 8 bits
    if ds.lut8():
        # the lean archive keeps the camera's codes, so nothing has to be guessed
        if image is None:
            return stored_values(png, info)
        low, high = stored_range(png, info)
        return np.asarray(image, dtype=np.float64) * (high - low) / 254.0 + low
    png = np.asarray(png, dtype=np.float64)
    span = recover_span(png)
    if span is None:
        if conversion != "TABLE":
            return None
        span = 254  # a TABLE frame spans at most 255 DN, so 254 is within 1 DN
    elif conversion == "12BIT" and len(np.unique(png)) < 0.75 * (span + 1):
        # too few levels to trust the gaps: a sparse frame with a big span can
        # leave gaps that happen to fit a small one
        return None

    # The darkest pixel's DN is unknown, but dark sky sits at the bias level, so put
    # the darkest 0.1% of the frame there
    bias = float(_value(info, "BIAS_STRIP_MEAN", "0"))
    offset = np.floor(png * span / 254.0 + 0.5)
    darkest = bias - np.percentile(offset, 0.1)
    if conversion == "TABLE":
        darkest = min(max(darkest, 0), 255 - span)
    if image is not None:
        offset = np.asarray(image, dtype=np.float64) * span / 254.0
    return offset + int(darkest)


"""
unstretch of each of the 256 codes (CODES) of a lean archive frame's 8-bit image, or of its PNG when image is None:
what unstretch gives a pixel of that code, to look the pixels up in (_lookup)
"""
def _unstretch_codes(png, info, image=None):
    if image is not None:
        return unstretch(png, info, CODES)
    if _value(info, "DATA_CONVERSION_TYPE", "") not in ("TABLE", "12BIT"):
        return None
    return stored_values(CODES, info)


"""
Lean archive (helper programs/convert_archive.py) only: what the camera sent for each
pixel, from the 8-bit codes in the PNG. TABLE frames were sent as the codes themselves,
12BIT frames as DN, which the archive squeezed into the same codes.
"""
def stored_values(codes, info):
    codes = np.asarray(codes)
    if _value(info, "DATA_CONVERSION_TYPE", "") == "12BIT":
        return LUT[codes]
    return codes.astype(np.float64)


# every 8-bit code, for working a per pixel step out once per code instead of once per pixel (_lookup)
CODES = np.arange(256, dtype=np.uint8)


"""
Lean archive only: the smallest and largest of stored_values(codes, info), from the codes' own smallest and largest
(both conversions keep the codes' order), so a frame's million pixels are not turned into floats just for two numbers
"""
def stored_range(codes, info):
    codes = np.asarray(codes)
    if codes.dtype != np.uint8 or not codes.size:
        stored = stored_values(codes, info)
        return stored.min(), stored.max()
    values = stored_values(CODES, info)
    return values[codes.min()], values[codes.max()]


"""
table[codes] for 8-bit codes: what a per pixel step gives each of the 256 codes (table, worked out on CODES with the
step's own arithmetic, so the same numbers), looked up for every pixel; cv2.LUT does that ten times quicker than numpy
"""
def _lookup(codes, table):
    if codes.ndim == 2 or (codes.ndim == 3 and codes.shape[2] in (3, 4)):
        return cv2.LUT(np.ascontiguousarray(codes), np.ascontiguousarray(table))
    return table[codes]


"""
Lean archive only: stretches a frame of codes min..max -> 0..254 the way the old
dataset PNGs were, so code written for those still sees the same images.
8LSB frames were copied from the old PNGs and are returned as they are.
"""
def display_stretch(codes, info):
    if _value(info, "DATA_CONVERSION_TYPE", "") not in ("TABLE", "12BIT"):
        return codes
    codes = np.asarray(codes)
    if codes.dtype != np.uint8 or not codes.size:
        stored = stored_values(codes, info)
        low, span = stored.min(), stored.max() - stored.min()
        if span <= 0:
            return np.zeros_like(codes)
        return np.floor((stored - low) * 254.0 / span + 0.5).astype(np.uint8)
    low, high = stored_range(codes, info)
    span = high - low
    if span <= 0:
        return np.zeros_like(codes)
    # the stretch of each code (the codes outside the frame's range are held to it: they are never looked up)
    stored = np.clip(stored_values(CODES, info), low, high)
    return _lookup(codes, np.floor((stored - low) * 254.0 / span + 0.5).astype(np.uint8))


"""
The frame's bias level, in the units of its stored values (DN for 12BIT frames, codes for TABLE ones): its bias
strip's mean. A frame that lost lines in transmission can lose its bias strip with them (a strip mean of 0 or
below, as in the last frames of the 2006-12-04 spoke movie, -235): in the lean archive, dark sky sits at the bias
level, so the darkest 0.1% of the frame is taken instead, leaving out the lost lines (code 0).
"""
def bias_of(png, info):
    bias = float(_value(info, "BIAS_STRIP_MEAN", "0"))
    lossy = _value(info, "INST_CMPRS_TYPE", "").upper() == "LOSSY"
    if lossy and _fsw(info) <= 1.3:
        bias = 0  # the SIS: a lossy frame's strip mean is not valid with flight software 1.2 and 1.3
    if bias <= 0 and ds.lut8():
        stored = stored_values(png, info)
        kept = stored[np.asarray(png) > 0]
        bias = float(np.percentile(kept, 0.1)) if kept.size else 0.0
    return bias


def _fsw(info):
    try:
        return float(_value(info, "FLIGHT_SOFTWARE_VERSION_ID", "0"))
    except ValueError:
        return 0.0


"""
The line-averaged overclocked pixels in DN, as cisscal's OverclockAvg gives them (ciss2isis ComputeOverclockAvg): the
two overclocked pixel sums each line's binary prefix carries (bytes 12-13 and 22-23, the lean archive's .prefix.gz),
averaged as the summing mode needs (one valid column before flight software 1.3), through the 12 -> 8 bit table for
TABLE frames, the first line taken from the second when it is over twice it. Returns (averages, kept): kept = the lines
whose overclocks can be used, leaving out lines lost in downlink (no valid pixels) and lines whose overclocks came down
garbled (OVERCLOCK_OUTLIER: more than 10 DN or 10 sigma from the frame's median; a partial downlink can keep a line's
count but not its prefix: N1413937500_2's line 129 reads -8,155 DN, which tilted the fitted bias by 36 DN down the
frame, a bright band at the top of a dark star field). Not as cisscal, which uses every line. None for a lossy frame
(cisscal reads no overclocks from those: they are corrupt) or when the prefixes aren't there.
"""
OVERCLOCK_OUTLIER = (10.0, 10.0)    # DN, robust sigmas: a line's overclock average further from the median than both
def overclock_avg(info):
    path = info.get("path")
    if not path or _value(info, "INST_CMPRS_TYPE", "").upper() == "LOSSY":
        return None
    base = str(path).split(".")[0]
    try:
        raw = gzip.decompress(ds.read_bytes(base + ".prefix.gz"))
    except Exception:
        return None
    lines = int(_value(info, "LINES", "0") or 0)
    if lines <= 0 or len(raw) % lines:
        return None
    prefix = np.frombuffer(raw, np.uint8).reshape(lines, -1)
    if prefix.shape[1] < 24:
        return None
    first = prefix[:, 12:14].copy().view(">i2")[:, 0].astype(np.float64)
    last = prefix[:, 22:24].copy().view(">i2")[:, 0].astype(np.float64)
    sums = {"FULL": 1, "SUM2": 2, "SUM4": 4}.get(_value(info, "INSTRUMENT_MODE_ID", "FULL"), 1)
    if _fsw(info) < 1.3:
        avg = last
    elif sums == 1:
        avg = (first / 2 + last / 6) / 2
    elif sums == 2:
        avg = (first + last / 3) / 2
    else:
        avg = (first + last) / 2
    if _value(info, "DATA_CONVERSION_TYPE") == "TABLE":
        avg = LUT[np.clip(avg, 0, 255).astype(np.int64)]
    kept = (prefix[:, 2].astype(int) * 256 + prefix[:, 3]) > 0
    if kept.sum() < 2:
        return None
    avg = avg.copy()
    if avg[0] > 2 * avg[1]:
        avg[0] = avg[1]
    middle = np.median(avg[kept])
    spread = 1.4826 * np.median(np.abs(avg[kept] - middle))
    kept &= np.abs(avg - middle) <= max(OVERCLOCK_OUTLIER[0], OVERCLOCK_OUTLIER[1] * spread)
    if kept.sum() < 2:
        return None
    return avg, kept


"""
CISSCAL's bias from the overclocked pixels (cassimg__debias.pro, cisscal ComputeBias, OverclockFit): a straight line
fitted down the frame to the kept lines' overclock averages (overclock_avg), the bias at each line. None where
CISSCAL 4 uses the strip mean instead: a lossy frame, an 8-bit table frame at a gain under 12 e-/DN (CISSCAL 4.0's
rule; its overclocks are too coarse after the table, cisscal_noise.table_low_gain), or no prefixes.
"""
def overclock_bias(info):
    if cn.table_low_gain(info):
        return None
    got = overclock_avg(info)
    if got is None:
        return None
    avg, kept = got
    n = np.arange(1, len(avg) + 1, dtype=np.float64)
    b, a = np.polyfit(n[kept], avg[kept], 1)
    return a + b * n


"""
Calibrates one frame to I/F. Returns None if the frame can't be calibrated.
png = the frame's PNG as stored in the dataset
image = optional image on the same scale as png to calibrate instead (see unstretch)
"""
def calibrate(png, info, image=None, smooth=True):
    camera = _value(info, "INSTRUMENT_ID", "")
    names = _filters_of(info)
    if any(name.startswith(("P", "IRP")) for name in names):
        # polarizers use their clear filter's calibration, like CISSCAL
        if camera == "ISSNA":
            names[0] = "CL1"
        else:
            names[1] = "CL2"
    filters = "".join(names)
    k = filter_table().get((camera, filters))
    gain = _value(info, "GAIN_MODE_ID", "").split("ELECTRONS")[0].strip()
    mode = _value(info, "INSTRUMENT_MODE_ID", "FULL")
    exposure = float(_value(info, "EXPOSURE_DURATION", "0"))
    distance = sun_distance(info)
    if k is None or gain not in GAIN_STATES or mode not in SUM_FACTORS or exposure <= 0 or distance is None:
        return None

    # lean archive: every pixel of the 8-bit image (or PNG) is one of 256 codes, so the steps up to the shutter's
    # per column exposure are worked out for the 256 codes and looked up (_lookup): the same numbers, a third of the time
    pixels = np.asarray(png if image is None else image)
    codes = ds.lut8() and pixels.dtype == np.uint8 and pixels.ndim == 2 and np.asarray(png).size > 0
    dn = _unstretch_codes(png, info, image) if codes else unstretch(png, info, image)
    if dn is None:
        return None

    bias = bias_of(png, info)
    if _value(info, "DATA_CONVERSION_TYPE") == "TABLE":
        dn = np.interp(dn, np.arange(256), LUT)
        bias = LUT[int(min(max(bias, 0), 255))]
    dn = dn - bias
    # what changes from pixel to pixel before the nonlinearity: the overclocked pixels' bias, line by line, in place
    # of the strip mean, and the dark current (the "dark" step); with neither, every step up to the shutter is
    # worked out per code
    shape = pixels.shape if codes else dn.shape
    offset = None
    spots = None
    lines_bias = overclock_bias(info)
    if step("twohz"):
        # CISSCAL's 2 Hz noise (cisscal_noise.two_hz), one value per line, taken off with the bias
        got = overclock_avg(info)
        hum = cn.two_hz(info, *got) if got is not None else None
        if hum is not None:
            lines_bias = (lines_bias if lines_bias is not None else np.full(len(hum), float(bias))) + hum
    if lines_bias is not None:
        rows = np.interp(np.linspace(0, len(lines_bias) - 1, shape[0]), np.arange(len(lines_bias)), lines_bias)
        offset = (rows - bias)[:, None] * np.ones((1, shape[1]))
    if step("dark"):
        dark = dc.dark_for(info, shape)
        if dark is not None:
            offset = dark.astype(np.float64) if offset is None else offset + dark
            spots = dc.dark_spots(info)
    if offset is not None:
        dn = (_lookup(pixels, dn) if codes else dn) - offset
        codes = False
    if step("pairs") and cn.wants_pairs(info) and shape == (int(_value(info, "LINES", "0") or 0),
                                                            int(_value(info, "LINE_SAMPLES", "0") or 0)):
        # CISSCAL's anti-blooming bright/dark pixel pairs (cisscal_noise.bright_dark), in DN after the dark
        full = _lookup(pixels, dn) if codes else dn
        fixed, count = cn.bright_dark(full)
        if count:
            dn, codes = fixed, False
    # CISSCAL's linearize: the factor for the whole DN below (a negative DN takes DN 0's)
    dn = dn * linearity(camera, GAIN_STATES[gain])[np.clip(dn, 0, 4095).astype(np.int64)]

    if _value(info, "SHUTTER_STATE_ID", "ENABLED") != "DISABLED":
        first, last = SHUTTER_SLOPE[camera]
        exposure = exposure - np.linspace(first, last, pixels.shape[1] if codes else dn.shape[1]) - SHUTTER_OFFSET[camera]
        exposure = np.maximum(exposure, 0.1)
    dn = dn * 1000.0
    per_second = (_lookup(pixels, dn) if codes else dn) / exposure
    if step("flat"):
        # dust rings, mottle and the flat field (flat_field.correction), at the image's own size
        flat = ff.correction_for(info, per_second.shape)
        if flat is not None:
            per_second *= flat
    if step("hotpix"):
        dc.repair_hot(per_second, info, spots)
    if smooth:
        per_second = deblock(per_second, pixels, info)

    gain_ratio = GAIN_RATIOS[camera][GAIN_STATES[gain]]
    slope, start = SENSITIVITY[camera]
    try:
        image_number = float(_value(info, "IMAGE_NUMBER", "0"))
    except ValueError:
        image_number = 0
    sensitivity = 1 + slope * (image_number - start) if image_number > start else 1.0

    # per_second * k / gain_ratio * SUM_FACTORS[mode] * sensitivity * distance ** 2, in place (the same steps in the
    # same order) so a frame's worth of float64 is not made five more times
    per_second *= k
    per_second /= gain_ratio
    per_second *= SUM_FACTORS[mode]
    per_second *= sensitivity
    per_second *= distance ** 2
    return per_second


LOSSY_RATIO = (6.0, 20.0)  # a lossy frame compressed more than LOSSY_RATIO[0] times has its compression blocks smoothed, all of
                     # LOSSY_SMOOTH from LOSSY_RATIO[1]: at 52 to 1 (the 2005-11-27 Enceladus plumes, 0.22 s) a faint glow is
                     # a staircase of flat 8 px blocks one code apart, which a picture stretched to show it draws as terraces
LOSSY_SMOOTH = 4.0   # ... towards the frame blurred over this many pixels (sigma, at full resolution),
LOSSY_STEP = 2.5     # ... only where the stored codes are within this many of that blur, so the blocks' one-code steps go
                     # and edges, stars and real detail (more codes apart) stay as they were


"""
A heavily compressed lossy frame's blocks smoothed (LOSSY_RATIO): its brightness drawn towards its blur over
LOSSY_SMOOTH pixels where the stored codes are within LOSSY_STEP of theirs, in proportion. iof = the frame calibrated,
pixels = its codes (or a stacked picture on their scale), the same size
"""
def deblock(iof, pixels, info):
    if _value(info, "INST_CMPRS_TYPE", "").upper() != "LOSSY":
        return iof
    try:
        ratio = float(_value(info, "INST_CMPRS_RATIO", "0"))
    except ValueError:
        return iof
    share = min(max((ratio - LOSSY_RATIO[0]) / (LOSSY_RATIO[1] - LOSSY_RATIO[0]), 0.0), 1.0)
    pixels = np.asarray(pixels)
    if share <= 0 or pixels.shape != iof.shape:
        return iof
    sigma = LOSSY_SMOOTH * iof.shape[1] / 1024
    codes = pixels.astype(np.float32)
    near = np.abs(codes - cv2.GaussianBlur(codes, (0, 0), sigma)) / LOSSY_STEP
    weight = share * np.clip(1 - near, 0, 1)
    return iof + weight * (cv2.GaussianBlur(iof, (0, 0), sigma) - iof)


"""
Which pixels of a frame the camera saturated (the top of its 12 bit range, or of the 8 bit
table). codes = the frame's PNG as stored; image = optional image on the same scale (resized or
stacked) to mark instead. A frame whose brightest pixel is below the top has none.
"""
def saturated(codes, info, image=None):
    conversion = _value(info, "DATA_CONVERSION_TYPE", "")
    image = np.asarray(codes if image is None else image)
    if ds.lut8() and conversion in ("TABLE", "12BIT"):
        top = 4095 if conversion == "12BIT" else 255
        if stored_range(codes, info)[1] < top:
            return np.zeros(image.shape, bool)
        # the display stretch puts the top at 254; a resized frame's partly full pixels count too
        return image >= 250
    return image >= 254


"""
How pictures are drawn from I/F, set per request (looking): "balanced", the one display model of the
color plan (steps C1-C5: black per channel at the sky's median plus one noise margin shared by every
channel, white at the WHITE_PCT percentile of the lit pixels with a soft shoulder, filled mosaic passes on
one black and white for every filter, mosaic seams solved once per tile on linear values), or "classic",
the stretch before it (black at the 98th percentile of the sky, white at the brightest pixel, each mosaic
filter stretched and matched on its own). The frame server keeps the two in separate caches.
"""
LOOKS = ("balanced", "classic")
_look = contextvars.ContextVar("look", default="balanced")

NOISE_MARGIN = 2.0   # balanced: the black sits this many times the sky's noise (pooled over the channels)
                     # above each channel's sky level
WHITE_PCT = 99.5     # balanced: the percentile of the lit pixels of the brightest channel that is white
MAX_STRETCH = 1.4    # balanced: white at most this many times darker than the classic white (the brightest
                     # pixel), so a picture is never stretched far enough to show its scan lines, compression
                     # blocks and 8-bit steps
SPIKE = 6.0          # balanced composites: a one-channel spike this many times the sky's grain is cleaned (_clean_spikes)
SKY_DARK = 99        # balanced composites: this percentile of the dark sky's brightness is below the toe (tone)
SHOULDER = 0.8       # balanced composites: above this share of white, brightness rolls off softly instead
                     # of clipping (limbs and ring highlights past the white keep their shape)
FLOOR_SHARE = 0.8    # balanced: the black is at least this share of the lit picture's floor, the FLOOR_PCT percentile of
FLOOR_PCT = 0.5      # its brightness (the channels' mean above their sky levels), so a picture whose lit part is one even
                     # surface (Titan's haze, a moon close-up) spreads over the range instead of the gamma lifting it to
                     # near-white, and a lit sky that fails the sky test (a plume's, stray light) goes dark.
FLOOR_EDGE = 10      # With sky, the floor is taken at least FLOOR_EDGE pixels from it (none when under FLOOR_MIN of the
FLOOR_MIN = 0.01     # picture is that far), and only an even lit part has it taken off: none when the floor is under
FLOOR_EVEN = (0.3, 0.6)  # FLOOR_EVEN[0] of the lit part's WHITE_PCT percentile, all of FLOOR_SHARE from FLOOR_EVEN[1],
                     # so dim things between the sky and the body (faint rings, a shadow, a night side) keep their light
GLOW_IOF = (1e-3, 5e-3)  # balanced, no sky: a picture whose median brightness (I/F) is under GLOW_IOF[0] is lit sky (a plume's
GLOW_PCT = 50        # or the E ring's glow, stray light, a star field's offset), not a sunlit surface, which is brighter than
                     # GLOW_IOF[1]: its black is its GLOW_PCT percentile, so the sky goes near black and only the glow
                     # brighter than the sky shows; in between, a blend (on a log scale) from the floor black
GLOW_FINE = (0.04, 0.12)  # ... but only for smooth light: none of it as the picture's fine structure (the 90th percentile of
                     # its 1.5 px detail, against 8 px, over its median) goes from GLOW_FINE[0] to GLOW_FINE[1], so faint
                     # rings seen at high phase or from their unlit side keep the floor black (glows and star fields measure
                     # under 0.04, rings over 0.15)
TOE = 0.05           # balanced composites: a margin up to this share of white (the sky's noise) has a toe (tone) as wide as
                     # it and centred on it, so a night side or twilight it reaches into (the sky test counts it as sky)
                     # fades out smoothly instead of being cut off with a ragged edge; from twice this (a floor black,
                     # FLOOR_SHARE) the toe is an eighth of the margin, starting at it, as before; in between, a blend
SATURATED = 4.0      # balanced, one frame: a pixel the camera saturated is drawn at least this many times white above its
                     # black (past the shoulder: white), whatever the picture's scale puts it at (draw_saturated)
SATURATED_FLOOR = (0.05, 0.25)  # ... and a frame saturated over more than SATURATED_FLOOR[0] of it has less of its floor (and
                     # glow) black, none from SATURATED_FLOOR[1]: what is left unsaturated is its dim edge, not an even
                     # surface, and keeps a soft gradient up to the white instead of going black
SATURATED_GLOW = (0.001, 0.01, 0.5)  # ... and a frame saturated over SATURATED_GLOW[0] of it has less of its glow black
                     # (GLOW_IOF), SATURATED_GLOW[2] of it from SATURATED_GLOW[1]: the camera saturated on something bright
                     # in it (a crescent and its plumes in a 100 s exposure), so it is not only lit sky, and its night side
                     # keeps a soft edge instead of a hard black cut-out (none of the glow black lifts the haze to flat gray)


def look():
    return _look.get()


"""
How a balanced color picture maps its filters to color (color plan phase 2b): "natural" (the default) turns a
true color set into the colors an eye would see (natural_mix) and balances a false color set so the body comes
out gray (false_mix); "raw" draws each filter straight as a channel, as before; "eye" (natural color emulation)
draws a true color set as "natural" does and any other set as what an eye would have seen of it (eye_mix). The
classic look is always raw.
"""
COLORS = ("natural", "raw", "eye")
_colors = contextvars.ContextVar("colors", default="natural")


def colors():
    return _colors.get()


@contextlib.contextmanager
def coloring(name):
    token = _colors.set(name if name in COLORS else COLORS[0])
    try:
        yield
    finally:
        _colors.reset(token)


"""
The display model in use, for cache names: "classic", "balanced" (natural color), "raw" (balanced, filters drawn
straight) or "eye" (balanced, natural color emulation)
"""
def style():
    if look() == "classic":
        return "classic"
    return colors() if colors() in ("raw", "eye") else "balanced"


@contextlib.contextmanager
def looking(name):
    token = _look.set(name if name in LOOKS else LOOKS[0])
    try:
        yield
    finally:
        _look.reset(token)


"""
The pipeline's steps a request turns off (Settings > Processing; the picture routes' off=, a comma list), to see what
each one does: "stack" (repeat exposures of the same filter merged, stacking.load_stacked and load_hdr), "hdr" (an
exposure bracket merged into one picture in mosaics and movies, stacking.load_hdr; off merges only identical
exposures, a plain stack), "fill" (pixels lost in downlink filled from round them), "calibrate" (every frame put on
I/F and one display scale; off shows each frame on the archive's own stretch), "twohz" (calibrate's 2 Hz noise, the
horizontal banding, taken out line by line, cisscal_noise.two_hz), "dark" (calibrate's dark current and
the WAC's hot pixels taken out, dark_current.py), "pairs" (calibrate's anti-blooming bright/dark pixel pairs replaced,
cisscal_noise.bright_dark), "flat" (calibrate's flat field: dust rings, mottle and the
detector's flat taken out, flat_field.py), "hotpix" (calibrate's repair of the hot and dead pixels, which stay put
while the sky moves, dark_current.repair_hot), "align" (a color set's channels moved onto one another), "blend" (a
mosaic's tiles blended where they meet, mosaic.composite), "level" (each tile leveled to the tiles round it along
their seams, mosaic._level), "surface" (a mosaic's tiles' surface redrawn as at one moment,
obs_mosaic.surface_pictures) and "panels" (a mosaic's pointings moved onto one another where they overlap,
obs_mosaic.panel_places). Every step is on by default; off steps go into the cache names (variant), so the pictures
made with every step on keep their names. "blend", "level", "surface" and "panels" are the exception: they change
only how tiles are drawn together, or redraw or move tiles from the tiles made, never a frame or a tile, so they are
left out of variant (a mosaic with them off draws the same tiles) and the mosaics name them themselves
(mosaic.drawing; obs_mosaic.SURFACE_TAG, PANEL_TAG, EDGE_TAG).
"""
STEPS = ("stack", "hdr", "fill", "calibrate", "twohz", "dark", "pairs", "flat", "hotpix", "align", "blend", "level", "surface", "panels")
_off = contextvars.ContextVar("off", default=frozenset())


def step(name):
    """True when the pipeline step name is on for this request (STEPS)."""
    return name not in _off.get()


def variant():
    """What a cache name gets for the steps turned off: "" with every step on, else "-off-" and their names."""
    off = _off.get() - {"blend", "level", "surface", "panels"}
    return "-off-" + "-".join(s for s in STEPS if s in off) if off else ""


@contextlib.contextmanager
def stepping(names):
    """The pipeline steps names (a comma list or an iterable of STEPS names; others are ignored) turned off."""
    if isinstance(names, str):
        names = names.split(",")
    token = _off.set(frozenset(n for n in names if n in STEPS))
    try:
        yield
    finally:
        _off.reset(token)


def mode():
    """The request's whole display model (look, colors and the steps turned off), to carry to another thread (in_mode)
    and to key what is kept in memory."""
    return look(), colors(), _off.get()


@contextlib.contextmanager
def in_mode(m):
    with looking(m[0]), coloring(m[1]), stepping(m[2]):
        yield


"""
The channel mix of a color set, a 3x3 matrix on linear values ([red, green, blue] out of the set's channels in
order), or None to draw each filter straight: natural color only, in the balanced look.
camera = "N" or "W"; bands = the set's color filters in channel order ("RED", "GRN", "BL1", "CB2", "MT3"...)
target = the body the set is of (TARGET_NAME), for false color
gains = false color: per band, the gain that brings the body's typical brightness to the set's mean
(false_gains), when the caller has measured it itself (a mosaic's pass); otherwise the table's
A two-filter set (longer wavelength first) is drawn as three channels, green the mean of the two (two_bands), and
balanced like a false color set: straight, one band floods the picture (IR3 over VIO, solid orange; UV2 over UV1,
solid blue). Two visible color filters (NATURAL_PAIR: RED with BL1 or GRN) already look natural and stay straight.
"""
NATURAL_PAIR = ("RED", "GRN", "BL1", "BL2", "VIO")
# A pair with the one filter a body's surface shows through, a window in its haze (Titan's CB3, 938 nm: its other filters
# see the haze and clouds above), stays straight too: its surface shows as the difference between the bands (dark
# markings bluer, the haze rim blue), which the false color balance flattens into one orange
SURFACE_WINDOW = {"TITAN": "CB3"}


def color_mix(camera, bands, target=None, gains=None, own=False):
    if style() == "eye" and len(bands) in (2, 3):
        return natural_mix(camera, bands) if len(bands) == 3 and natural_mix(camera, bands) is not None \
            else eye_mix(camera, bands, target)
    if style() != "balanced" or len(bands) not in (2, 3):
        return None
    if len(bands) == 2:
        if all(b in NATURAL_PAIR for b in bands) or SURFACE_WINDOW.get(str(target or "").upper()) in bands:
            return None
        if gains:
            # gains bring each band to the set's mean: the levels they balance are as their inverses
            gains = balance(two_bands([1 / g for g in gains]), tint_of(target))
    else:
        m = natural_mix(camera, bands)
        if m is not None:
            return m
    gains = gains or false_gains(target, bands, camera)
    if not gains and own:
        # no mission measure of the body in these bands (a clear frame, a rare filter or body): the picture's own
        # balance alone (load_linear's FALSE_OWN), so no band outshines the others
        gains = [1.0] * 3
    if not gains:
        return None
    m = np.diag(np.asarray(gains, np.float32)).view(FalseMix)
    m.tint = tint_of(target)
    return m


"""
A two-filter set's channels (or levels), longer wavelength first, as three: red the longer, blue the shorter and
green their mean, as the frame server always drew them
"""
def two_bands(channels):
    if len(channels) != 2:
        return list(channels)
    return [channels[0], (channels[0] + channels[1]) / 2, channels[1]]


class FalseMix(np.ndarray):
    """A false color mix (a gain per band, diagonal), the tint its balance aims at (tint_of) and, for a mosaic, its
    pass's typical color (each band's log share of the brightness, so the color doesn't shift as tiles arrive), kept
    through arithmetic."""
    tint = None
    typical = None

    def __array_finalize__(self, obj):
        self.tint = getattr(obj, "tint", None)
        self.typical = getattr(obj, "typical", None)


_matrices = None


"""
True color sets (RED, GRN and BL1, BL2 or VIO): the fitted filter-to-sRGB matrix of the camera
(color_matrices.json), which turns what the three filters saw into the color an eye would see; a gray body
stays gray. None for other sets, and for a NAC set with VIO (no fit).
"""
def natural_mix(camera, bands):
    global _matrices
    if list(bands[:2]) != ["RED", "GRN"] or bands[2] not in ("BL1", "BL2", "VIO"):
        return None
    if _matrices is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "color_matrices.json")) as f:
            _matrices = json.load(f)
    key = ("NAC" if camera.startswith("N") or camera == "ISSNA" else "WAC") + {"VIO": "vio", "BL2": "bl2"}.get(bands[2], "")
    m = _matrices.get(key)
    return None if m is None else np.asarray(m, np.float32)


_bodies = None
_wavelengths = None


def band_wavelength(camera, band):
    """A color filter's effective wavelength in nm on the camera ("N" or "W"), with the other wheel clear
    (filter_calibration.csv), or None."""
    global _wavelengths
    if _wavelengths is None:
        _wavelengths = {}
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "filter_calibration.csv")) as f:
            next(f)
            for line in f:
                cam, filters, nm = line.strip().split(",")[:3]
                for clear in ("CL1", "CL2"):
                    for name in (filters[3:] if filters.startswith(clear) else None,
                                 filters[:3] if filters.endswith(clear) and len(filters) == 6 else None):
                        if name and name not in ("CL1", "CL2"):
                            _wavelengths[(cam[3], name)] = float(nm)
    cam = "N" if str(camera or "").startswith("N") or camera == "ISSNA" else "W"
    return _wavelengths.get((cam, band)) or _wavelengths.get(("W" if cam == "N" else "N", band))


def body_level(target, band, camera=None, sure=True):
    """The body's typical lit I/F in a band over the mission (false_color_bodies.json, the camera's own, else both
    cameras'), or None: too few frames (BODY_MIN) or, when sure, a spread past BODY_SPREAD (false_gains' rules)."""
    global _bodies
    if _bodies is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "false_color_bodies.json")
        _bodies = {}
        if os.path.exists(path):
            with open(path) as f:
                _bodies = json.load(f)
    body = _bodies.get(str(target or "").upper(), {})
    cam = "N" if str(camera or "").startswith("N") or camera == "ISSNA" else "W"
    for m in (body.get(cam, {}).get(band), body.get(band)):
        if m and m.get("n", 0) >= BODY_MIN and m["median"] > 0 and \
                (not sure or m["iqr"][1] <= BODY_SPREAD * max(m["iqr"][0], 1e-9)):
            return m["median"]
    return None


"""
Natural color emulation (colors=eye): what an eye would have seen of a set taken through other filters than red,
green and blue. Each of RED, GRN and BL1 is estimated from the set's own bands, then the camera's natural matrix
(natural_mix) turns them into color, so the whole mix is one 3x3 matrix on the set's linear channels, the same as a
true color set's (the page mixes it as it does those).
- A band's brightness is read against the body's typical brightness in it (body_level, measured by this same
  pipeline over the mission, so a filter's calibration cancels out). Where every band is at its typical share the
  body has its own color (eye_tint: as the true color sets draw it, else BODY_TINTS, else gray); where they differ,
  the color leans the way the bands do: at a visible wavelength between two bands by their ratios interpolated
  linearly in wavelength, past the set's bands by the nearest band's. A body without a measure in every band is
  taken as gray (each ratio is the band's I/F).
- Methane bands (MT1, MT2, MT3) see how high the clouds are, not the color of what is there, and stay out of the
  estimate while the set has another band (Saturn's MT3 + CB2 + MT2 is drawn from CB2 alone, in Saturn's color).
- A two-filter set is its two bands, as color_mix's channels: longer, mean, shorter.
camera = "N" or "W"; bands = the set's color filters in channel order; target = TARGET_NAME
"""
METHANE = ("MT1", "MT2", "MT3")
EYE_BANDS = ("RED", "GRN", "BL1")
_eye_colors = None


def eye_tint(target):
    """The body's own color for eye_mix, linear red, green, blue of mean 1: as the pipeline's true color composites
    draw it (eye_colors.json, web/frames/eye_colors.py), else BODY_TINTS, else gray."""
    global _eye_colors
    if _eye_colors is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eye_colors.json")
        _eye_colors = {}
        if os.path.exists(path):
            with open(path) as f:
                _eye_colors = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    got = _eye_colors.get(str(target or "").upper())
    return got["rgb"] if got else tint_of(target) or [1.0, 1.0, 1.0]


def eye_mix(camera, bands, target=None):
    bands = list(bands)
    if len(bands) not in (2, 3):
        return None
    nm = [band_wavelength(camera, b) for b in bands]
    if any(v is None for v in nm):
        return None
    use = [i for i, b in enumerate(bands) if b not in METHANE] or list(range(len(bands)))
    natural = natural_mix(camera, list(EYE_BANDS)).astype(np.float64)
    # the body's natural color as what RED, GRN and BL1 would measure of it (the natural matrix undone)
    eye = np.linalg.solve(natural, np.asarray(eye_tint(target), np.float64))
    ref = {i: body_level(target, bands[i], camera, sure=False) for i in use}
    if any(v is None for v in ref.values()):
        ref = {i: 1.0 for i in use}
    want = [band_wavelength(camera, b) for b in EYE_BANDS]
    order = sorted(use, key=lambda i: nm[i])
    a = np.zeros((3, len(bands)), np.float64)
    for k, w in enumerate(want):
        # the ratio to the typical at w: the nearest band's past the ends, else the two bands' either side, linearly
        lo = [i for i in order if nm[i] <= w]
        hi = [i for i in order if nm[i] > w]
        if not lo or not hi:
            parts = [((lo or hi)[-1 if lo else 0], 1.0)]
        else:
            i, j = lo[-1], hi[0]
            t = (w - nm[i]) / (nm[j] - nm[i])
            parts = [(i, 1 - t), (j, t)]
        for i, share in parts:
            a[k, i] += eye[k] * share / ref[i]
    # brightness kept: the body at its typical brightness in the bands comes out as bright as their mean
    level = np.mean([ref[i] for i in use])
    a *= level
    if len(bands) == 2:
        a = np.stack([a[:, 0], np.zeros(3), a[:, 1]], axis=1)
    return (natural @ a).astype(np.float32)


"""
False color: per band, the gain that brings the body's typical lit brightness in that band (false_color_bodies.json,
the median over the mission's frames of the body, per camera) to the mean of the set's bands, so the body as a
whole comes out gray and only its differences between bands show as color: a methane band (MT2, MT3) is far darker
than its neighbors and otherwise turns the whole planet teal or magenta. One table for the mission, not a balance per
picture, so a movie of the set doesn't change color from frame to frame. None (filters drawn straight) when the
table lacks the body or a band, or its measure is unsure (BODY_MIN frames, a spread past BODY_SPREAD: a two-toned
or phase-dependent body, like Iapetus).
camera = "N" or "W"; target = TARGET_NAME
"""
BODY_MIN = 10
BODY_SPREAD = 3.0    # the upper quartile over the lower


def false_gains(target, bands, camera=None):
    global _bodies
    if _bodies is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "false_color_bodies.json")
        _bodies = {}
        if os.path.exists(path):
            with open(path) as f:
                _bodies = json.load(f)
    body = _bodies.get(str(target or "").upper(), {})
    cam = "N" if str(camera or "").startswith("N") or camera == "ISSNA" else "W"
    meds = []
    for b in bands:
        m = body.get(cam, {}).get(b) or body.get(b)
        if not m or m.get("n", 0) < BODY_MIN or m["median"] <= 0 or m["iqr"][1] > BODY_SPREAD * max(m["iqr"][0], 1e-9):
            return None
        meds.append(m["median"])
    return balance(two_bands(meds), tint_of(target))


"""
False color gains that bring levels (the body's brightness per band) toward their mean (times the body's natural
tint, BODY_TINTS, where it has one), FALSE_BALANCE of the way
in log terms, keeping their total: all the way would give a dim band like MT3 over four times its brightness and lift
its noise, so the body is left a little tinted instead (apply_mix holds what still stands out)
"""
FALSE_BALANCE = 0.9
FALSE_OWN = 0.75
OWN_NEAR = 0.3       # ... measured where every band's share is within this (log) of the picture's typical

# the most one band's gain may be over another's: MT3 is so dark on Saturn (gains of 8 to 11) that whatever is less
# methane-absorbed (the rings, the equatorial haze, the limb) would come out a vivid pink and its structure stand out
# like scan lines
GAIN_SPREAD = 12.0



def spread_capped(gains):
    low = min(gains)
    return [min(g, low * GAIN_SPREAD) for g in gains]


# the target of the balance for bodies with a color of their own, instead of gray: their natural color (sRGB, the color
# investigation's references, /mnt/project-files/color-investigation/filter_to_srgb_matrices.json), so a false color
# Jupiter comes out cream and tan rather than blue-gray
BODY_TINTS = {"JUPITER": (255, 237, 206), "SATURN": (255, 242, 214), "TITAN": (255, 217, 162)}


def tint_of(target):
    """The body's natural color as linear red, green, blue of mean 1, or None (gray)."""
    t = BODY_TINTS.get(str(target or "").upper())
    if t is None:
        return None
    lin = [float(decode(np.float64(v / 255), "srgb")) for v in t]
    return [v * 3 / sum(lin) for v in lin]


def balance(levels, tint=None):
    mean = sum(levels) / len(levels)
    tint = tint or [1.0] * len(levels)
    gains = spread_capped([(mean * t / v) ** FALSE_BALANCE for v, t in zip(levels, tint)])
    k = sum(levels) / sum(g * v for g, v in zip(gains, levels))
    return [g * k for g in gains]


"""
A channel mix (color_mix) on linear channels (3 x H x W). A false color mix (a gain per band, diagonal) is meant to
take the body's tint away; where it makes a pixel more colorful than drawn straight instead (Saturn's rings, which
methane doesn't darken, or Jupiter's limb haze, bright in MT3), the pixel goes to the body's tint (gray where it has
none) at the balanced brightness,
fully once the balance adds FALSE_REVERT of saturation (its straight color, teal on Jupiter, would stand out too). Then saturation past FALSE_CHROMA[0]
rolls off through a soft knee to at most FALSE_CHROMA[1] (on linear values, against the tint).
"""
FALSE_CHROMA = (0.15, 0.25)
FALSE_REVERT = 0.1
FALSE_DETAIL = 5.0    # ... and fine detail below this blur (pixels) taken from the bands at gentler gains:
DETAIL_SPREAD = 4.0   # none over this times another's (4x keeps the scan lines down; the full gains lift them)
REVERT_FLOOR = 0.02   # ... where the bands' mean is at least this share of white
# broad color differences across the body (a dusty-rose band under the ring shadow, one half of a disk pink and the
# other sage, a lavender side, one mosaic tile olive and the next mauve) are what a dim band's full gain makes of small
# real changes in its share; FALSE_FLAT of the picture's color variation broader than FALSE_BROAD (a share of the
# picture's size) is taken out, toward its typical color, while finer color (belts, clouds, storms) stays
FALSE_BROAD = 0.10
FALSE_FLAT = 0.6


def _saturation(x):
    top, low = x.max(axis=0), x.min(axis=0)
    return np.where(top > 0, (top - low) / np.maximum(top, 1e-12), 0)


def _broad_blur(v, sigma):
    """cv2.GaussianBlur(v, (0, 0), sigma) for a wide sigma (a tenth of a mosaic's canvas, hundreds of pixels):
    blurred at 1/f of the size and scaled back up, which is the same picture to well under a level (the blur
    leaves nothing finer than sigma) at a hundredth of the cost; a mosaic movie's color picture took seconds."""
    f = int(sigma // 8)
    h, w = v.shape[:2]
    if f < 2 or min(h, w) < 8 * f:
        return cv2.GaussianBlur(v, (0, 0), sigma)
    small = cv2.resize(v, (max(1, round(w / f)), max(1, round(h / f))), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma / f)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _flatten_broad(x, lit, typical=None):
    if lit.sum() < 100:
        return x
    lum = x.mean(axis=0)
    share = np.log(np.maximum(x, 1e-6) / np.maximum(lum, 1e-6))
    if typical is None:
        typical = [np.median(c[lit]) for c in share]
    typical = np.asarray(typical, np.float32).reshape(3, 1, 1)
    sigma = FALSE_BROAD * max(x.shape[1:])
    weight = np.where(lit, lum, 0).astype(np.float32)
    soft = lambda v: _broad_blur(v, sigma)
    norm = np.maximum(soft(weight), 1e-12)
    broad = np.stack([soft(c * weight) / norm for c in (share - typical)])
    flat = np.exp(share - FALSE_FLAT * broad)
    flat *= 3 / np.maximum(flat.sum(axis=0), 1e-12)
    return np.where(lit & (x.min(axis=0) > 0), lum * flat, x)


def apply_mix(mix, x):
    false = isinstance(mix, FalseMix)
    tint = np.asarray(mix.tint if false and mix.tint else [1.0, 1.0, 1.0], np.float32).reshape(3, 1, 1)
    raw = x
    x = np.tensordot(np.asarray(mix, np.float32), x, axes=1)
    if false:
        # the bands channels first in memory for the mean, min and max over them (mix_display's picture is channels
        # last, where those take 10 to 45 times as long): the same operations in the same order, so the same values.
        # The weighted sums (tensordot) keep raw, so BLAS gets the layout it had
        bands = np.ascontiguousarray(raw)
        # judged against the tint the balance aims at, not gray, so a body's own color (Titan's orange) is no outlier
        lum = x.mean(axis=0)
        mean = bands.mean(axis=0)
        straight = bands * (lum / np.maximum(mean, 1e-12))
        w = np.clip((_saturation(x / tint) - _saturation(straight / tint)) / FALSE_REVERT, 0, 1)
        # only where every band has signal: the sky's noise has no band ratio to compare
        w = np.where((bands.min(axis=0) > 0) & (mean > REVERT_FLOOR), w, 0)
        x = x + (lum * tint - x) * w
        knee, cap = FALSE_CHROMA
        sat = _saturation(x / tint)
        held = knee + (cap - knee) * np.tanh((sat - knee) / (cap - knee))
        k = np.where(sat > knee, held / np.maximum(sat, 1e-12), 1)
        x = lum * tint + (x - lum * tint) * k
        x = _flatten_broad(x, mean > REVERT_FLOOR, mix.typical)
        # the balance's color and broad brightness, the fine detail of the bands at gains no more than DETAIL_SPREAD
        # apart: a dim band's full gain (MT3 on Saturn, 8 to 10) would lift its ring, limb and haze structure and noise
        # far above the others', while equal weights (the straight picture) lose the detail only that band shows
        gains = np.diagonal(np.asarray(mix, np.float32))
        gentle = np.minimum(gains, gains.min() * DETAIL_SPREAD)
        sharp = np.tensordot(gentle / gentle.mean(), raw, axes=([0], [0])) / len(gains)
        soft = lambda v: cv2.GaussianBlur(v, (0, 0), FALSE_DETAIL)
        bright = x.mean(axis=0)
        base, flat = soft(bright), soft(sharp)
        ok = (flat > REVERT_FLOOR) & (soft(mean) > REVERT_FLOOR)
        detail = np.where(ok, sharp * base / np.maximum(flat, 1e-12), bright)
        x = np.stack([np.where(ok, detail * soft(c) / np.maximum(base, 1e-12), c) for c in x])
    return x


"""
A color picture already drawn (H x W x 3 uint8, gamma encoded, its channels on one white) with its channel mix
(color_mix) applied on the linear values, the brightest channel rolling off past the shoulder as in tone
"""
def mix_display(rgb, mix, gamma=2.2, shoulder=SHOULDER):
    x = decode(np.moveaxis(rgb[..., :3].astype(np.float32) / 255, -1, 0), gamma).astype(np.float32)
    x = apply_mix(mix, x)
    _shoulder(x, shoulder)
    return np.moveaxis((encode(np.clip(x, 0, 1), gamma) * 255 + 0.5).astype(np.uint8), 0, -1)


"""
A frame's color filter ("RED", "CB2", "BL1/GRN"...), the filters other than the clear ones, as reel.colour_filter
"""
def band_of(info):
    return "/".join(f for f in _filters_of(info) if not f.startswith("CL")) or "CL1/CL2"


"""
Loads the frames of one color image and puts them on the same brightness scale.

labels = label objects, one per channel
images = the channels' images as label.resize_image (or stacking.load_stacked) returns
them; loaded with resize_image if not given
iofs = optional list, one per label: an I/F image already calibrated (stacking.load_hdr) to use
instead of calibrating that channel's image, or None
scale = optional fixed display scale shared by every picture of a mosaic, a dict with "white"
(the I/F that becomes full brightness), "blacks" (one I/F per channel that becomes black) and
optionally "gamma" and "shoulder"; without it each picture is stretched on its own as below
saturated = with scale, optional list, one per label: the pixels the camera saturated (stacking.load_hdr's clipped,
saturated_of), drawn white, or None
Returns one BGR uint8 image per label. If every frame calibrates, all channels share one
stretch so their relative brightness is what the camera measured. Otherwise the images
are returned unchanged, each with its own stretch as before.
"""
def load_channels(labels, images=None, sky_fraction=0.1, sky_percentile=98, gamma=2.2, iofs=None, scale=None,
                  saturated=None):
    if images is None:
        images = [lbl.resize_image() for lbl in labels]
    iofs = _calibrated(labels, images, iofs)
    if iofs is None:
        return images
    if scale is not None:
        # every picture of a mosaic on the same scale, so tiles and filters keep what the camera saw
        gamma = scale.get("gamma", gamma)
        out = []
        for iof, black in zip(iofs, scale["blacks"]):
            # a picture's own black where the scale measures one on it (obs_mosaic.tile_scale)
            own = scale["black_of"](iof) if scale.get("black_of") else None
            black, toe = (own["black"], own["toe"]) if own else (black, scale.get("toe"))
            out.append(display(iof, black, scale["white"], gamma, scale.get("shoulder"), toe))
        for picture, full in zip(out, saturated or []):
            # what the camera saturated is brighter than it could measure: white, as in a one frame picture
            # (draw_saturated), wherever the shared white puts its clipped value (a mosaic's white is its brightest
            # tile's, often a shorter exposure's, and a clipped crescent came out one flat gray)
            if full is not None:
                picture[full] = 255
        return out
    blacks, white, _ = picture_scale(iofs, sky_fraction, sky_percentile)
    if white <= 0:
        return images
    shoulder = SHOULDER if look() == "balanced" else None
    return [display(iof, black, white, gamma, shoulder) for iof, black in zip(iofs, blacks)]


"""
Each channel's I/F image, calibrating those not given; None for a frame that can't be calibrated
"""
def calibrated_each(labels, images, iofs=None):
    given = iofs or [None] * len(labels)
    iofs = []
    for lbl, image, iof in zip(labels, images, given):
        if iof is None:
            png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            iof = calibrate(png, lbl.get_info(), gray)
        iofs.append(iof)
    return iofs


"""
The channels' I/F images (float32), calibrating those not given; None if any frame can't be calibrated
"""
def _calibrated(labels, images, iofs=None):
    iofs = calibrated_each(labels, images, iofs)
    if any(iof is None for iof in iofs):
        failed = [lbl.get_info().get("path") for lbl, iof in zip(labels, iofs) if iof is None]
        print(f"Can't calibrate {failed}, using the stretched frames")
        return None
    return [iof.astype(np.float32) for iof in iofs]


"""
Balanced composites, drawn after their channels are aligned (color_image.load_aligned): each channel's
linear brightness above its sky level (white = 1), and the noise margin in the same units, for tone.
Taking the margin off each channel on its own (a black above the sky per channel) changes the color of
everything only a little brighter than the sky, a shadowed ring or a night side: the channel that is
dimmest there loses the largest share of itself. tone takes it off the picture's brightness instead, so
dim parts keep the color the camera measured and only get darker.
labels, images, iofs = as load_channels; floor = how much of the picture's floor black to take (0 to 1, saturated_floor); glow = how much of its glow black (0 to 1, saturated_glow)
returns (channels, margin, the channel mix (color_mix) or None), or None when a frame can't be calibrated or there is nothing to draw
"""
def load_linear(labels, images=None, iofs=None, floor=1.0, glow=1.0):
    if images is None:
        images = [lbl.resize_image() for lbl in labels]
    iofs = _calibrated(labels, images, iofs)
    if iofs is None:
        return None
    # the sky is measured once, for the scale and the toe below
    sky = _sky(iofs)
    levels, margin, white, measured = _balanced_scale(iofs, sky=sky, floor=floor, glow=glow)
    if white <= 0:
        return None
    channels = [(iof - np.float32(level)) / np.float32(white) for iof, level in zip(iofs, levels)]
    infos = [lbl.get_info() for lbl in labels]
    mix = color_mix(_value(infos[0], "INSTRUMENT_ID", ""), [band_of(i) for i in infos], _value(infos[0], "TARGET_NAME", ""),
                    own=True)
    false = isinstance(mix, FalseMix)
    lum = None
    if false:
        # false color: the mission's typical balance of the body (the table) misses a frame unlike it (Saturn's
        # high latitudes); FALSE_OWN of what is left between the picture's own lit bands is taken off as well. A
        # movie of one scene, whose frames are alike, still keeps one color
        bands = two_bands(channels)
        lum = np.mean(channels, axis=0)
        lit = lum > 0.2 * np.percentile(lum, 99)
        if lit.sum() > 100:
            # over the pixels near the picture's typical band ratios, so rings or a bright equatorial band don't steer it
            logs = [np.log(np.maximum(c[lit], 1e-6) / np.maximum(lum[lit], 1e-6)) for c in bands]
            typical = np.logical_and.reduce([np.abs(v - np.median(v)) < OWN_NEAR for v in logs])
            if typical.sum() > 100:
                lit = np.where(lit)
                lit = tuple(i[typical] for i in lit)
            tint = tint_of(_value(infos[0], "TARGET_NAME", ""))
            own = [float(np.median(c[lit])) * g for c, g in zip(bands, np.diagonal(mix))]
            if min(own) > 0:
                gains = spread_capped([g * o ** FALSE_OWN for g, o in zip(np.diagonal(mix), balance(own, tint))])
                mix = np.diag(np.asarray(gains, np.float32)).view(FalseMix)
                mix.tint = tint
    margin /= white
    sky = sky if measured else np.ones(iofs[0].shape, dtype=bool)
    if measured:
        # the toe starts no lower than the darker half of the sky's own brightness (SKY_DARK of it stays black),
        # since the gamma lifts even a tiny remainder into visible grain. Only the darker half, by its mean over
        # 15 pixels, so faint ring glow or a night side in the sky doesn't count as sky
        lum = np.mean(channels, axis=0) if lum is None else lum
        local = cv2.blur(lum, (15, 15))
        dark = sky & (local <= np.median(local[sky]))
        if dark.sum() > 100:
            margin = max(margin, float(np.percentile(lum[dark], SKY_DARK)))
    if len(channels) > 1 and (measured or false):
        # without sky (a body filling the frame) the grain is measured on the whole picture
        channels = _clean_spikes(channels, sky, false)
    return channels, margin, mix


"""
Hot pixels and cosmic ray hits in one channel of a composite: a pixel far above its 3x3 median in its own
channel (SPIKE times that channel's sky grain, and above twice the median) where no other channel has a
peak within 2 pixels, is set to its median. False color (natural), whose balance would make them salmon or cyan dots:
against a 5x5 median, so 2x2 clusters go too, and where not every other channel peaks, so two-channel hits go. Drawn together (tone), such a pixel would be a pastel dot; a
star or a small bright feature is in every channel, so it stays.
channels = linear channels, not yet aligned; sky = the sky mask
"""
def _clean_spikes(channels, sky, natural=False):
    meds = [cv2.medianBlur(c, 5 if natural else 3) for c in channels]
    res = [c - m for c, m in zip(channels, meds)]
    noises = [float(np.percentile(np.abs(r[sky]), 99)) / 2.6 for r in res]
    peaks = [cv2.dilate(r, np.ones((5, 5), np.uint8)) > SPIKE * n for r, n in zip(res, noises)]
    out = []
    for i, (c, m, r, n) in enumerate(zip(channels, meds, res, noises)):
        spike = (r > SPIKE * n) & (r > m) & (r > 0)
        others = [p for j, p in enumerate(peaks) if j != i]
        # natural color: not where every other channel peaks too (a star or a moon); raw: where none does
        spike &= ~np.logical_and.reduce(others) if natural else ~np.logical_or.reduce(others)
        out.append(np.where(spike, m, c))
    return out


"""
Balanced composites' channels (load_linear, aligned) as BGR uint8 images: the noise margin comes off the
brightness (the channels' mean) through a toe (TOE), black up to its start (the sky at or below its own level is
black), then turning into the brightness less the margin, and every channel is scaled by the same factor, so a pixel
keeps its color.
Past the shoulder the brightest channel rolls off softly (roll_off), the others by the same factor. mix = the
set's channel mix (color_mix), applied first, on the linear values.
"""
def tone(channels, margin, mix=None, shoulder=SHOULDER, gamma=2.2):
    if mix is not None:
        # a two-filter set's mix is on three channels, green the mean of the two (color_mix)
        channels = two_bands(channels)
    x = np.stack(channels).astype(np.float32)
    if mix is not None:
        x = apply_mix(mix, x)
    lum = x.mean(axis=0)
    w = max(margin / 8, min(margin, TOE))
    # how far past the margin the toe starts: 0 for a sky's margin (centred on it), half its width for a floor black
    late = w / 2 * min(max(margin / TOE - 1, 0.0), 1.0) if TOE > 0 else w / 2
    start = margin - w / 2 + late
    if w > 0:
        toed = np.where(lum <= start, 0, np.where(lum <= start + w, (lum - start) ** 2 / (2 * w),
                                                  lum - margin - late))
        x *= np.where(lum > 0, toed / np.maximum(lum, 1e-12), 0)
    if shoulder:
        _shoulder(x, shoulder)
    x = np.clip(x, 0, 1)
    return [cv2.cvtColor((encode(c, gamma) * 255 + 0.5).astype(np.uint8), cv2.COLOR_GRAY2BGR) for c in x]


"""
One picture's own display scale, as load_channels uses it: (black per channel, white, whether the
blacks were measured on the sky or left at zero for want of sky), in I/F.
iofs = the picture's channels, float32 I/F
"""
def picture_scale(iofs, sky_fraction=0.1, sky_percentile=98, floor=True):
    # Sky is where every channel is dark; without enough sky the black point stays at zero.
    sky = _sky(iofs)
    blacks = [0.0] * len(iofs)
    measured = bool(sky.mean() > sky_fraction)
    if look() == "classic":
        # Black point per channel: just above the sky left after the bias (dark current,
        # stray light, noise), so the sky's noise, DN steps and lossy compression blocks
        # don't come out as colored speckle
        if measured:
            blacks = [np.percentile(iof[sky], sky_percentile) for iof in iofs]
        # One white point for all channels: the brightest channel's brightest pixel, after a
        # 3x3 median so a single cosmic ray hit or hot pixel can't set it
        white = max(cv2.medianBlur(iof - black, 3).max() for iof, black in zip(iofs, blacks))
        return blacks, white, measured
    # the sky just measured, not measured again (a percentile of every pixel of each channel)
    levels, margin, white, measured = _balanced_scale(iofs, sky_fraction, sky_percentile, sky=sky, floor=floor)
    return [level + margin for level in levels], white, measured


"""
Sky is where every channel is dark
"""
def _sky(iofs):
    sky = np.ones(iofs[0].shape, dtype=bool)
    for iof in iofs:
        sky &= iof < 0.05 * np.percentile(iof, 99.9)
    return sky


"""
The balanced scale of one picture: (sky level per channel, one noise margin, white, whether the sky was
measured), in I/F. The sky level (sky_levels) is the real offset left after the bias (dark current, stray
light), which differs between channels, so the sky stays neutral; the margin above it, the same for every
channel, keeps the sky's noise from coming out as colored speckle (a margin per channel, the 98th
percentile, takes more off the noisiest channel and tints dim limbs and terminators).
"""
"""
The noise floor of a balanced black: the noisiest channel's classic margin (its sky's 98th percentile above its
median), so no channel shows more of its sky noise, scan lines or compression blocks than before. The margin from
neighboring pixels' differences alone is about 0 on frames stored in 8 bits (most neighbors are equal).
skies = per channel, its sky pixels (I/F)
"""
def noise_floor(skies, sky_percentile=98):
    return max(float(np.percentile(v, sky_percentile) - np.median(v)) for v in skies if v.size) if skies else 0.0


def _balanced_scale(iofs, sky_fraction=0.1, sky_percentile=98, sky=None, floor=True, glow=1.0):
    sky = _sky(iofs) if sky is None else sky
    measured = bool(sky.mean() > sky_fraction)
    levels, margin = [0.0] * len(iofs), 0.0
    if measured:
        # the noise floor (noise_floor) taken with the sky levels, on the same sky pixels and medians
        levels, margin = sky_levels([[iof] for iof in iofs], [[sky]] * len(iofs), floor_pct=sky_percentile)
    # the black no lower than a share of the lit picture's own floor, as one margin (tone takes it off the brightness,
    # so every channel keeps its color): its darkest parts stay a little above black and the rest spreads out
    if floor:
        margin = max(margin, floor * _floor(iofs, levels, sky if measured else None, glow))
    blacks = [level + margin for level in levels]
    # One white for all channels: the WHITE_PCT percentile of the brightest channel over the lit pixels (the
    # body, not the sky), so a few bright limb or ring pixels don't leave the body dim and gray; the shoulder
    # (display) keeps what is brighter
    lit = ~sky if measured else np.ones(sky.shape, dtype=bool)
    if lit.sum() < 100:
        lit = np.ones(sky.shape, dtype=bool)
    blurred = [cv2.medianBlur(iof - np.float32(black), 3) for iof, black in zip(iofs, blacks)]
    white = max(float(np.percentile(b[lit], WHITE_PCT)) for b in blurred)
    white = max(white, max(float(b.max()) for b in blurred) / MAX_STRETCH)
    return levels, margin, white, measured


"""
Pixels the camera saturated (saturated: the top of its range, brighter than it could measure), per frame, at the size of
its codes; labels = the frames' labels (their own codes, so not for repeats merged in I/F, stacking.load_hdr)
"""
def saturated_masks(labels):
    return [saturated(ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE), lbl.get_info()) for lbl in labels]


"""How much of its floor black (load_linear's floor) a frame saturated over share of it gets (SATURATED_FLOOR)"""
def saturated_floor(share):
    return min(max((SATURATED_FLOOR[1] - share) / (SATURATED_FLOOR[1] - SATURATED_FLOOR[0]), 0.0), 1.0)


"""How much of its glow black (_floor's, GLOW_IOF) a frame saturated over share of it gets (SATURATED_GLOW)"""
def saturated_glow(share):
    less = min(max((share - SATURATED_GLOW[0]) / (SATURATED_GLOW[1] - SATURATED_GLOW[0]), 0.0), 1.0)
    return 1.0 - less * (1.0 - SATURATED_GLOW[2])


"""
Saturated pixels (masks, saturated_masks) drawn white in a one frame picture's balanced channels (load_linear's, white
= 1 above the margin), in place: a frame saturated all over is otherwise one even surface spread into the flat field's
pattern. margin = load_linear's; returns the share of the frame saturated
"""
def draw_saturated(channels, margin, masks):
    share = 0.0
    for c, full in zip(channels, masks):
        if not full.any():
            continue
        c[full] = np.maximum(c[full], np.float32(margin + SATURATED))
        share = max(share, float(full.mean()))
    return share


"""
The pixels the camera saturated in the frame of label lbl (saturated, on its own codes), at shape (rows, columns)
"""
def saturated_of(lbl, shape):
    full = saturated(ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE), lbl.get_info())
    if full.any() and full.shape != tuple(shape):
        full = cv2.resize(full.astype(np.uint8), tuple(shape)[::-1], interpolation=cv2.INTER_NEAREST).astype(bool)
    return full


"""
A picture's fine structure (GLOW_FINE): the 90th percentile of its detail at 1.5 px (against 8 px) over its median
brightness; a smooth glow, a star field or noise measure little, ringlets and gaps a lot
"""
def fine_structure(lum):
    detail = np.abs(cv2.GaussianBlur(lum, (0, 0), 1.5) - cv2.GaussianBlur(lum, (0, 0), 8))
    return float(np.percentile(detail, 90) / max(float(np.percentile(lum, 50)), 1e-12))


"""
The black a picture's floor sets (FLOOR_SHARE): a share of the FLOOR_PCT percentile of its brightness above the sky
levels. sky = the sky mask, or None for a picture without sky: then every pixel, and FLOOR_SHARE of it, or up to its
GLOW_PCT percentile when the picture is as dim as lit sky (GLOW_IOF) and smooth (GLOW_FINE), glow (0 to 1) of that. With sky, the
pixels at least FLOOR_EDGE from it, and a share from 0 to FLOOR_SHARE as that floor goes from FLOOR_EVEN[0] to
FLOOR_EVEN[1] of their WHITE_PCT percentile; 0 when under FLOOR_MIN of the picture is that far from the sky
"""
def _floor(iofs, levels, sky=None, glow=1.0):
    lum = iofs[0] - np.float32(levels[0]) if len(iofs) == 1 else \
        np.mean([iof - np.float32(level) for iof, level in zip(iofs, levels)], axis=0)
    if sky is None:
        floor, middle, lit = (float(v) for v in np.percentile(lum, (FLOOR_PCT, 50, GLOW_PCT)))
        black = FLOOR_SHARE * max(floor, 0.0)
        dim = min(max(float(np.log(GLOW_IOF[1] / max(middle, 1e-12)) / np.log(GLOW_IOF[1] / GLOW_IOF[0])), 0.0), 1.0)
        lit = max(lit - black, 0.0)
        if dim == 0 and -1e30 < lum.min() and lum.max() < 1e30:
            # a picture brighter than lit sky (most): none of its glow whatever its fine structure, a finite share for
            # pixels of this size (their blurs cannot overflow into a NaN), so the same number (zero, of the same
            # sign) without measuring it (two blurs, ~35 ms)
            return black + glow * dim * lit
        smooth = (GLOW_FINE[1] - fine_structure(lum)) / (GLOW_FINE[1] - GLOW_FINE[0])
        return black + glow * dim * min(max(smooth, 0.0), 1.0) * lit
    side = 2 * FLOOR_EDGE + 1
    far = cv2.erode((~sky).astype(np.uint8), np.ones((side, side), np.uint8)).astype(bool)
    if far.sum() < FLOOR_MIN * far.size:
        return 0.0
    floor, top = (float(v) for v in np.percentile(lum[far], (FLOOR_PCT, WHITE_PCT)))
    if floor <= 0 or top <= 0:
        return 0.0
    even = min(max((floor / top - FLOOR_EVEN[0]) / (FLOOR_EVEN[1] - FLOOR_EVEN[0]), 0.0), 1.0)
    return FLOOR_SHARE * even * floor


"""
Balanced blacks: per channel its sky level plus one margin for every channel, NOISE_MARGIN times the sky's
noise pooled over the channels. The sky level is its median, or, where the sky holds faint diffuse light (a
ring's glow, a night side lit by the rings), the 20th percentile plus 0.84 noise, whichever is lower: the
same for a sky of pure noise, and below the glow otherwise. The noise is measured from neighboring sky
pixels' differences, so a glow's slow change across the picture does not count as noise.
images = per channel, its pictures (2-D I/F); masks = per channel, the sky of each picture
"""
def sky_blacks(images, masks):
    levels, margin = sky_levels(images, masks)
    return [level + margin for level in levels]


"""
sky_blacks' parts: (the sky level per channel, the margin). floor_pct: the margin no less than the skies' noise floor
at that percentile (noise_floor), from the same sky pixels and medians
"""
def sky_levels(images, masks, floor_pct=None):
    levels, noises, floors = [], [], []
    for ims, ms in zip(images, masks):
        sky = np.concatenate([im[m] for im, m in zip(ims, ms)])
        steps = np.concatenate([np.abs(np.diff(im, axis=1))[m[:, 1:] & m[:, :-1]] for im, m in zip(ims, ms)])
        noise = 1.4826 * float(np.median(steps)) / math.sqrt(2) if steps.size else 0.0
        # sky is this loop's own array (concatenate's), so it can be reordered
        median, pcts = _median_percentiles(sky, (20,) if floor_pct is None else (20, floor_pct))
        levels.append(min(float(median), float(pcts[0]) + 0.84 * noise))
        noises.append(noise)
        if floor_pct is not None:
            floors.append(float(pcts[1] - median))
    margin = NOISE_MARGIN * math.sqrt(sum(n * n for n in noises) / len(noises))
    if floor_pct is not None:
        margin = max(margin, max(floors))
    return levels, margin


"""
np.median(v) and np.percentile(v, p) for each p of pcts, the same values as each call on its own: the same calls, in
place on v (a working array of the caller's, which this reorders) instead of each on a copy of its own. A value at a
rank is the same whichever order a partition starts from unless v holds a NaN or both signs of zero, which partitions
can order differently, so then each is taken on its own as before. Each percentile is its own call, with p as given:
numpy 2 works out a list of percentiles of float32 pixels in float64 and a single one (a Python number) in float32.
"""
def _median_percentiles(v, pcts):
    if v.size and not np.isnan(v).any():
        zero = np.signbit(v[v == 0])
        if zero.all() or not zero.any():
            got = [np.percentile(v, p, overwrite_input=True) for p in pcts]
            return np.median(v, overwrite_input=True), got
    return np.median(v), [np.percentile(v, p) for p in pcts]


"""
The display scale shared by the tiles of a mosaic that would each otherwise be stretched on its
own (the reel's mosaics): every tile's own scale (picture_scale, without the floor black), then per
channel the median of the blacks of the tiles that had sky to measure them on (a tile filled by the body
says nothing about the sky), and one white, the brightest tile's, so no tile clips. With no sky in any
tile, the tiles' own floor blacks (FLOOR_SHARE): the lowest, so no tile is darker than alone, and each
tile's white, above its own black, that much higher on the shared one. Each tile looks much as it would
alone, but all are on one scale, so they meet without brightness or colour steps.
pictures = one list of channel I/F images per tile (stacking.load_hdr)
"""
def tiles_scale(pictures, gamma=2.2):
    scales = [picture_scale([iof.astype(np.float32) for iof in iofs], floor=False) for iofs in pictures]
    measured = [s for s in scales if s[2]]
    if measured:
        blacks = [float(np.median([s[0][c] for s in measured])) for c in range(len(pictures[0]))]
        white = max(float(s[1]) for s in scales)
    else:
        scales = [picture_scale([iof.astype(np.float32) for iof in iofs]) for iofs in pictures]
        blacks = [min(float(s[0][c]) for s in scales) for c in range(len(pictures[0]))]
        white = max(float(s[1]) + float(np.mean(s[0])) - float(np.mean(blacks)) for s in scales)
    scale = {"blacks": blacks, "white": white, "gamma": gamma}
    if look() == "balanced":
        scale["shoulder"] = SHOULDER
    return scale


"""
The display scale shared by all the pictures of a mosaic, for load_channels: per channel a black, and
one white for all channels, the white_pct percentile of every pixel above its channel's black (every
channel on one white keeps the colour the camera measured).
the black is the sky's floor, the median over the pictures of each one's floor_pct percentile I/F, in both
looks: a mosaic's faint sky changes from tile to tile, and any black other than its floor (a sky level plus a
noise margin was tried) raised one filter's black more than another's and tinted that sky.
channels = one list per channel of the pictures' I/F images (stacking.load_hdr)
"""
def shared_scale(channels, white_pct=99.9, floor_pct=5, gamma=2.2):
    blacks = [float(np.median([np.percentile(iof, floor_pct) for iof in iofs])) for iofs in channels]
    white = max(float(np.percentile(np.concatenate([iof[::8, ::8].ravel() for iof in iofs]) - black, white_pct))
                for iofs, black in zip(channels, blacks))
    return {"blacks": blacks, "white": white, "gamma": gamma}


"""
Display brightness (0-1) from linear brightness (0-1, white = 1) and back: a power of 1 / gamma, or the
standard sRGB curve when gamma is "srgb".
"""
def encode(x, gamma=2.2):
    if gamma == "srgb":
        return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055)
    return np.power(x, 1 / float(gamma))


def decode(v, gamma=2.2):
    if gamma == "srgb":
        return np.where(v <= 0.04045, v / 12.92, np.power((np.maximum(v, 0.04045) + 0.055) / 1.055, 2.4))
    return np.power(v, float(gamma))


"""
A soft shoulder on linear brightness (white = 1): unchanged up to knee, then rolling off toward 1 with no
step in slope, so what is brighter than white keeps its shape instead of clipping flat. Worked out only past the
knee (a few bright pixels of most pictures), each the same value as over the whole picture.
"""
def roll_off(x, knee):
    room = 1 - knee
    out = x.copy()
    past = ~(x <= knee)
    out[past] = knee + room * np.tanh((x[past] - knee) / room)
    return out


"""
x (channels first, linear) with its brightest channel rolled off past shoulder (roll_off) and the other channels by
the same factor, so a pixel keeps its color; in place, and only the pixels past the shoulder (the rest were multiplied
by 1)
"""
def _shoulder(x, shoulder):
    top = x.max(axis=0)
    past = top > shoulder
    top = top[past]
    x[:, past] *= roll_off(top, shoulder) / np.maximum(top, 1e-12)


"""
An I/F image as a BGR uint8 image: black -> 0, black + white -> 255, gamma encoded (or the sRGB curve,
gamma "srgb"); with a shoulder, brightness past it rolls off softly (roll_off) instead of clipping
"""
def display(iof, black, white, gamma=2.2, shoulder=None, toe=None):
    x = iof - black
    if toe:
        # a soft toe instead of a hard clip at black: values just above it fade in quadratically over toe (I/F),
        # so noise sitting at the black point is a smooth dark fade, not black salt among gray grain
        x = np.where(x <= 0, 0, np.where(x <= toe, x * x / (2 * toe), x - toe / 2))
    x = x / white
    x = np.clip(roll_off(x, shoulder) if shoulder else x, 0, 1)
    gray = (encode(x, gamma) * 255 + 0.5).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
