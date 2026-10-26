"""Synthetic check that threads drawing different mosaic movies at once (the pre-build's threads in one process)
keep each other's last pictures (obs_mosaic._rolled, ROLLED_PASSES): every frame after a pass's first grows from
the one before (one tile's compose), none is drawn whole again because another thread's pass pushed its picture
out. Run: python web/test_rolling_threads.py"""
import os, sys, json, tempfile, threading, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

THREADS = int(os.environ.get("THREADS", "8"))   # more passes at once than the old 6 kept filters (one filter each here)
N = 12   # 4 places, 3 laps
SCALE = {"blacks": {}, "white": 1, "gamma": 3}
cache = tempfile.mkdtemp()
offs = [(-400, -400), (400, -400), (-400, 400), (400, 400)]
passes, by_id = [], {}
for q in range(THREADS):
    fr = [(f"p{i}", f"N{1500000000 + 1000 * q + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(N)]
    u = {"key": ("JUPITER", f"OBS{q}", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True,
         "last": 1000 + 30 * N, "place": [i % 4 for i in range(N)], "kind": "mosaic_movie", "repeats": 3}
    d = om.folder(u, cache)
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, (_, fid, f, t, *_r) in enumerate(fr):
        im = np.zeros((1448, 1448, 4), np.uint8)
        c = (1448 - 1024) // 2
        im[c:c + 1024, c:c + 1024, 3] = 255
        im[c:c + 1024, c:c + 1024, :3] = 60 + 10 * i
        Image.fromarray(im).save(f"{td}/{i}.png")
        json.dump({"n": i, "id": fid, "filter": f, "t": t, "offset": list(map(float, offs[i % 4])), "box": [-724, -724, 1448, 1448]},
                  open(f"{td}/{i}.json", "w"))
        by_id[fid] = (u, i)
    json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-1124, -1124, 1124, 1124],
               "fixed": True, "view": [2248, 2248], "k": 2048 / 2248, "colour": None, "grey": "CB2", "whole": False},
              open(d + "/" + om.PLAN_FILE, "w"))
    passes.append((u, td))
tds = {u["key"]: td for u, td in passes}
om.unit_of = lambda fid: by_id[fid]
om.tiles_ahead = lambda *a, **k: None
om.rolling_ahead = lambda *a, **k: None
om.tile = lambda u_, j, c, s=None: json.load(open(f"{tds[u_['key']]}/{j}.json"))

# each thread's composes, by the window sizes they drew (2 = one tile grown over the picture before)
calls = collections.defaultdict(list)
compose = om._compose
om._compose = lambda window, k, **kw: calls[threading.current_thread().name].append(len(window)) or compose(window, k, **kw)
if hasattr(om, "rolled_room"):
    om.rolled_room(THREADS + 1)   # as the pre-build does for its threads
start = threading.Barrier(THREADS)


def play(u):
    start.wait()
    for n in range(N):
        om.rolling_webp(u["frames"][n][1], 512, cache, 1)
        # every thread draws its frame n before any goes on (the pre-build's threads interleave like this, each at
        # its own pace; in lockstep, every other pass is drawn between a pass's two frames)
        start.wait()


threads = [threading.Thread(target=play, args=(u,), name=f"pass{q}") for q, (u, _) in enumerate(passes)]
for t in threads:
    t.start()
for t in threads:
    t.join()
for name in sorted(calls):
    whole = [w for w in calls[name][1:] if w > 2]
    print(name, "composes", calls[name])
    assert not whole, (name, "drawn whole again", calls[name])
print(f"{THREADS} threads, {N} frames each: every frame after the first grown by one tile; ok")
