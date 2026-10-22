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
SKY_DARK = 99       # balanced composites: this percentile of the dark sky's brightness is below the toe (tone)
SHOULDER = 0.8       # balanced composites: above this share of white, brightness rolls off softly instead
                     # of clipping (limbs and ring highlights past the white keep their shape)


def look():
    return _look.get()


@contextlib.contextmanager
def looking(name):
    token = _look.set(name if name in LOOKS else LOOKS[0])
    try:
        yield
    finally:
        _look.reset(token)


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
        return [display(iof, black, scale["white"], gamma, scale.get("shoulder"))
                for iof, black in zip(iofs, scale["blacks"])]
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
returns (channels, margin), or None when a frame can't be calibrated or there is nothing to draw
"""
def load_linear(labels, images=None, iofs=None):
    if images is None:
        images = [lbl.resize_image() for lbl in labels]
    iofs = _calibrated(labels, images, iofs)
    if iofs is None:
        return None
    levels, margin, white, measured = _balanced_scale(iofs)
    if white <= 0:
        return None
    channels = [(iof - np.float32(level)) / np.float32(white) for iof, level in zip(iofs, levels)]
    margin /= white
    if measured:
        # the toe starts no lower than the darker half of the sky's own brightness (SKY_DARK of it stays black),
        # since the gamma lifts even a tiny remainder into visible grain. Only the darker half, by its mean over
        # 15 pixels, so faint ring glow or a night side in the sky doesn't count as sky
        sky = _sky(iofs)
        lum = np.mean(channels, axis=0)
        local = cv2.blur(lum, (15, 15))
        dark = sky & (local <= np.median(local[sky]))
        if dark.sum() > 100:
            margin = max(margin, 1.5 * float(np.percentile(lum[dark], SKY_DARK)))
    return channels, margin


"""
Balanced composites' channels (load_linear, aligned) as BGR uint8 images: the noise margin comes off the
brightness (the channels' mean) through a toe, black up to two thirds of the margin, then curving into the
brightness less the margin, and every channel is scaled by the same factor, so a pixel keeps its color.
Past the shoulder the brightest channel rolls off softly (roll_off), the others by the same factor.
"""
def tone(channels, margin, shoulder=SHOULDER, gamma=2.2):
    x = np.stack(channels).astype(np.float32)
    lum = x.mean(axis=0)
    a = 2 * margin / 3
    if a > 0:
        toed = np.where(lum <= a, 0, np.where(lum <= 2 * a, (lum - a) ** 2 / (2 * a), lum - 1.5 * a))
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
def _balanced_scale(iofs, sky_fraction=0.1, sky_percentile=98):
    sky = _sky(iofs)
    measured = bool(sky.mean() > sky_fraction)
    levels, margin = [0.0] * len(iofs), 0.0
    if measured:
        levels, margin = sky_levels([[iof] for iof in iofs], [[sky]] * len(iofs))
        # noise floor: the margin is at least the noisiest channel's classic one (its 98th percentile above its
        # median), so no channel shows more of its sky noise, scan lines or compression blocks than before
        margin = max(margin, max(float(np.percentile(iof[sky], sky_percentile) - np.median(iof[sky])) for iof in iofs))
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
sky_blacks' parts: (the sky level per channel, the margin)
"""
def sky_levels(images, masks):
    levels, noises = [], []
    for ims, ms in zip(images, masks):
        sky = np.concatenate([im[m] for im, m in zip(ims, ms)])
        steps = np.concatenate([np.abs(np.diff(im, axis=1))[m[:, 1:] & m[:, :-1]] for im, m in zip(ims, ms)])
        noise = 1.4826 * float(np.median(steps)) / math.sqrt(2) if steps.size else 0.0
        levels.append(min(float(np.median(sky)), float(np.percentile(sky, 20)) + 0.84 * noise))
        noises.append(noise)
    margin = NOISE_MARGIN * math.sqrt(sum(n * n for n in noises) / len(noises))
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
def display(iof, black, white, gamma=2.2, shoulder=None):
    x = (iof - black) / white
    x = np.clip(roll_off(x, shoulder) if shoulder else x, 0, 1)
    gray = (encode(x, gamma) * 255 + 0.5).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
