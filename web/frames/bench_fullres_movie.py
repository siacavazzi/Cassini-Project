#!/usr/bin/env python3
"""
Full-resolution mosaic movie export: what it would cost. Run on the Mini from a pictures worktree:

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \
  python web/frames/bench_fullres_movie.py --repo <worktree> --native <mosaic_native.py from PR #113> --cache <scratch cache> \
      [--find 2012-11-27T21:00 2012-11-28T09:00] [--frame N... ] [--samples 4]

--find lists every mosaic movie / mosaic pass of Saturn in the stretch with its native size.
--frame times one frame of a pass (a frame id) at 1024 (the windows' size), 2048 (the canvas: existing size=full)
and native (mosaic_native.block on the same rolling layout), --samples frames spread over the pass, and prints
a JSON line per pass. Never point --cache at the served pre-build cache.
"""
import argparse, json, os, sys, time, resource, io

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--native", required=True)
ap.add_argument("--cache", required=True)
ap.add_argument("--find", nargs=2)
ap.add_argument("--frame", nargs="*", default=[])
ap.add_argument("--samples", type=int, default=4)
ap.add_argument("--native-max", type=int, default=24000)
a = ap.parse_args()
sys.path.insert(0, os.path.join(a.repo, "web", "frames"))
sys.path.insert(0, os.path.dirname(os.path.abspath(a.native)))
import numpy as np
import reel, obs_mosaic as om
import importlib.util
spec = importlib.util.spec_from_file_location("mosaic_native", a.native)
mn = importlib.util.module_from_spec(spec); spec.loader.exec_module(mn)
from PIL import Image

reel.data_source.KEEP_SPICE_CACHE = True
os.makedirs(a.cache, exist_ok=True)


def rss():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1 << 30) if sys.platform == "darwin" else r / (1 << 20), 2)


if a.find:
    import export
    idx, _ = reel.load_index()
    t = idx["seconds_1970"].to_numpy()
    lo, hi = np.searchsorted(t, export.unix(a.find[0])), np.searchsorted(t, export.unix(a.find[1]), "right")
    seen = set()
    for q in range(lo, hi):
        fid = idx["id"].iloc[q]
        found = om.unit_of(fid)
        if not found or found[0]["key"] in [s for s in seen]:
            continue
        u = found[0]
        seen.add(u["key"])
        kind = u.get("kind")
        if kind not in ("mosaic", "mosaic_movie"):
            continue
        t0 = time.time()
        p = om.plan(u, a.cache)
        v = p["view"]
        print(json.dumps({"first": u["frames"][0][1], "key": list(map(str, u["key"])), "kind": kind,
                          "frames": len(u["frames"]), "places": len(set(x for x in u.get("place", []) if x is not None)),
                          "native_px": [round(v[0]), round(v[1])], "canvas_px": [round(v[0] * p["k"]), round(v[1] * p["k"])],
                          "plan_s": round(time.time() - t0, 1)}), flush=True)


for fid in a.frame:
    u, n0 = om.unit_of(fid)
    p = om.plan(u, a.cache)
    N = len(u["frames"])
    picks = sorted(set(int(x) for x in np.linspace(N // 3, N - 1, a.samples)))
    out = {"pass": list(map(str, u["key"])), "kind": u.get("kind"), "frames": N, "native_px": [round(x) for x in p["view"]], "rows": []}
    # tiles first (they are what every size shares), timed apart
    t0 = time.time()
    for j in range(0, picks[-1] + 1):
        om.tile(u, j, a.cache, p["display_scale"])
    out["tiles_s_each"] = round((time.time() - t0) / (picks[-1] + 1), 2)
    for j in picks:
        row = {"n": j}
        made = om.rolling_layout(u, j, a.cache) if u.get("kind") == "mosaic_movie" else om.layout(u, j, a.cache)
        if not made:
            continue
        row["tiles_drawn"] = len(made[1])
        for name, out_px in (("s1024", 1024), ("s2048", 2048)):
            t0 = time.time()
            im, _ = om.so_far.__wrapped__(u, j, a.cache, made, out_px) if hasattr(om.so_far, "__wrapped__") else om.so_far(u, j, a.cache, made, out_px)
            buf = io.BytesIO(); im.convert("RGB").save(buf, "PNG", compress_level=1)
            row[name] = {"s": round(time.time() - t0, 2), "px": list(im.size)}
        k, w, h = mn.scale_of(made)
        t0 = time.time()
        corr = mn.corrections(u, made, a.cache)
        row["native_seams_s"] = round(time.time() - t0, 2)
        t0 = time.time()
        rgb = np.empty((h, w, 3), np.uint8)
        y = 0
        for strip in mn._rows(u, made, corr, k, 0, 0, w, h, a.cache):
            rgb[y:y + strip.shape[0]] = mn._on_black(strip); y += strip.shape[0]
        row["native"] = {"s": round(time.time() - t0, 2), "px": [w, h], "k": round(k, 3)}
        if j == picks[-1]:
            path = os.path.join(a.cache, f"native_{fid}_{j}.jpg")
            Image.fromarray(rgb).save(path, "JPEG", quality=92)
            Image.fromarray(rgb).resize((1024, round(1024 * h / w)) if w >= h else (round(1024 * w / h), 1024), Image.LANCZOS).save(path[:-4] + "_1024.png")
            row["native_jpg"] = path
        row["rss_gb"] = rss()
        out["rows"].append(row)
        print(json.dumps(row), flush=True)
    print("RESULT " + json.dumps(out), flush=True)
