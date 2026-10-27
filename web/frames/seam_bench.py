#!/usr/bin/env python3
"""How visible a real pass's seams are, in each setting of the blend and level steps (mosaic.composite), through
the checkout's own obs_mosaic (so_far: SPICE-placed tiles, the pass's scale, compose, colour_picture, the luminance
base), nothing re-implemented. Each pass's last mosaic is drawn as the viewer and the pre-build draw it: whole up to
GROW_FROM tiles of a filter and grown a tile at a time past that; --replay draws a mosaic movie frame by frame from
its first, as the viewer plays it (rolling_webp), and measures its last frame.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/seam_bench.py --cache SCRATCH_CACHE --out OUTDIR PASS... [--replay]

PASS is a frame id (W1750962932_1) or TARGET:OBSERVATION_ID:CAM[:pass]. Never point --cache at a cache the server
or the pre-build uses: the mosaics drawn here are written to it.

For each pass and setting: the picture (2048 px), the seam numbers (measure: the brightness step across the tiles'
edges inside the mosaic against the same over the tiles' insides, per cent; seam95 / flat95 near 1 = seams no more
visible than the picture's own texture), the time, and 1:1 crops of the worst seams side by side. OUTDIR/index.html
puts them on a page."""
import argparse
import html
import io
import json
import math
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

SETTINGS = [("before", "blend,level"), ("blend", "level"), ("blend + level", "")]
CROP = 256
CROPS = 4


def unit(spec):
    import obs_mosaic as om
    if ":" in spec:
        parts = spec.split(":")
        target, obs, cam = parts[:3]
        k = int(parts[3]) if len(parts) > 3 else None
        us = [v for v in om.units(target, obs, cam) if v["mosaic"]] or om.units(target, obs, cam)
        if not us:
            return None, None
        u = us[k] if k is not None else max(us, key=lambda v: len(v["frames"]))
        return u, len(u["frames"]) - 1
    found = om.unit_of(spec)
    return found if found else (None, None)


