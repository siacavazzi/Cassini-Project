# -*- coding: utf-8 -*-
"""
Measures the detectors' defect maps from the archive itself, for the "hotpix" calibration step (dark_current.repair_hot,
HOT_MAPS): the camera team's hot pixel lists hold only a small share of the pixels that stay put as fixed dots while the
sky moves (530 of about 7,300 in a 220 s Hyrokkin pass in 2015).

For each camera, summing mode, month and exposure band (dark_current.EXPOSURE_BANDS: a pixel's dark charge grows with
the exposure, so long exposures show far more defects), up to --frames of that month's longest exposures in the band
(no lost lines, at most --per-obs from one observation, so the scene moves between them) go through
dark_current.defects: the pixels more than 4 times the grain above (hot) or below (dead) their 3x3 median in 60% of
them. A month with fewer than --least such frames gets no map (frames there use the nearest month's within
dark_current.HOT_MAP_MONTHS). Written to one .npz (default dark_current.HOT_MAPS, beside the CISSCAL maps), keys like
ISSNA_SUM2_2015-08_3, values (n, 3) int16 (line, sample, +1 hot / -1 dead) at the mode's own resolution.

Run from the main folder with CASSINI_DATA set:
  python "helper programs/build_hot_maps.py" [--out hot_maps.npz] [--workers 4] [--years 2004-2017]
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dark_current as dc  # noqa: E402
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def month_of(t):
    """IMAGE_MID_TIME ("2015-218T11:26:40.123") -> year * 12 + month - 1, or None"""
    return dc._month({"IMAGE_TIME": str(t)})


def one_month(job):
    camera, month, rows, args = job
    rng = np.random.default_rng(month)
    rows = [rows[i] for i in rng.permutation(len(rows))[:args.labels]]
    found = {}
    for path, obs in rows:
        try:
            info = lh.label(path, as_png=True).get_info()
            exposure = float(info.get("EXPOSURE_DURATION", 0))
        except Exception:
            continue
        band = dc.exposure_band(exposure / 1000)
        if band is not None:
            found.setdefault((info.get("INSTRUMENT_MODE_ID", "FULL"), band), []).append((exposure, obs, path))
    out = {}
    for (mode, band), picks in found.items():
        picks.sort(reverse=True)
        chosen, per = [], {}
        for exposure, obs, path in picks:
            if per.get(obs, 0) < args.per_obs and len(chosen) < args.frames:
                per[obs] = per.get(obs, 0) + 1
                chosen.append(path)
        frames = [f for f in (ds.imread(p, cv2.IMREAD_GRAYSCALE) for p in chosen) if f is not None]
        shapes = {f.shape for f in frames}
        if len(frames) < args.least or len(shapes) != 1:
            continue
        out[dc.map_key(camera, mode, month, band)] = dc.defects(frames)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=dc.HOT_MAPS)
    ap.add_argument("--index", default=os.path.join(REPO, "Image_index.csv"))
    ap.add_argument("--years", default="1999-2017")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--labels", type=int, default=600, help="labels read per camera and month")
    ap.add_argument("--frames", type=int, default=40, help="frames measured per camera, mode, month and band")
    ap.add_argument("--least", type=int, default=8)
    ap.add_argument("--per-obs", type=int, default=4)
    args = ap.parse_args()
    first, last = (int(y) for y in args.years.split("-"))
    idx = pd.read_csv(args.index, usecols=["INSTRUMENT_ID", "IMAGE_MID_TIME", "OBSERVATION_ID", "MISSING_LINES", "path"],
                      low_memory=False)
    idx = idx[idx["MISSING_LINES"].astype(str) == "0"]
    idx["month"] = [month_of(t) for t in idx["IMAGE_MID_TIME"]]
    idx = idx[idx["month"].notna() & (idx["month"] // 12 >= first) & (idx["month"] // 12 <= last)]
    jobs = [(camera, int(month), list(zip(g["path"], g["OBSERVATION_ID"])), args)
            for (camera, month), g in idx.groupby(["INSTRUMENT_ID", "month"])]
    maps = {}
    with ProcessPoolExecutor(args.workers) as pool:
        for n, got in enumerate(pool.map(one_month, jobs), 1):
            maps.update(got)
            for k, v in got.items():
                print(f"{k}: {int((v[:, 2] > 0).sum())} hot, {int((v[:, 2] < 0).sum())} dead", flush=True)
            if n % 20 == 0:
                print(f"{n}/{len(jobs)} months", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    np.savez_compressed(args.out + ".part.npz", **maps)
    os.replace(args.out + ".part.npz", args.out)
    print(f"{len(maps)} maps, {sum(len(v) for v in maps.values())} defects, into {args.out}")


if __name__ == "__main__":
    main()
