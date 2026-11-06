"""Every pass obs_mosaic.units makes on current main, numbered like sets_passes.pass_table, with its judging stats
and its pictures (repeats merged) as (t, filter, x, y) in frames on the pass canvas (None when SPICE has no place),
plus the count of all frames taken (repeats too). JSON lines."""
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/dev/wt-moviecat/web/frames"))
import obs_mosaic, reel
idx, _ = reel.load_index()
out = open(sys.argv[1], "w")
n = 0
KEYS = ("kind", "movie", "mosaic", "track", "tossup", "jump_frac", "dwell", "repeats", "panned", "revisit", "strip", "whole", "slot_laps", "z")
for (target, ob, inst), rows in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices.items():
    if not isinstance(ob, str):
        continue
    for u in obs_mosaic.units(target, ob, "N" if inst == "ISSNA" else "W"):
        if not u["frames"]:
            continue
        rec = {k: u.get(k) for k in KEYS}
        rec = {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in rec.items()}
        pics = []
        for _, fid, f, t, nm, x, y, z in u["frames"]:
            if z and u["z"]:
                pics.append([fid, t, f, round(-x * z / u["z"] / obs_mosaic.FRAME, 3), round(-y * z / u["z"] / obs_mosaic.FRAME, 3)])
            else:
                pics.append([fid, t, f, None, None])
        rec.update(pass_id=n, target=target, obs=ob, cam=inst, num=u["key"][3], taken=len(u.get("taken") or []), pics=pics)
        out.write(json.dumps(rec) + "\n"); n += 1
print("passes", n)
