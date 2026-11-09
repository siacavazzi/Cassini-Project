"""render.py OUTDIR CACHE: picks through the repo's own entry points (run from a worktree). Stills as a camera window
draws them with Auto center (obs_mosaic.centre_view -> frame_server.centred, else the picture as it is,
frame_server.composite); movie frames with obs_mosaic.movie_webp; mosaics with obs_mosaic.mosaic_webp."""
import sys, json, os, time, io, threading
sys.path.insert(0, 'web/frames'); sys.path.insert(0, '.')
import numpy as np
from PIL import Image
import reel, obs_mosaic as om, frame_server as fs
reel.load_index(); om._observations(); om._row_of()
out, cache = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
PICKS = [
    ("still", "saturn_233SA_WIND5HR001", "W1836792533_1"),
    ("still", "titan_230TI_M90R3CLD011", "N1831177520_1"),
    ("still", "dione_280DI_COMPGLBL001", "N1876855321_1"),
    ("still", "enceladus_258EN_PLUME001", "N1864114111_1"),
    ("still", "rings_234RI_PROPRETRG001", "N1838331921_1"),
    ("still", "rings_239RI_PROPRETRG001", "N1849105263_1"),
    ("still", "saturn_271SA_HIRESWACS001_roll", "W1871890876_1"),
    ("still", "jupiter_N1357349290", "N1357349290_1"),
    ("movie", "enceladus_258EN_PLUME001_movie", "N1864114111_1"),
    ("mosaic", "saturn_233SA_WIND5HR001_mosaic", "W1836792533_1"),
]
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
slots = threading.Semaphore(1)
rows = []
for kind, name, fid in PICKS:
    if only and name not in only: continue
    t0 = time.time(); rec = {"kind": kind, "name": name, "frame": fid}
    own = reel.north_angles([fid]).get(fid)
    try:
        if kind == "still":
            v = om.centre_view(fid)
            shown = om.view_shown(v) if hasattr(om, "view_shown") else bool(v.get("centre") or v.get("north"))
            im, rep = fs.centred([fid], v) if shown else fs.composite([fid])
            rec["view"] = {k: v.get(k) for k in ("centre", "north", "quarter", "square", "turn", "axes")}
            drawn = (own - v["turn"]) if shown and own is not None else 0.0
            rec["drawn_deg"] = round(drawn, 2); rec["north_from_top_deg"] = round(abs(om_w := ((own - drawn + 180) % 360 - 180)), 2) if own is not None else None
            buf = io.BytesIO(); im.save(buf, "PNG"); data = buf.getvalue(); ext = "png"
        elif kind == "movie":
            data, rep = om.movie_webp(fid, 1024, cache, wait=True, ahead=0); ext = "webp"
        else:
            while True:
                got = om.mosaic_webp(fid, 1024, cache, slots)
                if got and not got[1].get("behind"): data, rep = got; break
                time.sleep(20)
            ext = "webp"
        if kind != "still":
            u = om.unit_of(fid)[0]
            vt = om.view_turn(u) if hasattr(om, "view_turn") else 0.0
            rec["view_turn"] = vt; rec["north_from_top_deg"] = round(abs((vt + 180) % 360 - 180), 2)
        path = os.path.join(out, f"{name}.{ext}"); open(path, "wb").write(data)
        img = Image.open(io.BytesIO(data)); rec["size"] = list(img.size)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    rec["own_north_angle"] = own; rec["secs"] = round(time.time() - t0, 1)
    print(json.dumps(rec), flush=True); rows.append(rec)
    json.dump(rows, open(os.path.join(out, "samples.json"), "w"), indent=1, default=str)
print("DONE", flush=True)
