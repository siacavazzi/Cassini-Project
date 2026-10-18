# -*- coding: utf-8 -*-
"""
Finds repeat exposures of a frame so they can be stacked into one lower-noise image.

A repeat is a frame from the same camera, target, observation and exact filter pair,
taken within a short window of the original with the same exposure settings.
Repeats that turn out to point somewhere else (the next panel of a mosaic) are
dropped later, when image_correction.stack_frames fails to align them.
"""

import pandas as pd
import label_handler as lh
import image_correction as ic

index = None
groups = None
keys = ["INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME"]
# label fields that must match for two frames to be stacked
same_settings = ["EXPOSURE_DURATION", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID"]


def load_index():
    global index, groups
    if index is None:
        index = pd.read_csv("Image_index.csv", low_memory=False).set_index("path", drop=False)
        # row positions of every camera/target/observation/filter combination, for fast lookup
        groups = index.groupby(keys, sort=False).indices
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
returns (label of the frame at path, stacked image resized like label.resize_image)
"""
def load_stacked(path, window=120, max_frames=5):
    lbl = lh.label(path, as_png=True)
    frames = [lbl.resize_image()]
    if max_frames <= 1:
        return lbl, frames[0]
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
    return lbl, ic.stack_frames(frames)
