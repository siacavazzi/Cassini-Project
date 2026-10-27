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

The maps are CISSCAL's own, from the USGS ISIS data mirror ("helper programs/fetch_cisscal.py" downloads them, about
1 GB) into the folder CASSINI_CISSCAL names (default: cisscal_calibration in the main folder), laid out like the
mirror: slope/slope_db_2.tab, slope/flat/flat<NNN>.<full|sum2|sum4>.cub, dustring/*.cub. Without them nothing is
corrected (correction returns None) and a warning says so once.
"""
import functools
import glob
import os
import re
import threading

import cv2
import numpy as np


ROOT = os.environ.get("CASSINI_CISSCAL", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cisscal_calibration"))

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
Reads an ISIS 3 cube (one band of 32-bit floats, tiled or band sequential) as a float32 image, special pixels NaN.
"""
def read_cube(path):
    with open(path, "rb") as f:
        raw = f.read()
    head = raw[:65536].decode("latin1")

    def key(name):
        return re.search(r"(?<![A-Za-z])" + name + r"\s*=\s*(\S+)", head).group(1)

    start, samples, lines = int(key("StartByte")) - 1, int(key("Samples")), int(key("Lines"))
    if key("Type") != "Real":
        raise ValueError(f"{path}: not a cube of floats")
    dtype = "<f4" if key("ByteOrder") == "Lsb" else ">f4"
    if key("Format") == "Tile":
        ts, tl = int(key("TileSamples")), int(key("TileLines"))
        rows, cols = -(-lines // tl), -(-samples // ts)
        a = np.frombuffer(raw, dtype, count=rows * cols * tl * ts, offset=start)
        a = a.reshape(rows, cols, tl, ts).transpose(0, 2, 1, 3).reshape(rows * tl, cols * ts)[:lines, :samples]
    else:
        a = np.frombuffer(raw, dtype, count=samples * lines, offset=start).reshape(lines, samples)
    a = a.astype(np.float32)
    a[~np.isfinite(a) | (np.abs(a) > SPECIAL)] = np.nan
    return a


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
1-3 above), at the camera's resolution for the frame's summing mode, float32; or None when there is nothing to correct
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
    dust = dust_name(info) if nac else None
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

    if dust:
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
            times(1.0 / f)
    if out is None:
        return None
    out = out.astype(np.float32)
    out.setflags(write=False)
    return out


"""
correction(info) sized to shape (lines, samples): the frame's image may have been resized from the camera's
(label.resize_image), so the map is resized the same way. None as correction.
"""
def correction_for(info, shape):
    c = correction(info)
    if c is None or c.shape == tuple(shape[:2]):
        return c
    return cv2.resize(c, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR if shape[0] > c.shape[0] else cv2.INTER_AREA)
