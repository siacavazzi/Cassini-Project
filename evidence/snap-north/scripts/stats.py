"""stats.py OUT.json: over every pass (geometry only): how far north is from the top, #381 (camera axes) vs snapped."""
import sys, json, time, math, collections
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np
import reel, obs_mosaic as om
reel.load_index(); idx, obs = om._observations(); om._row_of()
def wrap(a): return (np.asarray(a, float) + 180) % 360 - 180
bef, aft, rolls, t0 = [], [], [], time.time()
passes = collections.Counter(); per_target = collections.defaultdict(lambda: collections.Counter())
for k, (target, ob, inst) in enumerate(list(obs.keys())):
    cam = "N" if inst == "ISSNA" else "W"
    try: us = om.units(target, ob, cam)
    except Exception: passes["err"] += 1; continue
    for u in us:
        placed = [fr[1] for fr in u["frames"] if fr[7]]
        if not placed: continue
        ang = reel.north_angles(placed)
        if not ang: continue
        a = np.array(list(ang.values()))
        m = float(np.degrees(np.arctan2(np.sin(np.radians(a)).mean(), np.cos(np.radians(a)).mean())))
        turn = om.pass_turn(u)
        snapped = abs(wrap(turn - m)) > 1e-6 or om.body_in_view(u["key"][0], cam, [(fr[5], fr[6], fr[7]) for fr in u["frames"] if fr[7]])
        q = om.quarter_of(turn, m)
        passes["snapped" if snapped else "camera (no body)"] += 1
        passes[f"quarter {q * 90}"] += 1
        tgt = target if target in ("SATURN", "TITAN", "JUPITER", "ENCELADUS", "RHEA", "DIONE", "TETHYS", "MIMAS", "IAPETUS") else "other"
        per_target[tgt][q * 90] += 1
        # drawn turned a - turn, north ends up turn from the top (#381: turn = m)
        bef.extend([abs(float(wrap(m)))] * len(a)); aft.extend([abs(float(wrap(turn)))] * len(a)); rolls.extend(np.abs(wrap(a - m)).tolist())
    if k % 4000 == 0: print(k, dict(passes), f"{time.time()-t0:.0f}s", flush=True)
bef, aft = np.array(bef), np.array(aft)
# north's place on the picture: up (<45), sideways (45-135), down (>135); bef/aft = how far a frame is turned from north up
def where(x): return {"up (<45)": round(float((x <= 45).mean()), 4), "sideways (45-135)": round(float(((x > 45) & (x <= 135)).mean()), 4), "down (>135)": round(float((x > 135).mean()), 4)}
sq = lambda x: np.abs(((x + 45) % 90) - 45)
r = lambda x: {"median": round(float(np.median(x)), 2), "p90": round(float(np.percentile(x, 90)), 2), "max": round(float(x.max()), 2)}
res = {"frames": int(len(bef)), "passes": dict(passes), "quarters_by_target": {t: dict(c) for t, c in per_target.items()},
       "pr381_north_from_top_deg": r(bef), "snapped_north_from_top_deg": r(aft),
       "pr381_where_north_is": where(bef), "snapped_where_north_is": where(aft),
       "turn_off_square_deg_both": r(np.array(rolls)), "secs": round(time.time() - t0)}
json.dump(res, open(sys.argv[1], "w"), indent=1); print(json.dumps(res, indent=1))
