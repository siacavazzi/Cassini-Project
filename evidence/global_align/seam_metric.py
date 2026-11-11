#!/usr/bin/env python3
"""Seam residuals of a finished mosaic, as drawn: every pair of overlapping tiles of different pointings (same filter on
a clouded body) measured again at their final places with the pipeline's own panel_shift / edge_shift. Prints JSON:
per pair the residual move still left (px) and the agreement (ncc) at the final places.
  seam_metric.py --code WT/web/frames --cache DIR TARGET:OBS:CAM"""
import argparse, json, math, os, re, sys
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration
import numpy as np
from PIL import Image
target, obs, cam = a.obs.split(":")
out = []
with calibration.looking("balanced"):
    for u in om.units(target, obs, cam):
        if u.get("kind") not in ("mosaic", "mosaic_movie"):
            continue
        n = len(u["frames"]) - 1
        made = om.layout(u, n, a.cache)
        if not made:
            continue
        p, tiles = made[0], [t for t in made[1] if "offset" in t]
        edges = om.clouded(u)
        roots = {}
        for t in tiles:
            roots[t["n"]] = om._pointing_root(u, t["n"], roots)
        there = om._tiles(u, a.cache, p["display_scale"])
        pics = {}
        def pic(t):
            if t["n"] not in pics:
                fp = t.get("pic") or os.path.join(there, f"{t['n']}.png")
                pics[t["n"]] = np.asarray(Image.open(fp).convert("RGBA")) if os.path.exists(fp) else None
            return pics[t["n"]]
        used = set(made[4]) if len(made) > 4 else None
        rows = []
        for i, s in enumerate(tiles):
            for t in tiles[i + 1:]:
                if roots[s["n"]] == roots[t["n"]] or s["filter"] != t["filter"]:
                    continue
                if used and s["filter"] not in used:
                    continue
                A, B = pic(s), pic(t)
                if A is None or B is None:
                    continue
                f = om.edge_shift if edges else om.panel_shift
                kw = {} if edges else {"most": om.PANEL_FAR}
                shift, how = f(s, A, s["offset"], t, B, t["offset"], **kw)
                if shift is not None:
                    rows.append({"pair": [s["n"], t["n"]], "res": round(math.hypot(*shift), 2), "ncc0": how["ncc"][0], "ncc1": how["ncc"][1]})
                else:
                    m = re.search(r"([-+][\d.]+),([-+][\d.]+) ncc ([-\d.]+)->([-\d.]+)", str(how))
                    if m:
                        rows.append({"pair": [s["n"], t["n"]], "res": round(math.hypot(float(m[1]), float(m[2])), 2),
                                     "ncc0": float(m[3]), "ncc1": float(m[4]), "unbelieved": True})
        res = [r["res"] for r in rows if not r.get("unbelieved")]
        nc = [r["ncc0"] for r in rows]
        out.append({"pass": "_".join(map(str, u["key"])), "pairs": len(rows), "measured": len(res),
                    "res_median": float(np.median(res)) if res else None,
                    "res_p90": float(np.percentile(res, 90)) if res else None,
                    "over1px": int(sum(r > 1.0 for r in res)), "over2px": int(sum(r > 2.0 for r in res)),
                    "ncc0_mean": float(np.mean(nc)) if nc else None, "rows": rows})
print(json.dumps(out))
