#!/usr/bin/env python3
"""Is a mosaic's panel misregistration SPICE's pointing, or the surface moving between panels? For each pair of
panels panel_probe.py measured (OUTDIR/probe.json), the shift SPICE predicts for the surface at the middle of their
overlap: the body-fixed point there at the first panel's time, put back on the picture at the second panel's time
(the body turned and Cassini moved in between, while the panels are centred on the body's centre), in the pictures'
reference pixels, beside the shift measured. Pointing error is what is left.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/panel_motion.py --cache SCRATCH_CACHE --probe OUTDIR/probe.json

Prints per pair: measured, predicted for each way the picture's x can run (east left or right; north is up), and the
residual; and per pass the median residual for the convention that fits."""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--probe", required=True)
    a = ap.parse_args()
    import spiceypy as sp
    import bootleg_autonav as ba
    import obs_mosaic as om
    import panel_probe
    probe = json.load(open(a.probe))
    db = ba._geometry_db()
    loaded = set()
    out = []
    for rec in probe:
        u, n = panel_probe.unit(rec["pass"])
        p = om.plan(u, a.cache)
        tiles = {t["n"]: t for t in om._reports(u, a.cache, p, range(n + 1)) if "offset" in t}
        target = u["key"][0]
        km = om.IFOV[u["key"][2]] * u["z"]   # km on the sky at the body a reference pixel spans

        def geom(t):
            row = db.execute("SELECT et, camera FROM target WHERE frame = ?", (t["id"],)).fetchone()
            return row

        rows = []
        for r in rec["pairs_before"]:
            if "shift" not in r:
                continue
            ta, tb = tiles[r["a"]], tiles[r["b"]]
            ga, gb = geom(ta), geom(tb)
            if not ga or not gb or ga[0] is None:
                continue
            import datetime
            year = datetime.datetime.utcfromtimestamp(ta["t"]).year
            if year not in loaded:
                ba.load_kernels(year, year)
                loaded.add(year)
            # the middle of the overlap, reference pixels from the body's centre, as the picture draws it
            xa0, ya0 = ta["offset"][0] + ta["box"][0], ta["offset"][1] + ta["box"][1]
            xb0, yb0 = tb["offset"][0] + tb["box"][0], tb["offset"][1] + tb["box"][1]
            ox = (max(xa0, xb0) + min(xa0 + ta["box"][2], xb0 + tb["box"][2])) / 2
            oy = (max(ya0, yb0) + min(ya0 + ta["box"][3], yb0 + tb["box"][3])) / 2
            pred, why = {}, "off the body"
            for sign in (1, -1):   # picture x = sign * east
                try:
                    pred[sign] = predict(sp, target, ga[0], gb[0], ox, oy, km, sign)
                except Exception as e:
                    pred[sign] = None
                    why = str(e)[:80]
            m = r["shift"]
            row = {"a": r["a"], "b": r["b"], "dt": r["dt"], "measured": m, "at": [round(ox), round(oy)]}
            for sign, v in pred.items():
                if v is not None:
                    row[f"pred{sign:+d}"] = [round(v[0], 2), round(v[1], 2)]
                    row[f"left{sign:+d}"] = round(math.hypot(m[0] - v[0], m[1] - v[1]), 2)
            if all(v is None for v in pred.values()):
                row["why"] = why
            rows.append(row)
            print(rec["pass"], row, flush=True)
        summary = {"pass": rec["pass"], "pairs": len(rows),
                   "measured_median": round(float(np.median([math.hypot(*r["measured"]) for r in rows])), 2) if rows else None}
        for sign in (1, -1):
            left = [r[f"left{sign:+d}"] for r in rows if f"left{sign:+d}" in r]
            if left:
                summary[f"left{sign:+d}_median"] = round(float(np.median(left)), 2)
                summary[f"left{sign:+d}_max"] = round(float(max(left)), 2)
        print("SUMMARY", json.dumps(summary), flush=True)
        out.append({"summary": summary, "rows": rows})
    json.dump(out, open(os.path.join(os.path.dirname(a.probe), "motion.json"), "w"), indent=1)


def predict(sp, target, et_a, et_b, ox, oy, km, sign):
    """The shift (reference pixels, picture x right, y down) of the surface point at (ox, oy) from the body's centre
    on the picture at et_a, seen again at et_b; None when (ox, oy) is off the body."""
    radii = np.array(sp.bodvrd(target, "RADII", 3)[1])

    def view(et):
        pos, lt = sp.spkpos(target, et, "J2000", "LT+S", "CASSINI")
        c = np.array(pos)
        ch = c / np.linalg.norm(c)
        north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
        north /= np.linalg.norm(north)
        east = np.cross(north, ch)   # (east on the sky, north x line of sight: to the left seen from Cassini)
        rot = np.array(sp.pxform("J2000", f"IAU_{target}", et - lt))
        return c, ch, north, east, rot

    c, ch, north, east, rot = view(et_a)
    # the sky offset (km at the body) of the point, and the ray from Cassini through it
    e_km, n_km = sign * ox * km, -oy * km
    ray = c + e_km * east + n_km * north
    # in the body-fixed frame, from Cassini (at -c from the centre)
    try:
        P = np.array(sp.surfpt(rot @ -c, rot @ ray, *radii))
    except sp.utils.exceptions.NotFoundError:
        return None
    c2, ch2, north2, east2, rot2 = view(et_b)
    v = c2 + rot2.T @ P        # Cassini to the point, J2000
    d = np.linalg.norm(c2)
    sky = v * (d / (v @ ch2)) - c2   # where it lands on the sky plane at the body
    x2, y2 = sign * (sky @ east2) / km, -(sky @ north2) / km
    return x2 - ox, y2 - oy


if __name__ == "__main__":
    main()
