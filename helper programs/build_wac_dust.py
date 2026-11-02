# -*- coding: utf-8 -*-
"""
Measures the WAC's in-flight dust rings from the archive itself, for the "flat" calibration step (flat_field.py, step 4,
WAC_DUST): CISSCAL has no WAC dust ring map, and the WAC ground flats only hold the dust that was on the optics before
launch, so the donuts that settled on in flight stay in every calibrated WAC frame and a stretched sky makes them
plain (the 2009 south pole movie, 099SA; W1627244567_1).

For each year, up to --labels WAC frames per quarter (FULL, no lost lines, at most --per-obs from one observation so
the scene moves between them) are calibrated as the site does (flat field on, the WAC dust map itself off) and the ones
of a bright, evenly lit scene (flat_field.dust_ratio: lit over most of the frame, not too busy) give each pixel's
brightness over its neighborhood's. Per quarter, those ratios' middle-half mean per pixel (dust_combine) gives the map
(dust_correction), key like 2009Q3; a quarter with fewer than --least usable frames gets none (its frames use the
nearest quarter's, flat_field.WAC_DUST_QUARTERS). The dust's diffraction fringes scale with the wavelength, so a filter
pair with at least --least usable frames in the year also gets its own map, key like 2009_CB3_CL2, which its frames
use first.

Written to one .npz (default flat_field.WAC_DUST, beside the CISSCAL maps) of float16 corrections at 1024 x 1024,
plus a counts table (--out with .txt) and a preview PNG per map in --previews.

Run from the main folder with CASSINI_DATA and CASSINI_CISSCAL set (reads only; about 3 frames a second):
  python "helper programs/build_wac_dust.py" [--out wac_dust.npz] [--workers 2] [--years 2004-2017]
"""
import argparse
import os
import sys
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
    """A ratio map as uint8 (1 + (code - 128) / 1000, 0 = not measured), so a year's frames fit in memory."""
    out = np.clip(np.round((np.nan_to_num(r, nan=1.0) - 1) * 1000) + 128, 1, 255).astype(np.uint8)
    out[~np.isfinite(r)] = 0
    return out


def decode(codes):
    return np.where(codes > 0, 1 + (codes.astype(np.float32) - 128) / 1000, np.nan).astype(np.float32)


def measure(path):
    """(filter pair, encoded ratio) of one frame, or None when it can't say anything about the dust."""
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    if ff._value(info, "INSTRUMENT_MODE_ID") != "FULL" or ff._value(info, "SHUTTER_STATE_ID", "ENABLED") == "DISABLED":
        return None
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    if codes is None or codes.shape != (1024, 1024):
        return None
    # quick look before calibrating: most of the frame well above its sky
    top = np.percentile(codes, 99)
    if top <= 8 or np.mean(codes >= 0.3 * top) < 0.35:
        return None
    with cal.stepping("stack"):
        _, iof, _ = stacking.load_hdr(path, 120)
    if iof is None:
        return None
    r = ff.dust_ratio(np.asarray(iof, np.float32), bad=cal.saturated(codes, info))
    if r is None:
        return None
    return "_".join(ff._filters(info)[:2]), encode(r)


def one_year(job):
    year, rows, args = job
    ff.WAC_DUST_USE = False
    rng = np.random.default_rng(year)
    by_quarter, by_filter, counts = {}, {}, []
    for quarter, picks in sorted(rows.items()):
        picks = [picks[i] for i in rng.permutation(len(picks))[:args.labels]]
        per, got = {}, []
        for path, obs in picks:
            if per.get(obs, 0) >= args.per_obs or len(got) >= args.frames:
                continue
            try:
                m = measure(path)
            except Exception as e:  # a frame that can't be read is skipped
                print(f"{path}: {e}", flush=True)
                continue
            if m is not None:
                per[obs] = per.get(obs, 0) + 1
                got.append(m)
        by_quarter[quarter] = [r for _, r in got]
        for f, r in got:
            by_filter.setdefault(f, []).append(r)
    out = {}
    for quarter, ratios in by_quarter.items():
        counts.append((ff.quarter_key(quarter), len(ratios)))
        if len(ratios) >= args.least:
            out[ff.quarter_key(quarter)] = ff.dust_correction(ff.dust_combine([decode(r) for r in ratios]))
    for f, ratios in by_filter.items():
        counts.append((f"{year}_{f}", len(ratios)))
        if len(ratios) >= args.least:
            out[f"{year}_{f}"] = ff.dust_correction(ff.dust_combine([decode(r) for r in ratios]))
    return year, {k: v.astype(np.float16) for k, v in out.items()}, counts


def preview(c):
    """A map as a picture: 1 grey, +-4% black to white."""
    return np.clip((1 / c.astype(np.float32) - 0.96) / 0.08 * 255, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=ff.WAC_DUST)
    ap.add_argument("--index", default=os.path.join(REPO, "Image_index.csv"))
    ap.add_argument("--years", default="1999-2017")
    ap.add_argument("--workers", type=int, default=2, help="more makes the LaCie unresponsive")
    ap.add_argument("--labels", type=int, default=1500, help="frames looked at per quarter")
    ap.add_argument("--frames", type=int, default=150, help="usable frames kept per quarter")
    ap.add_argument("--least", type=int, default=25, help="usable frames a map needs")
    ap.add_argument("--per-obs", type=int, default=4)
    ap.add_argument("--previews", default=None, help="folder for a PNG of every map")
    args = ap.parse_args()
    first, last = (int(y) for y in args.years.split("-"))
    idx = pd.read_csv(args.index, usecols=["INSTRUMENT_ID", "IMAGE_MID_TIME", "OBSERVATION_ID", "MISSING_LINES", "path"],
                      low_memory=False)
    idx = idx[(idx["INSTRUMENT_ID"] == "ISSWA") & (idx["MISSING_LINES"].astype(str) == "0")]
    idx["quarter"] = [ff.quarter_of({"IMAGE_TIME": str(t)}) for t in idx["IMAGE_MID_TIME"]]
    idx = idx[idx["quarter"].notna()]
    idx["quarter"] = idx["quarter"].astype(int)
    idx = idx[(idx["quarter"] // 4 >= first) & (idx["quarter"] // 4 <= last)]
    jobs = []
    for year, g in idx.groupby(idx["quarter"] // 4):
        rows = {int(q): list(zip(h["path"], h["OBSERVATION_ID"])) for q, h in g.groupby("quarter")}
        jobs.append((int(year), rows, args))
    maps, counts = {}, []
    with ProcessPoolExecutor(args.workers) as pool:
        for year, got, n in pool.map(one_year, jobs):
            maps.update(got)
            counts += n
            print(f"{year}: " + ", ".join(f"{k} {c}{'' if k in got else ' (no map)'}" for k, c in n), flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    np.savez_compressed(args.out + ".part.npz", **maps)
    os.replace(args.out + ".part.npz", args.out)
    with open(os.path.splitext(args.out)[0] + ".txt", "w") as f:
        f.write("".join(f"{k}\t{c}\t{'map' if k in maps else '-'}\n" for k, c in sorted(counts)))
    if args.previews:
        os.makedirs(args.previews, exist_ok=True)
        for k, v in maps.items():
            cv2.imwrite(os.path.join(args.previews, f"{k}.png"), preview(v))
    print(f"{len(maps)} maps into {args.out}")


if __name__ == "__main__":
    main()
