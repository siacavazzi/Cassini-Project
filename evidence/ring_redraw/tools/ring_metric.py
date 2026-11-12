#!/usr/bin/env python3
"""ring_metric.py --code WT/web/frames --cache DIR TARGET:OBS:CAM : ring seams of a finished Saturn mosaic, as drawn.
For every pair of overlapping tiles of one filter in different pointings, the radial profiles (SPICE's ring plane at
each tile's own time) of the part both cover, each where the layout puts it; the radial lag (sub-bin, by a parabola)
that lines the two profiles up, in px. 0 = the ringlets meet across the seam."""
import argparse, json, math, os, sys
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration, reproject as rp
from PIL import Image
LAG = 25   # bins of RING_BIN km each way
out = []
with calibration.looking("balanced"):
    for u in om.units(*a.obs.split(":")):
        if u.get("kind") != "mosaic":
            continue
        rings = om._ring_geometry(u)
        if rings is None:
            continue
        n = len(u["frames"]) - 1
        made = om.layout(u, n, a.cache)
        p, tiles = made[0], [t for t in made[1] if "offset" in t]
        km_px = om.IFOV[u["key"][2]] * u["z"]
        there = om._tiles(u, a.cache, p["display_scale"])
        roots = {}
        for t in tiles:
            roots[t["n"]] = om._pointing_root(u, t["n"], roots)
        samp = {}
        for t in tiles:
            im = np.asarray(Image.open((t.get("pic") or os.path.join(there, f"{t['n']}.png"))).convert("RGBA"))
            h, w = im.shape[:2]
            k = t["box"][2] / w
            x0, y0 = t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]
            sy, sx = np.mgrid[2:h - 2:3, 2:w - 2:3]
            sy, sx = sy.ravel(), sx.ravel()
            # each tile's own geometry: SPICE's ring plane at its time, at the place the layout drew it
            gx, gy = sx * k + x0, sy * k + y0
            radius, on = rings(gx, gy, t.get("ring_at", t["id"]))
            px = im[sy, sx]
            use = on & (px[:, 3] == 255)
            samp[t["n"]] = (gx[use], gy[use], radius[use], px[use, :3].astype(np.float32).mean(axis=1))
        pics = {t["n"]: np.asarray(Image.open((t.get("pic") or os.path.join(there, f"{t['n']}.png"))).convert("RGBA")) for t in tiles}
        rows = []
        within = []
        for i, s in enumerate(tiles):
            for t in tiles[i + 1:]:
                if roots[s["n"]] == roots[t["n"]] and s["filter"] != t["filter"]:
                    mv, how = om.ring_pair_shift(u, rings, s, pics[s["n"]], t, pics[t["n"]])
                    if mv is not None:
                        within.append(round(math.hypot(*mv), 2))
                    continue
                if roots[s["n"]] == roots[t["n"]] or s["filter"] != t["filter"]:
                    continue
                mv, how = om.ring_pair_shift(u, rings, s, pics[s["n"]], t, pics[t["n"]])
                if mv is None:
                    continue
                rows.append({"pair": [s["n"], t["n"]], "lag_px": round(math.hypot(*mv), 2), "ncc": how["ncc"], "ncc0": how["ncc"],
                             "lag_km": how["lag_km"]})
        lags = [r["lag_px"] for r in rows]
        out.append({"pass": "_".join(map(str, u["key"])), "pairs": len(rows),
                    "median": float(np.median(lags)) if lags else None, "p90": float(np.percentile(lags, 90)) if lags else None,
                    "over2px": int(sum(l > 2 for l in lags)), "ncc0_mean": float(np.mean([r["ncc0"] for r in rows])) if rows else None,
                    "within_pairs": len(within), "within_median": float(np.median(within)) if within else None,
                    "within_p90": float(np.percentile(within, 90)) if within else None, "within_over1": int(sum(w > 1 for w in within)),
                    "rows": rows})
print(json.dumps(out))