def edges(u, made, cache, shape):
    """Where the edges of the tiles drawn lie on the picture (bool, shape): each tile's picture (its alpha) placed
    as _window places it."""
    import obs_mosaic as om
    p, tiles, rect, _, used, _ = made
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)
    out = np.zeros((H, W), np.uint8)
    there = om._tiles(u, cache, p["display_scale"])
    lum = om.lum_frames(u, p)
    for t in tiles:
        if "offset" not in t or (t["filter"] not in used and t["n"] not in lum):
            continue
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        # (the tile's picture can fill its part to the border: padded, so its border is an edge)
        a = np.pad((om._part(os.path.join(there, f"{t['n']}.png"), sw, sh)[..., 3] > 0).astype(np.uint8), 1)
        e = (cv2.dilate(a, np.ones((3, 3), np.uint8)) - cv2.erode(a, np.ones((3, 3), np.uint8)))[1:-1, 1:-1]
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] |= e[y0 - top:y1 - top, x0 - left:x1 - left]
    return cv2.resize(out, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 0


def measure(rgba, edge, band=4, sigma=4.0):
    """The seam numbers of a picture (RGBA) whose tiles' edges are edge: the change of its brightness (log, smoothed
    by sigma) over band pixels each side, p50 and p95, at the tiles' edges inside the mosaic (seam) and away from them
    (flat), per cent; and where the seams are worst (a map of the change along them)."""
    a = rgba[..., 3] == 255
    lum = rgba[..., :3].astype(np.float32).mean(axis=2)
    lit = a & (lum > 20)
    w = cv2.GaussianBlur(lit.astype(np.float32), (0, 0), sigma)
    e = cv2.GaussianBlur(np.where(lit, np.log(np.maximum(lum, 1)), 0).astype(np.float32), (0, 0), sigma) / np.maximum(w, 1e-3)
    gy, gx = np.gradient(e)
    grad = np.hypot(gx, gy) * (2 * band)
    inner = cv2.erode(lit.astype(np.uint8), np.ones((2 * band + 9, 2 * band + 9), np.uint8)) > 0
    near = cv2.dilate(edge.astype(np.uint8), np.ones((2 * band + 1, 2 * band + 1), np.uint8)) > 0
    seam = near & inner
    flat = inner & ~(cv2.dilate(edge.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0)
    pct = lambda m, q: round(float(np.percentile(grad[m], q) * 100), 2) if m.any() else None
    worst = cv2.GaussianBlur(np.where(seam, grad, 0).astype(np.float32), (0, 0), 24)
    return {"seam50": pct(seam, 50), "seam95": pct(seam, 95), "flat50": pct(flat, 50), "flat95": pct(flat, 95)}, worst


def spots(worst, n=CROPS, half=CROP // 2, taken=()):
    """The n places where worst is highest, at least a crop apart and from the places taken."""
    w = worst.copy()
    for y, x in taken:
        w[max(0, y - 2 * half):y + 2 * half, max(0, x - 2 * half):x + 2 * half] = 0
    out = []
    for _ in range(n):
        y, x = np.unravel_index(int(np.argmax(w)), w.shape)
        if w[y, x] <= 0:
            break
        out.append((int(y), int(x)))
        w[max(0, y - 2 * half):y + 2 * half, max(0, x - 2 * half):x + 2 * half] = 0
    return out


def over_black(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3].astype(np.float32) * a + 0.5).astype(np.uint8)


def draw(u, n, cache, replay):
    """The pass's mosaic at tile n (RGBA, up to 2048 px; a replayed mosaic movie's 1024), as the viewer draws it."""
    import obs_mosaic as om
    if replay:
        # at 1024 px, as the viewer and the pre-build play it (each frame grown from the one before)
        frames = u["frames"]
        res = None
        for j in range(n + 1):
            res = om.rolling_webp(frames[j][1], 1024, cache, 1, wait=True) or res
        data = res[0] if res else None
        return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")) if data else None
    made = om.layout(u, n, cache)
    im, _ = om.so_far(u, n, cache, made, out=2048)
    return None if im is None else np.asarray(im.convert("RGBA"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", action="store_true", help="draw mosaic movies frame by frame, as the viewer plays them")
    ap.add_argument("passes", nargs="+")
    args = ap.parse_args()
    import calibration
    import obs_mosaic as om
    os.makedirs(args.out, exist_ok=True)
    results = []
    with calibration.looking("balanced"):
        for spec in args.passes:
            u, n = unit(spec)
            if u is None:
                print(spec, "in no pass", flush=True)
                continue
            name = "_".join(map(str, u["key"]))
            replay = args.replay and u.get("kind") == "mosaic_movie"
            row = {"pass": name, "spec": spec, "tiles": n + 1, "kind": u.get("kind"), "settings": {}}
            pics = {}
            for label, off in SETTINGS:
                with calibration.stepping(off):
                    t0 = time.perf_counter()
                    rgba = draw(u, n, args.cache, replay)
                    took = time.perf_counter() - t0
                if rgba is None:
                    continue
                made = om.layout(u, n, args.cache)
                m, worst = measure(rgba, edges(u, made, args.cache, rgba.shape[:2]))
                m["seconds"] = round(took, 2)
                row["settings"][label] = m
                pics[label] = (rgba, worst)
                Image.fromarray(over_black(rgba)).save(os.path.join(args.out, f"{name}-{off.replace(',', '_') or 'all'}.jpg"),
                                                       quality=92)
                print(name, label, m, flush=True)
            if not pics:
                continue
            # the worst seams before, and after, cropped at 1:1 from every setting side by side
            places = spots(pics[SETTINGS[0][0]][1], CROPS // 2)
            places += spots(pics[SETTINGS[-1][0]][1], CROPS - len(places), taken=places)
            row["crops"] = []
            for i, (y, x) in enumerate(places):
                parts = []
                for label, _ in SETTINGS:
                    rgba = pics[label][0]
                    H, W = rgba.shape[:2]
                    y0, x0 = min(max(y - CROP // 2, 0), max(H - CROP, 0)), min(max(x - CROP // 2, 0), max(W - CROP, 0))
                    parts.append(over_black(rgba[y0:y0 + CROP, x0:x0 + CROP]))
                    parts.append(np.full((parts[-1].shape[0], 4, 3), 60, np.uint8))
                crop = np.hstack(parts[:-1])
                path = f"{name}-crop{i}.png"
                Image.fromarray(crop).save(os.path.join(args.out, path))
                row["crops"].append({"file": path, "at": [x, y]})
            results.append(row)
            with open(os.path.join(args.out, "results.json"), "w") as fh:
                json.dump(results, fh, indent=1)
    page(args.out, results)


def page(out, results):
    rows = []
    for r in results:
        cells = "".join(f"<td>{html.escape(label)}<br>seam {m['seam50']} / {m['seam95']}<br>inside {m['flat50']} / "
                        f"{m['flat95']}<br>{m['seconds']} s</td>" for label, m in r["settings"].items())
        pics = "".join(f"<a href='{html.escape(r['pass'])}-{off.replace(',', '_') or 'all'}.jpg'>{html.escape(label)}</a> "
                       for label, off in SETTINGS)
        crops = "".join(f"<div><img src='{html.escape(c['file'])}'><br><small>at {c['at']}</small></div>" for c in r.get("crops", []))
        rows.append(f"<h2>{html.escape(r['pass'])}</h2><p>{r['tiles']} tiles, {html.escape(str(r['kind']))}. Whole "
                    f"pictures: {pics}</p><table><tr>{cells}</tr></table><p>Crops at 1:1, "
                    f"{' | '.join(html.escape(label) for label, _ in SETTINGS)}:</p>{crops}")
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Seam bench</title><style>body{background:#111;color:#ddd;"
                 "font:14px system-ui;margin:16px}img{max-width:100%}td{padding:6px 12px;vertical-align:top}"
                 "a{color:#8cf}</style><h1>Seam bench</h1><p>Seam numbers: the brightness step across the tiles' edges "
                 "inside the mosaic, p50 / p95, per cent; inside: the same away from the edges. Seams are no more visible "
                 "than the picture's own texture when the two match.</p>" + "".join(rows))


if __name__ == "__main__":
    main()
