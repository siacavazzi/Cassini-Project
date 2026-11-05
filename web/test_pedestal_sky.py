"""A dark sky with a small even offset is still dark sky (pass_scale's _dark_sky; moon colour fixes, 2026-11-05).
Phoebe in 2004 (ISS_000PH_FULROTIN001_PRIME) is 30 to 50 px across. The calibration leaves its RED, IR1 and UV3 skies
an even 5e-5 to 4e-4 I/F, 8 to 21% of their 99.9th percentile, so the old test (under 5% of the 99.9th percentile)
counted under 1% of them as sky, the pass's sky step never ran, and every band's black stayed at its 1st percentile,
under the sky: a blue-grey sky behind the moon (N1465550027_1: RED 2, GRN 18, BL1 32 levels).
- _dark_sky: measured from the frame's floor (its 1st percentile, at least 0), an offset sky is sky; a sky at 0 is
  found as before
- pass_scale: frames of such a sky get the sky step (sky_tops) and a black over the sky's level in every band
Run: python web/test_pedestal_sky.py"""
import os, sys  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
import calibration  # noqa: E402
import stacking  # noqa: E402
import obs_mosaic as om  # noqa: E402

yy, xx = np.mgrid[:1024, :1024].astype(np.float32)
moon = np.hypot(yy - 511.5, xx - 511.5) < 25   # Phoebe, 50 px across: its 99.9th percentile on the moon


def frame(offset, seed):
    rng = np.random.default_rng(seed)
    return (offset + 5e-6 * rng.standard_normal((1024, 1024))).astype(np.float32) + np.where(moon, 7e-4, 0).astype(np.float32)


for offset, name in ((6e-5, "offset sky (Phoebe's RED)"), (0.0, "sky at 0")):
    q = frame(offset, 1)[::4, ::4]
    old = (q < 0.05 * np.percentile(q, 99.9)).mean()
    new = om._dark_sky(q).mean()
    print(f"{name}: sky share {old:.3f} before, {new:.3f} now")
    assert new > 0.95, new
    if offset == 0.0:
        assert abs(new - old) < 0.01, (old, new)
    else:
        assert old < om.SKY_MIN, old

# a pass of RED, GRN and BL1 frames whose RED and BL1 skies sit over 0 (as Phoebe's): the sky step runs, and each
# band's black is over its own sky's level
LEVEL = {"RED": 6e-5, "GRN": 2e-5, "BL1": 7e-5}
fr = [(f"x{i}", f"N{1465550000 + i}_1", f, 1000.0 + 30 * i, {"RED": 650, "GRN": 568, "BL1": 451}[f], 0.0, 0.0,
       om.RADIUS["PHOEBE"] / (25 * om.IFOV["N"])) for i, f in enumerate(["BL1", "RED", "GRN"] * 3)]
of = {x[0]: x[2] for x in fr}


def load_hdr(path, window=120, max_frames=8, valid=False):
    return None, frame(LEVEL[of[path]], int(path[1:]) + 7), 1


real = stacking.load_hdr
stacking.load_hdr = load_hdr
with calibration.looking("balanced"):
    s = om.pass_scale(fr, {"key": ("PHOEBE", "OBST", "N", 0), "frames": fr, "z": fr[0][7], "movie": True},
                      ["RED", "GRN", "BL1"], True)
stacking.load_hdr = real
print("blacks", {f: f"{v:.2e}" for f, v in s["blacks"].items()}, "sky_tops" in s)
assert "sky_tops" in s
assert all(s["blacks"][f] > LEVEL[f] for f in LEVEL), s["blacks"]
print("ok")
