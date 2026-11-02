"""PR12 (tile placement): a grey frame that lost lines in downlink (obs_mosaic._lossy, LOST_FILL) or was left out leaves no hole in
the luminance base where a frame of another of its filters covers that place (obs_mosaic.lum_fills). Titan
ISS_021TI_GLOBMAPNA001: CB3 N1519692683_2 lost a third of its lines, MT1 N1519692611_1 was taken at the same place a
minute before, and lum_frames left the MT1 frame out (a CB3 frame is at its place), so the picture had a black hole.
- lum_fills takes the other filter's frame only once every grey frame at its place is made, and only when all of them
  are partial or left out; a whole grey frame there keeps it out; the set only grows as the pass goes on
- the base draws a fill under every other tile (under_first): where the partial grey frame came down it shows the
  grey; where it lost lines, the fill
- lum_base: a pass drawn in its grey filter alone draws its base once it has a fill
Run: python web/test_lum_fills.py"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
SCALE = {"blacks": {}, "white": 1, "gamma": 3}
Z = 1e6
# place A (0, 0): MT1 then CB3, the CB3 frame's top 600 lines lost; place B (900, 0): CB3 then MT1, both whole;
# place C (1800, 0): CB3 alone
plan_ = [("MT1", 0.0, 120), ("CB3", 0.0, 200), ("CB3", 900.0, 200), ("MT1", 900.0, 120), ("CB3", 1800.0, 200)]
fr = [(f"x{i}", f"N{1519692000 + 60 * i}_1", f, 1000.0 + 60 * i, 900, -ox, 0.0, Z) for i, (f, ox, _) in enumerate(plan_)]
u = {"key": ("TITAN", "ISS_TEST_FILLS", "N", 0), "frames": fr, "z": Z, "movie": False, "mosaic": True, "last": 2000}
p = {"display_scale": SCALE, "k": 0.25, "colour": None, "grey": "CB3",
     "luminance": {"filters": ["CB3", "MT1"], "gains": {"MT1": 1.0}}}
TD = om._tiles(u, cache, SCALE)
os.makedirs(TD, exist_ok=True)
tiles = []
for i, (f, ox, level) in enumerate(plan_):
    im = np.zeros((1024, 1024, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = level
    t = {"n": i, "id": fr[i][1], "filter": f, "t": fr[i][3], "offset": [ox, 0.0], "box": [-512, -512, 1024, 1024]}
    if i == 1:
        im[:600, :, 3] = 0
        t["lost"] = 0.59
    Image.fromarray(im).save(f"{TD}/{i}.png")
    tiles.append(t)

assert om.partial(tiles[1]) and not om.partial(tiles[2])
assert om.lum_frames(u, p) == {1, 2, 4}, om.lum_frames(u, p)   # both MT1 frames have a CB3 frame at their place
grown = [om.lum_fills(u, p, tiles[:n + 1]) for n in range(len(tiles))]
print("fills as the pass grows:", grown)
assert grown[0] == set(), "the CB3 frame at place A is not made yet: undecided, so not in"
assert all(g == {0} for g in grown[1:]), "place A's only CB3 frame is partial: its MT1 frame fills in, from then on"
assert all(3 not in g for g in grown), "place B's CB3 frame is whole: its MT1 frame stays out"
# a grey frame left out (no place: 8LSB, saturated all over) counts as missing too
out = [dict(t) for t in tiles]
out[1].pop("offset"); out[1].pop("lost")
assert om.lum_fills(u, p, out) == {0}
# a frame that lost a third of its lines (Titan's CB3: not partial, under half lost) leaves a gap all the same
third = [dict(t) for t in tiles]
third[1]["lost"] = 0.3438
assert not om.partial(third[1]) and om.lum_fills(u, p, third) == {0}
# ... and the usual few lost lines at a frame's edge (0.4%) do not
edge = [dict(t) for t in tiles]
edge[1]["lost"] = 0.0039
assert om.lum_fills(u, p, edge) == set()
# a colour pass draws its base under a colour tile with lost lines (Dione 016DI's GRN N1507742100_3, 2.8%): the colour
# is only where every filter is, so the lost lines were a black strip; with every colour tile whole, no base
ct = [{k: v for k, v in t.items() if k != "lost"} for t in tiles[:4]]   # places A and B, both filters at each
assert not om.lum_base(u, p, ct, ["CB3", "MT1"])
ct[3] = dict(ct[3], lost=0.028)
assert om.lum_base(u, p, ct, ["CB3", "MT1"])
# the usual pass: every grey frame whole, nothing to work out
whole = [dict(t) for t in tiles]
whole[1].pop("lost")
assert om.lum_fills(u, p, whole) == set()

# drawn in the grey filter alone, the pass now draws its base, and the base has no hole at place A's lost top
assert om.lum_base(u, p, tiles, ["CB3"])
assert not om.lum_base(u, p, whole, ["CB3"])
mine = om._mine(u, p, tiles, om.LUM)
assert [t["n"] for t in mine] == [0, 1, 2, 4] and mine[0].get("fill") and not any(t.get("fill") for t in mine[1:])
assert [t["n"] for t in om.under_first(mine)] == [0, 1, 2, 4], "the fill lowest, then the partial frame, then the rest"
rect = (-512, -512, 1800 + 1024, 1024)
with calibration.looking("balanced"):
    rgba = om.filter_mosaic(u, p, om.LUM, tiles, rect, cache)
rgba = np.asarray(Image.open(io.BytesIO(rgba)).convert("RGBA")) if isinstance(rgba, bytes) else np.asarray(rgba)
at = lambda x, y: rgba[int((y - rect[1]) * 0.25), int((x - rect[0]) * 0.25)].astype(int)
lost, came = at(-200, -400), at(-200, 300)   # place A: inside the CB3 frame's lost top, and its part that came down
print(f"place A: lost top {lost.tolist()}, the part that came down {came.tolist()}")
# (the compose matches the tiles' levels where they overlap: the MT1 frame's 120 and the CB3 frame's 200 meet near 155)
assert lost[3] == 255 and lost[0] > 60, "the lost top is the MT1 frame's, not a hole"
assert came[3] == 255 and abs(int(came[0]) - int(lost[0])) < 30, "the two join without a step"
# before (the fill left out): the lost top was a hole
before = [t for t in mine if not t.get("fill")]
with calibration.looking("balanced"):
    old = om._compose(om._window(u, p, before, rect, cache)[0], 0.25, pin=None)
assert old[int((-400 - rect[1]) * 0.25), int((-200 - rect[0]) * 0.25), 3] == 0, "the form replaced left a hole there"
print("lum fills: ok")
