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
  3. subtract the bias (BIAS_STRIP_MEAN)
  4. divide by the exposure time, corrected for the shutter offset
  5. scale by the gain state, the pixel summation and the sensor's decline over time
  6. divide by the filter's sensitivity to sunlight (filter_calibration.csv) and the
     distance from the sun, giving I/F

Not done (needs CISSCAL's per pixel calibration files or the raw images): dark current,
flat fields and dust rings, 2 Hz noise, nonlinearity and anti-blooming pixel pairs.

Frames that can't be unstretched return None and the caller keeps the old behavior.
"""
import contextlib
import contextvars
import datetime
import json
import math
import os

import cv2
import numpy as np

import data_source as ds


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
    if bias <= 0 and ds.lut8():
        stored = stored_values(png, info)
        kept = stored[np.asarray(png) > 0]
        bias = float(np.percentile(kept, 0.1)) if kept.size else 0.0
    return bias


"""
Calibrates one frame to I/F. Returns None if the frame can't be calibrated.
png = the frame's PNG as stored in the dataset
image = optional image on the same scale as png to calibrate instead (see unstretch)
"""
def calibrate(png, info, image=None):
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

    if _value(info, "SHUTTER_STATE_ID", "ENABLED") != "DISABLED":
        first, last = SHUTTER_SLOPE[camera]
        exposure = exposure - np.linspace(first, last, pixels.shape[1] if codes else dn.shape[1]) - SHUTTER_OFFSET[camera]
        exposure = np.maximum(exposure, 0.1)
    dn = dn * 1000.0
    per_second = (_lookup(pixels, dn) if codes else dn) / exposure

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


def look():
    return _look.get()


"""
How a balanced color picture maps its filters to color (color plan phase 2b): "natural" (the default) turns a
true color set into the colors an eye would see (natural_mix) and balances a false color set so the body comes
out gray (false_mix); "raw" draws each filter straight as a channel, as before. The classic look is always raw.
"""
COLORS = ("natural", "raw")
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
The display model in use, for cache names: "classic", "balanced" (natural color) or "raw" (balanced, filters drawn
straight)
"""
def style():
    if look() == "classic":
        return "classic"
    return "raw" if colors() == "raw" else "balanced"


@contextlib.contextmanager
def looking(name):
    token = _look.set(name if name in LOOKS else LOOKS[0])
    try:
        yield
    finally:
        _look.reset(token)


"""
The channel mix of a color set, a 3x3 matrix on linear values ([red, green, blue] out of the set's channels in
order), or None to draw each filter straight: natural color only, in the balanced look.
camera = "N" or "W"; bands = the set's color filters in channel order ("RED", "GRN", "BL1", "CB2", "MT3"...)
target = the body the set is of (TARGET_NAME), for false color
gains = false color: per band, the gain that brings the body's typical brightness to the set's mean
(false_gains), when the caller has measured it itself (a mosaic's pass); otherwise the table's
"""
def color_mix(camera, bands, target=None, gains=None, own=False):
    if style() != "balanced" or len(bands) != 3:
        return None
    m = natural_mix(camera, bands)
    if m is not None:
        return m
    gains = gains or false_gains(target, bands, camera)
    if not gains and own:
        # no mission measure of the body in these bands (a clear frame, a rare filter or body): the picture's own
        # balance alone (load_linear's FALSE_OWN), so no band outshines the others
        gains = [1.0] * len(bands)
    if not gains:
        return None
    m = np.diag(np.asarray(gains, np.float32)).view(FalseMix)
    m.tint = tint_of(target)
    return m


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
    return balance(meds, tint_of(target))


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
        # judged against the tint the balance aims at, not gray, so a body's own color (Titan's orange) is no outlier
        lum = x.mean(axis=0)
        mean = raw.mean(axis=0)
        straight = raw * (lum / np.maximum(mean, 1e-12))
        w = np.clip((_saturation(x / tint) - _saturation(straight / tint)) / FALSE_REVERT, 0, 1)
        # only where every band has signal: the sky's noise has no band ratio to compare
        w = np.where((raw.min(axis=0) > 0) & (mean > REVERT_FLOOR), w, 0)
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
        base, flat = soft(x.mean(axis=0)), soft(sharp)
        ok = (flat > REVERT_FLOOR) & (soft(mean) > REVERT_FLOOR)
        detail = np.where(ok, sharp * base / np.maximum(flat, 1e-12), x.mean(axis=0))
        x = np.stack([np.where(ok, detail * soft(c) / np.maximum(base, 1e-12), c) for c in x])
    return x


"""
A color picture already drawn (H x W x 3 uint8, gamma encoded, its channels on one white) with its channel mix
(color_mix) applied on the linear values, the brightest channel rolling off past the shoulder as in tone
"""
def mix_display(rgb, mix, gamma=2.2, shoulder=SHOULDER):
    x = decode(np.moveaxis(rgb[..., :3].astype(np.float32) / 255, -1, 0), gamma).astype(np.float32)
    x = apply_mix(mix, x)
    top = x.max(axis=0)
    x *= np.where(top > shoulder, roll_off(top, shoulder) / np.maximum(top, 1e-12), 1)
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
Returns one BGR uint8 image per label. If every frame calibrates, all channels share one
stretch so their relative brightness is what the camera measured. Otherwise the images
are returned unchanged, each with its own stretch as before.
"""
def load_channels(labels, images=None, sky_fraction=0.1, sky_percentile=98, gamma=2.2, iofs=None, scale=None):
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
        return out
    blacks, white, _ = picture_scale(iofs, sky_fraction, sky_percentile)
    if white <= 0:
        return images
    shoulder = SHOULDER if look() == "balanced" else None
    return [display(iof, black, white, gamma, shoulder) for iof, black in zip(iofs, blacks)]


"""
The channels' I/F images (float32), calibrating those not given; None if any frame can't be calibrated
"""
def _calibrated(labels, images, iofs=None):
    given = iofs or [None] * len(labels)
    iofs = []
    for lbl, image, iof in zip(labels, images, given):
        if iof is None:
            png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            iof = calibrate(png, lbl.get_info(), gray)
        iofs.append(iof)
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
labels, images, iofs = as load_channels
returns (channels, margin, the channel mix (color_mix) or None), or None when a frame can't be calibrated or there is nothing to draw
"""
def load_linear(labels, images=None, iofs=None):
    if images is None:
        images = [lbl.resize_image() for lbl in labels]
    iofs = _calibrated(labels, images, iofs)
    if iofs is None:
        return None
    # the sky is measured once, for the scale and the toe below
    sky = _sky(iofs)
    levels, margin, white, measured = _balanced_scale(iofs, sky=sky)
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
        lum = np.mean(channels, axis=0)
        lit = lum > 0.2 * np.percentile(lum, 99)
        if lit.sum() > 100:
            # over the pixels near the picture's typical band ratios, so rings or a bright equatorial band don't steer it
            logs = [np.log(np.maximum(c[lit], 1e-6) / np.maximum(lum[lit], 1e-6)) for c in channels]
            typical = np.logical_and.reduce([np.abs(v - np.median(v)) < OWN_NEAR for v in logs])
            if typical.sum() > 100:
                lit = np.where(lit)
                lit = tuple(i[typical] for i in lit)
            own = [float(np.median(c[lit])) * g for c, g in zip(channels, np.diagonal(mix))]
            if min(own) > 0:
                tint = tint_of(_value(infos[0], "TARGET_NAME", ""))
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
brightness (the channels' mean) through a toe, black up to the margin (the sky at or below its own level is
black), then turning within an eighth of the margin into the brightness less the margin, and every channel is scaled by the same factor, so a pixel keeps its color.
Past the shoulder the brightest channel rolls off softly (roll_off), the others by the same factor. mix = the
set's channel mix (color_mix), applied first, on the linear values.
"""
def tone(channels, margin, mix=None, shoulder=SHOULDER, gamma=2.2):
    x = np.stack(channels).astype(np.float32)
    if mix is not None:
        x = apply_mix(mix, x)
    lum = x.mean(axis=0)
    w = margin / 8
    if w > 0:
        toed = np.where(lum <= margin, 0, np.where(lum <= margin + w, (lum - margin) ** 2 / (2 * w),
                                                  lum - margin - w / 2))
        x *= np.where(lum > 0, toed / np.maximum(lum, 1e-12), 0)
    if shoulder:
        top = x.max(axis=0)
        x *= np.where(top > shoulder, roll_off(top, shoulder) / np.maximum(top, 1e-12), 1)
    x = np.clip(x, 0, 1)
    return [cv2.cvtColor((encode(c, gamma) * 255 + 0.5).astype(np.uint8), cv2.COLOR_GRAY2BGR) for c in x]


"""
One picture's own display scale, as load_channels uses it: (black per channel, white, whether the
blacks were measured on the sky or left at zero for want of sky), in I/F.
iofs = the picture's channels, float32 I/F
"""
def picture_scale(iofs, sky_fraction=0.1, sky_percentile=98):
    # Sky is where every channel is dark; without enough sky the black point stays at zero.
    sky = np.ones(iofs[0].shape, dtype=bool)
    for iof in iofs:
        sky &= iof < 0.05 * np.percentile(iof, 99.9)
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
    levels, margin, white, measured = _balanced_scale(iofs, sky_fraction, sky_percentile)
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


def _balanced_scale(iofs, sky_fraction=0.1, sky_percentile=98, sky=None):
    sky = _sky(iofs) if sky is None else sky
    measured = bool(sky.mean() > sky_fraction)
    levels, margin = [0.0] * len(iofs), 0.0
    if measured:
        # the noise floor (noise_floor) taken with the sky levels, on the same sky pixels and medians
        levels, margin = sky_levels([[iof] for iof in iofs], [[sky]] * len(iofs), floor_pct=sky_percentile)
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
        median = np.median(sky)
        levels.append(min(float(median), float(np.percentile(sky, 20)) + 0.84 * noise))
        noises.append(noise)
        if floor_pct is not None:
            floors.append(float(np.percentile(sky, floor_pct) - median))
    margin = NOISE_MARGIN * math.sqrt(sum(n * n for n in noises) / len(noises))
    if floor_pct is not None:
        margin = max(margin, max(floors))
    return levels, margin


"""
The display scale shared by the tiles of a mosaic that would each otherwise be stretched on its
own (the reel's mosaics): every tile's own scale (picture_scale), then per channel the median of
the blacks of the tiles that had sky to measure them on (a tile filled by the body says nothing
about the sky), and one white, the brightest tile's, so no tile clips. Each tile looks much as it
would alone, but all are on one scale, so they meet without brightness or colour steps.
pictures = one list of channel I/F images per tile (stacking.load_hdr)
"""
def tiles_scale(pictures, gamma=2.2):
    scales = [picture_scale([iof.astype(np.float32) for iof in iofs]) for iofs in pictures]
    measured = [s for s in scales if s[2]]
    blacks = [float(np.median([s[0][c] for s in measured])) if measured else 0.0 for c in range(len(pictures[0]))]
    white = max(float(s[1]) for s in scales)
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
step in slope, so what is brighter than white keeps its shape instead of clipping flat.
"""
def roll_off(x, knee):
    room = 1 - knee
    return np.where(x <= knee, x, knee + room * np.tanh((x - knee) / room))


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
