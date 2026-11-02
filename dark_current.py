# -*- coding: utf-8 -*-
"""
CISSCAL's dark current step (cassimg_subtractdark.pro), as ISIS 3's cisscal runs it (DarkCurrent.cpp): the charge
every pixel of the CCD gathers with no light, which is taken out of a frame in DN after the bias.

The camera team measured each pixel's dark charge at eight times (0, 10, 32, 100, 220, 320, 460 and 1200 s;
darkcurrent/<nac|wac>_dark_parameters.<full|sum2|sum4>.cub, electrons). A pixel's charge sits in the CCD from the
light-flood erase until its line is read out, and on the way out it is shifted down through every line below it,
picking up those lines' dark too; how long each line waits comes from the readout model (line_times: the exposure,
the summing mode, the 12-bit or 8-bit conversion, the compression and its ratio, the telemetry rate, the flight
software and the delayed readout flag, all in the label). The pixels that went hot over the mission are
listed per epoch (darkcurrent/<NAC|WAC>_hotpix<year>_<made>.tab; the epoch nearest the frame is used) with their own
charge curves, which replace the map's at those pixels. Spikes in the summed dark that fall more than 10 electrons
below a 5 line median are lifted to it, and the dark is turned into DN by the gain.

Done line by line in cisscal; here the sum over the lines below is a convolution down each column (the time a pixel
spends in a line depends only on how many lines it still has to travel), done once per frame with FFTs of the
parameter maps worked out once per map. A frame's dark is kept for the next frame with the same readout.

Not as cisscal: a time past the last grid point (1200 s) is taken at the grid's end instead of failing; the
readout order (which camera is read first) is not in the PDS label, so the label's READOUT_ORDER is used when it has
one, else 0 (the NAC first, the usual order); and the NAC's hot pixel lists are left out (HOT_PIXEL_CAMERAS). Their
curves, put in exactly as cisscal does, are 3 to 6 times the hot pixels' real excess on raw NAC frames (median 0.17 to
0.29 of the model over 2006-2014 frames, smaller still on the brightest), so taking them out dug dark holes where the
hot pixels were (pixels under -5 sigma: 478 to 1177 on N1778453158); the WAC's lists match (about 0.99) and stay.
The NAC's parameter maps carry hot spots of their own that over-predict the same way (up to 1961 DN on a 180 s frame,
still 478 to 826 holes there), so its maps are taken through a 3x3 median first (SMOOTH_MAP_CAMERAS): the NAC gets
its smooth dark (the ramp down the frame) and its hot pixels stay in the picture as they were before this step.

Maps from CASSINI_CISSCAL (flat_field.ROOT), downloaded by "helper programs/fetch_cisscal.py".
"""
import datetime
import functools
import glob
import math
import os

import cv2
import numpy as np
from scipy.interpolate import CubicSpline

import flat_field as ff

# the cameras whose hot pixel lists are used (the NAC's over-predict its hot pixels; see above)
HOT_PIXEL_CAMERAS = ("ISSWA",)
# the cameras whose dark parameter maps are put through a 3x3 median (the NAC's hot spots over-predict too)
SMOOTH_MAP_CAMERAS = ("ISSNA",)
TGRID = np.array([0.0, 10.0, 32.0, 100.0, 220.0, 320.0, 460.0, 1200.0])
# DarkCurrent::ComputeDarkDN: gain constants (e-/DN at gain state 2, ratios by GAIN_MODE_ID) and the saturation points
GAIN2 = {"ISSNA": 30.27, "ISSWA": 27.68}
GAIN_RATIOS = {"ISSNA": {215: 0.135386, 95: 0.309569, 29: 1.0, 12: 2.357285},
               "ISSWA": {215: 0.125446, 95: 0.290637, 29: 1.0, 12: 2.360374}}
E_SATURATION = {"ISSNA": 123700, "ISSWA": 113300}
DN_SATURATION = 4095.0
TELEMETRY = ((60.0, 61.0, 8), (121.0, 122.0, 16), (182.0, 183.0, 24), (203.0, 204.0, 32), (304.0, 305.0, 40),
             (365.0, 366.0, 48))
