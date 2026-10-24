"""Synthetic check of tile tuning (Cassini Studio's mosaic tab: obs_mosaic.parse_tune, tuned_layout): a moved
pointing's tiles move by the fraction of the picture asked and nothing else moves, a hidden pointing is left out,
the tuned mosaic is composed by so_far / mosaic.compose under a name of its own, and the untouched mosaic is the
same picture before and after. Run: python web/test_mosaic_tune.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om

cache = tempfile.mkdtemp()
offs = [(-380, -380), (380, -380), (-380, 380), (380, 380)]   # a 2 x 2 pass, the tiles overlapping a little
fr = [(f"p{i}", f"N{1500000000 + i}_1", "CB2", 1000.0 + 30 * i, 600, 0, 0, 1e6) for i in range(4)]
u = {"key": ("JUPITER", "TUNE", "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": 1120}
SCALE = {"blacks": {}, "white": 1, "gamma": 3}
TD = om._tiles(u, cache, SCALE)
os.makedirs(TD, exist_ok=True)
for i in range(4):
    im = np.zeros((1024, 1024, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = 60
    im[462:562, 462:562, :3] = 250          # each tile's marker in its middle
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": fr[i][1], "filter": "CB2", "t": fr[i][3], "offset": list(map(float, offs[i])), "box": [-512, -512, 1024, 1024]},
              open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
           "view": [1800, 1800], "k": 1024 / 1800, "colour": None, "grey": "CB2", "whole": False},
          open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
om.tile = lambda u_, j, c, s=None: json.load(open(f"{TD}/{j}.json"))
mapped = {"pointings": [{"n": i + 1, "tiles": [i]} for i in range(4)]}

def marker(im, near):
    """Middle of the bright marker nearest near (x, y), in picture pixels."""
    a = np.asarray(im.convert("L")).astype(float)
    ys, xs = np.nonzero(a > 200)
    d = (xs - near[0]) ** 2 + (ys - near[1]) ** 2
    keep = d < 120 ** 2
    return xs[keep].mean(), ys[keep].mean()

made = om.layout(u, 3, cache)
plain, _ = om.so_far(u, 3, cache, made)
W, H = plain.size
centres = [((x + 900) / 1800 * W, (y + 900) / 1800 * H) for x, y in offs]
before = [marker(plain, c) for c in centres]

# move pointing 2 right by 5% of the picture and down by 2%
moves, gone = om.parse_tune("2:0.05:0.02", "")
tuned = om.tuned_layout(made, mapped, moves, gone)
assert tuned[5] != made[5] and "-tune" in tuned[5], tuned[5]
im, rep = om.so_far(u, 3, cache, tuned)
after = [marker(im, (c[0] + (0.05 * W if i == 1 else 0), c[1] + (0.02 * H if i == 1 else 0))) for i, c in enumerate(centres)]
dx, dy = after[1][0] - before[1][0], after[1][1] - before[1][1]
print("pointing 2 moved", round(dx, 1), round(dy, 1), "px; asked", round(0.05 * W, 1), round(0.02 * H, 1))
assert abs(dx - 0.05 * W) < 2 and abs(dy - 0.02 * H) < 2
for i in (0, 2, 3):
    assert abs(after[i][0] - before[i][0]) < 1 and abs(after[i][1] - before[i][1]) < 1, (i, before[i], after[i])

# hide pointing 4: its corner of the picture is empty
moves, gone = om.parse_tune("", "4")
hid, _ = om.so_far(u, 3, cache, om.tuned_layout(made, mapped, moves, gone))
a = np.asarray(hid)[..., 3]
assert a[int(H * 0.95), int(W * 0.95)] == 0 and np.asarray(plain)[..., 3][int(H * 0.95), int(W * 0.95)] > 0
print("pointing 4 hidden")

# nothing to change: the layout itself; bad requests are refused; the plain mosaic is unchanged
assert om.tuned_layout(made, mapped, {}, set()) is made
assert om.tuned_layout(made, mapped, {2: (0.0, 0.0)}, set()) is made
for bad in ["2:x:1", "2:1", "2:nan:0"]:
    try:
        om.parse_tune(bad, ""); raise SystemExit(f"accepted {bad}")
    except ValueError:
        pass
again, _ = om.so_far(u, 3, cache, om.layout(u, 3, cache))
assert np.array_equal(np.asarray(again), np.asarray(plain))
print("untouched mosaic the same; ok")
