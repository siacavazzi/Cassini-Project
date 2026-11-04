"""Spot check 7, fix D: a movie frame with no dark sky, lit all over by a glow (the forward-scattered light round
Enceladus's backlit jets, ISS_155EN_PLMHPHR001_PIE N1697688814_1: its sky at a sixth of the jets' root), gets a black
of its own over its flat floor (obs_mosaic.tile_scale), so it is not a flat gray square in the movie; the jets stay
over it. A frame a lit body fills, a frame with dark sky in a pass with no sky height of its own, and a veil with no
flat floor keep the pass's black. Synthetic I/F. Run: python web/test_movie_glow_sky.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(5)
N = 1024
yy, xx = np.mgrid[:N, :N].astype(np.float32)
scale = {"blacks": {"RED": 2.0e-4}, "white": 0.1, "gamma": 3.0}     # the pass's black from its crescent frames
black_of = om.tile_scale(scale, "RED", True)["black_of"]

# the jets frame: a flat floor of 2.3e-4 rising gently to a halo, and the jets' root at 1.5e-3 at the bottom
r = np.hypot(xx - 512, yy - 1000)
glow = 2.3e-4 + 6e-5 * np.clip(1 - r / 700, 0, 1) ** 2 + 1.3e-3 * np.exp(-r / 60)
jets = (glow + rng.normal(0, 4e-6, (N, N))).astype(np.float32)
got = black_of(jets)
q = jets[::4, ::4]
assert got is not None, "a glow's frame gets a black of its own"
print("glow: black", round(got["black"] * 1e4, 3), "e-4; frame under it", round(float(np.mean(q < got["black"])), 2))
assert np.mean(q < got["black"]) >= 0.45, "its far side goes black: no flat gray square"
assert got["black"] < 3e-4 < float(jets[990, 512]), "the jets' root and the halo close round it stay over black"

# a lit body filling the frame (its darkest quarter terrain, not a flat floor) keeps the pass's black
terrain = (0.03 + 0.02 * np.sin(xx / 37) * np.cos(yy / 53) + rng.normal(0, 0.003, (N, N))).astype(np.float32)
assert black_of(terrain) is None, "a lit body filling the frame keeps the pass's black"
# a frame with dark sky, in a pass that measured no sky height: as before, the pass's black
dark = np.full((N, N), 2.1e-4, np.float32) + rng.normal(0, 4e-6, (N, N)).astype(np.float32)
dark[400:600, 400:600] = 0.05
assert black_of(dark) is None, "a frame with dark sky keeps the pass's black"
# a smooth veil with no flat floor (a plume's glow filling the frame) keeps it too
veil = (2.3e-4 * (1 + 0.3 * yy / N) + rng.normal(0, 2e-6, (N, N))).astype(np.float32)
veil[500:520, 500:520] = 2e-3
assert black_of(veil) is None, "a glow that fills the frame with no flat floor keeps the pass's black"
print("ok")
