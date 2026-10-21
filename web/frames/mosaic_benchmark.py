#!/usr/bin/env python3
"""
Mosaic benchmark: one whole observation put together by the pipeline, to compare with the mosaic
NASA published from the same frames. The standing case is "In Saturn's Shadow" (PIA08329): Cassini
in Saturn's shadow on 2006-09-15, WAC observation ISS_028RI_HIPHWAC001_PRIME, 14:32-17:12 UTC, clear,
violet and IR3 frames, several exposures per tile.

Every frame goes through color_image.processed_frame (repeat exposures stacked, lost pixels filled,
calibrated, centred on the body north up by SPICE), is placed on one canvas by where SPICE puts the
body (its frame_offset), and is drawn into that filter's mosaic with mosaic.compose (gain matched,
feathered), oldest first. The three filter mosaics make a false colour picture: IR3 red, clear
green, violet blue (the published version's filters).

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/mosaic_benchmark.py --out DIR
  (--obs/--target/--cam pick another observation, --scale the canvas resolution)

Writes <filter>.png for each filter, false_colour.png, and report.json (frames used, stacked,
placed, failed, seconds).
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
os.environ.setdefault("MPLBACKEND", "Agg")
import color_image  # noqa: E402
import mosaic  # noqa: E402

REPEAT_GAP = 120   # stacking.load_stacked folds repeats this close into one picture (as reel.py)
COLOUR = {"IR3": 0, "CL1/CL2": 1, "VIO": 2}   # false colour channel of each filter


def frames(obs, target, cam):
    idx = pd.read_csv(os.path.join(REPO, "Image_index.csv"), low_memory=False,
                      usecols=["path", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "filter1", "filter2", "seconds_1970"])
    idx = idx[(idx.OBSERVATION_ID == obs) & (idx.TARGET_NAME == target) & (idx.INSTRUMENT_ID == cam) & idx.path.notna()]
    idx = idx.sort_values("seconds_1970")
    out, last = [], {}
    for r in idx.itertuples(index=False):
        f = "/".join(x for x in (str(r.filter1), str(r.filter2)) if not x.startswith("CL")) or "CL1/CL2"
        if f in last and r.seconds_1970 - last[f] <= REPEAT_GAP:
            continue
        last[f] = r.seconds_1970
        out.append((r.path, f, r.seconds_1970))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obs", default="ISS_028RI_HIPHWAC001_PRIME")
    ap.add_argument("--target", default="SATURN")
    ap.add_argument("--cam", default="ISSWA")
    ap.add_argument("--scale", type=float, default=0.5, help="canvas pixels per full resolution pixel")
    ap.add_argument("--size", type=int, default=3072, help="canvas side in canvas pixels")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    todo = frames(args.obs, args.target, args.cam)
    print(f"{args.obs}: {len(todo)} pictures after stacking repeats", flush=True)
    acc, report, start = {}, {"obs": args.obs, "pictures": [], "failed": []}, time.time()
    S = args.size
    for n, (path, f, t) in enumerate(todo):
        t0 = time.time()
        try:
            image, _, rep = color_image.processed_frame([path])
        except Exception as e:
            report["failed"].append({"path": path, "why": f"{type(e).__name__}: {e}"[:200]})
            continue
        if "frame_offset" not in rep:
            report["failed"].append({"path": path, "why": rep.get("why", "not placed by SPICE")})
            continue
        # the frame's canvas, north up, its middle at the canvas middle; scaled, then put where the
        # frame sits relative to the body's centre (the middle of the benchmark canvas)
        h = image.shape[0]
        small = np.asarray(Image.fromarray(image).resize((round(h * args.scale),) * 2, Image.LANCZOS))
        cx = S // 2 + round(rep["frame_offset"][0] * args.scale) - small.shape[1] // 2
        cy = S // 2 + round(rep["frame_offset"][1] * args.scale) - small.shape[0] // 2
        placed = np.zeros((S, S, 4), np.uint8)
        x0, y0, x1, y1 = max(cx, 0), max(cy, 0), min(cx + small.shape[1], S), min(cy + small.shape[0], S)
        if x1 <= x0 or y1 <= y0:
            report["failed"].append({"path": path, "why": "off the canvas"})
            continue
        placed[y0:y1, x0:x1] = small[y0 - cy:y1 - cy, x0 - cx:x1 - cx]
        mosaic.reset()
        acc[f] = mosaic.compose([(acc[f], None, None, None), (placed, None, None, None)], False) if f in acc else placed
        report["pictures"].append({"path": path, "filter": f, "t": t, "stacked": rep.get("stacked"),
                                   "frame_offset": rep["frame_offset"], "seconds": round(time.time() - t0, 2)})
        if n % 10 == 0:
            print(f"{n + 1}/{len(todo)} {f} {time.time() - start:.0f} s", flush=True)
    for f, im in acc.items():
        Image.fromarray(im).save(os.path.join(args.out, f.replace("/", "_") + ".png"))
    if all(f in acc for f in COLOUR):
        rgb = np.zeros((S, S, 3), np.uint8)
        for f, c in COLOUR.items():
            rgb[..., c] = acc[f][..., 0]
        Image.fromarray(rgb).save(os.path.join(args.out, "false_colour.png"))
    report["seconds"] = round(time.time() - start, 1)
    json.dump(report, open(os.path.join(args.out, "report.json"), "w"), indent=1, default=str)
    print(f"done: {len(report['pictures'])} placed, {len(report['failed'])} failed, {report['seconds']} s")


if __name__ == "__main__":
    main()
