"""A pass's mosaic draws a tile far darker than the picture before it under that picture (obs_mosaic.dim_under,
dim_places): the same ground seen again from far round the body, past the terminator (Dione 221DI's last 20 tiles,
4 to 20 times darker on their overlaps, were drawn over the lit disk as a dark column). A tile a little darker (an
exposure error the seams even out) stays over it, a tile overlapping nothing stays, and every filter of a colour set
at one pointing takes the decision of the pointing's first tile, which never changes as later tiles come in (decided
on the grey tile, taken last, Dione 221DI's colour tiles were first drawn over the disk and the grown mosaic kept them
there). Synthetic tiles on a strip.
Run: python web/test_dim_under.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2}
p = {"display_scale": scale, "grey": "CL1/CL2"}
u = {"key": ("DIONE", "ISS_TEST_DIM", "N", 0), "frames": [], "z": 1e6, "movie": False, "mosaic": True}
os.makedirs(om.folder(u, cache), exist_ok=True)
rng = np.random.default_rng(3)


def pic(name, linear):
    """A 400 px tile of textured ground at this linear brightness, as the pass's scale draws it."""
    v = np.clip(linear * (1 + 0.2 * rng.standard_normal((400, 400))), 0, 1)
    im = np.zeros((400, 400, 4), np.uint8)
    im[..., :3] = (calibration.encode(v, 2.2) * 255 + 0.5).astype(np.uint8)[..., None]
    im[..., 3] = 255
    path = os.path.join(cache, name + ".png")
    Image.fromarray(im).save(path)
    return path


# (n, filter, x offset, linear brightness, time): pointings 1000 s apart, a grey and a colour tile at each, 10 s
# apart (_register_to puts the second on the first): lit ones, one 15% darker (stays), one 8 times darker (goes under),
# one beside nothing (stays); then a dark pointing whose colour tile is taken first (9 GRN, then 10 CL), as on Dione
# 221DI
plan = [(0, "CL1/CL2", 0, 0.5, 0), (1, "GRN", 0, 0.55, 10), (2, "CL1/CL2", 250, 0.43, 1000), (3, "GRN", 250, 0.5, 1010),
        (4, "CL1/CL2", 120, 0.06, 2000), (5, "GRN", 120, 0.07, 2010), (6, "CL1/CL2", 3000, 0.05, 3000),
        (7, "GRN", 3000, 0.05, 3010), (8, "CL1/CL2", 500, 0.5, 4000), (9, "GRN", 620, 0.05, 5000),
        (10, "CL1/CL2", 620, 0.04, 5010)]
tiles = [{"n": n, "filter": f, "t": float(s), "offset": [float(x), 0.0], "box": [-200, -200, 400, 400], "pic": pic(f"t{n}", v)}
         for n, f, x, v, s in plan]
# the frames as the pass holds them (_register_to: name, id, filter, time, -, place x, y, distance)
u["frames"] = [(f"N{n}", n, f, float(s), None, float(x), 0.0, u["z"]) for n, f, x, v, s in plan]
grey = [t for t in tiles if t["filter"] == "CL1/CL2"]
low = om.dim_under(u, p, "CL1/CL2", grey, cache)
print("under:", low)
assert set(low) == {4, 10}, low
assert low[4] < 0.2, low
# measured once and kept: asked again, the same answer from the folder
again = om.dim_under(u, p, "CL1/CL2", grey, cache)
assert again == low, again
# the colour filter at the dark tile's pointing goes under with it, whatever its own overlaps say; at the pointing
# whose colour tile came first, the grey tile takes the colour tile's decision
green = [t for t in tiles if t["filter"] == "GRN"]
greens = om.dim_places(u, p, "GRN", green, tiles, cache)
print("green under:", greens)
assert greens == {5, 9}, greens
assert om.dim_places(u, p, "CL1/CL2", grey, tiles, cache) == {4, 10}
# decided once: as the tiles come in one at a time, no tile's decision changes once it is drawn
for f in ("GRN", "CL1/CL2"):
    seen = {}
    for m in range(1, len(tiles) + 1):
        so_far = tiles[:m]
        now = om.dim_places(u, p, f, [t for t in so_far if t["filter"] == f], so_far, cache)
        for t in so_far:
            if t["filter"] == f:
                assert seen.setdefault(t["n"], t["n"] in now) == (t["n"] in now), (f, t["n"], m)
# and the mosaic's drawing order puts it first (under every whole tile), as a partial frame
order = [t["n"] for t in om.under_first([dict(t, under=True) if t["n"] == 4 else t for t in grey])]
assert order == [4, 0, 2, 6, 8, 10], order

# a colour picture's tiles take the decision of their pointing's first colour tile (among), not of a filter it does
# not draw: a black VIO frame first at a pointing (195RI HIPHASEC001) put the lit colour tiles after it under too
u2 = {"key": ("SATURN", "ISS_TEST_DIM_AMONG", "W", 0), "frames": [], "z": 1e6, "movie": False, "mosaic": True}
os.makedirs(om.folder(u2, cache), exist_ok=True)
plan2 = [(0, "VIO", 0, 0.5, 0), (1, "GRN", 0, 0.5, 10), (2, "VIO", 250, 0.0005, 1000), (3, "GRN", 250, 0.5, 1010)]
tiles2 = [{"n": n, "filter": f, "t": float(s_), "offset": [float(x), 0.0], "box": [-200, -200, 400, 400], "pic": pic(f"a{n}", v)}
          for n, f, x, v, s_ in plan2]
u2["frames"] = [(f"W{n}", n, f, float(s_), None, float(x), 0.0, u2["z"]) for n, f, x, v, s_ in plan2]
g2 = [t for t in tiles2 if t["filter"] == "GRN"]
assert om.dim_places(u2, p, "GRN", g2, tiles2, cache) == {3}, "without among: the VIO root decides (as before)"
assert om.dim_places(u2, p, "GRN", g2, tiles2, cache, ["GRN"]) == set(), "the lit colour tile stays over"
assert om.dim_places(u2, p, "VIO", [t for t in tiles2 if t["filter"] == "VIO"], tiles2, cache) == {2}
print("ok")
