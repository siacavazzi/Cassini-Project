#!/usr/bin/env python3
"""Probe for movie strobing, pumping and panel flicker (spot check round 2): for each pass named by one of its frames,
every frame's exposure, saturated share, sky test, own-sky black, exposure gain, tile place (SPICE's and registered) and
(mosaic movies) lap gain, as JSON lines; --layout N ...: a mosaic movie's drawn tiles at those frames. Reads the archive through the pipeline into a scratch cache (--cache); nothing is served.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/strobe_probe.py --cache DIR --out probe.jsonl FRAME_ID ...
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=int, default=80, help="most frames per pass")
    ap.add_argument("--layout", type=int, nargs="*", default=[], help="mosaic movies: rolling_layout at these frames")
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()
    import cv2
    import numpy as np
    import calibration as cal
    import data_source as ds
    import label_handler as lh
    import stacking
    import obs_mosaic as om

    out = open(args.out, "w")
    for fid in args.ids:
        found = om.unit_of(fid)
        if not found:
            print(fid, "in no pass")
            continue
        u, _ = found
        p = om.plan(u, args.cache)
        scale = p["display_scale"]
        head = {"pass": fid, "key": list(u["key"]), "frames": len(u["frames"]), "mosaic": bool(u.get("mosaic")),
                "movie": bool(u.get("movie")), "kind": om.kind_of(fid).get("kind"), "z": u.get("z"),
                "scale": {k: v for k, v in scale.items() if k != "black_of"}, "colour": p.get("colour"),
                "grey": p.get("grey"), "tiles_dir": om._tiles(u, args.cache, scale)}
        print(json.dumps(head, default=str))
        out.write(json.dumps(head, default=str) + "\n")
        radius_km = om.RADIUS.get(u["key"][0], 0)
        try:
            gains = om.exposure_gains(u, args.cache, p, om.EXPOSURE_SMOOTH, True, True, 0)
        except Exception as e:
            gains = {"error": repr(e)}
        prev = om._lap_prev(u) if u.get("mosaic") else None
        for n, fr in enumerate(u["frames"][:args.max]):
            path, fid2, f, t, nm, x, y, z = fr
            row = {"n": n, "id": fid2, "filter": f}
            try:
                lbl = lh.label(path, as_png=True)
                info = lbl.get_info()
                codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
                row["exp"] = info.get("EXPOSURE_DURATION")
                row["conv"] = info.get("DATA_CONVERSION_TYPE")
                row["sat"] = round(float(cal.saturated(codes, info).mean()), 4)
                # lines lost in downlink (the prefix's tails) and what garbled_lines cuts on top of them
                valid = lbl.valid_mask()
                row["invalid"] = round(1 - float(valid.mean()), 4)
                if codes is not None and codes.shape == valid.shape:
                    row["garbled"] = round(float(lh.garbled_lines(codes, valid).mean()), 4)
                row["packet_flag"] = info.get("MISSING_PACKET_FLAG")
                _, iof, _ = stacking.load_hdr(path, u.get("repeat_gap", om.mosaic_benchmark.REPEAT_GAP))
                if iof is not None:
                    q = iof[::4, ::4].astype(np.float32)
                    top = 0.05 * np.percentile(q, 99.9)
                    row["p50"], row["p99_9"] = float(np.median(q)), float(np.percentile(q, 99.9))
                    row["sky_share"] = round(float((q < top).mean()), 4)
                    rpx = radius_km / (z * om.IFOV[u["key"][2]]) if z else 0
                    row["disk_r_px"] = round(rpx, 1)
                    row["disk_px"] = int(om._disk_pixels(q, iof.shape, x, y, rpx).size) if z else None
                    row["xy"] = [round(x, 1), round(y, 1)] if z else None
            except Exception as e:
                row["read_error"] = repr(e)[:200]
            try:
                tr = om.tile(u, n, args.cache, scale)
                row.update({k: tr.get(k) for k in ("black", "lost", "why", "gain", "stacked", "calibrated", "saturated", "offset",
                                                   "spice_offset", "registered", "box") if k in tr})
                row["placed"] = "offset" in tr
                if prev is not None:
                    row["lap_prev"] = prev[n]
                    if "offset" in tr:
                        row["lap_gain"] = om.lap_gain(u, p, args.cache, n, lambda i: om.tile(u, i, args.cache, scale))
            except Exception as e:
                row["tile_error"] = repr(e)[:200]
            if isinstance(gains, dict):
                row["egain"] = gains.get(n)
            print(json.dumps(row, default=str))
            out.write(json.dumps(row, default=str) + "\n")
            out.flush()
        if args.layout and om.kind_of(fid).get("kind") == "mosaic_movie":
            # a mosaic movie's pictures: what rolling_layout draws at each of these frames (tiles, base, filters)
            for n in args.layout:
                made = om.rolling_layout(u, min(n, len(u["frames"]) - 1), args.cache)
                if made:
                    _, tiles, rect, count, used, name = made
                    row = {"layout": n, "used": used, "name": name, "rect": rect, "count": count,
                           "base": sorted(t["n"] for t in tiles if t.get("base")),
                           "drawn": sorted(t["n"] for t in tiles if t.get("drawn")), "luminance": om.lum_base(u, p, tiles, used)}
                    print(json.dumps(row, default=str))
                    out.write(json.dumps(row, default=str) + "\n")


if __name__ == "__main__":
    main()
