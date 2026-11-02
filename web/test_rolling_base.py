"""Synthetic check of a mosaic movie's picture when its colour begins and between its laps (obs_mosaic.rolling_layout):

1. The picture never shrinks when a colour set completes. A 2 x 2 pass taken in its gray filter for two laps, then
   RED, GRN and BL1 at one place only: before, the picture fell to that one place (only the colour filters were drawn
   once a set existed); now the gray base stays under it everywhere a tile is, the colour where all three cover, and
   the name counts the base's tiles.
2. A place's copies stay on one level from lap to lap. Each copy is the same ground at another exposure; drawn as it
   came, a place flashed darker or brighter than its neighbours, lap after lap. Each copy is now brought to the copy it
   replaces (lap_gain), grown or drawn whole alike; a step bigger than LAP_BELIEVE (another scene) is left as it is.
3. A pass whose gray filter starts a lap after its other filters (or its polarized frames) keeps the places they
   showed (rolling_base).
Run: python web/test_rolling_base.py"""
import io
import json
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}
OFFS = [(-380, -380), (380, -380), (-380, 380), (380, 380)]
LEVEL = {"CL1/CL2": 160, "RED": 170, "GRN": 130, "BL1": 90}
yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)


def texture(q):
    """The same ground under every tile (fixed to the body), so overlaps agree."""
    gx, gy = xx - 512 + OFFS[q][0], yy - 512 + OFFS[q][1]
    return 0.75 + 0.2 * np.sin(gx / 37.0) * np.cos(gy / 53.0) + 0.05 * np.sin((gx + gy) / 11.0)


