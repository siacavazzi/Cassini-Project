"""render.py PICKS.json OUTDIR: each pick's still through frame_server.centred, BEFORE (no turn: today's north up) and AFTER."""
import sys, json, os, time, datetime
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np
import frame_server as fs, reel, obs_mosaic as om
reel.load_index(); om._observations(); om._row_of()
picks, out = json.load(open(sys.argv[1])), sys.argv[2]
idx, row = om._row_of()
rows = []
def wrap(a): return (a + 180) % 360 - 180
for p in picks:
    ids = p["ids"]; last = ids[-1]
    after = om.centre_view(last)
    before = {k: v for k, v in after.items() if k != "turn"}
    found = om.unit_of(last)
    if found and before.get("north") and not before.get("centre"):
        for k in ("hold", "at"): before.pop(k, None)
        h = om.hold_of(found[0], found[1], 0.0)
        if h: before.update(h)
    own = reel.north_angles([last]).get(last)
    t = float(idx.iloc[row[last]]["seconds_1970"])
    rec = {"ids": ids, "body": p["body"], "why": p["why"], "date": datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),
           "centre": after.get("centre"), "north": after.get("north"), "view_turn": after.get("turn"), "north_angle": own,
           "tilt_before": round(abs(wrap(own)), 2) if own is not None else None,
           "tilt_after": round(abs(wrap(own - after.get("turn", 0))), 2) if own is not None else None}
    for tag, view in (("before", before), ("after", after)):
        t0 = time.time()
        im, rep = fs.centred(ids, view)
        a = np.asarray(im)[..., -1]
        name = f"{p['body'].lower()}_{last}_{tag}.png"
        im.save(os.path.join(out, name))
        rec[tag] = {"png": name, "size": list(im.size), "transparent": round(float((a == 0).mean()), 4),
                    "turn_applied": rep.get("turn", 0.0), "frame_offset": rep.get("frame_offset"),
                    "held": rep.get("held"), "hold_skipped": rep.get("hold_skipped"), "secs": round(time.time() - t0, 1)}
    print(json.dumps(rec), flush=True)
    rows.append(rec)
json.dump(rows, open(os.path.join(out, "samples.json"), "w"), indent=1)
