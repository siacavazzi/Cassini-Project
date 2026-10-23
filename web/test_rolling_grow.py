"""Synthetic check of a mosaic movie's pictures grown from the last one (obs_mosaic._roll): each new frame
composes only its own tile over the picture before, it looks like the picture drawn whole from every place's
newest tile, a filter whose tiles did not change is not drawn again, and rolling_ahead makes the next frames'
pictures in the background. Run: python web/test_rolling_grow.py"""
import os, sys, json, tempfile, io, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

cache = tempfile.mkdtemp()
offs = [(-400, -400), (400, -400), (-400, 400), (400, 400)]
N = 16   # 4 places, 4 laps
fr = [(f"p{i}", f"N{1500000000 + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(N)]
u = {"key": ("JUPITER", "OBS", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1000 + 30 * N,
     "place": [i % 4 for i in range(N)], "kind": "mosaic_movie", "repeats": 4}
d = om.folder(u, cache)
TD = om._tiles(u, cache, {"blacks": {}, "white": 1, "gamma": 3})
os.makedirs(TD, exist_ok=True)
yy, xx = np.mgrid[0:1024, 0:1024]
for i, (_, fid, f, t, *_r) in enumerate(fr):
    im = np.zeros((1448, 1448, 4), np.uint8)
    c = (1448 - 1024) // 2
    im[c:c + 1024, c:c + 1024, 3] = 255
    # each lap a little brighter, with a pattern that moves (the planet turning)
    v = 50 + 25 * (i // 4) + 40 * np.sin((xx + 60 * (i // 4)) / 90.0) * np.cos(yy / 120.0)
    im[c:c + 1024, c:c + 1024, :3] = np.clip(v, 0, 255).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": fid, "filter": f, "t": t, "offset": list(map(float, offs[i % 4])), "box": [-724, -724, 1448, 1448]},
              open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": {"blacks": {}, "white": 1, "gamma": 3}, "angle": 0, "footprint": [-1124, -1124, 1124, 1124],
           "fixed": True, "view": [2248, 2248], "k": 2048 / 2248, "colour": None, "grey": "CB2", "whole": False},
          open(d + "/" + om.PLAN_FILE, "w"))
om.unit_of = lambda fid: (u, [x[1] for x in fr].index(fid))
om.tiles_ahead = lambda *a, **k: None
om.tile = lambda u_, j, c, s=None: json.load(open(f"{TD}/{j}.json"))
ahead = om.rolling_ahead
om.rolling_ahead = lambda *a, **k: None

calls = []
compose = om._compose
om._compose = lambda window, k, **kw: calls.append(len(window)) or compose(window, k, **kw)


def pic(data):
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")).astype(np.float32)


# played in order: frame 0 drawn whole, every later frame grows by one tile (a two-frame compose)
grown, took = {}, []
for n in range(N):
    calls.clear()
    t0 = time.perf_counter()
    data, rep = om.rolling_webp(fr[n][1], 512, cache, 1)
    took.append(time.perf_counter() - t0)
    grown[n] = pic(data)
    if n >= 1:
        assert calls == [2], (n, calls)   # one tile composed over the picture before
print("grown: one tile's compose per frame; s per frame", [round(x, 2) for x in took])

# the same frames drawn whole (a fresh process's state: nothing to grow from) look the same
for n in (3, 7, 11, 15):   # whole laps (a whole picture of mixed laps pulls the laps to one level)
    om._rolled.clear()
    cache2 = tempfile.mkdtemp()
    import shutil
    shutil.copytree(d, om.folder(u, cache2), dirs_exist_ok=True)
    for sub in ("rolling-level", "filters-level"):
        shutil.rmtree(os.path.join(om.folder(u, cache2), sub), ignore_errors=True)
    calls.clear()
    whole = pic(om.rolling_webp(fr[n][1], 512, cache2, 1)[0])
    assert calls and calls[0] > 2 or n < 4, (n, calls)
    # where only one place's tile is (the middle of each quarter) the two are the same picture; where places
    # overlap, the grown one has each place's newest tile on top and the whole one blends them
    H, W = whole.shape[:2]
    for cy, cx in ((H // 4, W // 4), (H // 4, 3 * W // 4), (3 * H // 4, W // 4), (3 * H // 4, 3 * W // 4)):
        a, b = whole[cy - 30:cy + 30, cx - 30:cx + 30, :3], grown[n][cy - 30:cy + 30, cx - 30:cx + 30, :3]
        assert np.abs(a - b).mean() < 6, (n, cy, cx, np.abs(a - b).mean())
    diff = np.abs(whole[..., :3] - grown[n][..., :3])[whole[..., 3] > 200]
    print(n, "grown vs whole: places' middles the same; whole picture mean diff", round(float(diff.mean()), 2))

# made ahead: a window at frame 4 finds frames 5.. made by rolling_ahead
om._rolled.clear()
cache3 = tempfile.mkdtemp()
shutil.copytree(d, om.folder(u, cache3), dirs_exist_ok=True)
for sub in ("rolling-level", "filters-level"):
    shutil.rmtree(os.path.join(om.folder(u, cache3), sub), ignore_errors=True)
om.rolling_webp(fr[4][1], 512, cache3, 1)
ahead(u, 4, 512, cache3)
t0 = time.time()
while om._roll_ahead and time.time() - t0 < 120:
    time.sleep(0.2)
level = os.path.join(om.folder(u, cache3), "rolling-level", "512")
made = len([x for x in os.listdir(level) if x.endswith(".webp")])
print("made ahead:", made - 1, "pictures")
assert made - 1 >= min(om.ROLL_AHEAD, N - 5), made
calls.clear()
t0 = time.perf_counter()
om.rolling_webp(fr[9][1], 512, cache3, 1)
print("frame 9 after the ahead: composes", calls, round(time.perf_counter() - t0, 3), "s")
assert not calls
print("ok")
