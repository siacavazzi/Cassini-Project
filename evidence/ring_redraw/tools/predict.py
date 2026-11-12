#!/usr/bin/env python3
"""predict.py --code --cache PASSDIR... : how far SPICE says the ring plane changes shape across each ring pass:
for each pointing's first tile, the ring field (reproject.ring_field, epoch = the pass's middle frame) over its box on
the rings; the part no single shift can take out (the field less its median, 95th percentile of its length) and the
largest such over the pass's pointings. One JSON line per pass."""
import argparse, os, sys, math, json, re
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("dirs", nargs="+")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server  # noqa
import obs_mosaic as om, calibration, reproject as rp
with calibration.looking("balanced"):
    for d in a.dirs:
        m = re.match(r"(SATURN)_(.+)_([NW])_(\d+)", d)
        try:
            us = [u for u in om.units(m.group(1), m.group(2), m.group(3)) if "_".join(map(str, u["key"])) == "_".join(d.split("_")[:len(u["key"]) + 3]) or om.folder(u, a.cache).endswith(d)]
            if not us:
                print(json.dumps({"pass": d, "err": "no unit"}), flush=True); continue
            u = us[0]
            p = om.plan(u, a.cache)
            tiles = [t for t in om._reports(u, a.cache, p, range(len(u["frames"]))) if "offset" in t]
            roots = {}
            for t in tiles:
                roots[t["n"]] = om._pointing_root(u, t["n"], roots)
            firsts = [t for t in tiles if roots[t["n"]] == t["n"]]
            fr = u["frames"]; mid = fr[len(fr) // 2]
            ets = om._ets([mid[1]] + [t["id"] for t in firsts])
            km_px = om.IFOV[u["key"][2]] * u["z"]
            om._with_kernels(mid[3])
            epoch = rp.sky_view("SATURN", ets[mid[1]])
            turn = om.view_turn(u)
            worst, rows = 0.0, []
            for t in firsts:
                if t["id"] not in ets:
                    continue
                view = rp.sky_view("SATURN", ets[t["id"]])
                h, w = int(t["box"][3]), int(t["box"][2])
                gy, gx = np.mgrid[0:h + 16:16, 0:w + 16:16].astype(float)
                x, y = gx + t["offset"][0] + t["box"][0], gy + t["offset"][1] + t["box"][1]
                aa = math.radians(turn); c, sn = math.cos(aa), math.sin(aa)
                X, Y = c * x + sn * y, c * y - sn * x
                re_, on = rp.ring_plane(epoch, X, Y, km_px)
                rv, on2 = rp.ring_plane(view, X, Y, km_px)
                rx, _ = rp.ring_plane(epoch, X + c, Y - sn, km_px)
                ry, _ = rp.ring_plane(epoch, X + sn, Y + c, km_px)
                g = np.hypot(rx - re_, ry - re_)
                on &= on2 & (g > 0)
                if on.sum() < 20:
                    continue
                dpx = (rv - re_)[on] / g[on]
                dpx = dpx - np.median(dpx)
                nr = float(np.percentile(np.abs(dpx), 95))
                rows.append(round(nr, 1)); worst = max(worst, nr)
            print(json.dumps({"pass": d, "pointings": len(firsts), "nonrigid_px": rows, "worst": round(worst, 1), "minutes": round((fr[-1][3] - fr[0][3]) / 60, 1)}), flush=True)
        except Exception as e:
            print(json.dumps({"pass": d, "err": f"{type(e).__name__}: {e}"[:200]}), flush=True)
