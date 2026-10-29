#!/usr/bin/env python3
"""Which passes split their frames again after obs_mosaic._judge placed them (a movie taking a filter more often than
REPEAT_GAP: repeat_window), and whether each such pass has a place, slot and lap for every frame, through the
checkout's own obs_mosaic. Before the fix u["place"] kept one entry per frame of the first split, so lap_of(u)[n]
raised IndexError (TITAN ISS_209TI_CLOUD002_PRIME, N1792936427_1) and slots put later frames at earlier frames' places.
Reads the index and the geometry cache only; with --picture it also draws the passes named there with so_far at their
last tile (into --cache, which must be a scratch cache, never the server's or the pre-build's).

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/repeat_places_evidence.py --out OUTDIR [--years 2013] [--picture N1792936427_1 --cache SCRATCH]

Run it from the checkout to measure (cwd: its root, for Image_index.csv). OUTDIR/passes.json lists every pass whose
frames were split again: key, frames, places, slots, laps, and ok (one of each per frame)."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--years", default="", help="comma separated; every year when left out")
    ap.add_argument("--picture", action="append", default=[], help="frame id of a pass to draw at its last tile")
    ap.add_argument("--cache")
    a = ap.parse_args()
    import obs_mosaic as om
    os.makedirs(a.out, exist_ok=True)
    idx, groups = om._observations()
    years = {int(y) for y in a.years.split(",") if y}
    year = time.gmtime
    rows, t0 = [], time.time()
    for (target, obs, inst), qs in groups.items():
        if years and year(float(idx["seconds_1970"].iloc[qs[0]])).tm_year not in years:
            continue
        cam = "N" if inst == "ISSNA" else "W"
        try:
            us = om.units(target, obs, cam)
        except Exception as e:   # (a pass the grouping itself cannot take: listed, not hidden)
            rows.append({"key": [target, obs, cam], "error": repr(e)})
            continue
        for u in us:
            if u["repeat_gap"] >= om.mosaic_benchmark.REPEAT_GAP:
                continue
            n = len(u["frames"])
            r = {"key": list(u["key"]), "kind": u["kind"], "first": u["frames"][0][1] if n else None, "frames": n,
                 "repeat_gap": u["repeat_gap"], "places": len(u.get("place") or []), "slots": len(om.slots(u)),
                 "laps": len(om.lap_of(u))}
            r["ok"] = r["places"] == r["slots"] == r["laps"] == n
            rows.append(r)
    bad = [r for r in rows if not r.get("ok")]
    summary = {"passes_split_again": len(rows), "short": len(bad),
               "by_kind": {k: sum(1 for r in bad if str(r.get("kind")) == k) for k in sorted({str(r.get("kind")) for r in bad})},
               "seconds": round(time.time() - t0, 1)}
    print(json.dumps(summary), flush=True)
    json.dump({"summary": summary, "passes": rows}, open(os.path.join(a.out, "passes.json"), "w"), indent=1)
    for fid in a.picture:
        found = om.unit_of(fid)
        if not found:
            print(fid, "in no pass", flush=True)
            continue
        u, _ = found
        n = len(u["frames"]) - 1
        try:
            im, rep = om.so_far(u, n, a.cache, out=om.OUT)
        except Exception as e:
            print(fid, "so_far at tile", n, "raised", repr(e), flush=True)
            continue
        if im is None:
            print(fid, "so_far drew nothing", flush=True)
            continue
        im.save(os.path.join(a.out, f"{fid}_tile{n}.png"))
        print(fid, "so_far at tile", n, json.dumps(rep), flush=True)


if __name__ == "__main__":
    main()
