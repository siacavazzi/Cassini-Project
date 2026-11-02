"""A pass's mosaic draws a tile far darker than the picture before it under that picture (obs_mosaic.dim_under,
dim_places): the same ground seen again from far round the body, past the terminator (Dione 221DI's last 20 tiles,
4 to 20 times darker on their overlaps, were drawn over the lit disk as a dark column). A tile a little darker (an
exposure error the seams even out) stays over it, a tile overlapping nothing stays, and every filter of a colour set
at one pointing takes the grey filter's decision. Synthetic tiles on a strip.
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


# (n, filter, x offset, linear brightness): lit tiles, one 15% darker (stays), one 8 times darker (goes under),
# one beside nothing (stays), and the dark tile's colour filters at its pointing
plan = [(0, "CL1/CL2", 0, 0.5), (1, "CL1/CL2", 250, 0.43), (2, "CL1/CL2", 120, 0.06), (3, "CL1/CL2", 3000, 0.05),
        (4, "GRN", 0, 0.55), (5, "GRN", 120, 0.07), (6, "GRN", 250, 0.5)]
tiles = [{"n": n, "filter": f, "t": 10.0 * n, "offset": [float(x), 0.0], "box": [-200, -200, 400, 400], "pic": pic(f"t{n}", v)}
         for n, f, x, v in plan]
grey = [t for t in tiles if t["filter"] == "CL1/CL2"]
low = om.dim_under(u, p, "CL1/CL2", grey, cache)
print("under:", low)
assert set(low) == {2}, low
assert low[2] < 0.2, low
# measured once and kept: asked again (one more tile), the same answer from the folder
again = om.dim_under(u, p, "CL1/CL2", grey, cache)
assert again == low, again
# the colour filter at the dark tile's pointing goes under with it, whatever its own overlaps say
green = [t for t in tiles if t["filter"] == "GRN"]
assert om.dim_places(u, p, "GRN", green, tiles, cache) == {5}
# and the mosaic's drawing order puts it first (under every whole tile), as a partial frame
order = [t["n"] for t in om.under_first([dict(t, under=True) if t["n"] == 2 else t for t in grey])]
assert order == [2, 0, 1, 3], order
print("ok")
