# -*- coding: utf-8 -*-
"""
CISSCAL's flat field step (Porco et al. 2004, West et al. 2010, Knowles et al. 2020), as ISIS 3's cisscal runs it
(cisscal main.cpp, FindDustRingParameters, FindFlatFile and step 5 of Calibrate): how much light every pixel of the
detector loses or gains compared with the middle of the frame, taken out of a calibrated frame.

  1. dust rings (NAC only): specks of dust on the camera's optics throw out-of-focus shadows, rings a few to a
     hundred pixels across. Ground calibration (the slope files, below) caught the ones on the detector before
     launch; more settled on during the mission, so CISSCAL has a dust ring map for each epoch (named by the image
     number from which it holds, each one holding every ring found up to then) and uses the latest one before the
     frame. Frames taken with anti-blooming off also get the ring at sample 887, line 636 corrected (aboff map;
     CISSCAL's notes say line 388, counting from the bottom as IDL draws)
  2. mottle (NAC only, from image number 1455892746, late 2003): a fine blotchy pattern that appeared after the
     2003 decontamination heating, stronger at short wavelengths (a strength factor from the filter's wavelength)
  3. divide by the flat field: the ground calibration's slope file for the camera, its optics temperature (NAC:
     -10, +5 or +25 C) and filter pair (slope_db_2.tab), inverted and normalized to its middle 400 x 400 pixels.
     It holds the detector's pixel to pixel sensitivity, the vignetting at the corners, the column pattern of the
     anti-blooming pixel pairs and the dust rings that were on the detector before launch

  4. WAC dust rings (beyond CISSCAL, which has no WAC dust map): the WAC's optics gathered dust in flight too, and
     the ground flats only hold what was there before launch, so frames of bright extended scenes show in-flight
     donuts that the flat field leaves (and a stretched sky makes plain: the 2009 south pole movie, 099SA). Measured
     from the archive itself, like the hot pixel maps: "helper programs/build_wac_dust.py" takes WAC frames of
     evenly lit scenes in each quarter year, each over its own blur (dust_ratio), their median per pixel, then
     undoes the blur's share (dust_correction). One map per quarter in WAC_DUST, used like the NAC's epochs, from
     the frame's own quarter or the nearest one within WAC_DUST_QUARTERS

The maps of steps 1-3 are CISSCAL's own, from the USGS ISIS data mirror ("helper programs/fetch_cisscal.py" downloads them, about
1 GB) into the folder CASSINI_CISSCAL names (default: cisscal_calibration in the main folder), laid out like the
mirror: slope/slope_db_2.tab, slope/flat/flat<NNN>.<full|sum2|sum4>.cub, dustring/*.cub. Without them nothing is
corrected (correction returns None) and a warning says so once.
"""
import functools
import glob
import os
import re
import threading
import warnings

import cv2
import numpy as np


