#!/usr/bin/env python3
"""steady_metric.py --code --cache OBS: for each movie pass, the steadied places (steady_places, the default smoothing)
and how still the target is in them: every pair of placed tiles k apart (k = 1, 3, 8, 20) matched again on the target
where the steadied places put them (_shift_onto, steady_guide's square): the residual move. Prints JSON per pass."""
import argparse, os, sys, math, json, time
ap = argparse.ArgumentParser(); ap.add_argument("--code"); ap.add_argument("--cache"); ap.add_argument("obs")
a = ap.parse_args()
code = os.path.abspath(os.path.expanduser(a.code)); a.cache = os.path.abspath(a.cache)
sys.path.insert(0, code); os.chdir(os.path.join(code, "..", ".."))
import frame_server, obs_mosaic as om, calibration, numpy as np
with calibration.looking("balanced"):
    for u in om.units(*a.obs.split(":")):
        if u.get("kind") != "movie" or u.get("track"):
            continue
        p = om.plan(u, a.cache)
        t0 = time.time()
        places = om.steady_places(u, a.cache, p)
        secs = time.time() - t0
        if not places:
            continue
        made, pic, there = om._every_tile(u, a.cache, p)
        by = {t["n"]: t for t in made if "offset" in t}
        ns = [n for n in sorted(places) if n in by]
        guide = om.steady_guide(u)
        out = {"pass": "_".join(map(str, u["key"])), "frames": len(ns), "solve_s": round(secs, 1)}
        for k in (1, 3, 8, 20):
            res = []
            # (the k-th next frame of the same filter: a colour cycle's frames are matched within their filter)
            seq = {}
            for m in ns:
                seq.setdefault(by[m]["filter"], []).append(m)
            pairs = [(fs[i], fs[i + k]) for fs in seq.values() for i in range(len(fs) - k)]
            for j, n in pairs:
                rel = (places[n][0] - places[j][0], places[n][1] - places[j][1])
                g = guide({j: places[j]}, j, n, None)
                sh, how = om._shift_onto(by[j], pic(j), (0.0, 0.0), by[n], pic(n), rel, around=g.get("around"),
                                         holes=g.get("holes", ()), kept=g.get("kept"))
                if sh is not None and math.hypot(*sh) < 40:
                    res.append(math.hypot(*sh))
            out[f"k{k}"] = {"n": len(res), "median": round(float(np.median(res)), 2) if res else None,
                            "p90": round(float(np.percentile(res, 90)), 2) if res else None}
        print(json.dumps(out), flush=True)
