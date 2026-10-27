"""Synthetic check that a colour movie frame (obs_mosaic.movie_frame) is mixed as the pass's mosaic is
(colour_picture: the natural color mix on the pass's balance), not its three bands stacked raw on the grey scale,
and from the camera windows' filter sets (colour_sets). Run: python web/test_movie_colour.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 2.0, "BL1": 3.0}}
fr = [(f"p{i}", f"W{1500000000 + i}_1", ["RED", "GRN", "BL1"][i % 3], 1000.0 + 60 * i, 600, 0, 0, 1e6) for i in range(6)]
u = {"key": ("JUPITER", "OBS", "W", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False, "last": 1400}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for i, (_, fid, f, t, *_r) in enumerate(fr):
    im = np.zeros((1448, 1448, 4), np.uint8)
    im[..., 3] = 255
    im[400:1000, 400:1000, :3] = {"RED": 150, "GRN": 110, "BL1": 70}[f]    # a red body, as the grey scale shows it
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": fid, "filter": f, "t": t, "offset": [0.0, 0.0], "box": [-724, -724, 1448, 1448]}, open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-724, -724, 724, 724], "fixed": True,
           "view": [1448, 1448], "k": 1, "colour": ["RED", "GRN", "BL1"], "grey": "RED", "whole": False},
          open(os.path.join(d, om.PLAN_FILE), "w"))
om.movie_footprint = lambda u, cache, p=None: [-724, -724, 724, 724]
with calibration.looking("balanced"):
    im, rep = om.movie_frame(u, 5, cache, centre=False)
    assert rep.get("color") == ["RED", "GRN", "BL1"], rep
    mid = lambda a: a[a.shape[0] // 3:2 * a.shape[0] // 3, a.shape[1] // 3:2 * a.shape[1] // 3, :3].reshape(-1, 3).astype(float).mean(axis=0)
    got = mid(np.asarray(im))
    p = om.plan(u, cache)
    rect = om.movie_rect(om.movie_footprint(u, cache, p), om.tile(u, 5, cache, scale))
    k = om.OUT / max(rect[2], rect[3])
    W, H = max(1, int(np.ceil(rect[2] * k))), max(1, int(np.ceil(rect[3] * k)))
    planes = [om._place(u, om.tile(u, j, cache, scale), rect, k, W, H, cache, scale) for j in (3, 4, 5)]
    want = mid(om.colour_picture(u, p, ["RED", "GRN", "BL1"], planes))
    raw = mid(np.dstack([a[..., 0] for a in planes]))
    print("movie", got.round(1), "mosaic mix", want.round(1), "raw bands", raw.round(1))
    assert np.allclose(got, want, atol=1), (got, want)
    assert not np.allclose(got, raw, atol=5), (got, raw)    # mixed, not the bands stacked as they are
# B115's cycle (VIO, GRN, CB2, CB3, RED, then a move to the next raster place): the sets are the windows' sets, so a
# frame never mixes one place's RED with the next place's VIO and GRN
b115 = [("", "", f, t) for f, t in [("VIO", 408), ("GRN", 456), ("CB2", 510), ("CB3", 564), ("RED", 621),
                                    ("VIO", 828), ("GRN", 876), ("CB2", 930)]]
assert [[j for _, j in s] for s in om.colour_sets(b115)] == [[0, 1, 2, 3, 4], [5, 6, 7]]
assert [[j for _, j in s] for s in om.colour_sets(b115[:3] + [("", "", "CL1/CL2", 520)] + b115[3:5])] == [[0, 1, 2], [4, 5]]
print("ok")
