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
# the index's columns find_repeats reads, as numpy arrays (views of the index, no copies)
columns = None
_index_lock = threading.Lock()
keys = ["INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME"]
# label fields that must match for two frames to be stacked
same_settings = ["EXPOSURE_DURATION", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID"]


def load_index():
    global index, groups, columns
    if index is None:
        # read once, even when several threads (the frame server's) ask at the same time
        with _index_lock:
            if index is None:
                idx = pd.read_csv("Image_index.csv", usecols=keys + ["path", "seconds_1970"], low_memory=False).set_index("path", drop=False)
                # row positions of every camera/target/observation/filter combination, for fast lookup
                groups = idx.groupby(keys, sort=False).indices
                columns = {k: idx[k].to_numpy() for k in keys + ["path", "seconds_1970"]}
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
    try:
        at = idx.index.get_loc(key)
    except KeyError:
        return [path]
    if not isinstance(at, (int, np.integer)):
        # a path in the index more than once: its first row
        at = np.arange(len(idx))[at][0]

    # on the index's columns as arrays: the frames of its group within window, nearest first (the order and the
    # ties of pandas' sort_values("gap"), a quicksort of the same gaps), a fortieth of the time pandas takes
    rows = groups.get(tuple(columns[k][at] for k in keys))
    if rows is None:
        return [path]
    paths = columns["path"][rows]
    gap = np.abs(columns["seconds_1970"][rows] - columns["seconds_1970"][at])
    near = pd.notna(paths) & (gap <= window) & (paths != key)
    nearest = paths[near][np.argsort(gap[near], kind="quicksort")].tolist()
    return [path] + [prefix + p for p in nearest[:max_frames - 1]]


"""
Loads the frame at path and stacks it with its repeat exposures.
returns (label of the frame at path, stacked image resized like label.resize_image),
plus how many frames went in when count is True, and with valid True last the mask of pixels
valid in any frame stacked (label.valid_mask): a repeat fills what the frame lost in downlink
"""
def load_stacked(path, window=120, max_frames=5, count=False, valid=False):
    lbl = lh.label(path, as_png=True)
    frames = [lbl.resize_image()]
    masks = [lbl.valid_mask()] if valid else None
    if not cal.step("stack"):   # Settings > Processing: the frame alone
        max_frames = 1
    if max_frames <= 1:
        return (lbl, frames[0]) + ((1,) if count else ()) + ((masks[0],) if valid else ())
    for repeat in find_repeats(path, window, 4 * max_frames)[1:]:
        if len(frames) >= max_frames:
            break
        try:
            repeat_lbl = lh.label(repeat, as_png=True)
            # only identical exposures can be averaged; many repeats are exposure brackets
            if any(repeat_lbl.info.get(k) != lbl.info.get(k) for k in same_settings):
                continue
            frame = repeat_lbl.resize_image()
            mask = repeat_lbl.valid_mask() if valid and frame is not None else None
        except Exception as e:
            print(f"Skipping repeat {repeat}: {e}")
            continue
        if frame is not None:
            frames.append(frame)
            if valid:
                masks.append(mask)
    if len(frames) > 1:
        print(f"Stacking {len(frames)} frames for {path}")
    if valid:
        stacked, mask = ic.stack_frames(frames, masks=masks)
        return (lbl, stacked) + ((len(frames),) if count else ()) + (mask,)
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
frames went in), or the label, None and 1 when the frame at path can't be calibrated.
valid = also return, last, the mask of pixels valid in any frame merged (label.valid_mask): what a frame lost in
downlink is left out of the merge, so a repeat fills it (None with the None image)
Settings > Processing (calibration.step): with "hdr" off only the exposures identical to the frame at path are merged
(a plain stack, in I/F), with "stack" off the frame at path alone.
"""
def load_hdr(path, window=120, max_frames=8, valid=False):
    lbl = lh.label(path, as_png=True)
    ref = first = None
    total, weight, n = None, None, 0
    seen = None
    plain = not cal.step("hdr")
    for p in find_repeats(path, window, max_frames if cal.step("stack") else 1):
        try:
            l = lbl if p == path else lh.label(p, as_png=True)
            if plain and l is not lbl and any(l.info.get(k) != lbl.info.get(k) for k in same_settings):
                continue
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
                return (lbl, None, 1, None) if valid else (lbl, None, 1)
            continue
        mask = l.valid_mask() if valid else None
        if ref is None:
            ref, first = image, iof
        else:
            shift = ic.find_shift(ref, image, 20)
            if shift is not None:
                iof = ic.shift_image(iof.astype(np.float32), *shift)
                gray = ic.shift_image(gray, *shift)
                if valid:
                    mask = ic.shift_image(mask.astype(np.float32), *shift) > 0.99
        good = ~cv2.dilate(cal.saturated(codes, info, gray).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        if valid and not mask.all():
            good &= mask
        if valid and seen is None:
            seen = mask   # the frame at path's own
        w = good * np.float32(float(info.get("EXPOSURE_DURATION", 1)) or 1)
        total = iof * w if total is None else total + iof * w
        weight = w if weight is None else weight + w
        n += 1
    if total is None:
        return (lbl, None, 1, None) if valid else (lbl, None, 1)
    # pixels saturated in every exposure keep the reference's (clipped) value
    merged = total / np.maximum(weight, 1e-9)
    merged = np.where(weight > 0, merged, first).astype(np.float32)
    if n > 1:
        print(f"Merged {n} exposures for {path}")
    if valid:
        # valid where some exposure went in, or where every one saturated but the frame at path has its (clipped) pixel
        return lbl, merged, n, seen | (weight > 0)
    return lbl, merged, n
