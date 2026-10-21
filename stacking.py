# -*- coding: utf-8 -*-
"""
Finds repeat exposures of a frame so they can be stacked into one lower-noise image.

A repeat is a frame from the same camera, target, observation and exact filter pair,
taken within a short window of the original with the same exposure settings.
Repeats that turn out to point somewhere else (the next panel of a mosaic) are
dropped later, when image_correction.stack_frames fails to align them.
"""

import threading
import cv2
import numpy as np
import pandas as pd
import calibration as cal
import data_source as ds
import label_handler as lh
import image_correction as ic

index = None
groups = None
_index_lock = threading.Lock()
keys = ["INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME"]
# label fields that must match for two frames to be stacked
same_settings = ["EXPOSURE_DURATION", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID"]


def load_index():
    global index, groups
    if index is None:
        # read once, even when several threads (the frame server's) ask at the same time
        with _index_lock:
            if index is None:
                idx = pd.read_csv("Image_index.csv", usecols=keys + ["path", "seconds_1970"], low_memory=False).set_index("path", drop=False)
                # row positions of every camera/target/observation/filter combination, for fast lookup
                groups = idx.groupby(keys, sort=False).indices
                index = idx
    return index


"""
Returns the paths of repeat exposures of the frame at path, nearest in time first,
including path itself as the first entry.
path = frame path as get_images returns it (with or without the "data/" prefix)
window = largest time difference in seconds for a frame to count as a repeat
max_frames = most frames to return
"""
def find_repeats(path, window=120, max_frames=5):
    idx = load_index()
    prefix = "data/" if path.startswith("data/") else ""
    key = path[len(prefix):]
    if key not in idx.index:
        return [path]
    row = idx.loc[key]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]

    rows = groups.get(tuple(row[k] for k in keys))
    if rows is None:
        return [path]
    same = idx.iloc[rows]
    same = same[same["path"].notna()]
    same = same.assign(gap=(same["seconds_1970"] - row["seconds_1970"]).abs())
    same = same[(same["gap"] <= window) & (same["path"] != key)]
    nearest = same.sort_values("gap")["path"].tolist()
    return [path] + [prefix + p for p in nearest[:max_frames - 1]]


"""
Loads the frame at path and stacks it with its repeat exposures.
returns (label of the frame at path, stacked image resized like label.resize_image),
plus how many frames went in when count is True
"""
def load_stacked(path, window=120, max_frames=5, count=False):
    lbl = lh.label(path, as_png=True)
    frames = [lbl.resize_image()]
    if max_frames <= 1:
        return (lbl, frames[0], 1) if count else (lbl, frames[0])
    for repeat in find_repeats(path, window, 4 * max_frames)[1:]:
        if len(frames) >= max_frames:
            break
        try:
            repeat_lbl = lh.label(repeat, as_png=True)
            # only identical exposures can be averaged; many repeats are exposure brackets
            if any(repeat_lbl.info.get(k) != lbl.info.get(k) for k in same_settings):
                continue
            frame = repeat_lbl.resize_image()
        except Exception as e:
            print(f"Skipping repeat {repeat}: {e}")
            continue
        if frame is not None:
            frames.append(frame)
    if len(frames) > 1:
        print(f"Stacking {len(frames)} frames for {path}")
    stacked = ic.stack_frames(frames)
    return (lbl, stacked, len(frames)) if count else (lbl, stacked)


"""
Loads the frame at path with every repeat exposure of it, whatever their exposure times, summing
modes or gains, and merges them in I/F (calibration.calibrate): an exposure bracket (a short
exposure for the bright parts, a long one for the faint ones) becomes one picture with the range
of both. Each frame is calibrated on its own, aligned to the frame at path, and averaged weighted by
its exposure time (the long exposures carry the faint signal), leaving out its saturated pixels
and the few around them (charge bleeds out of a full pixel), so where a long exposure saturated the
short one is used. A repeat that can't be matched (a faint frame of mostly empty sky, where phase
correlation finds nothing) is taken as it is: repeats are seconds apart at the same pointing.
returns (label of the frame at path, float32 I/F image sized like label.resize_image, how many
frames went in), or the label, None and 1 when the frame at path can't be calibrated
"""
def load_hdr(path, window=120, max_frames=8):
    lbl = lh.label(path, as_png=True)
    ref = first = None
    total, weight, n = None, None, 0
    for p in find_repeats(path, window, max_frames):
        try:
            l = lbl if p == path else lh.label(p, as_png=True)
            info = l.get_info()
            image = l.resize_image()
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            codes = ds.imread(l.export(), cv2.IMREAD_GRAYSCALE)
            iof = cal.calibrate(codes, info, gray)
        except Exception as e:
            print(f"Skipping repeat {p}: {e}")
            continue
        if iof is None:
            if p == path:
                return lbl, None, 1
            continue
        if ref is None:
            ref, first = image, iof
        else:
            shift = ic.find_shift(ref, image, 20)
            if shift is not None:
                iof = ic.shift_image(iof.astype(np.float32), *shift)
                gray = ic.shift_image(gray, *shift)
        good = ~cv2.dilate(cal.saturated(codes, info, gray).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        w = good * np.float32(float(info.get("EXPOSURE_DURATION", 1)) or 1)
        total = iof * w if total is None else total + iof * w
        weight = w if weight is None else weight + w
        n += 1
    if total is None:
        return lbl, None, 1
    # pixels saturated in every exposure keep the reference's (clipped) value
    merged = total / np.maximum(weight, 1e-9)
    merged = np.where(weight > 0, merged, first).astype(np.float32)
    if n > 1:
        print(f"Merged {n} exposures for {path}")
    return lbl, merged, n
