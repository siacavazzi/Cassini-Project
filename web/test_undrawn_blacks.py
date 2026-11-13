"""A filter a mosaic does not draw (a luminance base's, a narrow band taken between the colour sets) whose frames hold
nothing brighter than the drawn filters' lowest black gets that black (obs_mosaic.undrawn_blacks, pass_scale): Jupiter
ATMOS02A (2001) drew its HAL night-side frames (top 0.002 I/F) on a black of 0 beside colour filters whose black sat at
0.003-0.0055, and the day side's faint glow in them showed as a gray panel beside the terminator. A band with light of
its own over that black (a dim methane band on a filled Saturn pass) keeps its own black.
Fails on the code before it (no undrawn_blacks). Run: python web/test_undrawn_blacks.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

blacks = {"HAL": -1e-5, "BL1": 0.0032, "CB2": 0.0055, "MT2": 0.0033, "MT3": 0.0010}
tops = {"HAL": 0.0019, "BL1": 0.6, "CB2": 0.7, "MT2": 0.2, "MT3": 0.03}
out = om.undrawn_blacks(blacks, ["CB2", "BL1"], tops)
assert out["BL1"] == 0.0032 and out["CB2"] == 0.0055, out          # the drawn filters as they were
assert out["HAL"] == 0.0032, out                                    # nothing over the drawn black: raised to it
assert out["MT3"] == 0.0010 and out["MT2"] == 0.0033, out           # light of its own: kept
print("an undrawn band holding only light under the drawn black gets that black; one with its own light keeps its own; ok")
assert om.undrawn_blacks(blacks, None, tops) == blacks and om.undrawn_blacks(blacks, ["RED"], tops) == blacks
print("no drawn filter with a black: as they were; ok")
