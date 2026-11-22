"""A balanced picture of Saturn's night side with no sky takes its black from the night side, keeping NIGHT_KEEP of
the ringshine (calibration.night_black, taste call 31: 196SA STORMW014's set drew its night side at a third of white).
A sunlit disk with dark terrain (Iapetus), a frame mostly lit, and a body other than Saturn keep black at 0. Run:
python web/test_night_black.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import calibration as c

sat = [{"TARGET_NAME": '"SATURN"'}]
night = np.full((300, 300), 0.05, np.float32)
night[240:, :] = 0.9                                   # a crescent along the bottom, a fifth of the frame
b = c.night_black(night, sat)
assert abs(b - 0.05 * (1 - c.NIGHT_KEEP)) < 1e-4, b   # black under the night side, the ringshine kept
assert c.night_black(night, [{"TARGET_NAME": "IAPETUS"}]) == 0.0
lit = np.full((300, 300), 0.6, np.float32); lit[:, :120] = 0.04   # a sunlit Saturn, a dark band
assert c.night_black(lit, sat) == 0.0
half = np.full((300, 300), 0.05, np.float32); half[:, 150:] = 0.9  # half lit: not a night side
assert c.night_black(half, sat) == 0.0
assert c.night_black(night, [{"TARGET_NAME": '"UNK"', "OBSERVATION_ID": '"ISS_196SA_STORMW014_RIDER"'}]) == b
assert c.night_black(night, [{"TARGET_NAME": '"UNK"', "OBSERVATION_ID": '"ISS_196IA_X001_PRIME"'}]) == 0.0
dark = np.full((300, 300), 0.015, np.float32); dark[240:, :] = 0.9   # a night side drawn near black already: kept
assert c.night_black(dark, sat) == 0.0
assert c.night_black(night, sat, margin=0.04) == 0.0   # drawn near black already: kept

# a movie's frame of the same night side (obs_mosaic.tile_scale, night: the movie's body) takes the black its still has
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om
with c.looking("balanced"):
    W = 0.02                                               # the pass's white (I/F)
    scale = {"blacks": {"CL1": 0.0}, "white": W, "gamma": 3.0}
    seen = {}
    out = om.tile_scale(scale, "CL1", own_sky=True, seen=seen, on_body=True, t=5.0, night="SATURN")
    got = out["black_of"](night * W)
    assert abs(got["black"] - b * W) < 1e-6, got          # the still's black, in the pass's I/F
    assert seen["night_black"] == got["black"]
    assert got["toe"] > 0
    assert out["black_of"](dark * W) is None               # a night side drawn near black already: the pass's black
    assert om.tile_scale(scale, "CL1", own_sky=True, on_body=True, t=5.0, night="IAPETUS")["black_of"](night * W) is None
    assert "black_of" not in om.tile_scale(scale, "CL1", own_sky=True, on_body=True, t=5.0)   # no night: as before
    assert "black_of" not in om.tile_scale(scale, "CL1", own_sky=False, on_body=True, t=5.0, night="SATURN")  # mosaics
print("night black ok")