TELEM_ORDER = (8, 16, 24, 32, 40, 48)
# ComputeLineTime's readout rates (lines/s): (rate, flight software 1.4 correction, telem0, telem by rate 8..48)
NOT_COMPRESSED = {
    ("12Bit", 1024): (67.49, 1.0027, 1.0161, (1.0128, 1.0095, 1.0082, 1.0031, 1.0033, 1.0)),
    ("12Bit", 512): (85.11, 1.0073, 1.0297, (1.0296, 1.0252, 1.0148, 1.0114, 1.0071, 1.0)),
    ("12Bit", 256): (142.54, 1.0087, 1.0356, (1.0320, 1.0260, 1.0201, 1.0128, 1.0057, 1.0)),
    ("8Bit", 1024): (71.96, 1.0016, 1.0194, (1.0148, 1.0028, 1.0011, 1.0014, 1.0009, 1.0)),
    ("8Bit", 512): (88.99, 1.0042, 1.0248, (1.0219, 1.0173, 1.0151, 1.0097, 1.0057, 1.0)),
    ("8Bit", 256): (152.12, 0.9946, 1.0010, (1.0000, 0.9970, 0.9910, 0.9821, 0.9763, 1.0)),
}
# lossless: (rate0, slope with the compression ratio, flight software 1.4 correction, telem0, telem by rate)
LOSSLESS = {
    ("12Bit", 1024): (67.673, 1.6972, 0.9999, 1.0276, (1.0284, 1.0182, 1.0122, 1.0048, 1.0016, 1.0)),
    ("12Bit", 512): (90.568, 0.3671, 1.0034, 1.0030, (0.9979, 0.9933, 0.9854, 0.9884, 1.0023, 1.0)),
    ("12Bit", 256): (150.593, 0.4541, 1.0073, 1.0011, (0.9976, 0.9894, 0.9864, 1.0000, 1.0000, 1.0)),
    ("8Bit", 1024): (74.862, 0.4918, 1.0019, 1.0013, (1.0004, 0.9935, 0.9920, 1.0002, 0.9992, 1.0)),
    ("8Bit", 512): (91.429, 0.4411, 1.0050, 1.0013, (0.9950, 1.0000, 1.0000, 1.0000, 1.0001, 1.0)),
    ("8Bit", 256): (152.350, 0.5417, 1.0080, 0.9986, (0.9863, 1.0017, 1.0021, 1.0010, 1.0017, 1.0)),
}
LOSSY_RATES = {256: 89.754, 512: 110.131, 1024: 201.734}


def _value(info, key, default=""):
    return ff._value(info, key, default)


"""
The readout of a frame, from its label, in the form cisscal's DarkCurrent takes it (a hashable tuple, so a frame's
dark can be kept for others read out the same way), or None when the label lacks what the model needs (cisscal
fails on those: unknown readout cycle or delayed readout flag, an odd data rate or summing mode).
"""
def readout(info):
    camera = _value(info, "INSTRUMENT_ID")
    lines = {"FULL": 1024, "SUM2": 512, "SUM4": 256}.get(_value(info, "INSTRUMENT_MODE_ID", "FULL").upper())
    # "95 ELECTRONS PER DN" (the label handler drops the spaces: "95ELECTRONSPERDN"), as calibration.calibrate reads it
    gain = _value(info, "GAIN_MODE_ID").upper().split("ELECTRONS")[0].strip()
    if camera not in GAIN2 or lines is None or not gain.isdigit() or int(gain) not in GAIN_RATIOS[camera]:
        return None
    comp = {"NOTCOMP": "NotCompressed", "LOSSLESS": "Lossless", "LOSSY": "Lossy"}.get(
        _value(info, "INST_CMPRS_TYPE").upper())
    if comp is None:
        return None
    ratio = 1.0 if comp == "NotCompressed" else ff._number(_value(info, "INST_CMPRS_RATIO", "1"), None)
    rate = ff._number(_value(info, "INSTRUMENT_DATA_RATE", "-999"), -999.0)
    telemetry = next((t for lo, hi, t in TELEMETRY if lo <= rate <= hi), None)
    cycle = _value(info, "READOUT_CYCLE_INDEX", "UNKNOWN")
    delayed = {"NO": 0, "YES": 1}.get(_value(info, "DELAYED_READOUT_FLAG").upper())
    if ratio is None or telemetry is None or not cycle.lstrip("-").isdigit() or delayed is None:
        return None
    fsw = ff._number(_value(info, "FLIGHT_SOFTWARE_VERSION_ID", "0"), 0.0)
    conv = "12Bit" if _value(info, "DATA_CONVERSION_TYPE").upper() == "12BIT" else "8Bit"
    order = int(ff._number(_value(info, "READOUT_ORDER", "0"), 0) or 0)
    exposure = ff._number(_value(info, "EXPOSURE_DURATION", "0"), 0.0)
    year = _year(info)
    return (camera, lines, int(gain), comp, float(ratio), conv, float(fsw), telemetry, int(cycle), delayed, order,
            float(exposure), hot_file(camera, year))


