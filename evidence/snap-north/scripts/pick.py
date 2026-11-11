import sys, json, datetime
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np, reel, obs_mosaic as om
reel.load_index(); idx, obs = om._observations(); om._row_of()
idx_, row = om._row_of()
out = []
for (target, ob, inst) in obs.keys():
    cam = "N" if inst == "ISSNA" else "W"
    try: us = om.units(target, ob, cam)
    except Exception: continue
    for u in us:
        placed = [fr for fr in u["frames"] if fr[7]]
        if len(placed) < 3: continue
        last = placed[-1][1]
        yr = datetime.datetime.utcfromtimestamp(float(idx_.iloc[row[last]]["seconds_1970"])).year
        if yr < 2016: continue
        m = om.view_axes(u); t = om.view_turn(u)
        if m is None: continue
        q = om.quarter_of(t, m)
        v = om.centre_view(last)
        kind = "centre" if v.get("centre") else "north" if v.get("north") else "quarter" if v.get("quarter") else "asis"
        out.append({"target": target, "obs": ob, "cam": cam, "n": len(placed), "last": last, "first": placed[0][1], "year": yr,
                    "axes": m, "turn": t, "q": q, "kind": kind, "square": bool(v.get("square")), "mosaic": bool(u.get("mosaic")), "ukind": u.get("kind")})
json.dump(out, open(sys.argv[1], "w"))
import collections
print(len(out), collections.Counter((o["kind"], o["q"]) for o in out))
