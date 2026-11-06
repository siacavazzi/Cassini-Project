"""A movie frame the body fills (no dark sky, on the body's disk, no small body: 191SA FEATRAK001's Saturn frames) in a
pass that measures its frames' own skies keeps the pass's black. The #279 merge lost the guard for no small body, and
obs_mosaic.tile_scale's black_of raised TypeError on such frames (_disk_mask(*None)): 75 of that movie's 120 tiles
failed and the frames answered 404. Synthetic I/F. Run: python web/test_black_of_body.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(3)
N = 1024
yy, xx = np.mgrid[:N, :N].astype(np.float32)
# Saturn's clouds over the whole frame: banded, lit everywhere, nothing near black
body = (0.02 + 0.004 * np.sin(yy / 37.0) + 0.002 * np.cos(xx / 53.0) + rng.normal(0, 2e-4, (N, N))).astype(np.float32)
for top, on_body in ((0.03, True), (0.03, False), (None, True)):
    scale = {"blacks": {"CB3": 1.0e-3}, "white": 0.05, "gamma": 2.2}
    if top is not None:
        scale["sky_tops"] = {"CB3": top}
    black_of = om.tile_scale(scale, "CB3", True, None, None, on_body).get("black_of")
    got = black_of(body) if black_of else None
    assert got is None, (top, on_body, got)
print("a frame the body fills, with no small body, keeps the pass's black (no TypeError); ok")