"""
cisscal's ComputeLineTime: seconds from the light-flood erase until line lline (1..lines) of a frame is read out
"""
def line_time(r, lline):
    camera, lines, _, comp, ratio, conv, fsw, telemetry, cycle, btsm, order, exposure, _ = r
    tlm = telemetry // 8
    t0 = exposure / 1000 + 0.020 + 0.68 * (lines - lline) / float(lines)
    line = lline - 1
    if comp == "Lossy":
        return t0 + line / LOSSY_RATES[lines]
    data = 16.0 if conv == "12Bit" else 8.0
    k = TELEM_ORDER.index(telemetry)
    if comp == "NotCompressed":
        rate_nc, corr, telem0, telem = NOT_COMPRESSED[conv, lines]
        correction = corr if fsw >= 1.4 else 1.0
        r1 = rate_nc * telem[k] * correction
        r0 = rate_nc * telem0 * correction
    else:
        rate0, slope, corr, telem0, telem = LOSSLESS[conv, lines]
        correction = corr if fsw >= 1.4 else 1.0
        fit = rate0 + slope * ratio
        r1 = fit * telem[k] * correction
        r0 = fit * telem0 * correction
    tratio = max(ratio, 2.0) if comp == "Lossless" else ratio
    fpacket = 440 // (4 + int(lines * data / 16 / tratio))
    biu_line = fpacket + 1
    second = (camera == "ISSNA" and order == 1) or (camera == "ISSWA" and order == 0)
    biutime = 0.289
    early_lines = 1
    if second and btsm == 0:
        early_lines = int(0.262 * r0) + 1
        biu_line = max(biu_line, early_lines)
        biutime = 0.539
    if lines < 1024:
        rate = r0 if btsm == 1 else r1
        if btsm == 0 and line >= biu_line and fsw < 1.4:
            return t0 + biutime + (line - biu_line) / rate
        return t0 + line / rate
    r2 = (3.5989 if conv == "12Bit" else 7.1989) * tlm
    if comp == "Lossless":
        r2 = telemetry * 462.46 / (4.0 + 1024.0 * data / 16.0 / tratio)
    r2 = min(r2, r1)
    buffer = 336 if fsw < 1.4 else 340
    if conv != "12Bit":
        buffer *= 2
    if comp == "Lossless":
        buffer *= 2
    if fsw < 1.4:
        buffer -= 1
    if btsm == 0:
        if fsw >= 1.4:
            early_lines = int(biutime * r0) + 1
            inbuffer = early_lines - fpacket if early_lines > fpacket else 0
            line_break = 1024 if r2 >= r1 else early_lines + int(r1 * (buffer - inbuffer) / (r1 - r2)) + 1
            linetime = t0 + line / r1
            if line > line_break:
                linetime = t0 + line_break / r1 + (line - line_break) / r2
        else:
            inbuffer = early_lines - fpacket if early_lines > fpacket else 0
            line_break = 1024 if r2 >= r1 else biu_line + int(r1 * (buffer - inbuffer) / (r1 - r2)) + 1
            linetime = t0 + line / r1
            if biu_line <= line <= line_break:
                linetime = t0 + biutime + (line - biu_line) / r1
            if line > line_break:
                linetime = t0 + biutime + (line_break - biu_line) / r1 + (line - line_break) / r2
        return linetime
    readouts = {0: 50, 1: 25, 2: 14, 3: 6}
    if cycle // 4 not in readouts:
        raise ValueError("readout cycle index out of range")
    # cisscal rounds readout * 6 / tlm down always (its "nearest" test compares the number with itself)
    t1 = math.floor(readouts[cycle // 4] * (6.0 / tlm)) + 0.539
    linetime = t0 + line / r0
    line_break = buffer + fpacket + 1
    if conv == "12Bit" and comp == "NotCompressed":
        if line >= line_break:
            linetime = t0 + t1 + (line - line_break) / r2
        return linetime
    if fsw < 1.4:
        trans_line, biu_swap = int((t1 - 0.25) * r0) + 1, 0.25
    else:
        trans_line, biu_swap = int(t1 * r0) + 1, 0.0
    if (conv != "12Bit" and comp == "NotCompressed") or (conv == "12Bit" and comp == "Lossless"):
        if trans_line >= line_break:
            if line >= line_break:
                linetime = t0 + t1 + (line - line_break) / r2
        else:
            line_break = 1024 if r2 >= r1 else trans_line + int((line_break - trans_line) * r1 / (r1 - r2)) + 1
            if line > trans_line:
                linetime = t0 + trans_line / r0 + (line - trans_line) / r1 + biu_swap
            if line > line_break:
                linetime = t0 + trans_line / r0 + (line_break - trans_line) / r1 + (line - line_break) / r2 + biu_swap
    return linetime


def _basis(t):
    """cisscal's CubicNeighborhood spline of each unit vector over TGRID, at times t: (len(t), 8). A time past the
    grid is taken at its end (cisscal would fail there)."""
    t = np.clip(np.asarray(t, np.float64), TGRID[0], TGRID[-1])
    n = len(TGRID)
    s = np.searchsorted(TGRID, t, side="left") - 1    # the last grid index below t
    s = np.clip(s, 1, n - 3) - 1
    out = np.zeros((len(t), n))
    for s0 in np.unique(s):
        pick = s == s0
        spline = CubicSpline(TGRID[s0:s0 + 4], np.eye(4), bc_type="natural", axis=0)
        out[np.ix_(pick, np.arange(s0, s0 + 4))] = spline(t[pick])
    return out


@functools.lru_cache(maxsize=None)
def _hot_lists(prefix):
    out = []
    for path in sorted(glob.glob(os.path.join(ff.ROOT, "darkcurrent", f"{prefix}_hotpix*.tab"))):
        base = os.path.basename(path)
        try:
            out.append((float(base[10:16]), base))
        except ValueError:
            pass
    return tuple(out)


def _year(info):
    time = _value(info, "IMAGE_TIME", "0000-000")
    return float(time[0:4]) + float(time[5:8]) / 365 if time[0:4].isdigit() and time[5:8].isdigit() else 0.0


def hot_file(camera, year, every=False):
    """The hot pixel list of the epoch nearest the frame's year (cisscal's FindDarkFiles), or "" (none, or a camera
    whose lists are left out of the dark; every=True: any camera's, for repair_hot)."""
    best, name = 0.0, ""
    if camera not in HOT_PIXEL_CAMERAS and not every:
        return name
    for epoch, base in _hot_lists("NAC" if camera == "ISSNA" else "WAC"):
        if abs(epoch - year) < abs(best - year):
            best, name = epoch, base
    return name


def _hot_pixels(path, lines):
    """[(line, sample, charge at each TGRID time)] from a hot pixel list (cisscal's MakeDarkArray)."""
    with open(path) as f:
        text = f.read().split("\\begindata", 1)[-1]
    rows = [r.split() for r in text.splitlines() if r.strip()]
    exptimes = [float(v) for v in rows[0][2:]]
    out = []
    for cols in rows[2:]:
        values = [float(v) for v in cols]
        x, y = int(math.floor(values[0] / 1024 * lines)), int(math.floor(values[1] / 1024 * lines))
        elec, hotsat = values[2:-1], values[-1]
        if hotsat == 0.0:
            continue
        top = exptimes[int(hotsat) - 1] if hotsat > 0 else max(exptimes)
        # some of cisscal's own lists have NaN for a time (WAC_hotpix2014.3 and 2015.7 at 1200 s): that time is left
        # out, as if never measured, since one NaN here turns the pixel's whole column of the frame NaN
        known = [(t, e) for t, e in zip(exptimes, elec) if t <= top and math.isfinite(e)]
        if len(known) < 2:
            continue
        kt, ke = np.array(known).T
        # IDL style linear interpolation, carried on past the ends along the end segments
        i = np.clip(np.searchsorted(kt, TGRID, side="left"), 1, len(kt) - 1)
        slope = (ke[i] - ke[i - 1]) / (kt[i] - kt[i - 1])
        curve = slope * (TGRID - kt[i - 1]) + ke[i - 1]
        if np.isfinite(curve).all():
            out.append((y, x, curve))
    return out


@functools.lru_cache(maxsize=4)
def _parameters(camera, lines, hot):
    """The dark parameter maps (8, lines, samples) with the hot pixels put in, and their FFTs down each column."""
    mode = {1024: "full", 512: "sum2", 256: "sum4"}[lines]
    path = os.path.join(ff.ROOT, "darkcurrent", f"{'nac' if camera == 'ISSNA' else 'wac'}_dark_parameters.{mode}.cub")
    if not os.path.exists(path):
        ff._warn(f"{os.path.basename(path)} missing, no dark current")
        return None
    p = np.nan_to_num(ff.read_cube(path).astype(np.float64))
    if camera in SMOOTH_MAP_CAMERAS:
        p = np.stack([cv2.medianBlur(band.astype(np.float32), 3) for band in p]).astype(np.float64)
    if hot:
        for y, x, curve in _hot_pixels(os.path.join(ff.ROOT, "darkcurrent", hot), lines):
            p[:, y, x] = curve
    if camera == "ISSWA":
        p[0] = 0.0          # the WAC's dark at 0 s is taken as none (the NAC's has negatives near its left edge)
    spectra = np.fft.rfft(p, n=2 * lines, axis=1).astype(np.complex64)
    return p[0].astype(np.float32), spectra


"""
The frame's dark current in DN, (lines, samples) at the camera's resolution for its summing mode, float32; or None
when the label lacks what the model needs or the maps aren't there.
"""
def dark_dn(info):
    r = readout(info)
    return None if r is None else _dark(r)


@functools.lru_cache(maxsize=16)
def _dark(r):
    camera, lines, gain = r[0], r[1], r[2]
    made = _parameters(camera, lines, r[-1])
    if made is None:
        return None
    constant, spectra = made
    try:
        t = np.array([line_time(r, i + 1) for i in range(lines)])
    except (ValueError, ZeroDivisionError):
        return None
    if (t < 0).any():
        return None
    # a pixel read out on line i spent [t[d-1], t[d]] in line i - d (d = 0: from the erase until t[0])
    start = np.concatenate([[0.0], t[:-1]])
    end = start + np.maximum(t - start, 0.0)
    if (end == start).all():
        return None
    weights = _basis(end) - _basis(start)                       # (lines, 8): what each map adds per line travelled
    kernel = np.fft.rfft(weights, n=2 * lines, axis=0)          # (lines + 1, 8)
    summed = np.einsum("bfs,fb->fs", spectra, kernel.astype(np.complex64), optimize=True)
    # the inverse FFT down each column, taken along the rows of summed.T (einsum lays summed out column by column):
    # the same transforms of the same numbers as down axis 0, without numpy copying the spectrum across twice
    down = np.fft.irfft(summed.T, n=2 * lines, axis=1)[:, :lines].astype(np.float32)
    dark = constant + cv2.transpose(down)
    _lift_spikes(dark)
    dn = dark / (GAIN2[camera] / GAIN_RATIOS[camera][gain])
    dn[(dn >= DN_SATURATION) | (dark >= E_SATURATION[camera])] = DN_SATURATION
    dn.setflags(write=False)
    return dn


"""
Spikes below the summed dark (lines, samples) lifted in place to the median of the 5 lines round them (not the first
and last two lines), where that is more than 10 above them. The median from minimum and maximum passes (_median5);
np.median's own where it picks among values that are equal but not the same (zeros of both signs, NaN), since which
of those it returns is its partition's choice
"""
def _lift_spikes(dark):
    lines = len(dark)
    five = [dark[k:lines - 4 + k] for k in range(5)]
    if np.isnan(dark).any() or np.signbit(dark[dark == 0]).any():
        med = np.median(np.stack(five), axis=0)
    else:
        med = _median5(*five)
    inner = dark[2:-2]
    np.copyto(inner, med, where=med - inner > 10)


def _median5(a, b, c, d, e):
    """np.median of five arrays stacked, at each place, from a few minimum and maximum passes (a sort of five at every
    pixel down axis 0 took half the dark's time). The middle of five is the middle of e and the two of a, b, c, d that
    are neither the least nor the greatest of the four: the greater of the two pairs' lower values and the lesser of
    their upper ones."""
    f = np.maximum(np.minimum(a, b), np.minimum(c, d))
    g = np.minimum(np.maximum(a, b), np.maximum(c, d))
    return np.maximum(np.minimum(e, f), np.minimum(np.maximum(e, f), g))


"""
dark_dn(info) sized to shape (lines, samples) like the image calibrate is given (label.resize_image). None as dark_dn.
"""
def dark_for(info, shape):
    d = dark_dn(info)
    if d is None or d.shape == tuple(shape[:2]):
        return d
    k = shape[0] // d.shape[0]
    if shape[0] == k * d.shape[0] and shape[1] == k * d.shape[1]:
        # label.resize_image draws a summed frame's pixels as k x k blocks: the dark the same way, so a pixel's dark
        # stays on its own block (spread linearly, a hot spot's dark ringed the block it was repaired in, repair_hot)
        return np.repeat(np.repeat(d, k, 0), k, 1)
    return cv2.resize(d, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR if shape[0] > d.shape[0] else cv2.INTER_AREA)


@functools.lru_cache(maxsize=8)
def _hot_spots(name):
    """(x, y) at full resolution (0-1023) of every pixel a hot pixel list names, (n, 2) int"""
    with open(os.path.join(ff.ROOT, "darkcurrent", name)) as f:
        text = f.read().split("\\begindata", 1)[-1]
    rows = [r.split() for r in text.splitlines() if r.strip()][2:]
    return np.array([(int(float(r[0])), int(float(r[1]))) for r in rows if len(r) > 3], np.int64).reshape(-1, 2)


# the defect maps measured from the archive itself ("helper programs/build_hot_maps.py"): for each camera, summing
# mode and month, the pixels that stood out from the 3x3 round them in most of that month's frames while the scene
# moved, as (line, sample, +1 hot / -1 dead) at the mode's own resolution, under keys "ISSNA_SUM2_2015-08_3". The
# last part is the exposure band (EXPOSURE_BANDS): a pixel's dark charge grows with the exposure, so a 220 s frame has
# thousands of defects that a month of 30 s frames never shows (Hyrokkin, August 2015: 7,760 against 1,000)
HOT_MAPS = os.environ.get("CASSINI_HOT_MAPS") or os.path.join(ff.ROOT, "hot_maps.npz")
HOT_MAP_SPAN = 1       # a frame uses its band's maps of its month and this many months either side, together,
HOT_MAP_MONTHS = 3     # else the nearest month's within this many months
EXPOSURE_BANDS = (2.0, 10.0, 60.0, 180.0)   # seconds: band 0 is 2-10 s, ..., band 3 is 180 s and longer


def exposure_band(seconds):
    """The EXPOSURE_BANDS band of an exposure in seconds, or None under the shortest"""
    return None if seconds < EXPOSURE_BANDS[0] else int(np.searchsorted(EXPOSURE_BANDS, seconds, side="right")) - 1


@functools.lru_cache(maxsize=1)
def _hot_maps(path):
    if not os.path.exists(path):
        ff._warn(f"{os.path.basename(path)} missing, only the listed hot pixels are repaired")
        return {}
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def map_key(camera, mode, month, band):
    return f"{camera}_{mode}_{month // 12:04d}-{month % 12 + 1:02d}_{band}"


def _month(info):
    time = _value(info, "IMAGE_TIME", "")
    if not (time[0:4].isdigit() and time[5:8].isdigit()):
        return None
    year, day = int(time[0:4]), int(time[5:8])
    return year * 12 + (datetime.date(year, 1, 1) + datetime.timedelta(day - 1)).month - 1


def hot_map(info):
    """The frame's defect map from HOT_MAPS, (n, 3) int (line, sample, sign), or None: the maps of its exposure band
    and the shorter ones (a pixel hot in a shorter exposure is hot in a longer one), of its own month and the months
    either side of it, together (HOT_MAP_SPAN; a pixel that turns hot late in a month is in too few of that month's
    frames, but in the next month's map: the 2013 Hyrrokkin pass's late March dots, in April's 10-60 s map), else
    the nearest month's within HOT_MAP_MONTHS in the band nearest it (a longer one first: a defect it lists that isn't
    misbehaving in a shorter exposure is left alone by repair_hot, one missing is left in)."""
    maps, month = _hot_maps(HOT_MAPS), _month(info)
    band = exposure_band(ff._number(_value(info, "EXPOSURE_DURATION", "0"), 0.0) / 1000)
    if not maps or month is None or band is None:
        return None
    camera, mode = _value(info, "INSTRUMENT_ID"), _value(info, "INSTRUMENT_MODE_ID", "FULL")
    near = [m for d in range(-HOT_MAP_SPAN, HOT_MAP_SPAN + 1) for b in range(band, -1, -1)
            if (m := maps.get(map_key(camera, mode, month + d, b))) is not None]
    if near:
        return near[0] if len(near) == 1 else np.unique(np.concatenate(near), axis=0)
    bands = sorted(range(len(EXPOSURE_BANDS)), key=lambda b: (abs(b - band), -b))
    for b in bands:
        for d in sorted(range(-HOT_MAP_MONTHS, HOT_MAP_MONTHS + 1), key=abs):
            found = maps.get(map_key(camera, mode, month + d, b))
            if found is not None:
                return found
    return None


"""
The "hotpix" step: the detector's defects, the pixels that stay put while the sky moves (so a movie shows them as
fixed dots), each put back to the median of the 3x3 round it, in place. They are the pixels the camera team listed as
hot at the frame's epoch (the list nearest its date, either camera; the dark step can't take them out on the NAC, its
lists over-predict, see above) and the far more the archive's own frames show (hot_map; a 220 s Hyrokkin pass in
2015 has about 7,300, the list 530 of them). A hot one is repaired only where it stands REPAIR_SIGMAS times the frame's
grain above the pixels round it and a dead one only where it is as far below, so one that isn't misbehaving in this
frame is left alone (a short exposure's listed pixels are mostly just noise); a star that lands
exactly on one is filled in too. image = the frame at a whole multiple of its own size (label.resize_image gives a
summed frame's pixels as 2x2 or 4x4 blocks); returns how many were repaired.
spots: the pixels where the dark step took out more than round them (dark_spots), at the frame's own size. The
dark model over-predicts some of those in the pictures: WAC hot pixels whose listed curves (HOT_PIXEL_CAMERAS) are
stronger than the pixel has since become, and the WAC parameter maps' own hot spots (the NAC's are smoothed out,
SMOOTH_MAP_CAMERAS). They land below the sky round them, black pinholes (dozens to hundreds across a 2010 or 2016
WAC sky), and are repaired too where they stand REPAIR_SIGMAS below.
"""
REPAIR_SIGMAS = 3.0
DARK_SPOT_DN = 2.0     # a pixel whose dark is this many DN above the 3x3 median of the dark round it is a spot


def dark_spots(info):
    """The pixels, (lines, samples) bool at the frame's own size, where dark_dn(info) stands DARK_SPOT_DN above the
    3x3 median of the dark round it; None without a dark"""
    d = dark_dn(info)
    if d is None:
        return None
    return (d - cv2.medianBlur(np.ascontiguousarray(d, np.float32), 3)) > DARK_SPOT_DN


def repair_hot(image, info, spots=None):
    lines = int(ff._number(_value(info, "LINES", "1024"), 1024) or 1024)
    h, w = image.shape[:2]
    if image.ndim != 2 or h % lines or w % lines or h != w:
        return 0
    sign = np.zeros((lines, lines), np.int8)
    name = hot_file(_value(info, "INSTRUMENT_ID"), _year(info), every=True)
    if name:
        xy = _hot_spots(name) * lines // 1024
        sign[xy[:, 1], xy[:, 0]] = 1
    measured = hot_map(info)
    if measured is not None and len(measured):
        sign[measured[:, 0], measured[:, 1]] = measured[:, 2]
    below = sign < 0
    if spots is not None and spots.shape == below.shape:
        below |= spots
    if not sign.any() and not below.any():
        return 0
    k = h // lines
    native = np.ascontiguousarray(image[::k, ::k], np.float32)
    level = cv2.medianBlur(native, 3)
    # only where it stands out from the frame's grain (the spread of the frame minus its 3x3 median, from every 4th
    # pixel), so a listed pixel that is just noise in this frame is left as it is
    rest = (native - level)[::4, ::4]
    rest = rest[np.isfinite(rest)]
    grain = 1.4826 * float(np.median(np.abs(rest))) if rest.size else 0.0
    fix = (((sign > 0) & (native > level + REPAIR_SIGMAS * grain))
           | (below & (native < level - REPAIR_SIGMAS * grain)))
    fix &= np.isfinite(level)
    if k > 1:
        level = np.repeat(np.repeat(level, k, 0), k, 1)
        fix_up = np.repeat(np.repeat(fix, k, 0), k, 1)
    else:
        fix_up = fix
    image[fix_up] = level[fix_up]
    return int(fix.sum())


"""
The defects a run of one camera and summing mode's frames shows (for HOT_MAPS, "helper programs/build_hot_maps.py"):
frames = 2D arrays of one size (the archive's codes), from different observations so the scene moves. A pixel is a
defect when it stands more than SIGMAS times the frame's grain (the spread of the frame minus its 3x3 median) above
(hot) or below (dead) its 3x3 median in at least SHARE of the frames. Returns (n, 3) int16 (line, sample, sign).
"""
DEFECT_SIGMAS = 4.0
DEFECT_SHARE = 0.6


def defects(frames):
    above = below = None
    for f in frames:
        f = np.asarray(f, np.float32)
        r = f - cv2.medianBlur(f, 3)
        grain = max(1.4826 * float(np.median(np.abs(r))), 0.5)
        hi, lo = (r > DEFECT_SIGMAS * grain), (r < -DEFECT_SIGMAS * grain)
        above = hi.astype(np.int32) if above is None else above + hi
        below = lo.astype(np.int32) if below is None else below + lo
    if above is None:
        return np.zeros((0, 3), np.int16)
    need = DEFECT_SHARE * len(frames)
    hot, dead = np.argwhere(above >= need), np.argwhere(below >= need)
    return np.concatenate([np.column_stack([hot, np.ones(len(hot), np.int64)]),
                           np.column_stack([dead, -np.ones(len(dead), np.int64)])]).astype(np.int16)