ROOT = os.environ.get("CASSINI_CISSCAL", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cisscal_calibration"))
# the WAC dust ring maps ("helper programs/build_wac_dust.py"): keys like 2009Q3, the correction (what a FULL frame is
# multiplied by) as float16 at 1024 x 1024
WAC_DUST = os.environ.get("CASSINI_WAC_DUST") or os.path.join(ROOT, "wac_dust.npz")
WAC_DUST_QUARTERS = 2   # a frame in a quarter with no map uses the nearest quarter's within this many
WAC_DUST_USE = True     # the map builder measures with this off

# no mottle before this image number (cisscal: 2003-286T10:28:04)
MOTTLE_FROM = 1455892746
# mottle strength by filter when one filter of the pair is clear (cisscal's FilterIndex numbers, from CissLabels)
FILTER_INDEX = [
    {"UV1": 0, "UV2": 1, "BL1": 3, "RED": 6, "IR2": 8, "IR4": 10, "CL1": 17, "HAL": 19, "IRP0": 20, "P0": 21,
     "P60": 22, "P120": 23, "IR3": 24, "IR5": 25, "CB3": 26, "MT3": 27, "CB2": 28, "MT2": 29},
    {"UV3": 2, "BL2": 4, "GRN": 5, "IR1": 7, "IR3": 9, "CB1": 11, "CB2": 12, "CB3": 13, "MT1": 14, "MT2": 15,
     "MT3": 16, "CL2": 18, "RED": 30, "BL1": 31, "VIO": 32, "HAL": 33, "IRP90": 34, "IRP0": 35},
]
STRENGTH_FIRST = {0: 1.119, 1: 1.186, 3: 1.00, 6: 0.843, 8: 0.897, 10: 0.780, -1: 0.763}
STRENGTH_SECOND = {2: 1.069, 4: 0.833, 5: 0.890, 7: 0.997, 9: 0.505, 11: 0.764, 12: 0.781, 13: 0.608, 14: 0.789,
                   15: 0.722, 16: 0.546}
MODES = {"FULL": "full", "SUM2": "sum2", "SUM4": "sum4"}
# ISIS stores special pixels (null, saturated) as huge negative or positive floats
SPECIAL = 1e30

_warned = set()
_lock = threading.Lock()


def _warn(what):
    with _lock:
        if what not in _warned:
            _warned.add(what)
            print(f"Flat field: {what}")


"""
Reads an ISIS 3 cube of 32-bit floats (tiled or band sequential) as a float32 image, special pixels NaN: (lines,
samples) for one band, (bands, lines, samples) for more.
"""
def read_cube(path):
    with open(path, "rb") as f:
        raw = f.read()
    head = raw[:65536].decode("latin1")

    def key(name, default=None):
        m = re.search(r"(?<![A-Za-z])" + name + r"\s*=\s*(\S+)", head)
        return m.group(1) if m else default

    start, samples, lines = int(key("StartByte")) - 1, int(key("Samples")), int(key("Lines"))
    bands = int(key("Bands", "1"))
    if key("Type") != "Real":
        raise ValueError(f"{path}: not a cube of floats")
    dtype = "<f4" if key("ByteOrder") == "Lsb" else ">f4"
    if key("Format") == "Tile":
        ts, tl = int(key("TileSamples")), int(key("TileLines"))
        rows, cols = -(-lines // tl), -(-samples // ts)
        a = np.frombuffer(raw, dtype, count=bands * rows * cols * tl * ts, offset=start)
        a = a.reshape(bands, rows, cols, tl, ts).transpose(0, 1, 3, 2, 4).reshape(bands, rows * tl, cols * ts)
        a = a[:, :lines, :samples]
    else:
        a = np.frombuffer(raw, dtype, count=bands * samples * lines, offset=start).reshape(bands, lines, samples)
    a = a.astype(np.float32)
    a[~np.isfinite(a) | (np.abs(a) > SPECIAL)] = np.nan
    return a[0] if bands == 1 else a


def _value(info, key, default=""):
    value = info.get(key, default)
    return default if value is None else str(value).replace('"', "").strip()


def _filters(info):
    return [n.strip() for n in _value(info, "FILTER_NAME").strip("()").split(",")]


def _number(text, default=None):
    try:
        return float(str(text).strip("()").split(",")[0].replace("<DEGC>", "").strip())
    except ValueError:
        return default


@functools.lru_cache(maxsize=None)
def _slope_db():
    rows = []
    path = os.path.join(ROOT, "slope", "slope_db_2.tab")
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        text = f.read().split("\\begindata", 1)[-1]
    for line in text.splitlines():
        cols = [c.strip("'") for c in line.split()]
        if len(cols) >= 8:
            rows.append(cols)
    return rows


@functools.lru_cache(maxsize=None)
def _dust_epochs():
    """The numbered dust ring maps' image numbers, oldest first."""
    epochs = set()
    for path in glob.glob(os.path.join(ROOT, "dustring", "nac_dustring_*.full.cub")):
        number = os.path.basename(path)[len("nac_dustring_"):-len(".full.cub")]
        if number.isdigit():
            epochs.add(int(number))
    return tuple(sorted(epochs))


@functools.lru_cache(maxsize=None)
def _wavelengths():
    """Each camera and filter pair's effective wavelength in nm (filter_calibration.csv, CISSCAL's na_effwl)."""
    out = {}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filter_calibration.csv")
    with open(path) as f:
        next(f)
        for line in f:
            camera, filters, wavelength = line.strip().split(",")[:3]
            out[(camera, filters)] = float(wavelength)
    return out


def temperature_name(info):
    """The slope files' nominal optics temperature for the frame: m10, p5 or p25 (cisscal's FindFlatFile)."""
    t = _number(_value(info, "OPTICS_TEMPERATURE", "0"), 0.0)
    return "m10" if t < -5.0 else "p5" if t < 25.0 else "p25"


def flat_name(info):
    """The flat field for the frame's camera, optics temperature and filter pair (slope_db_2.tab), or None."""
    camera, (f1, f2) = _value(info, "INSTRUMENT_ID"), (_filters(info) + [""])[:2]
    temp = temperature_name(info)
    for cols in _slope_db():
        if cols[0] == camera and (cols[1] == temp or camera == "ISSWA") and cols[2] == f1 and cols[3] == f2:
            # SLOPE113.IMG -> flat113
            return "flat" + cols[7][5:].split(".")[0]
    return None


def dust_name(info):
    """The dust ring map for an NAC frame: the latest one whose image number is at most the frame's, else venus."""
    number = _number(_value(info, "IMAGE_NUMBER", "0"), 0)
    held = [e for e in _dust_epochs() if e <= number]
    return f"nac_dustring_{held[-1]}" if held else "nac_dustring_venus"


def quarter_of(info):
    """The frame's quarter year (IMAGE_TIME "2009-206T19:40:48"): year * 4 + quarter - 1, or None."""
    time = _value(info, "IMAGE_TIME", "")
    if not (time[0:4].isdigit() and time[5:8].isdigit()):
        return None
    year, day = int(time[0:4]), int(time[5:8])
    return year * 4 + min((day - 1) * 4 // 365, 3)


def quarter_key(quarter):
    return f"{quarter // 4}Q{quarter % 4 + 1}"


@functools.lru_cache(maxsize=None)
def _wac_dust_maps():
    """The quarters WAC_DUST has maps for, its keys and the open file (its maps are read when used)."""
    if not os.path.exists(WAC_DUST):
        _warn(f"{os.path.basename(WAC_DUST)} missing, no WAC dust ring correction")
        return {}, frozenset(), None
    store = np.load(WAC_DUST)
    quarters = {}
    for key in store.files:
        if re.fullmatch(r"\d{4}Q[1-4]", key):
            quarters[int(key[:4]) * 4 + int(key[5]) - 1] = key
    return quarters, frozenset(store.files), store


def wac_dust_name(info):
    """The WAC dust ring map for a WAC frame (wac_dust_<key>): its filter pair's own map of its year (the dust's
    fringes scale with the wavelength), else its quarter's for every filter, else the nearest quarter's within
    WAC_DUST_QUARTERS (the earlier one on a tie: dust stays on), else None."""
    quarter = quarter_of(info)
    quarters, keys, _ = _wac_dust_maps()
    if quarter is None or not keys:
        return None
    own = f"{quarter // 4}_" + "_".join((_filters(info) + [""])[:2])
    if own in keys:
        return "wac_dust_" + own
    for d in range(WAC_DUST_QUARTERS + 1):
        for q in (quarter - d, quarter + d):
            if q in quarters:
                return "wac_dust_" + quarters[q]
    return None


@functools.lru_cache(maxsize=8)
def _wac_dust(key, mode):
    """A WAC dust ring correction at the summing mode's size (a summed frame's pixel sees its block's mean), or None."""
    _, keys, store = _wac_dust_maps()
    if store is None or key not in keys:
        return None
    full = np.asarray(store[key], np.float32)
    k = {"full": 1, "sum2": 2, "sum4": 4}[mode]
    if k > 1:
        full = full.reshape(full.shape[0] // k, k, full.shape[1] // k, k).mean(axis=(1, 3))
    return np.where(np.isfinite(full) & (full > 0), full, 1.0).astype(np.float32)


"""
Measuring the WAC dust rings (step 4) from one calibrated frame (I/F, flat field on, WAC_DUST_USE off): how much
brighter or darker each pixel is than its neighborhood, the frame over its blur over DUST_SIGMA pixels, where the
scene can say so: lit (at least DUST_LIT of its bright end, its blur too), not saturated (bad), away from the lit
area's edge, and not on a feature of the scene (a limb or ring edge: more than DUST_CLIP off). NaN elsewhere. The
median of many frames' ratios at a pixel is the dust (the scene moves between them, the dust stays put).
"""
DUST_SIGMA = 40.0     # px at full resolution: wider than the rings' dark annulus, so it holds the neighborhood
DUST_LIT = 0.3        # a pixel counts when the frame is at least this share of its 99th percentile there
DUST_CLIP = 0.15      # a ratio further than this from 1 is the scene, not dust
DUST_ITERATIONS = 8
DUST_SMOOTH = 1.5     # px: the map is smoothed this much (the rings are broad; a pixel's own noise is not dust)
DUST_TEXTURE = 0.02   # a frame whose ratios spread more than this (median absolute deviation) is too busy to use
DUST_LEAST = 8        # a pixel needs this many frames' say


def _normalized_blur(x, weight, sigma):
    num = cv2.GaussianBlur(np.where(weight > 0, x, 0).astype(np.float32), (0, 0), sigma)
    den = cv2.GaussianBlur(weight.astype(np.float32), (0, 0), sigma)
    return num / np.maximum(den, 1e-6), den


def dust_ratio(iof, bad=None):
    iof = np.asarray(iof, np.float32)
    good = np.isfinite(iof)
    if bad is not None:
        good &= ~cv2.dilate(np.asarray(bad, np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if good.mean() < 0.5:
        return None
    top = float(np.percentile(iof[good], 99))
    if not top > 0:
        return None
    lit = good & (iof >= DUST_LIT * top)
    if lit.mean() < 0.3:
        return None
    smooth, cover = _normalized_blur(np.where(lit, iof, 0), lit.astype(np.float32), DUST_SIGMA)
    r = iof / np.maximum(smooth, 1e-12)
    keep = lit & (cover > 0.9) & (smooth >= DUST_LIT * top) & (np.abs(r - 1) < DUST_CLIP)
    if keep.mean() < 0.2 or float(np.median(np.abs(r[keep] - 1))) > DUST_TEXTURE:
        return None
    return np.where(keep, r, np.nan).astype(np.float32)


"""
Many frames' ratios (dust_ratio, frames, lines, samples) combined per pixel: the mean of the middle half (the scene's
leftovers spread both ways round the dust and its odd edges are cut), NaN where fewer than DUST_LEAST said anything.
"""
def dust_combine(ratios):
    stack = np.asarray(ratios, np.float32)
    count = np.isfinite(stack).sum(axis=0)
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)       # pixels no frame measured
        lo, hi = np.nanpercentile(stack, [25, 75], axis=0)
        middle = np.where((stack >= lo) & (stack <= hi), stack, np.nan)
        out = np.nanmean(middle, axis=0)
    out[count < DUST_LEAST] = np.nan
    return out.astype(np.float32)


"""
The correction (what a frame is multiplied by) from the median ratio of many frames, ratio (NaN where too few
frames said anything). The ratio is the dust over its own blur (a broad ring takes part of its blur down with
it, so it reads shallower than it is); the dust is found again by putting the blur back, a few times over:
dust = ratio * blur(dust). That also lifts the slow swells of what the scenes left, which are the flat field's
business anyway, so the result keeps only what differs from its own blur over 3 x DUST_SIGMA. Unmeasured pixels are 1
(no correction).
"""
def dust_correction(ratio):
    ratio = np.asarray(ratio, np.float32)
    known = np.isfinite(ratio)
    q = np.where(known, ratio, 1.0).astype(np.float32)
    q = _normalized_blur(q, known.astype(np.float32) + 1e-3, DUST_SMOOTH)[0]
    dust = q.copy()
    for _ in range(DUST_ITERATIONS):
        blur, _ = _normalized_blur(dust, known.astype(np.float32) + 1e-3, DUST_SIGMA)
        dust = q * blur
    dust /= cv2.GaussianBlur(dust, (0, 0), 3 * DUST_SIGMA)
    dust = np.clip(np.where(known, dust, 1.0), 1 - 2 * DUST_CLIP, 1 + 2 * DUST_CLIP)
    return (1.0 / dust).astype(np.float32)


def mottle_strength(info):
    """How strong the mottle is in the frame's filter pair (cisscal's strength factor)."""
    f1, f2 = (_filters(info) + [""])[:2]
    i1, i2 = FILTER_INDEX[0].get(f1, -2), FILTER_INDEX[1].get(f2, -2)
    if i1 in (17, 21, 22, 23, 35) and i2 == 18:   # CL1, P0, P60, P120 or IRP0 with CL2
        i1 = -1
    if (i1 < 17 and i2 < 17) or (i1 >= 17 and i2 >= 17):
        wavelength = _wavelengths().get((_value(info, "INSTRUMENT_ID"), f1 + f2))
        return 1.30280 - 0.000717552 * wavelength if wavelength else 1.0
    if i1 in STRENGTH_FIRST:
        return STRENGTH_FIRST[i1]
    return STRENGTH_SECOND.get(i2, 1.0)


@functools.lru_cache(maxsize=24)
def _map(name, mode):
    folder = "slope/flat" if name.startswith("flat") else "dustring"
    path = os.path.join(ROOT, folder, f"{name}.{mode}.cub")
    if not os.path.exists(path):
        return None
    return read_cube(path)


"""
What the frame's calibrated image is multiplied by to take the flat field out (dust rings, mottle and the flat, steps
1-4 above), at the camera's resolution for the frame's summing mode, float32; or None when there is nothing to correct
(a frame taken with the shutter disabled, as cisscal) or the maps aren't there. A step with its map missing is left
out, the others still done.
"""
def correction(info):
    if _value(info, "SHUTTER_STATE_ID", "ENABLED").upper() == "DISABLED":
        return None
    mode = MODES.get(_value(info, "INSTRUMENT_MODE_ID", "FULL"))
    if mode is None:
        return None
    if not _slope_db():
        _warn(f"no CISSCAL files in {ROOT} (helper programs/fetch_cisscal.py), frames are not flat fielded")
        return None
    nac = _value(info, "INSTRUMENT_ID") == "ISSNA"
    flat = flat_name(info)
    dust = dust_name(info) if nac else wac_dust_name(info) if WAC_DUST_USE else None
    aboff = nac and _value(info, "ANTIBLOOMING_STATE_FLAG", "ON").upper() == "OFF"
    mottle = nac and (_number(_value(info, "IMAGE_NUMBER", "0"), 0) or 0) >= MOTTLE_FROM
    strength = round(mottle_strength(info), 6) if mottle else 0.0
    return _correction(flat, dust, aboff, strength, mode)


@functools.lru_cache(maxsize=32)
def _correction(flat, dust, aboff, strength, mode):
    out = None

    def times(m):
        nonlocal out
        out = m.copy() if out is None else out * m

    if dust and dust.startswith("wac_dust_"):
        d = _wac_dust(dust[len("wac_dust_"):], mode)
        if d is not None:
            times(d)
    elif dust:
        d = _map(dust, mode)
        if d is None:
            _warn(f"{dust}.{mode}.cub missing, no dust ring correction")
        else:
            times(np.nan_to_num(d, nan=1.0))
        if aboff:
            a = _map("nac_dustring_aboff", mode)
            if a is not None:
                times(np.nan_to_num(a, nan=1.0))
    if strength:
        m = _map("nac_mottle_1444733393", mode)
        if m is not None:
            times(1 - strength * np.nan_to_num(m, nan=0.0) / 1000.0)
    if flat:
        f = _map(flat, mode)
        if f is None:
            _warn(f"{flat}.{mode}.cub missing, no flat field")
        else:
            f = np.where(np.isfinite(f) & (f > 0), f, 1.0)
            if usable_flat(f):
                times(1.0 / f)
            else:
                _warn(f"{flat}.{mode}.cub is not a flat field (corrupt in CISSCAL's own files), no flat field")
    if out is None:
        return None
    out = out.astype(np.float32)
    out.setflags(write=False)
    return out


"""
True when a flat field map (as _correction takes it, the bad pixels already 1) is one: its middle at about 1 and
next to none of it far from 1. The USGS mirror's flat129 (the NAC's UV2/CL2 flat at every temperature) is not: its
slope file was read as the wrong number type when it was brought into ISIS (pds2isis, 2009) and then divided by
-2.3e20, so its full map is 20 everywhere and its summed maps run from 1e-11 to 4e12, which turned every NAC UV2
frame into a few bright blobs on black (the 2001 Jupiter and 2017 Titan UV pairs).
"""
FLAT_RANGE = (0.2, 5.0)    # a flat field's pixels lie well inside this; more than FLAT_OUTSIDE of them outside: not one
FLAT_OUTSIDE = 0.01


def usable_flat(f):
    h, w = f.shape
    middle = float(np.median(f[h // 2 - h // 5:h // 2 + h // 5, w // 2 - w // 5:w // 2 + w // 5]))
    outside = float(np.mean((f < FLAT_RANGE[0]) | (f > FLAT_RANGE[1])))
    return 0.5 < middle < 2.0 and outside < FLAT_OUTSIDE


"""
correction(info) sized to shape (lines, samples): the frame's image may have been resized from the camera's
(label.resize_image), so the map is resized the same way. None as correction.
"""
def correction_for(info, shape):
    c = correction(info)
    if c is None or c.shape == tuple(shape[:2]):
        return c
    return cv2.resize(c, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR if shape[0] > c.shape[0] else cv2.INTER_AREA)
