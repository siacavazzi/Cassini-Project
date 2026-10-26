"""Red cast follow-up: a movie frame's black (obs_mosaic.tile_scale black_of) sits at least the frame's own sky grain
over its sky, not only the pass's typical height, so a stray-lit frame's grain (Jupiter approach WAC movie, frames
4-13: red and green) stays under black. A quiet frame keeps the pass's height. Run: python web/test_movie_sky_grain.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402

rng = np.random.default_rng(5)
scale = {"blacks": {"RED": 0.0014}, "sky_tops": {"RED": 0.0019}, "toe": 0.0027, "white": 0.67, "gamma": 3.0}


def frame(level, grain):
    iof = level + rng.normal(0, grain, (1024, 1024)).astype(np.float32)
    iof[400:600, 400:600] = 0.3        # the body, so the sky threshold has something bright to sit under
    return iof


black_of = obs_mosaic.tile_scale(scale, "RED", True)["black_of"]
quiet = black_of(frame(0.0027, 0.0003))
grainy = black_of(frame(0.0027, 0.0012))
print("quiet", quiet and round(quiet["black"], 5), "grainy", grainy and round(grainy["black"], 5))
assert abs(quiet["black"] - (0.0027 + 0.0019)) < 0.0003           # the pass's height when the frame's grain is lower
q = frame(0.0027, 0.0012)[::4, ::4]
sky = q[q < 0.05 * np.percentile(q, 99.9)]
assert grainy["black"] > 0.0027 + 0.0019 + 0.0005                  # raised to the frame's own grain
assert np.mean(sky > grainy["black"]) < 0.02                         # so its sky grain stays under black
# never lowered: a dark frame's own sky keeps the pass's black
assert black_of(frame(-0.001, 0.0003)) is None
print("ok")
