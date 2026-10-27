#!/usr/bin/env python3
"""Read-only: every pass of the mission through obs_mosaic.units() (the server's own pass rules and _judge), one row
per pass with its kind, frames, places, laps, filters and time span. No images are read; needs the geometry cache.
  CASSINI_GEOMETRY_CACHE=/Volumes/LaCie/claude_scratch_spk/geometry.sqlite python docs/interesting-moments/scan_passes.py OUT.csv"""
import os, sys, csv, time
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "web/frames")); sys.path.insert(0, REPO)
import reel, obs_mosaic as om  # noqa

SKIP = {"SKY", "UNK", "NONE", "DARK", "STAR", "PLAQUE", "CAL_LAMPS"}
idx, _ = reel.load_index()
groups = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).size()
out = open(sys.argv[1], "w", newline=""); w = csv.writer(out)
w.writerow(["target", "obs", "cam", "n", "kind", "mosaic", "whole", "movie", "frames", "taken", "places", "repeats",
            "jump_frac", "dwell", "filters", "start", "end", "z_km", "first_id"])
t0 = time.time()
for k, ((target, obs, inst), size) in enumerate(groups.items()):
    if target in SKIP or not isinstance(obs, str):
        continue
    cam = "N" if inst == "ISSNA" else "W"
    try:
        us = om.units(target, obs, cam)
    except Exception as e:  # noqa
        print("skip", target, obs, cam, e, flush=True); continue
    for u in us:
        fr = u["frames"]
        if not fr:
            continue
        places = len(set(p for p in u.get("place", []) if p is not None))
        filt = sorted(set(f[2] for f in fr))
        w.writerow([target, obs, cam, u["key"][3], u.get("kind"), int(bool(u.get("mosaic"))), int(bool(u.get("whole"))),
                    int(bool(u.get("movie"))), len(fr), len(u.get("taken", fr)), places, u.get("repeats"),
                    u.get("jump_frac"), u.get("dwell"), " ".join(filt), fr[0][3], u["last"], u.get("z"), fr[0][1]])
    om._units.clear()
    if k % 2000 == 0:
        print(k, len(groups), round(time.time() - t0), flush=True)
out.close(); print("done", round(time.time() - t0))
