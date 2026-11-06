"""A movie or mosaic pass of lit sky (a smooth glow of stray or ring light with no dark sky and no body filling it) has its
blacks raised toward the glow's median with a soft toe, as a single picture of it does (calibration._floor's glow,
calibration.glow_share): 033RI HIPHAMOVB001's 2 s NAC frames came out a lifted gray square speckled with noise at its dark
end. A pass of the same brightness with fine structure (rings at high phase) keeps its blacks. Synthetic frames through
obs_mosaic.pass_scale. Run: python web/test_glow_pass.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402
import calibration as cal  # noqa: E402
import stacking  # noqa: E402

rng = np.random.default_rng(5)
H = 512
xx = np.mgrid[:H, :H][1].astype(np.float32)


def glow():
    """a smooth gradient of faint light, 1e-4 to 5e-4 I/F across the frame, with noise"""
    return (1e-4 + 4e-4 * (1 - xx / H) + rng.normal(0, 2e-5, (H, H))).astype(np.float32)


def rings():
    """the same brightness in narrow ringlets"""
    return (1e-4 + 4e-4 * (1 - xx / H) * (0.5 + 0.5 * np.sin(xx / 3.0) ** 2) + rng.normal(0, 2e-5, (H, H))).astype(np.float32)


def scale_of(make):
    images = {f"nac_data/N{i}_1.png": make() for i in range(3)}
    stacking.load_hdr = lambda path, window=120, *a, **k: (None, images[path], 1)
    frames = [(p, float(i), "CL1/CL2", None, None, 0.0, 0.0, 0.0) for i, p in enumerate(images)]
    u = {"key": ("SATURN", "ISS_033RI_TEST", "N", 0)}
    with cal.looking("balanced"):
        return pass_scale(frames, u)


pass_scale = obs_mosaic.pass_scale
lit = scale_of(glow)
print("glow", {k: lit.get(k) for k in ("blacks", "white", "toe", "filled")})
# black near the glow's median (3e-4), not at its dark end, with a toe; the top (black + white) where it was
assert lit["blacks"]["CL1/CL2"] > 2e-4 and lit.get("toe", 0) > 0, lit
fine = scale_of(rings)
print("rings", {k: fine.get(k) for k in ("blacks", "white", "toe", "filled")})
assert fine["blacks"]["CL1/CL2"] < 1.5e-4 and not fine.get("toe"), fine
print("ok")
