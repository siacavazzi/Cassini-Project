"""A tile that SPICE (or filter registration, or a person's tuning) puts wholly or partly past the edge of a pass's
view: the grown mosaic (past obs_mosaic.GROW_FROM tiles, _grown / _over) draws what of it is on the canvas and
skips the rest, instead of failing with "could not broadcast input array" (four passes of the 2026-10-26 pre-build,
e.g. SATURN ISS_033RI_LPHRDFMOV001_PRIME N 0). Tiles inside the view come out as before.
Run: python web/test_tile_off_canvas.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

SCALE = {"blacks": {}, "white": 1, "gamma": 3}
N = om.GROW_FROM + 6


def make(name, offs):
    cache = tempfile.mkdtemp()
    fr = [(f"p{i}", f"N{1500000000 + i}_1", "CL1/CL2", 1000.0 + 20 * i, 600, 0.0, 0.0, 1e6) for i in range(len(offs))]
    u = {"key": ("SATURN", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": fr[-1][3]}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, o in enumerate(offs):
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = 60 + 7 * i
        Image.fromarray(im).save(f"{td}/{i}.png")
        json.dump({"n": i, "id": fr[i][1], "filter": "CL1/CL2", "t": fr[i][3], "offset": [float(o[0]), float(o[1])],
                   "box": [-512, -512, 1024, 1024]}, open(f"{td}/{i}.json", "w"))
    json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-2000, -2000, 2000, 2000],
               "fixed": True, "view": [4000, 4000], "k": 1024 / 4000, "colour": None, "grey": "CL1/CL2", "whole": False,
               "luminance": {"filters": ["CL1/CL2"], "gains": {}}}, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    return u, cache


# a raster inside the view, then tiles hanging off each edge and one wholly past the bottom (inside the soft edge's
# margin, which is what failed: the margin overlaps the canvas, the tile itself does not)
inside = [(-1400 + 400 * (i % 8), -1400 + 400 * (i // 8)) for i in range(N - 4)]
off = [(2000 + 512 + 40, 0), (0, -2000 - 512 - 30), (-2000 - 300, 900), (0, 2000 + 512 + 20)]
u, cache = make("OFF", inside + off)
im, rep = om.so_far(u, N - 1, cache)
a = np.asarray(im)
print("drew", rep["mosaic"], "tiles,", a.shape)
# the tile half off the left edge is drawn where it is on the canvas
h, w = a.shape[:2]
assert a[int((900 + 2000) / 4000 * h), 2, 3] == 255

# tiles inside the view: the same picture as a pass of those tiles alone, at every grown step
u2, cache2 = make("IN", inside)
for n in range(om.GROW_FROM, len(inside)):
    a1 = np.asarray(om.so_far(u, n, cache)[0])
    a2 = np.asarray(om.so_far(u2, n, cache2)[0])
    assert np.array_equal(a1, a2), n
print("inside tiles unchanged; ok")
