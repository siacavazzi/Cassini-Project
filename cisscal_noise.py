# -*- coding: utf-8 -*-
"""
Two steps of CISSCAL 4.1 (the camera team's IDL calibration, the last PDS release, COISS_0011/extras/cisscal.tar.gz)
that ISIS's cisscal leaves out, ported line for line from the IDL:

  "twohz"  cassimg__twohz.pro, overclocked pixel method (CISSCAL's default, bias type OC): the horizontal banding
           ("2 Hz noise") added during readout, taken out one value per line. Run after the bias, before the dark.
  "pairs"  cassimg__brightdark.pro: the bright/dark pixel pairs anti-blooming mode leaves (a pixel 30 DN over its
           neighbors sitting on one 30 DN under them), replaced by the mean of their left and right neighbors. Run
           after the dark, before the nonlinearity.

  "twohzsky" cassimg__twohz.pro, image mean method (CISSCAL's bias type IM, offered as an option there): the same
           banding measured from the frame's own background, each line's median with stars and bodies masked, which
           catches the bands far better than the few overclocked pixels. Used where the frame has dark sky enough
           (sky_lines, not in CISSCAL), also on the 8-bit low gain and lossy frames CISSCAL leaves alone; else the
           overclock method.

The IDL's own limits are kept for the overclock method: no 2 Hz removal on summed frames, on lossy frames (their overclocks are corrupt, so
CISSCAL has none to use) or on 8-bit table frames at a gain below 12 e-/DN (the table's steps are bigger than the
noise; cassimg__debias.pro takes the bias from BIAS_STRIP_MEAN for those, calibration.overclock_bias); pairs only
on full-size frames with anti-blooming on.

Not as the IDL: the lines calibration.overclock_avg drops from the bias fit (lost in downlink, or garbled: #190) are
treated as missing here too and filled from the fit, as the IDL fills its zeros, so a garbled overclock never turns
into a bright line.

IDL helpers (smooth, median, convol, SavGol) are ported with their edge rules: smooth leaves its (w-1)/2 edge points
as they were, median of an even count is the upper middle value, convol /edge_truncate repeats the edge values.
"""
import functools
import math

import numpy as np
from scipy.ndimage import correlate1d, uniform_filter
from scipy.signal import savgol_coeffs

# cassimg__brightdark.pro: the CISSCAL default threshold (cisscal_default_options.txt "abpp threshold", DN)
PAIR_THRESHOLD = 30.0


def _value(info, key, default=""):
    value = info.get(key, default) if info else default
    return str(value).strip().strip('"') if value is not None else default


def _number(text, default):
    try:
        return float(str(text).split("<")[0])
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------------------------------------------
# IDL built-ins, as CISSCAL uses them

def idl_smooth(x, width):
    """IDL SMOOTH(x, width) of a 1-D array with no EDGE keyword: a boxcar mean, the first and last (width-1)/2 points
    copied unchanged (an even width is taken as width+1, as IDL does)."""
    x = np.asarray(x, dtype=np.float64)
    w = int(width)
    if w % 2 == 0:
        w += 1
    half = (w - 1) // 2
    if w <= 1 or x.size < w:
        return x.copy()
    out = x.copy()
    c = np.concatenate(([0.0], np.cumsum(x)))
    out[half:x.size - half] = (c[w:] - c[:-w]) / w
    return out


