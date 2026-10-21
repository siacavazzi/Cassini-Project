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
import datetime
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
        stored = stored_values(png, info)
        if image is None:
            return stored
        low, high = stored.min(), stored.max()
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
Lean archive (helper programs/convert_archive.py) only: what the camera sent for each
pixel, from the 8-bit codes in the PNG. TABLE frames were sent as the codes themselves,
12BIT frames as DN, which the archive squeezed into the same codes.
"""
def stored_values(codes, info):
    codes = np.asarray(codes)
    if _value(info, "DATA_CONVERSION_TYPE", "") == "12BIT":
        return LUT[codes]
    return codes.astype(np.float64)


"""
Lean archive only: stretches a frame of codes min..max -> 0..254 the way the old
dataset PNGs were, so code written for those still sees the same images.
8LSB frames were copied from the old PNGs and are returned as they are.
"""
def display_stretch(codes, info):
    if _value(info, "DATA_CONVERSION_TYPE", "") not in ("TABLE", "12BIT"):
        return codes
    stored = stored_values(codes, info)
    low, span = stored.min(), stored.max() - stored.min()
    if span <= 0:
        return np.zeros_like(codes)
    return np.floor((stored - low) * 254.0 / span + 0.5).astype(np.uint8)


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

    dn = unstretch(png, info, image)
    if dn is None:
        return None

    bias = float(_value(info, "BIAS_STRIP_MEAN", "0"))
    if _value(info, "DATA_CONVERSION_TYPE") == "TABLE":
        dn = np.interp(dn, np.arange(256), LUT)
        bias = LUT[int(min(max(bias, 0), 255))]
    dn = dn - bias

    if _value(info, "SHUTTER_STATE_ID", "ENABLED") != "DISABLED":
        first, last = SHUTTER_SLOPE[camera]
        exposure = exposure - np.linspace(first, last, dn.shape[1]) - SHUTTER_OFFSET[camera]
        exposure = np.maximum(exposure, 0.1)
    per_second = dn * 1000.0 / exposure

    gain_ratio = GAIN_RATIOS[camera][GAIN_STATES[gain]]
    slope, start = SENSITIVITY[camera]
    try:
        image_number = float(_value(info, "IMAGE_NUMBER", "0"))
    except ValueError:
        image_number = 0
    sensitivity = 1 + slope * (image_number - start) if image_number > start else 1.0

    return per_second * k / gain_ratio * SUM_FACTORS[mode] * sensitivity * distance ** 2


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
        if stored_values(codes, info).max() < top:
            return np.zeros(image.shape, bool)
        # the display stretch puts the top at 254; a resized frame's partly full pixels count too
        return image >= 250
    return image >= 254


"""
Loads the frames of one color image and puts them on the same brightness scale.

labels = label objects, one per channel
images = the channels' images as label.resize_image (or stacking.load_stacked) returns
them; loaded with resize_image if not given
iofs = optional list, one per label: an I/F image already calibrated (stacking.load_hdr) to use
instead of calibrating that channel's image, or None
scale = optional fixed display scale shared by every picture of a mosaic, a dict with "white"
(the I/F that becomes full brightness), "blacks" (one I/F per channel that becomes black) and
optionally "gamma"; without it each picture is stretched on its own as below
Returns one BGR uint8 image per label. If every frame calibrates, all channels share one
stretch so their relative brightness is what the camera measured. Otherwise the images
are returned unchanged, each with its own stretch as before.
"""
def load_channels(labels, images=None, sky_fraction=0.1, sky_percentile=98, gamma=2.2, iofs=None, scale=None):
    if images is None:
        images = [lbl.resize_image() for lbl in labels]
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
        return images

    iofs = [iof.astype(np.float32) for iof in iofs]
    if scale is not None:
        # every picture of a mosaic on the same scale, so tiles and filters keep what the camera saw
        gamma = scale.get("gamma", gamma)
        return [display(iof, black, scale["white"], gamma) for iof, black in zip(iofs, scale["blacks"])]
    # Black point per channel: just above the sky left after the bias (dark current,
    # stray light, noise), so the sky's noise, DN steps and lossy compression blocks
    # don't come out as colored speckle. Sky is where every channel is dark; without
    # enough sky the black point stays at zero.
    sky = np.ones(iofs[0].shape, dtype=bool)
    for iof in iofs:
        sky &= iof < 0.05 * np.percentile(iof, 99.9)
    blacks = [0.0] * len(iofs)
    if sky.mean() > sky_fraction:
        blacks = [np.percentile(iof[sky], sky_percentile) for iof in iofs]
    # One white point for all channels: the brightest channel's brightest pixel, after a
    # 3x3 median so a single cosmic ray hit or hot pixel can't set it
    white = max(cv2.medianBlur(iof - black, 3).max() for iof, black in zip(iofs, blacks))
    if white <= 0:
        return images
    return [display(iof, black, white, gamma) for iof, black in zip(iofs, blacks)]


"""
An I/F image as a BGR uint8 image: black -> 0, black + white -> 255, gamma encoded
"""
def display(iof, black, white, gamma=2.2):
    scaled = np.clip((iof - black) / white, 0, 1) ** (1 / gamma)
    gray = (scaled * 255 + 0.5).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
