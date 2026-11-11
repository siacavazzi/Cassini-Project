"""render_mm.py PICKS.json OUTDIR CACHE: each pick through the repo's own entry points, at size 1024:
movies with obs_mosaic.movie_webp (centre=True default; first, middle and last frame of the pass), mosaics with
obs_mosaic.mosaic_webp at the pass's last frame (what frame_server's /frames/mosaic/<ID>.webp?size=1024 sends),
waited for until no tile is behind. Same script in the BEFORE and AFTER worktrees (run from the worktree)."""
import sys, json, os, time, io, datetime, threading, math
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np
from PIL import Image
import reel, obs_mosaic as om
reel.load_index(); om._observations()
idx, row = om._row_of()
picks, out, cache = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
slots = threading.Semaphore(2)
def wrap(a): return (a + 180) % 360 - 180
def date(fid): return datetime.datetime.utcfromtimestamp(float(idx.iloc[row[fid]]["seconds_1970"])).strftime("%Y-%m-%d %H:%M")
def alpha_share(data):
    im = Image.open(io.BytesIO(data)); im.load()
    if im.mode != "RGBA": return im, 0.0
    a = np.asarray(im)[..., 3]
    return im, round(float((a == 0).mean()), 4)
rows = []
for p in picks:
    u, _ = om.unit_of(p["first"])
    ids = [fr[1] for fr in u["frames"]]
    ang = reel.north_angles([i for i in ids])
    vt = om.view_turn(u) if hasattr(om, "view_turn") else None
    base = vt or 0.0
    rel = [wrap(ang[i] - base) for i in ids if i in ang]
    rec = {"name": p["name"], "kind": u.get("kind"), "observation": u["key"][1], "tiles": len(ids), "twist": bool(u.get("twist")),
           "view_turn": vt, "turn_range_vs_axes": [round(min(rel), 2), round(max(rel), 2)] if rel else None,
           "north_angles_range": [round(min(ang.values()), 2), round(max(ang.values()), 2)] if ang else None, "pictures": []}
    which = [0, len(ids) // 2, len(ids) - 1] if p["type"] == "movie" else [len(ids) - 1]
    for k in which:
        fid = ids[k]
        t0 = time.time()
        if p["type"] == "movie":
            got = om.movie_webp(fid, 1024, cache, wait=True, ahead=0)
            data, rep = got if got else (None, {"why": "no pass"})
        else:
            while True:
                got = om.mosaic_webp(fid, 1024, cache, slots)
                if got and not got[1].get("behind"):
                    data, rep = got; break
                print("  waiting", fid, got[1].get("behind") if got else None, flush=True)
                time.sleep(20)
        pic = {"frame": fid, "n": k, "date": date(fid), "own_north_angle": ang.get(fid), "secs": round(time.time() - t0, 1)}
        if data:
            name = f"{p['name']}_{k}.webp"
            open(os.path.join(out, name), "wb").write(data)
            im, tr = alpha_share(data)
            pic.update({"file": name, "size": list(im.size), "mode": im.mode, "transparent": tr,
                        "turn_vs_axes": round(wrap(ang[fid] - base), 2) if fid in ang else None,
                        "report": {k2: rep.get(k2) for k2 in ("turn", "centre", "steady", "why", "behind", "tiles", "scale") if k2 in rep}})
        else:
            pic["why"] = rep.get("why")
        rec["pictures"].append(pic)
        print(json.dumps(pic), flush=True)
    rows.append(rec)
    json.dump(rows, open(os.path.join(out, "samples.json"), "w"), indent=1, default=str)
print("DONE", flush=True)