def idl_median(x):
    """IDL MEDIAN(x) of an array (no /EVEN): an even count gives the upper of the two middle values."""
    x = np.sort(np.asarray(x, dtype=np.float64).ravel())
    return x[x.size // 2]


@functools.lru_cache(maxsize=None)
def savgol(half):
    """IDL SAVGOL(half, half, 0, 4): the degree 4 Savitzky-Golay smoothing kernel 2*half+1 long."""
    return savgol_coeffs(2 * half + 1, 4)


def idl_convol_truncate(x, kernel):
    """IDL CONVOL(x, kernel, /EDGE_TRUNCATE) of a 1-D array with an odd, centred kernel (no scaling)."""
    return correlate1d(np.asarray(x, dtype=np.float64), np.asarray(kernel, dtype=np.float64), mode="nearest")


# ---------------------------------------------------------------------------------------------------------------
# CassImg::LineBreak (cassimg__define.pro) and cisscal_linetime.pro's line_break

_TELEM_NC = ((1.0161, 1.0128, 1.0095, 1.0082, 1.0031, 1.0033, 1.0),   # full, not converted
             (1.0297, 1.0296, 1.0252, 1.0148, 1.0114, 1.0071, 1.0),   # sum2, not converted
             (1.0356, 1.0320, 1.0260, 1.0201, 1.0128, 1.0057, 1.0),   # sum4, not converted
             (1.0194, 1.0148, 1.0028, 1.0011, 1.0014, 1.0009, 1.0),   # full, converted
             (1.0248, 1.0219, 1.0173, 1.0151, 1.0097, 1.0057, 1.0),   # sum2, converted
             (1.0010, 1.0000, 0.9970, 0.9910, 0.9821, 0.9763, 1.0))   # sum4, converted
_TELEM_L = ((1.0276, 1.0284, 1.0182, 1.0122, 1.0048, 1.0016, 1.0),
            (1.0030, 0.9979, 0.9933, 0.9854, 0.9884, 1.0023, 1.0),
            (1.0011, 0.9976, 0.9894, 0.9864, 1.0000, 1.0000, 1.0),
            (1.0013, 1.0004, 0.9935, 0.9920, 1.0002, 0.9992, 1.0),
            (1.0013, 0.9950, 1.0000, 1.0000, 1.0000, 1.0001, 1.0),
            (0.9986, 0.9863, 1.0017, 1.0021, 1.0010, 1.0017, 1.0))
_RATE_NC = ((67.49, 85.11, 142.54), (71.96, 88.99, 152.12))
_CORR_NC = ((1.0027, 1.0073, 1.0087), (1.0016, 1.0042, 0.9946))
_RATE0_L = ((67.673, 90.568, 150.593), (74.862, 91.429, 152.350))
_SLOPE_L = ((1.6972, 0.3671, 0.4541), (0.4918, 0.4411, 0.5417))
_CORR_L = ((0.9999, 1.0034, 1.0073), (1.0019, 1.0050, 1.0080))
_CDSR = ((60.0, 61.0, 8), (121.0, 122.0, 16), (182.0, 183.0, 24), (243.0, 244.0, 32), (304.0, 305.0, 40),
         (365.0, 366.0, 48))

f32 = np.float32


def line_break(info):
    """The line where a frame's readout paused or slowed (cisscal_linetime's line_break, as CassImg::LineBreak asks
    for it: line 0, the camera named "ISSNA"/"ISSWA", so linetime's NAC/WAC "second camera" test never holds), in
    the IDL's single precision; 1024 when there is none."""
    sum_mode = _value(info, "INSTRUMENT_MODE_ID", "FULL").upper()
    sindex = {"FULL": 0, "SUM2": 1, "SUM4": 2}.get(sum_mode)
    if sindex is None:
        return 1024
    nlines = (1024, 512, 256)[sindex]
    comp = _value(info, "INST_CMPRS_TYPE", "NOTCOMP").upper()
    conv = _value(info, "DATA_CONVERSION_TYPE", "TABLE").upper()
    btsm = 1 if _value(info, "DELAYED_READOUT_FLAG", "NO").upper() == "YES" else 0
    rate = _number(_value(info, "INSTRUMENT_DATA_RATE", "0"), 0.0)
    cdsr = next((c for lo, hi, c in _CDSR if lo <= rate <= hi), 24)
    tlm = cdsr // 8
    fsw = _number(_value(info, "FLIGHT_SOFTWARE_VERSION_ID", "0"), 0.0) or 1.4
    ratio = 1.0
    if comp != "NOTCOMP":
        ratio = _number(_value(info, "INST_CMPRS_RATIO", "-1"), -1.0)
        if ratio == -1:
            ratio = _number(_value(info, "COMPRESSION_RATIO", "0"), 0.0)
    roindex = int(_number(_value(info, "READOUT_CYCLE_INDEX", "0"), 0.0))
    if comp == "LOSSY":
        return 1024
    cindex = 0 if conv == "12BIT" else 1
    if not ratio:
        ratio = 2.0
    if comp == "NOTCOMP":
        ratio = 1.0
    data = (16.0, 8.0)[cindex]
    correction = f32(1.0)
    if comp == "NOTCOMP":
        if fsw >= 1.4:
            correction = f32(_CORR_NC[cindex][sindex])
        base = f32(_RATE_NC[cindex][sindex])
        r1 = base * f32(_TELEM_NC[sindex + 3 * cindex][tlm]) * correction
        r0 = base * f32(_TELEM_NC[sindex + 3 * cindex][0]) * correction
    elif comp == "LOSSLESS":
        if fsw >= 1.4:
            correction = f32(_CORR_L[cindex][sindex])
        fit = f32(_RATE0_L[cindex][sindex]) + f32(_SLOPE_L[cindex][sindex]) * f32(ratio)
        r1 = fit * f32(_TELEM_L[sindex + 3 * cindex][tlm]) * correction
        r0 = fit * f32(_TELEM_L[sindex + 3 * cindex][0]) * correction
    else:
        return 1024
    tratio = ratio
    if comp == "LOSSLESS" and tratio < 2.0:
        tratio = 2.0
    fpacket = 440 // (4 + int(f32(nlines) * f32(data) / f32(16) / f32(tratio)))
    biutime = f32(0.289)
    early_lines = 1
    if sum_mode != "FULL":
        return 1024
    r2 = f32(3.5989) * f32(tlm) if conv == "12BIT" else f32(7.1989) * f32(tlm)
    if comp == "LOSSLESS":
        r2 = f32(cdsr) * f32(462.46) / (f32(4.0) + f32(1024.0) * f32(data) / f32(16.0) / f32(tratio))
    r2 = min(r2, r1)
    buffer = 336 if fsw < 1.4 else 340
    if conv != "12BIT":
        buffer *= 2
    if comp == "LOSSLESS":
        buffer *= 2
    if fsw < 1.4:
        buffer -= 1
    biu_line = fpacket + 1
    if btsm == 0:
        if fsw >= 1.4:
            early_lines = int(biutime * r0) + 1
        inbuffer = max(early_lines - fpacket, 0)
        start = early_lines if fsw >= 1.4 else biu_line
        if r2 >= r1:
            return 1024
        return start + int(r1 * f32(buffer - inbuffer) / (r1 - r2)) + 1
    readout = (50, 25, 14, 6)
    t1 = f32(math.floor(readout[roindex // 4] * (6.0 / float(tlm)) + 0.5)) + f32(0.539)   # IDL ROUND: half away from 0
    brk = buffer + fpacket + 1
    if conv == "12BIT" and comp == "NOTCOMP":
        return brk
    if fsw < 1.4:
        trans_line = int((t1 - f32(0.25)) * r0) + 1
    else:
        trans_line = int(t1 * r0) + 1
    if (conv != "12BIT" and comp == "NOTCOMP") or (conv == "12BIT" and comp == "LOSSLESS"):
        if trans_line >= brk:
            return brk
        if r2 >= r1:
            return 1024
        return trans_line + int(f32(brk - trans_line) * r1 / (r1 - r2)) + 1
    return brk


# ---------------------------------------------------------------------------------------------------------------
# CassImg::TwoHz, overclocked pixel method

def _gain_state(info):
    gain = _value(info, "GAIN_MODE_ID").upper().split("ELECTRONS")[0].split("E/DN")[0].strip()
    return {"215": 0, "1400K": 0, "95": 1, "400K": 1, "29": 2, "100K": 2, "12": 3, "40K": 3}.get(gain)


def table_low_gain(info):
    """An 8-bit table frame at a gain state below 3 (under 12 e-/DN): CISSCAL takes its bias from BIAS_STRIP_MEAN and
    leaves its 2 Hz noise in (cassimg__debias.pro, cassimg__twohz.pro)."""
    state = _gain_state(info)
    return _value(info, "DATA_CONVERSION_TYPE").upper() == "TABLE" and state is not None and state < 3


def filter_hum(hum, info, overclocks=True, fine=False):
    """The 2 Hz signal per line (hum, one value per line) filtered as cassimg__twohz.pro does ("filterhum44h"): the
    ends mirrored out 100 lines, a degree 4 Savitzky-Golay smoothing (15 points each side on the NAC, 10 on the
    WAC) less the slow part (nested boxcars), split in two at the readout's line break when there is one far enough
    from both ends. fine (not in CISSCAL): no Savitzky-Golay smoothing, so the bands finer than it passes (a few lines
    apart) are kept too, for a signal measured well enough not to need it (image_hum's, from hundreds of pixels a
    line)."""
    hum = np.asarray(hum, dtype=np.float64).copy()
    w = hum.size
    if overclocks:
        hum[0] = hum[2]
        hum[1] = hum[2]
        hum[w - 1] = hum[w - 2]
    humx = np.zeros(w + 200)
    humx[100:100 + w] = hum
    for i in range(100):
        humx[99 - i] = hum[0:i + 1].mean()
        humx[100 + w + i] = hum[w - 1 - i:w].mean()
    sw = 15 if _value(info, "INSTRUMENT_ID") == "ISSNA" else 10
    sg = savgol(sw)
    lbreak = line_break(info)
    if lbreak - 2 >= 49 and lbreak <= w - 51:
        humx1 = np.concatenate((humx[0:99 + lbreak], np.zeros(100)))
        for i in range(100):
            humx1[99 + lbreak + i] = humx1[99 + lbreak - 1 - i:99 + lbreak].mean()
        humx2 = np.concatenate((np.zeros(100), humx[100 + lbreak + 1:]))
        for i in range(100):
            humx2[99 - i] = humx2[100:100 + i + 1].mean()
        shumx1 = humx1 if fine else idl_convol_truncate(humx1, sg)
        shumx2 = humx2 if fine else idl_convol_truncate(humx2, savgol(3))
        slow1 = idl_smooth(idl_smooth(idl_smooth(humx1, 31), 49), 49)
        slow2 = idl_smooth(idl_smooth(idl_smooth(humx2, 31), 49), 49)
        n1 = humx1.size
        slowpart = np.concatenate((slow1[0:n1 - 100], [0.0, 0.0], slow2[100:]))
        shumx = np.concatenate((shumx1[0:n1 - 100], [0.0, 0.0], shumx2[100:]))
        shumx = shumx - slowpart
        shumx[100 + lbreak - 1:100 + lbreak + 1] = 0.0
    else:
        shumx = humx if fine else idl_convol_truncate(humx, sg)
        slowpart = idl_smooth(idl_smooth(idl_smooth(idl_smooth(humx, 21), 31), 49), 49)
        shumx = shumx - slowpart
    return shumx[100:100 + w]


def two_hz(info, overclock, kept):
    """The 2 Hz noise of each line in DN, to subtract from it (cassimg__twohz.pro, overclocked pixel method), or None
    where CISSCAL leaves it in (a summed frame, a lossy one, an 8-bit table frame under 12 e-/DN, no overclocks).
    overclock = the line-averaged overclocked pixels in DN (calibration.overclock_avg), kept = the lines whose
    overclocks are valid (the others are filled from a straight line through the kept ones, as the IDL fills its
    zeros)."""
    if _value(info, "INSTRUMENT_MODE_ID", "FULL").upper() != "FULL":
        return None
    if _value(info, "INST_CMPRS_TYPE").upper() == "LOSSY" or table_low_gain(info):
        return None
    if overclock is None:
        return None
    oc = np.asarray(overclock, dtype=np.float64).copy()
    kept = np.asarray(kept, dtype=bool) & (oc != 0.0)
    n = oc.size
    if kept.sum() < 2:
        return None
    idx = np.arange(n, dtype=np.float64)
    if not kept.all():
        b, a = np.polyfit(idx[kept], oc[kept], 1)
        oc[~kept] = a + b * idx[~kept]
    b, a = np.polyfit(idx, oc, 1)
    return filter_hum(oc - (a + b * idx), info, overclocks=True)


# ---------------------------------------------------------------------------------------------------------------
# cassimg__twohz.pro's image mean method (CISSCAL bias type IM): the 2 Hz signal measured from the frame's own
# background, one median per line, where the overclock method has nothing to work from

IMAGE_SIGMAS = 4.0      # AutoStarLevel(in_image, sigmas=4): the threshold over the background that makes the mask
IMAGE_PIXRANGE = 9      # cisscal_default_options.txt "pixrange": how far the mask is grown round what's over it
# not in CISSCAL: the image method is used only where the frame has this much background, else the frame keeps its
# bands (a moon or Saturn filling it leaves too little sky to measure; CISSCAL runs it anyway when asked)
IMAGE_MIN_SKY = 64      # pixels of dark sky a line needs (of the 1,008 the median is taken over) ...
IMAGE_SKY_DN = 12.0     # dark sky: where the sky round it (31 x 31) is within this many DN of the darkest, dark current off
                        # (a glow, a plume ray or a lit body is brighter than that)
IMAGE_MIN_LINES = 0.9   # ... in this share of the frame's lines


def missing_pixels(raw):
    """cassimg__readvic.pro's missing pixel array: the zeros of the raw image, each line's run filtered by a 9 wide
    median (the 0/1 majority; IDL MEDIAN leaves the 4 at each end as they were). raw = (lines, samples)."""
    m = np.asarray(raw) == 0
    out = m.copy()
    w = m.shape[1]
    if w >= 9:
        c = np.concatenate((np.zeros((m.shape[0], 1), np.int32), np.cumsum(m, axis=1, dtype=np.int32)), axis=1)
        out[:, 4:w - 4] = (c[:, 9:] - c[:, :-9]) >= 5
    return out


def _idl_median_filter(x, width):
    """IDL MEDIAN(x, width) of a 1-D array, odd width: the first and last (width-1)/2 values left as they were"""
    x = np.asarray(x)
    half = (width - 1) // 2
    out = x.copy()
    if x.size >= width:
        win = np.lib.stride_tricks.sliding_window_view(x, width)
        out[half:x.size - half] = np.sort(win, axis=1)[:, half]
    return out


def _auto_star_level(img, sigmas):
    """AutoStarLevel: the mean of the background plus sigmas of its spread, after clipping at 8 sigma and then at
    sigmas (IDL STDDEV: n - 1)"""
    d = np.asarray(img, dtype=np.float64).ravel()
    m, s = d.mean(), d.std(ddof=1)
    d = np.clip(d, m - 8 * s, m + 8 * s)
    m, s = d.mean(), d.std(ddof=1)
    d = np.clip(d, m - sigmas * s, m + sigmas * s)
    m, s = d.mean(), d.std(ddof=1)
    return m + sigmas * s


def _box_truncate(a, width):
    """IDL SMOOTH(a, width, /EDGE_TRUNCATE) of a 2-D array: a width x width mean, the edges repeated"""
    return uniform_filter(np.asarray(a, dtype=np.float64), size=width, mode="nearest")


def image_mask(image, missing):
    """The image method's mask (1 = star, body, cosmic ray or what's round it; 0 = background), from the image after
    the bias (missing pixels healed and filled first, as cassimg__twohz.pro does). Returns (mask, image healed)."""
    img = np.asarray(image, dtype=np.float64).copy()
    missing = np.asarray(missing, dtype=bool)
    w = img.shape[1]
    # FindMissing: lines (nearly) all missing, kept where 3 in a row are; single missing lines between good ones
    hsum = (missing.sum(axis=1) >= w - 5).astype(np.uint8)
    hsum = _idl_median_filter(hsum, 3).astype(bool)
    chunks = hsum[:, None] & missing
    alt = missing & ~np.roll(missing, 1, axis=0) & ~np.roll(missing, -1, axis=0)
    # HealMissingAvg: a lone missing pixel takes the mean of the lines above and below, truncated to a whole DN
    # (in single precision, as the IDL works: where the sum of the two lands a hair from a whole DN, the truncation
    # follows its rounding)
    f = img.astype(np.float32)
    heal = np.trunc(np.float32(0.5) * (np.roll(f, 1, axis=0) + np.roll(f, -1, axis=0))).astype(np.float64)
    img = np.where(alt, heal, img)
    good = ~missing
    fill = img[good].sum() / max(good.sum(), 0) if good.any() else 0.0
    img = np.where(chunks, fill, img)
    thresh = _auto_star_level(img, IMAGE_SIGMAS)
    r = IMAGE_PIXRANGE
    mask = (img > thresh).astype(np.float64)
    mask = (_box_truncate(mask, r) > 0.5 / r ** 2).astype(np.float64)
    mask = (_box_truncate(mask, r) > 0.25).astype(np.float64)
    return mask, img


def image_hum(image, missing, info, dark=None, guard=True):
    """The 2 Hz noise of each line in DN by the image mean method (cassimg__twohz.pro): each line's median over
    samples 12 to NS-5 with the masked pixels put at the mean of the line's background, filtered as filter_hum.
    image = the frame after the bias, (lines, samples) at full size; missing = missing_pixels of the raw frame;
    dark = the frame's dark current in DN (dark_current.dark_dn), or None.
    None for a summed frame or, with guard, one with too little dark sky (IMAGE_MIN_SKY pixels in IMAGE_MIN_LINES of
    its lines, dark_sky); guard=False is CISSCAL's method as it is (each line's median of the image outside the
    mask)."""
    if _value(info, "INSTRUMENT_MODE_ID", "FULL").upper() != "FULL":
        return None
    mask, img = image_mask(image, missing)
    nl, ns = img.shape
    if guard:
        # not in CISSCAL: measured on the dark sky only (dark_sky), each line's mean of it: a faint glow the mask lets
        # through (a plume, the E ring, stray light) and the unlit side of a moon are left out, so their own shape
        # isn't taken for bands, and the mean of many noisy 8-bit values steps far more finely than their median
        sky = dark_sky(img, mask, missing, dark)
        lines = ~missing.all(axis=1)
        counts = sky[:, 12:ns - 4].sum(axis=1)
        enough = counts >= IMAGE_MIN_SKY
        if not lines.any() or enough[lines].mean() < IMAGE_MIN_LINES:
            return None
        sums = (img * sky)[:, 12:ns - 4].sum(axis=1)
        means = sums / np.maximum(counts, 1)
        y = np.arange(nl)
        means = np.interp(y, y[enough], means[enough])   # a line with too little sky takes its neighbors'
        return filter_hum(means, info, overclocks=False, fine=True)
    ngood = (1.0 - mask).sum(axis=1)
    avg = (img * (1.0 - mask)).sum(axis=1) / np.maximum(ngood, 1.0)
    tmp = mask * avg[:, None] + (1.0 - mask) * img
    tmp[0] = tmp[2]
    tmp[1] = tmp[2]
    tmp[nl - 1] = tmp[nl - 2]
    return filter_hum(_line_medians(tmp[:, 12:ns - 4]), info, overclocks=False)


def dark_sky(img, mask, missing, dark):
    """Not in CISSCAL: the dark sky, a background pixel (not masked, not missing) where the background round it is
    within IMAGE_SKY_DN of the frame's darkest, once the dark current is taken off. The image mask is relative to the frame (a star is what
    stands well over the rest), so on a frame filled by Saturn, the rings or a moon it masks next to nothing and a
    line's median would be the scene's own belts, ringlets or craters; those frames have no lines this dark and keep
    the overclock method. (lines, samples) bool."""
    level = img if dark is None else img - dark
    bg = (mask == 0) & ~missing
    if bg.sum() < 100:
        return np.zeros_like(bg)
    # the level of the sky round each pixel (a 31 x 31 mean of the background: over the bands, which it averages away,
    # but not over a glow's or a plume ray's shape), against the darkest of it
    w = bg.astype(np.float64)
    smooth = uniform_filter(np.where(bg, level, 0.0), 31, mode="nearest") / np.maximum(uniform_filter(w, 31, mode="nearest"), 1e-9)
    floor = np.percentile(smooth[bg], 1)
    return bg & (smooth <= floor + IMAGE_SKY_DN)


def _line_medians(a):
    """IDL MEDIAN of each line (row): an even count gives the upper middle value"""
    return np.partition(a, a.shape[1] // 2, axis=1)[:, a.shape[1] // 2]


# ---------------------------------------------------------------------------------------------------------------
# CassImg::BrightDark

def wants_pairs(info):
    return (_value(info, "ANTIBLOOMING_STATE_FLAG").upper() == "ON"
            and _value(info, "INSTRUMENT_MODE_ID", "FULL").upper() == "FULL")


def bright_dark(image, threshold=PAIR_THRESHOLD):
    """cassimg__brightdark.pro on an image in DN (rows = lines in readout order, as the IDL's second index): a dark
    pixel more than threshold under its left, right and previous-line neighbors, with a bright pixel more than
    threshold over its left, right and next-line neighbors on the next line, are both replaced by the mean of their
    left and right neighbors (IDL SHIFT wraps round the edges). Returns (image, number of pairs)."""
    img = np.asarray(image, dtype=np.float64)
    left, right = np.roll(img, 1, axis=1), np.roll(img, -1, axis=1)
    prev, nxt = np.roll(img, 1, axis=0), np.roll(img, -1, axis=0)
    darks = (img < left - threshold) & (img < right - threshold) & (img < prev - threshold)
    brights = (img > left + threshold) & (img > right + threshold) & (img > nxt + threshold)
    bad = np.roll(brights, -1, axis=0) & darks
    count = int(bad.sum())
    if not count:
        return image, 0
    bad = bad | np.roll(bad, 1, axis=0)
    mim = 0.5 * (right + left)
    return np.where(bad, mim, img), count
