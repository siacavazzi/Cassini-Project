# -*- coding: utf-8 -*-
"""
Measures the WAC's in-flight dust rings from the archive itself, for the "flat" calibration step (flat_field.py, step 4,
WAC_DUST): CISSCAL has no WAC dust ring map, and the WAC ground flats only hold the dust that was on the optics before
launch, so the donuts that settled on in flight stay in every calibrated WAC frame and a stretched sky makes them
plain (the 2009 south pole movie, 099SA; W1627244567_1). Some of the dust sits on the filters and moves with their
wheels, so every filter pair has donuts of its own: one map per filter pair and epoch (flat_field.WAC_DUST_EPOCHS).

For each filter pair and epoch, up to --labels of its WAC frames (FULL, no lost lines, at most --per-obs from one
observation so the scene moves between them) are calibrated as the site does (flat field on, the WAC dust map itself
off) and the ones of a lit, not too busy scene (flat_field.dust_ratio) give each pixel's brightness over its
neighborhood's, until --frames are found. Their middle-half mean per pixel (dust_combine) gives the map
(dust_correction), key like CL1_CL2_2008; a pair and epoch with fewer than --least usable frames gets none (its frames
use the pair's nearest epoch's).

Written to one .npz (default flat_field.WAC_DUST, beside the CISSCAL maps) of float16 corrections at 1024 x 1024; the
combined ratios themselves to <out>_ratios.npz (so the maps can be made again without reading the frames), a counts
table to <out>.txt and a preview PNG per map in --previews.

Run from the main folder with CASSINI_DATA and CASSINI_CISSCAL set (reads only):
  python "helper programs/build_wac_dust.py" [--out wac_dust.npz] [--workers 2] [--years 1999-2017]
"""
import argparse
import os
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402
import flat_field as ff  # noqa: E402
import label_handler as lh  # noqa: E402
import stacking  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def encode(r):
    """A ratio map as uint8 (1 + (code - 128) / 1000, 0 = not measured), so many frames fit in memory."""
    out = np.clip(np.round((np.nan_to_num(r, nan=1.0) - 1) * 1000) + 128, 1, 255).astype(np.uint8)
    out[~np.isfinite(r)] = 0
    return out


def decode(codes):
    return np.where(codes > 0, 1 + (codes.astype(np.float32) - 128) / 1000, np.nan).astype(np.float32)


def measure(path):
    """One frame's encoded ratio, or None when it can't say anything about the dust."""
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    if ff._value(info, "INSTRUMENT_MODE_ID") != "FULL" or ff._value(info, "SHUTTER_STATE_ID", "ENABLED") == "DISABLED":
        return None
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    if codes is None or codes.shape != (1024, 1024):
        return None
    # quick look before calibrating: a good part of the frame well above its sky
    top = np.percentile(codes, 90)
    if top <= 8 or np.mean(codes >= 0.3 * top) < 0.2:
        return None
    with cal.stepping("stack"):
        _, iof, _ = stacking.load_hdr(path, 120)
    if iof is None:
        return None
    r = ff.dust_ratio(np.asarray(iof, np.float32), bad=cal.saturated(codes, info))
    return None if r is None else encode(r)


def one_pair(job):
    key, rows, args = job
    ff.WAC_DUST_USE = False
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    rows = [rows[i] for i in rng.permutation(len(rows))[:args.labels]]
    per, got = {}, []
    for path, obs in rows:
        if len(got) >= args.frames:
            break
        if per.get(obs, 0) >= args.per_obs:
            continue
        try:
            r = measure(path)
        except Exception as e:  # a frame that can't be read is skipped
            print(f"{path}: {e}", flush=True)
            continue
        if r is not None:
            per[obs] = per.get(obs, 0) + 1
            got.append(r)
    if len(got) < args.least:
        return key, None, None, len(got)
    ratio = ff.dust_combine([decode(r) for r in got])
    return key, ff.dust_correction(ratio).astype(np.float16), ratio.astype(np.float16), len(got)


def preview(c):
    """A map as a picture: 1 grey, +-4% black to white."""
    c = np.nan_to_num(c.astype(np.float32), nan=1.0)
    return np.clip((1 / np.maximum(c, 1e-3) - 0.96) / 0.08 * 255, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=ff.WAC_DUST)
    ap.add_argument("--index", default=os.path.join(REPO, "Image_index.csv"))
    ap.add_argument("--years", default="1999-2017")
    ap.add_argument("--workers", type=int, default=2, help="more makes the LaCie unresponsive")
    ap.add_argument("--labels", type=int, default=1200, help="frames looked at per filter pair and epoch")
    ap.add_argument("--frames", type=int, default=200, help="usable frames kept per filter pair and epoch")
    ap.add_argument("--least", type=int, default=30, help="usable frames a map needs")
    ap.add_argument("--per-obs", type=int, default=4)
    ap.add_argument("--min-frames", type=int, default=150, help="pairs and epochs with fewer frames in the index are skipped")
    ap.add_argument("--previews", default=None, help="folder for a PNG of every map")
    args = ap.parse_args()
    first, last = (int(y) for y in args.years.split("-"))
    idx = pd.read_csv(args.index, usecols=["INSTRUMENT_ID", "IMAGE_MID_TIME", "OBSERVATION_ID", "MISSING_LINES",
                                           "filter1", "filter2", "path"], low_memory=False)
    idx = idx[(idx["INSTRUMENT_ID"] == "ISSWA") & (idx["MISSING_LINES"].astype(str) == "0")]
    idx["year"] = pd.to_numeric(idx["IMAGE_MID_TIME"].astype(str).str[:4], errors="coerce")
    idx = idx[(idx["year"] >= first) & (idx["year"] <= last)]
    idx["epoch"] = [ff.dust_epoch(int(y)) for y in idx["year"]]
    jobs = []
    for (f1, f2, epoch), g in idx.groupby(["filter1", "filter2", "epoch"]):
        if len(g) >= args.min_frames:
            jobs.append((ff.wac_dust_key((f1, f2), int(epoch)), list(zip(g["path"], g["OBSERVATION_ID"])), args))
    jobs.sort(key=lambda j: -len(j[1]))
    print(f"{len(jobs)} filter pairs and epochs", flush=True)
    maps, ratios, counts = {}, {}, []
    with ProcessPoolExecutor(args.workers) as pool:
        for key, c, ratio, n in pool.map(one_pair, jobs):
            counts.append((key, n))
            if c is not None:
                maps[key], ratios[key] = c, ratio
            print(f"{key}: {n} usable frames{'' if c is not None else ' (no map)'}", flush=True)
    base = os.path.splitext(args.out)[0]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    np.savez_compressed(args.out + ".part.npz", **maps)
    os.replace(args.out + ".part.npz", args.out)
    np.savez_compressed(base + "_ratios.npz", **ratios)
    with open(base + ".txt", "w") as f:
        f.write("".join(f"{k}\t{n}\t{'map' if k in maps else '-'}\n" for k, n in sorted(counts)))
    if args.previews:
        os.makedirs(args.previews, exist_ok=True)
        for k, v in maps.items():
            cv2.imwrite(os.path.join(args.previews, f"{k}.png"), preview(v))
    print(f"{len(maps)} maps into {args.out}")


if __name__ == "__main__":
    main()
