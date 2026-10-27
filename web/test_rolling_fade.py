"""Synthetic check of a mosaic movie whose older tiles fade (obs_mosaic.rolling_layout fade=, Settings > Movie >
Older tiles fade over): the newest place is as bright as the time-lapse's, older places dim with their age down to
the persistence floor and stay there, the picture never empties between laps, it still grows a tile a frame from
the last one (_roll), the time-lapse's own pictures keep their names, and rolling_ahead makes the faded pictures
ahead. Run: python web/test_rolling_fade.py"""
import os, sys, json, tempfile, io, time, shutil
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
for i, (_, fid, f, t, *_r) in enumerate(fr):
    im = np.zeros((1448, 1448, 4), np.uint8)
    c = (1448 - 1024) // 2
    im[c:c + 1024, c:c + 1024, 3] = 255
    im[c:c + 1024, c:c + 1024, :3] = 200   # every tile the same flat gray, so brightness is the fade alone
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


def middles(a):
    H, W = a.shape[:2]
    return [float(a[cy - 20:cy + 20, cx - 20:cx + 20, :3].mean()) for cy, cx in
            ((H // 4, W // 4), (H // 4, 3 * W // 4), (3 * H // 4, W // 4), (3 * H // 4, 3 * W // 4))]


FADE = (2, 30)   # older tiles fade over 2 frames to 30%
assert om.fade_style(0, 50) == (0, 0) and om.fade_style(999, 150) == (om.FADE_MAX, 100)
assert om._fade_weight(0, FADE) == 1 and abs(om._fade_weight(1, FADE) - 0.65) < 1e-9 and om._fade_weight(3, FADE) == 0.3

plain = {}
for n in range(N):
    plain[n] = middles(pic(om.rolling_webp(fr[n][1], 512, cache, 1)[0]))
for n in range(N):
    calls.clear()
    data, rep = om.rolling_webp(fr[n][1], 512, cache, 1, fade=FADE)
    a = pic(data)
    assert rep["fade"] == list(FADE), rep
    if n >= 1:
        assert calls in ([], [2]), (n, calls)   # still grown a tile at a time (or the time-lapse's filter mosaic reused)
    got = middles(a)
    for place in range(min(4, n + 1)):
        newest = max(j for j in range(n + 1) if j % 4 == place)
        want = plain[n][place] * om._fade_weight(n - newest, FADE)
        assert abs(got[place] - want) < 4, (n, place, got, want)
    if n >= 3:
        assert min(got) > 0.25 * max(got), (n, got)   # never empties: the oldest place keeps the floor
    print(n, "middles", [round(x) for x in got])

names = os.listdir(os.path.join(om.drawn(u, cache), "rolling-level", "512"))
assert any(x.startswith("lap-1-f2p30-") for x in names) and any(x.startswith("lap-1-") and "-f" not in x[6:9] for x in names), names
print("time-lapse names unchanged, faded pictures named lap-1-f2p30-...")

# made ahead with the fade
om._rolled.clear()
cache3 = tempfile.mkdtemp()
shutil.copytree(d, om.folder(u, cache3), dirs_exist_ok=True)
for sub in ("rolling-level", "filters-level"):
    shutil.rmtree(os.path.join(om.drawn(u, cache3), sub), ignore_errors=True)
om.rolling_webp(fr[4][1], 512, cache3, 1, fade=FADE)
ahead(u, 4, 512, cache3, fade=FADE)
t0 = time.time()
while om._roll_ahead and time.time() - t0 < 120:
    time.sleep(0.2)
level = os.path.join(om.drawn(u, cache3), "rolling-level", "512")
made = [x for x in os.listdir(level) if x.endswith(".webp")]
assert all("-f2p30-" in x for x in made) and len(made) - 1 >= min(om.ROLL_AHEAD, N - 5), made
calls.clear()
om.rolling_webp(fr[9][1], 512, cache3, 1, fade=FADE)
assert not calls
print("made ahead:", len(made) - 1, "faded pictures; ok")