def make_pass(name, seq, colour, grey):
    """seq: (filter, place, exposure) per frame. A mosaic movie (kind mosaic_movie) of those frames."""
    cache = tempfile.mkdtemp()
    fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 20 * i, 600, -OFFS[q][0], -OFFS[q][1], 1e6) for i, (f, q, _) in enumerate(seq)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": fr[-1][3],
         "place": [q for _, q, _ in seq], "kind": "mosaic_movie", "repeats": 2}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, (f, q, e) in enumerate(seq):
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        # the exposure on linear brightness (the pass's display gamma), as a frame's level differs
        v = LEVEL[f] * texture(q) / 255
        im[..., :3] = np.clip(255 * (v ** 2.2 * e) ** (1 / 2.2), 0, 255).round().astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{td}/{i}.png")
        t = {"n": i, "id": fr[i][1], "filter": f, "t": fr[i][3], "offset": list(map(float, OFFS[q])), "box": [-512, -512, 1024, 1024]}
        json.dump(t, open(f"{td}/{i}.json", "w"))
    lum = [grey] + sorted({f for f, _, _ in seq} - {grey})
    plan = {"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
            "view": [1800, 1800], "k": 1024 / 1800, "colour": colour, "grey": grey, "whole": False,
            "luminance": {"filters": lum, "gains": {}}}
    json.dump(plan, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    return u, cache


def use(u):
    om.unit_of = lambda fid: (u, int(fid[1:11]) - 1500000000)


om.tiles_ahead = lambda *a, **k: None
om.rolling_ahead = lambda *a, **k: None


def pic(data):
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")).astype(np.float32)


def middles(a):
    H, W = a.shape[:2]
    return [a[cy - 25:cy + 25, cx - 25:cx + 25] for cy, cx in
            ((H // 4, W // 4), (H // 4, 3 * W // 4), (3 * H // 4, W // 4), (3 * H // 4, 3 * W // 4))]


# ---------- 1. the colour begins: the picture keeps its gray ----------
seq = [("CL1/CL2", q, 1.0) for q in range(4)] * 2 + [("RED", 0, 1.0), ("GRN", 0, 1.0), ("BL1", 0, 1.0)]
u, cache = make_pass("BASE", seq, ["RED", "GRN", "BL1"], "CL1/CL2")
use(u)
area, names = [], []
for n in range(len(seq)):
    data, rep = om.rolling_webp(u["frames"][n][1], 512, cache, 1, wait=True)
    a = pic(data)
    area.append(float((a[..., 3] > 128).mean()))
    names.append(om.rolling_layout(u, n, cache)[5])
    print(n, seq[n][0], "covered", round(area[-1], 3), "filters", rep["filter_names"], "base", rep["luminance"])
full = area[7]
assert full > 0.9, area
# the colour set completes at frame 10: the picture keeps all four places (it fell to one before)
assert min(area[8:]) > 0.97 * full, area
last = pic(om.rolling_webp(u["frames"][10][1], 512, cache, 1, wait=True)[0])
m = middles(last)
r, g, b = (float(m[0][..., c].mean()) for c in range(3))
assert r > g + 15 and g > b + 15, (r, g, b)            # place 0: the colour
for q in (1, 2, 3):                                       # the others: the gray base (tinted to the colour beside it)
    assert m[q][..., 3].min() > 250 and m[q][..., :3].mean() > 60, (q, m[q][..., 3].min(), m[q][..., :3].mean())
# frames 8 and 9 (RED, GRN: no set yet) draw the gray only: they share frame 7's picture
assert names[8] == names[9] == names[7], names
assert names[10] != names[9], names
print("colour begins: the picture keeps its", round(full, 3), "coverage, colour at its place, gray around it")

# the old rule, for the record: only the colour filters' tiles drawn once a set exists
made = om.rolling_layout(u, 10, cache)
p, tiles, rect, count, used, name = made
drawn = [t for t in tiles if t.get("drawn")]
assert len(drawn) > len([t for t in tiles if t["filter"] in used]), (len(drawn), used)
assert {t["n"] for t in drawn} == {4, 5, 6, 7, 8, 9, 10}, [t["n"] for t in drawn]

# ---------- 2. a place's copies on one level from lap to lap ----------
EXPO = [1.0, 1.0, 1.0, 1.0,     # lap 1
        1.0, 1.5, 1.0, 1.0,     # lap 2: place 1 brighter
        1.0, 0.7, 1.0, 1.0,     # lap 3: darker
        1.0, 1.4, 1.0, 1.0,     # lap 4: brighter again (an A-B-A swing each lap)
        1.0, 1.0, 1.0, 1.0]
seq = [("CL1/CL2", i % 4, e) for i, e in enumerate(EXPO)]
u, cache = make_pass("LEVEL", seq, None, "CL1/CL2")
use(u)
grown = {}
for n in range(len(seq)):
    grown[n] = pic(om.rolling_webp(u["frames"][n][1], 512, cache, 1, wait=True)[0])
gains = [om.lap_gain(u, om.plan(u, cache), cache, j, lambda i: om.tile(u, i, cache, SCALE)) for j in range(len(seq))]
print("lap gains of place 1:", gains[1::4])
for j in range(1, len(seq), 4):
    assert abs(gains[j] * EXPO[j] - 1) < 0.03, (j, gains[j], EXPO[j])
ref = float(middles(grown[3])[1][..., :3].mean())
swing = []
for n in range(3, len(seq)):
    v = float(middles(grown[n])[1][..., :3].mean())
    swing.append(round(v / ref, 3))
    assert abs(v / ref - 1) < 0.03, (n, v, ref)
print("place 1 over the laps (its level / lap 1's):", swing)
# without the lap gains, the swing this takes out
step = om._lap_step
om._lap_step = lambda *a: 1.0
u2, cache2 = make_pass("LEVEL0", seq, None, "CL1/CL2")
use(u2)
was = [round(float(middles(pic(om.rolling_webp(u2["frames"][n][1], 512, cache2, 1, wait=True)[0]))[1][..., :3].mean()) / ref, 3)
       for n in range(3, len(seq))]
om._lap_step = step
use(u)
print("... drawn as each copy came:", was)
assert max(was) > 1.12 and min(was) < 0.9, was
# drawn whole (nothing to grow from) it is the same picture
for n in (9, 13):
    om._rolled.clear()
    cache2 = tempfile.mkdtemp()
    shutil.copytree(om.folder(u, cache), om.folder(u, cache2), dirs_exist_ok=True)
    for sub in ("rolling-level", "filters-level"):
        shutil.rmtree(os.path.join(om.drawn(u, cache2), sub), ignore_errors=True)
    whole = pic(om.rolling_webp(u["frames"][n][1], 512, cache2, 1, wait=True)[0])
    for a, b in zip(middles(whole), middles(grown[n])):
        assert np.abs(a[..., :3] - b[..., :3]).mean() < 4, (n, np.abs(a[..., :3] - b[..., :3]).mean())
print("grown and whole alike")

# another scene (a step past LAP_BELIEVE) is left as it is
EXPO2 = [1.0] * 4 + [1.0, 0.2, 1.0, 1.0]
u, cache = make_pass("SCENE", [("CL1/CL2", i % 4, e) for i, e in enumerate(EXPO2)], None, "CL1/CL2")
use(u)
p = om.plan(u, cache)
assert om.lap_gain(u, p, cache, 5, lambda i: om.tile(u, i, cache, SCALE)) == 1.0
print("a change of scene keeps its own level")

# a short and a long exposure of each place in turn (SPOLEDYN001: 2.6-2.8 times apart): the place holds its level
EXPO3 = [1.0, 1.0, 1.0, 1.0] + [0.37, 0.37, 0.37, 0.37, 1.0, 1.0, 1.0, 1.0] * 2
u, cache = make_pass("PAIRS", [("CL1/CL2", i % 4, e) for i, e in enumerate(EXPO3)], None, "CL1/CL2")
use(u)
lv = [float(middles(pic(om.rolling_webp(u["frames"][n][1], 512, cache, 1, wait=True)[0]))[1][..., :3].mean()) for n in range(3, len(EXPO3))]
print("short and long exposures in turn, place 1:", [round(v) for v in lv])
assert max(lv) / min(lv) < 1.03, lv

# made_only: a copy whose earlier copies are not made yet is drawn on the level of those made, the picture is not
# the frame's own yet (skipped), and its name is not the one the frame's own picture will have
u, cache = make_pass("ONLY", seq, None, "CL1/CL2")
use(u)
whole = om.rolling_layout(u, 9, cache)[5]
om._passes.clear()
u.pop("_lap_step", None)
os.remove(os.path.join(om._tiles(u, cache, SCALE), "1.json"))
skipped = []
made = om.rolling_layout(u, 9, cache, made_only=True, skipped=skipped)
assert 1 in skipped and made[5] != whole, (skipped, made[5], whole)

# ---------- 3. the gray filter starts a lap after another: the places shown keep their picture ----------
# BL1 at every place first, then the clear filter (the pass's gray) lap after lap: when the first clear tile came in,
# the picture fell to it alone (the clear filter covers every place later in the pass, so BL1 was not in its base)
seq = [("BL1", q, 1.0) for q in range(4)] + [("CL1/CL2", q, 1.0) for q in range(4)] * 2
u, cache = make_pass("LATE", seq, None, "CL1/CL2")
use(u)
area = []
for n in range(len(seq)):
    a = pic(om.rolling_webp(u["frames"][n][1], 512, cache, 1, wait=True)[0])
    area.append(round(float((a[..., 3] > 128).mean()), 3))
print("gray filter late: covered", area)
assert all(area[n] >= 0.97 * area[n - 1] for n in range(1, len(area))), area
made = om.rolling_layout(u, 4, cache)
assert sorted(t["n"] for t in made[1] if t.get("base")) == [1, 2, 3, 4], [(t["n"], t.get("base")) for t in made[1]]
made = om.rolling_layout(u, 11, cache)
assert not any(t.get("base") for t in made[1]) and sorted(t["n"] for t in made[1] if t.get("drawn")) == [8, 9, 10, 11]

# polarized frames first (C23JU_PORTRAIT: P0/GRN and IRP0/CB3, which the base never draws), then BL1, the pass's gray:
# the places keep the polarized filter drawn so far (the most taken) until BL1 reaches them
LEVEL.update({"P0/GRN": 110, "IRP0/CB3": 70})
seq = [(f, q, 1.0) for q in range(4) for f in ("P0/GRN", "IRP0/CB3")] + [("BL1", q, 1.0) for q in range(4)] * 3
u, cache = make_pass("POLAR", seq, None, "BL1")
use(u)
area = []
for n in range(len(seq)):
    a = pic(om.rolling_webp(u["frames"][n][1], 512, cache, 1, wait=True)[0])
    area.append(round(float((a[..., 3] > 128).mean()), 3))
print("polarized frames first: covered", area)
assert all(area[n] >= 0.97 * area[n - 1] for n in range(1, len(area))), area
made = om.rolling_layout(u, 8, cache)
assert sorted((t["n"], t["filter"]) for t in made[1] if t.get("base")) == [(2, "P0/GRN"), (4, "P0/GRN"), (6, "P0/GRN"), (8, "BL1")], \
    [(t["n"], t["filter"], t.get("base")) for t in made[1]]
print("ok")
