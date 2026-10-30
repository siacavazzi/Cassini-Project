# -*- coding: utf-8 -*-
"""
Finds repeat exposures of a frame so they can be stacked into one lower-noise image.

A repeat is a frame from the same camera, target, observation and exact filter pair,
taken within a short window of the original, that SPICE (the geometry cache) puts at the
same pointing: within REPEAT_PLACE of a frame of it. A frame taken seconds later at another
pointing (the next panel of a mosaic; Phoebe 2004-06-11 goes back and forth between two
pointings a minute apart) is not a repeat, however close in time. Where SPICE can't place a
frame, the repeat must line up with it (image_correction.find_shift) to be merged.
"""

import math
import os
import threading
import cv2
import numpy as np
import pandas as pd
import calibration as cal
import data_source as ds
import label_handler as lh
import image_correction as ic
import bootleg_autonav as ba

index = None
groups = None
# the index's columns find_repeats reads, as numpy arrays (views of the index, no copies)
columns = None
_index_lock = threading.Lock()
keys = ["INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME"]
# label fields that must match for two frames to be stacked
same_settings = ["EXPOSURE_DURATION", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID"]
# of a frame (FRAME full resolution pixels): two frames whose body SPICE places this close are at one pointing. Over the
# whole mission (geometry cache, 2026-10-26; spoke movies aside, which follow a patch of ring and are never stacked),
# consecutive frames of one filter 20 to 40 s apart are within 20 px in 94% of cases (most 3 to 8 px: an exposure
# bracket), and a third of those 80 to 120 s apart are over 40 px away, up to 2400 (the next panel of a mosaic).
# find_shift lines a repeat up by at most 20 px, the same.
REPEAT_PLACE = 0.02
FRAME = 1024


def frame_id(path):
    return os.path.basename(path).split(".")[0]


"""
Where SPICE puts the body in each of the frames ids, from the geometry cache (bootleg_autonav,
CASSINI_GEOMETRY_CACHE): {id: (x, y, z)}, find_target's centring shift in full resolution pixels and
the distance in km. Frames that are not cached, or that SPICE could not place, are left out.
"""
def places(ids):
    if not ba.GEOMETRY_CACHE or not os.path.exists(ba.GEOMETRY_CACHE):
        return {}
    db, out = ba._geometry_db(), {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        for frame, x, y, z in db.execute(f"SELECT frame, x, y, z FROM target WHERE version = ? AND error IS NULL "
                                         f"AND frame IN ({','.join('?' * len(part))})", (ba.GEOMETRY_VERSION, *part)):
            out[frame] = (x, y, z)
    return out


"""
Whether SPICE puts two frames at one pointing: a, b = their places ((x, y, ...) as places gives, or None);
True within REPEAT_PLACE of a frame, False further apart, None when either has no place.
"""
def same_place(a, b):
    if a is None or b is None or a[0] is None or b[0] is None:
        return None
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= REPEAT_PLACE * FRAME


"""
Which picture a frame taken at t (unix seconds) at place is a repeat exposure of: kept = [(time, place, picture)],
the pictures of its filter so far, oldest first; the newest of them taken within window seconds before t at the
same place (or where SPICE can't tell: then find_shift decides as the frames are merged), else None, and the frame
is a picture of its own. The one rule for the pictures obs_mosaic.units and reel.shots make of an observation.
"""
def repeat_of(kept, t, place, window):
    for when, at, picture in reversed(kept):
        if t - when > window:
            return None
        if same_place(at, place) is not False:
            return picture
    return None


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
including path itself as the first entry. A frame SPICE puts at another pointing is left out (same_place).
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
    if nearest:
        where = places([frame_id(p) for p in [key] + nearest])
        nearest = [p for p in nearest if same_place(where.get(frame_id(key)), where.get(frame_id(p))) is not False]
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
correlation finds nothing) is taken as it is only where SPICE puts it at the frame's pointing
(same_place); otherwise it is left out, as a frame of another pointing would put its scene over
this one (Phoebe's black blotches: the other pointing's shadow where this frame saturated).
returns (label of the frame at path, float32 I/F image sized like label.resize_image, how many
frames went in), or the label, None and 1 when the frame at path can't be calibrated.
valid = also return, last, the mask of pixels valid in any frame merged (label.valid_mask): what a frame lost in
downlink is left out of the merge, so a repeat fills it (None with the None image)
clipped = also return, last, the mask of pixels the camera saturated in every exposure merged (cal.saturated: no
shorter exposure measured them), which keep the first frame's clipped value: they are brighter than that, and are drawn
white (calibration.load_channels); None with the None image
Settings > Processing (calibration.step): with "hdr" off only the exposures identical to the frame at path are merged
(a plain stack, in I/F), with "stack" off the frame at path alone.
"""
def load_hdr(path, window=120, max_frames=8, valid=False, clipped=False):
    lbl = lh.label(path, as_png=True)
    ref = first = None
    total, weight, n = None, None, 0
    merging, own, differ = [], None, False
    plain = not cal.step("hdr")
    repeats = find_repeats(path, window, max_frames if cal.step("stack") else 1)
    where = places([frame_id(p) for p in repeats]) if len(repeats) > 1 else {}
    for p in repeats:
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
                return (lbl, None, 1) + ((None,) if valid else ()) + ((None,) if clipped else ())
            continue
        shift = None
        if ref is not None:
            # a frame SPICE puts at another pointing is never merged, one that doesn't line up only where SPICE puts it
            # at this one
            here = same_place(where.get(frame_id(path)), where.get(frame_id(p)))
            shift = ic.find_shift(ref, image, 20) if here is not False else None
            if not here and shift is None:
                print(f"Skipping repeat {p}: it doesn't line up with {path}, and SPICE doesn't put it at the same pointing")
                continue
        mask = l.valid_mask() if valid else None
        if valid:
            own = mask if own is None else own
            # a frame that lost other pixels than the frame at path: then every frame's lost ones are left out, so
            # they fill one another (the same ones, as a summed frame's edge column: nothing to fill, merged as before)
            differ = differ or not np.array_equal(mask, own)
        if ref is None:
            ref, first = image, iof
        elif shift is not None:
            iof = ic.shift_image(iof.astype(np.float32), *shift)
            gray = ic.shift_image(gray, *shift)
            if valid:
                mask = ic.shift_image(mask.astype(np.float32), *shift) > 0.99
        full = cal.saturated(codes, info, gray)
        good = ~cv2.dilate(full.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        merging.append((iof, good, mask, np.float32(float(info.get("EXPOSURE_DURATION", 1)) or 1), full))
    for iof, good, mask, exposure, _ in merging:
        if differ:
            good = good & mask
        w = good * exposure
        total = iof * w if total is None else total + iof * w
        weight = w if weight is None else weight + w
        n += 1
    if total is None:
        return (lbl, None, 1) + ((None,) if valid else ()) + ((None,) if clipped else ())
    # pixels saturated in every exposure keep the reference's (clipped) value
    merged = total / np.maximum(weight, 1e-9)
    merged = np.where(weight > 0, merged, first).astype(np.float32)
    # ... and where the first frame saturated or is next to a pixel it saturated (left out above), the shortest exposure
    # that did not saturate there: next to a long exposure's blown crescent a short one measured it, though its own
    # saturated core is near. What every exposure saturated keeps the first frame's clipped value (clip)
    clip = (weight <= 0) & ~merging[0][1]
    if n > 1 and clip.any():
        for iof, _, mask, _, full in sorted(merging, key=lambda m: m[3]):
            take = clip & ~full & (mask if differ else True)
            merged[take] = iof[take]
            clip &= ~take
    if n > 1:
        print(f"Merged {n} exposures for {path}")
    out = (lbl, merged, n)
    if valid:
        # valid where some exposure went in, or where every one saturated but the frame at path has its (clipped) pixel
        out += (own | (weight > 0) if differ else own,)
    if clipped:
        out += (clip & merging[0][4],)
    return out
