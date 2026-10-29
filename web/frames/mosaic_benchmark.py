#!/usr/bin/env python3
"""
Mosaic benchmark: one whole observation put together by the pipeline, to compare with the mosaic
NASA published from the same frames. The standing case is "In Saturn's Shadow" (PIA08329): Cassini
in Saturn's shadow on 2006-09-15, WAC observation ISS_028RI_HIPHWAC001_PRIME, 14:32-17:12 UTC, clear,
violet and IR3 frames, several exposures per tile.

Every frame goes through color_image.processed_frame (all its repeat exposures, short and long,
merged in I/F by stacking.load_hdr, lost pixels filled, calibrated, centred on the body north up by
SPICE), is placed on one canvas by where SPICE puts the body (its frame_offset), and is drawn into
that filter's mosaic with mosaic.compose (calibrated: small gain and sky level corrections only,
feathered), oldest first, all of a filter's tiles matched to each other at once. Every picture is put on one display scale (calibration.load_channels):
a black point per filter at the sky's floor (the median over the tiles of each tile's 5th
percentile) and one white point for all filters (the --white percentile of all the pixels), so
tiles and filters keep the brightness the camera measured. The three filter mosaics make a false
colour picture: IR3 red, clear green, violet blue (the published version's filters).

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/mosaic_benchmark.py --out DIR
  (--obs/--target/--cam pick another observation, --scale the canvas resolution, --gamma and
  --white the display scale)

Writes <filter>.png for each filter, false_colour.png, and report.json (frames used, stacked,
placed, failed, the display scale, the canvas, seconds).
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
import calibration  # noqa: E402
import color_image  # noqa: E402
import mosaic  # noqa: E402
import stacking  # noqa: E402

REPEAT_GAP = 120   # stacking.load_hdr merges repeats this close into one picture
COLOUR = {"IR3": 0, "CL1/CL2": 1, "VIO": 2}   # false colour channel of each filter


def frames(obs, target, cam):
    idx = pd.read_csv(os.path.join(REPO, "Image_index.csv"), low_memory=False,
                      usecols=["path", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "filter1", "filter2", "seconds_1970"])
    idx = idx[(idx.OBSERVATION_ID == obs) & (idx.TARGET_NAME == target) & (idx.INSTRUMENT_ID == cam) & idx.path.notna()]
    idx = idx.sort_values("seconds_1970")
    where = stacking.places([stacking.frame_id(p) for p in idx.path])
    out, kept = [], {}
    for r in idx.itertuples(index=False):
        f = "/".join(x for x in (str(r.filter1), str(r.filter2)) if not x.startswith("CL")) or "CL1/CL2"
        # a repeat exposure at the same pointing (stacking.repeat_of) is merged into the frame before it
        at = where.get(stacking.frame_id(r.path))
        if stacking.repeat_of(kept.setdefault(f, []), r.seconds_1970, at, REPEAT_GAP) is not None:
            continue
        kept[f].append((r.seconds_1970, at, r.path))
        out.append((r.path, f, r.seconds_1970))
    return out


def display_scale(todo, white_pct, gamma):
    """
    The display scale shared by every picture (calibration.shared_scale, one channel per filter):
    {"blacks": {filter: I/F}, "white": I/F, "gamma": gamma}
    """
    by = {}
    for path, f, _ in todo:
        _, iof, _ = stacking.load_hdr(path, REPEAT_GAP)
        if iof is not None:
            by.setdefault(f, []).append(iof)
    scale = calibration.shared_scale(list(by.values()), white_pct, gamma=gamma)
    return {**scale, "blacks": dict(zip(by, scale["blacks"]))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obs", default="ISS_028RI_HIPHWAC001_PRIME")
    ap.add_argument("--target", default="SATURN")
    ap.add_argument("--cam", default="ISSWA")
    ap.add_argument("--scale", type=float, default=0.5, help="canvas pixels per full resolution pixel")
    ap.add_argument("--size", type=int, default=0, help="canvas side in canvas pixels (0: big enough for every frame)")
    ap.add_argument("--gamma", type=float, default=3.0, help="display gamma")
    ap.add_argument("--white", type=float, default=99.9, help="percentile of all pixels that becomes white")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    todo = frames(args.obs, args.target, args.cam)
    print(f"{args.obs}: {len(todo)} pictures after merging repeats", flush=True)
    report, start = {"obs": args.obs, "pictures": [], "failed": []}, time.time()
    scale = display_scale(todo, args.white, args.gamma)
    report["display_scale"] = scale
    print(f"display scale {scale} ({time.time() - start:.0f} s)", flush=True)
    placed = []
    for n, (path, f, t) in enumerate(todo):
        t0 = time.time()
        try:
            image, _, rep = color_image.processed_frame([path], hdr=True,
                                                        scale={**scale, "blacks": [scale["blacks"].get(f, 0.0)]})
        except Exception as e:
            report["failed"].append({"path": path, "why": f"{type(e).__name__}: {e}"[:200]})
            continue
        if "frame_offset" not in rep:
            report["failed"].append({"path": path, "why": rep.get("why", "not placed by SPICE")})
            continue
        # the frame's canvas, north up, its middle at the canvas middle, scaled
        h = image.shape[0]
        small = np.asarray(Image.fromarray(image).resize((round(h * args.scale),) * 2, Image.LANCZOS))
        placed.append((f, small, rep["frame_offset"]))
        report["pictures"].append({"path": path, "filter": f, "t": t, "stacked": rep.get("stacked"),
                                   "calibrated": rep.get("calibrated"), "frame_offset": rep["frame_offset"],
                                   "seconds": round(time.time() - t0, 2)})
        if n % 10 == 0:
            print(f"{n + 1}/{len(todo)} {f} {time.time() - start:.0f} s", flush=True)

    # the canvas: the body's centre at (cx, cy), every frame on it (or a fixed square --size)
    half = [s.shape[0] / 2 for _, s, _ in placed]
    xs = [o[0] * args.scale for _, _, o in placed]
    ys = [o[1] * args.scale for _, _, o in placed]
    if args.size:
        W = H = args.size
        cx = cy = args.size // 2
    else:
        x0, x1 = min(x - r for x, r in zip(xs, half)), max(x + r for x, r in zip(xs, half))
        y0, y1 = min(y - r for y, r in zip(ys, half)), max(y + r for y, r in zip(ys, half))
        W, H = int(np.ceil(x1 - x0)) + 2, int(np.ceil(y1 - y0)) + 2
        cx, cy = int(np.ceil(-x0)) + 1, int(np.ceil(-y0)) + 1
    report["canvas"] = {"width": W, "height": H, "centre": [cx, cy], "scale": args.scale}

    tiles = {}
    for (f, small, offset), pic in zip(placed, report["pictures"]):
        # put where the frame sits relative to the body's centre
        left = cx + round(offset[0] * args.scale) - small.shape[1] // 2
        top = cy + round(offset[1] * args.scale) - small.shape[0] // 2
        frame = np.zeros((H, W, 4), np.uint8)
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + small.shape[1], W), min(top + small.shape[0], H)
        if x1 <= x0 or y1 <= y0:
            report["failed"].append({"path": pic["path"], "why": "off the canvas"})
            continue
        frame[y0:y1, x0:x1] = small[y0 - top:y1 - top, x0 - left:x1 - left]
        tiles.setdefault(f, []).append((frame, None, None, None))
    # each filter's tiles in one window, oldest first, matched to each other with none pinned
    acc = {}
    for f, window in tiles.items():
        mosaic.reset()
        acc[f] = mosaic.compose(window, False, calibrated=True, pin=None)
    del tiles
    for f, im in acc.items():
        Image.fromarray(im).save(os.path.join(args.out, f.replace("/", "_") + ".png"))
    if all(f in acc for f in COLOUR):
        rgb = np.zeros((H, W, 3), np.uint8)
        for f, c in COLOUR.items():
            rgb[..., c] = acc[f][..., 0]
        # only where every filter has the picture: past one filter's edge the others alone are a
        # coloured rim
        alpha = np.min([acc[f][..., 3] for f in COLOUR], axis=0).astype(np.float32) / 255
        rgb = (rgb * alpha[..., None] + 0.5).astype(np.uint8)
        Image.fromarray(rgb).save(os.path.join(args.out, "false_colour.png"))
    report["seconds"] = round(time.time() - start, 1)
    json.dump(report, open(os.path.join(args.out, "report.json"), "w"), indent=1, default=str)
    print(f"done: {len(report['pictures'])} placed, {len(report['failed'])} failed, {report['seconds']} s")


if __name__ == "__main__":
    main()
