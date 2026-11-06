"""Spot check 8 (2026-11-06): movie frames whose sky is stored in whole codes, and faint long-exposure runs.
1. obs_mosaic.tile_scale black_of: a sky in whole codes (an 8-bit frame: blocks a code apart, pixel steps mostly 0)
   gets the sky median as its level and its 98th percentile as its least height, so its upper half no longer draws
   as a veil (089MI GRN, Atlas RED). A sky of pixel noise (the near miss) keeps the rule it had.
2. obs_mosaic._long_white: a run of frames exposed 10x longer than the frame setting the white, off the disk and
   faint, takes its own white (155EN jets); a single-exposure pass, a run with a frame on the disk, or a bright run
   does not. tile_scale gives that white only to frames in such a run.
Run: python web/test_movie_sky_codes.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402

rng = np.random.default_rng(8)
CODE = 0.0004   # I/F of one stored code


def body(iof):
    iof[400:600, 400:600] = 0.3
    return iof


def coded_sky():
    # 32 px blocks at the bias (a third) or a code above it (as 089MI's GRN sky: 20th percentile a code under its
    # median), no pixel noise: steps between neighbours mostly 0
    blocks = (rng.random((32, 32)) > 0.33).astype(np.float32) * CODE
    return body(np.kron(blocks, np.ones((32, 32), np.float32)) + 0.001)


def noisy_sky():
    return body((0.001 + rng.normal(0, CODE / 2, (1024, 1024))).astype(np.float32))


scale = {"blacks": {"GRN": 0.0}, "sky_tops": {"GRN": 0.0001}, "toe": 0.0001, "white": 0.6, "gamma": 3.0}
# 1. whole codes: black at or over the upper block level, so the whole sky is black
seen = {}
own = obs_mosaic.tile_scale(scale, "GRN", True, seen)["black_of"](coded_sky())
print("coded", own, seen)
assert seen.get("whole_codes") and own["black"] >= 0.001 + CODE
# the near miss: pixel noise, no whole codes: the rule it had (no whole_codes mark)
seen = {}
own = obs_mosaic.tile_scale(scale, "GRN", True, seen)["black_of"](noisy_sky())
print("noisy", own, seen)
assert "whole_codes" not in seen
# a frame of the body (no own sky): nothing changes
assert "black_of" not in obs_mosaic.tile_scale({**scale, "sky_tops": {}}, "GRN", True, {}, None, True)

# 2. long-exposure runs
lit = np.full((64, 64), 0.0002, np.float32); lit[20:40, 20:40] = 0.08       # a lit crescent, 0.26 s
faint = np.full((64, 64), 0.0002, np.float32); faint[20:40, 20:40] = 0.0016  # the jets, 22 s
blacks, white = {"CL": 0.0004, "RED": 0.0004}, 0.08
crescent = [("CL", lit, 0.26, True, t) for t in (0, 1)]
jets = [("RED", faint, 22.0, False, t) for t in (2, 3, 4)]
long = obs_mosaic._long_white(crescent + jets + [("CL", lit, 0.26, True, 5)], blacks, white)
print("long", long)
assert long and long["runs"] == [[2, 4]] and abs(long["exposure"] - 2.6) < 1e-9 and 0 < long["white"] < white
# near misses: one exposure only; a run with a frame on the disk; a run brighter than LONG_FAINT of the white
assert obs_mosaic._long_white(crescent + [("CL", faint, 0.26, False, 2)], blacks, white) is None
assert obs_mosaic._long_white(crescent + jets[:2] + [("RED", faint, 22.0, True, 4)], blacks, white) is None
bright = np.full((64, 64), 0.0002, np.float32); bright[20:40, 20:40] = 0.03
assert obs_mosaic._long_white(crescent + [("RED", bright, 22.0, False, 2)], blacks, white) is None
# tile_scale: the run's white only for a long exposure inside a run, off the disk, in a movie
sc = {"blacks": blacks, "white": white, "gamma": 3.0, "long": long}
assert obs_mosaic.tile_scale(sc, "RED", True, {}, None, False, 22.0, 3)["white"] == long["white"]
assert obs_mosaic.tile_scale(sc, "RED", True, {}, None, False, 22.0, 9)["white"] == white      # outside the run
assert obs_mosaic.tile_scale(sc, "CL", True, {}, None, False, 0.26, 3)["white"] == white       # short exposure
assert obs_mosaic.tile_scale(sc, "RED", True, {}, None, True, 22.0, 3)["white"] == white       # on the disk
assert obs_mosaic.tile_scale(sc, "RED", False, {}, None, False, 22.0, 3)["white"] == white      # a mosaic's tile
print("ok")
