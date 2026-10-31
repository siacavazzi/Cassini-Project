"""Synthetic checks of the two gentler rules for the 2005-11-27 Enceladus plume frames: a dim frame the camera saturated
over part of it (a crescent and its plumes in a 100 s exposure) takes only part of its glow black (SATURATED_GLOW), so its
night side keeps a soft edge, while a dim frame with nothing saturated (lit sky, the E ring's glow) keeps all of it; and a
lossy frame compressed far past LOSSY_RATIO has its one-code block steps smoothed (deblock) while a star, a sharp edge and
a lossless or lightly compressed frame stay as they were. Run: python web/test_plume_tone.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402

rng = np.random.default_rng(11)
H = 512
yy, xx = np.mgrid[:H, :H].astype(np.float32)

# ---- saturated_glow: all of the glow black up to SATURATED_GLOW[0], SATURATED_GLOW[2] of it from SATURATED_GLOW[1] ----
assert cal.saturated_glow(0.0) == 1.0
assert cal.saturated_glow(cal.SATURATED_GLOW[0]) == 1.0
assert abs(cal.saturated_glow(0.087) - cal.SATURATED_GLOW[2]) < 1e-9
assert cal.SATURATED_GLOW[2] < cal.saturated_glow(0.005) < 1.0

# ---- a dim frame without sky (the 100 s plume frame: night side 3e-4, haze 6e-4, I/F) ----
disc = (xx - 256) ** 2 + (yy - 220) ** 2 < 120 ** 2
frame = np.where(disc, 3e-4, 5e-4 + 1.5e-4 * yy / H) + rng.normal(0, 4e-6, (H, H))
iofs = [frame.astype(np.float32)]
full_black = cal._floor(iofs, [0.0], None)
half_black = cal._floor(iofs, [0.0], None, cal.saturated_glow(0.087))
print("glow black: lit sky", full_black, "saturated frame", half_black)
assert full_black > np.percentile(frame, 40)                  # lit sky: its dim half goes black, as before
assert np.percentile(frame, 0.5) * cal.FLOOR_SHARE < half_black < full_black   # saturated: less, but still above the floor


# ---- deblock: 8 px blocks one code apart in a faint glow ----
ramp = 8 + 6 * np.exp(-((xx - 256) ** 2 + (yy - 300) ** 2) / (2 * 90 ** 2))
blocks = np.round(ramp[::8, ::8]).repeat(8, 0).repeat(8, 1)       # what a 52:1 lossy frame stores
codes = blocks.copy()
codes[100, 100] = 60                                              # a star
codes[:, 400:] += 40                                              # a sharp edge (a limb)
iof = (codes * 1e-5).astype(np.float64)
lossy = {"INST_CMPRS_TYPE": "LOSSY", "INST_CMPRS_RATIO": "52.5"}
out = cal.deblock(iof, codes.astype(np.uint8), lossy)


def steps(v):
    # how far the picture jumps across the block borders inside the glow, against within the blocks
    a = v[200:400, 120:380]
    return float(np.abs(np.diff(a, axis=1))[:, 7::8].mean())


print("block steps: before", steps(iof), "after", steps(out))
assert steps(out) < 0.4 * steps(iof)
assert abs(out[100, 100] - iof[100, 100]) < 0.02 * iof[100, 100]      # the star stays
assert abs(out[200, 420] - iof[200, 420]) < 0.02 * iof[200, 420]      # and the edge
assert np.array_equal(cal.deblock(iof, codes.astype(np.uint8), {"INST_CMPRS_TYPE": "LOSSLESS"}), iof)
assert np.array_equal(cal.deblock(iof, codes.astype(np.uint8), {"INST_CMPRS_TYPE": "LOSSY", "INST_CMPRS_RATIO": "3.1"}), iof)
print("ok")
