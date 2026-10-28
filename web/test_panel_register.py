"""Synthetic check of panel registration (obs_mosaic.panel_places): a 2x2 mosaic of one textured surface whose
pointings SPICE put a few pixels off, each differently, is moved back into line (to the first pointing, within a
fraction of a pixel), a second filter at a pointing moves with it, a featureless overlap or a pointing that overlaps
nothing keeps SPICE's place, the moves are kept with the pass and never change for later tiles, the layout's name
says its tiles moved, and Settings > Processing's panels step off gives SPICE's places and the plain name.
Run: python web/test_panel_register.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import cv2
from PIL import Image
import calibration as cal
import obs_mosaic as om

rng = np.random.default_rng(3)
S = 2600
# a cratered surface: smooth light, craters of many sizes, fine grain
surface = cv2.GaussianBlur(rng.random((S, S)).astype(np.float32), (0, 0), 40) * 400
yy, xx = np.mgrid[0:S, 0:S]
for _ in range(500):
    cx, cy, r = int(rng.integers(100, S - 100)), int(rng.integers(100, S - 100)), int(rng.integers(4, 30))
    sl = np.s_[cy - 2 * r:cy + 2 * r, cx - 2 * r:cx + 2 * r]
    d = np.hypot(xx[sl] - cx, yy[sl] - cy)
    surface[sl] += np.where(d < r, -30, np.where(d < 1.3 * r, 25, 0))
surface += cv2.GaussianBlur(rng.random((S, S)).astype(np.float32), (0, 0), 1.2) * 60
surface = np.clip((surface - surface.min()) / np.ptp(surface) * 200 + 15, 0, 255)

T = 1024
true = [(-400, -400), (400, -400), (-400, 400), (400, 400)]
err = [(0.0, 0.0), (6.3, -2.6), (-4.4, 5.2), (3.1, 7.7)]   # SPICE's error, reference pixels
gain = [1.0, 1.2, 0.8, 1.1]                                # each pointing's exposure differs too
# tiles: the 4 pointings in CB2, then a second filter at pointing 1 (C8 registered it onto tile 1, where SPICE put it)
plan_ = [(0, "CB2"), (1, "CB2"), (2, "CB2"), (3, "CB2"), (1, "MT2")]


def tiles_in(cache, pictures=True):
    td = om._tiles(u, cache, scale)
    os.makedirs(td, exist_ok=True)
    if pictures:
        for i, (q, f) in enumerate(plan_):
            cx, cy = S // 2 + true[q][0], S // 2 + true[q][1]
            v = surface[cy - T // 2:cy + T // 2, cx - T // 2:cx + T // 2] * gain[q]
            im = np.zeros((T, T, 4), np.uint8)
            im[..., :3] = np.clip(v, 0, 255).astype(np.uint8)[..., None]
            im[..., 3] = 255
            Image.fromarray(im).save(f"{td}/{i}.png")
    json.dump(p, open(os.path.join(om.folder(u, cache), om.PLAN_FILE), "w"))
    return td


fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 40 * i, 600, -true[q][0], -true[q][1], 1e6) for i, (q, f) in enumerate(plan_)]
u = {"key": ("RHEA", "OBS", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1000 + 40 * len(fr), "kind": "mosaic"}
scale = {"blacks": {}, "white": 1, "gamma": 3}
p = {"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-1000, -1000, 1000, 1000], "fixed": True,
     "view": [2000, 2000], "k": 2048 / 2000, "colour": None, "grey": "CB2", "whole": False, "luminance": None}
reports = [{"n": i, "id": fr[i][1], "filter": f, "t": fr[i][3], "offset": [true[q][0] + err[q][0], true[q][1] + err[q][1]],
            "box": [-T / 2, -T / 2, T, T]} for i, (q, f) in enumerate(plan_)]
om.tile = lambda u_, j, c, s=None: reports[j]

cache = tempfile.mkdtemp()
TD = tiles_in(cache)
report = {}
moved = om.panel_places(u, cache, p, reports, report=report)
for i, (q, f) in enumerate(plan_):
    want = (err[0][0] - err[q][0], err[0][1] - err[q][1])
    got = moved.get(i, [0, 0])
    print(i, f, "want", want, "got", got, report.get(i, {}).get("matches"))
    assert abs(got[0] - want[0]) < 0.35 and abs(got[1] - want[1]) < 0.35, (i, want, got)
assert 0 not in moved
assert moved[4] == moved[1], "the second filter moves with its pointing"

# kept with the pass: read back, the same, and the moves do not change when asked for with fewer tiles
kept = json.load(open(os.path.join(om.folder(u, cache), om.PANEL_FILE)))
assert set(kept) == {"0", "1", "2", "3", "4"}, kept
again = om.panel_places(u, cache, p, reports[:3])
assert all(again[n] == moved[n] for n in again), (again, moved)

# the order a pass is asked in does not matter: tiles 0..2 first, then all
cache2 = tempfile.mkdtemp()
tiles_in(cache2)
om.panel_places(u, cache2, p, reports[:3])
assert om.panel_places(u, cache2, p, reports) == moved

# the panels step off: SPICE's places, and the cache names of frames and tiles stay as they are
with cal.stepping("panels"):
    assert om.panel_places(u, cache, p, reports) == {}
    assert cal.variant() == ""
with cal.stepping("align"):
    assert om.panel_places(u, cache, p, reports) == {}

# featureless overlaps (flat grey) keep SPICE's place
cache3 = tempfile.mkdtemp()
TD3 = tiles_in(cache3, pictures=False)
for i in range(5):
    im = np.full((T, T, 4), 120, np.uint8)
    im[..., 3] = 255
    Image.fromarray(im).save(f"{TD3}/{i}.png")
assert om.panel_places(u, cache3, p, reports) == {}

# a pointing that overlaps nothing keeps SPICE's place
far = [dict(r) for r in reports]
far[3] = dict(far[3], offset=[5000, 5000])
cache4 = tempfile.mkdtemp()
tiles_in(cache4)
assert 3 not in om.panel_places(u, cache4, p, far)

# a match much further than SPICE is ever off is not believed
big = [dict(r) for r in reports]
big[2] = dict(big[2], offset=[true[2][0] + 90, true[2][1] - 80])
cache5 = tempfile.mkdtemp()
tiles_in(cache5)
r5 = {}
m5 = om.panel_places(u, cache5, p, big, report=r5)
assert 2 not in m5, (m5, r5)

# the layout moves the tiles and names itself for it; with the step off it is SPICE's, under the plain name
made = om.layout(u, 4, cache)
assert made[5].endswith(om.PANEL_TAG), made[5]
t1 = [t for t in made[1] if t["n"] == 1][0]
assert abs(t1["offset"][0] - true[1][0]) < 0.4 and abs(t1["offset"][1] - true[1][1]) < 0.4, t1
with cal.stepping("panels"):
    plain = om.layout(u, 4, cache)
assert plain[5] == made[5][:-len(om.PANEL_TAG)], (plain[5], made[5])
assert [t for t in plain[1] if t["n"] == 1][0]["offset"] == reports[1]["offset"]
print("panel registration: ok")
