"""stats.py OUT.json: over every frame in a centred or north pass (centre_view, geometry only), tilt before/after."""
import sys, json, time
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np
import reel, obs_mosaic as om
reel.load_index(); idx, obs = om._observations(); om._row_of()
def wrap(a): return (np.asarray(a) + 180) % 360 - 180
bef, aft, kinds, npass, t0 = [], [], {"centre": 0, "north": 0, "other": 0, "err": 0}, 0, time.time()
keys = list(obs.keys())
for k, (target, ob, inst) in enumerate(keys):
    cam = "N" if inst == "ISSNA" else "W"
    try:
        us = om.units(target, ob, cam)
    except Exception:
        kinds["err"] += 1; continue
    for u in us:
        placed = [fr[1] for fr in u["frames"] if fr[7]]
        if not placed: continue
        try:
            v = om.centre_view(placed[0])
        except Exception:
            kinds["err"] += 1; continue
        if not (v.get("centre") or v.get("north")):
            kinds["other"] += 1; continue
        kinds["centre" if v.get("centre") else "north"] += 1
        ang = reel.north_angles(placed)
        a = np.array(list(ang.values()))
        if not len(a): continue
        bef.extend(np.abs(wrap(a)).tolist()); aft.extend(np.abs(wrap(a - v.get("turn", 0.0))).tolist())
    if k % 2000 == 0:
        print(k, len(keys), kinds, len(bef), f"{time.time()-t0:.0f}s", flush=True)
bef, aft = np.array(bef), np.array(aft)
sq = lambda x: np.abs(((x + 45) % 90) - 45)   # how far off the square the picture looks (a 90/180 deg turn keeps it square)
r = lambda x: {"median": round(float(np.median(x)), 2), "p90": round(float(np.percentile(x, 90)), 2), "mean": round(float(x.mean()), 2)}
res = {"frames": int(len(bef)), "passes": kinds, "before_deg": r(bef), "after_deg": r(aft),
       "before_off_square_deg": r(sq(bef)), "after_off_square_deg": r(sq(aft)),
       "share_after_lt_1deg": round(float((aft < 1).mean()), 4), "share_before_lt_1deg": round(float((bef < 1).mean()), 4),
       "share_after_off_square_lt_1deg": round(float((sq(aft) < 1).mean()), 4), "share_before_off_square_lt_1deg": round(float((sq(bef) < 1).mean()), 4),
       "share_after_lt_5deg": round(float((aft < 5).mean()), 4), "secs": round(time.time() - t0)}
json.dump(res, open(sys.argv[1], "w"), indent=1); print(json.dumps(res, indent=1))
