"""A filter a mosaic does not draw (a luminance base's, a narrow band taken between the colour sets) never gets a black
under the lowest of the drawn filters' (obs_mosaic.undrawn_blacks, pass_scale): Jupiter ATMOS02A (2001) drew its HAL
night-side frames on a black of 0 I/F beside colour filters whose black sat at 0.003-0.0055, and the day side's faint
glow in them showed as a gray panel beside the terminator. Fails on the code before it (no undrawn_blacks).
Run: python web/test_undrawn_blacks.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

blacks = {"HAL": -8e-6, "BL1": 0.0032, "CB2": 0.0055, "MT2": 0.0033, "MT3": 0.0010}
out = om.undrawn_blacks(blacks, ["CB2", "BL1"])
assert out["BL1"] == 0.0032 and out["CB2"] == 0.0055, out          # the drawn filters as they were
assert out["HAL"] == 0.0032 and out["MT3"] == 0.0032, out          # raised to the drawn filters' lowest
assert out["MT2"] == 0.0033, out                                    # a higher black kept
print("undrawn filters' blacks at least the drawn filters' lowest; ok")
assert om.undrawn_blacks(blacks, None) == blacks and om.undrawn_blacks(blacks, ["RED"]) == blacks
assert om.undrawn_blacks(blacks, ["BL1"])["HAL"] == 0.0032          # a grey mosaic: its one filter
print("no drawn filter with a black: as they were; ok")
