"""probe.py PATTERN...: passes of observations matching the patterns, kind, size, view_turn, turn range, twist."""
import sys, re, json
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import reel, obs_mosaic as om
idx, obs = om._observations()
pats = [re.compile(p) for p in sys.argv[1:]]
def wrap(a): return (a + 180) % 360 - 180
for (tgt, ob, inst), rows in obs.items():
    if not any(p.search(ob) for p in pats) or len(rows) > 400: continue
    for u in om.units(tgt, ob, "N" if inst == "ISSNA" else "W"):
        if len(u["frames"]) < 3: continue
        ids = [fr[1] for fr in u["frames"] if fr[7]]
        ang = reel.north_angles(ids)
        vt = om.view_turn(u)
        rel = [wrap(ang[i] - vt) for i in ids if i in ang]
        print(json.dumps({"t": tgt, "o": ob, "c": inst, "kind": u.get("kind"), "movie": u.get("movie"), "mosaic": u.get("mosaic"),
              "n": len(u["frames"]), "placed": len(ids), "twist": bool(u.get("twist")), "view_turn": vt,
              "rel": [round(min(rel), 2), round(max(rel), 2)] if rel else None, "first": u["frames"][0][1], "last": u["frames"][-1][1]}), flush=True)
