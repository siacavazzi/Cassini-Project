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

# Black movie frames (group D, 2026-10-29): a faint frame that lost lines in downlink (code 0, about -1 I/F once
# calibrated). The mean over SKY_SMOOTH pixels spread a ninth of a lost row onto the rows beside it, which the darker
# half of the sky took as grain, and the black went to ~0.11 I/F, over the whole frame (W1474409175_1, W1823078862_1,
# N1880461314_1 on the Mini). With the lost lines left out the frame's black is what it is without them
faint = {"blacks": {"CL1": 0.0010}, "sky_tops": {"CL1": 0.0012}, "toe": 0.0012, "white": 0.6, "gamma": 3.0}
dim = obs_mosaic.tile_scale(faint, "CL1", True)["black_of"]


def faint_frame(lost=(), scattered=0.0):
    iof = 0.0006 + rng.normal(0, 0.0002, (1024, 1024)).astype(np.float32)
    iof[300:700, 300:700] = 0.03       # a faint body (the frame's 99th percentile ~0.03, as W1823078862_1)
    for row in lost:
        iof[row:row + 8] = -1.0       # a lost run of rows, on the quarter-size grid's rows
    if scattered:
        iof[rng.random(iof.shape) < scattered] = -1.07   # and dead pixels across it (N1880461314_1: 1% at -1.07)
    return iof


clean = dim(faint_frame())
for name, f in (("lost rows", faint_frame((100, 512, 840))), ("dead pixels", faint_frame(scattered=0.02)),
                ("both", faint_frame((200,), 0.01))):
    got = dim(f)
    print(name, got and round(got["black"], 5), "clean", clean and round(clean["black"], 5))
    assert got is not None and abs(got["black"] - clean["black"]) < 0.0004, (name, got, clean)
    assert got["black"] < 0.03 / 4                                   # far under the body
# the old reading of the same frame (a box mean over the lost rows) put black over the body
q = faint_frame((100, 512, 840))[::4, ::4]
m = q < 0.05 * np.percentile(q, 99.9)
fine = obs_mosaic._sky_fine([q], [m])
assert np.percentile(fine, obs_mosaic.SKY_TOP_PCT) - np.median(fine) > 0.03

# never at or over the frame's lit median, whatever its sky: a pass whose sky band is tall and a frame that is dim
tall = obs_mosaic.tile_scale({**faint, "sky_tops": {"CL1": 0.03}}, "CL1", True)["black_of"]
assert tall(faint_frame()) is None
print("ok")
