"""Every movie frame plays its own moment (Sam 2026-11-06: frames were lost behind one held color picture; the 2012
Titan transit played 25 of its 26 frames as one set taken 50 minutes into it, and the first Titan flyby never showed
the CB3 frames that see its surface through the haze):

1. set_shown: a frame of the shown color set, or taken within HOLD_AGE of it, shows the set; one further from it plays
   its moment in the set's color (tinted), drawn from lum_of's frame: the gray filter's beside it, else its own; a
   methane, UV or polarizer frame (held_band) through another filter's beside it, else on its own in gray. A set taken
   after the frame (the movie's opening, before its first set) counts the same way.
2. step_frame: in a movie playing its gray filter, another filter's frame shows the gray frame beside it only when that
   was taken within HOLD_AGE of it.
3. tinted_frame: the frame's brightness and detail in the set's hue, at the set's brightness; off the set, its mean hue.
4. The page leaves tinted frames to the server (the steady table's "tint", no set in its "by").
Run: python web/test_movie_own_moments.py"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402


def unit(fs, times):
    frames = [(f"p{i}", f"W{1700000000 + i}_1", f, t, 600, 0, 0, 1e6) for i, (f, t) in enumerate(zip(fs, times))]
    return {"key": ("TITAN", "OBS", "W", 0), "frames": frames, "z": 1e6, "movie": True, "mosaic": False, "kind": "movie"}


ok, none, want = (lambda j: True), (lambda j: False), ["RED", "GRN", "BL1"]

# ---------- 1. the transit's shape: clear frames a minute apart, a set 50 minutes in, another 2 hours later ----------
fs = ["CL1/CL2"] * 20 + ["RED", "GRN", "BL1"] + ["CL1/CL2"] * 3 + ["RED", "GRN", "BL1"]
ts = [60.0 * i for i in range(20)] + [3000, 3060, 3120] + [3200, 3300, 3500] + [7000, 7060, 7120]
u = unit(fs, ts)
u["_sets"] = [[("RED", 20), ("GRN", 21), ("BL1", 22)], [("RED", 26), ("GRN", 27), ("BL1", 28)]]
assert om.plays_colour(u, want, "CL1/CL2")
shown = [om.set_shown(u, n, want, none, ok) for n in range(len(fs))]
# the clear frames before the first set (all over HOLD_AGE before it) play themselves, in its color
assert all(t for _, t in shown[:20]), [t for _, t in shown]
# the set's own frames: the set
assert not any(t for _, t in shown[20:23]) and all(g for g, _ in shown[20:23])
# after the set: within HOLD_AGE the set, then its own picture in the set's color
assert [t for _, t in shown[23:26]] == [False, False, True]
# the next set coming in, long after the last: its first channels show it (its own colors), not the old set
assert [sorted(g.values()) for g, _ in shown[26:29]] == [[26, 27, 28]] * 3 and not any(t for _, t in shown[26:29])
print("clear frames far from a set play themselves, in its color; ok")

# a methane frame: within HOLD_AGE of the set, the set; further, its moment in the set's color
fs2 = ["RED", "GRN", "BL1", "MT3", "MT3"]
u2 = unit(fs2, [0, 60, 120, 200, 900])
u2["_sets"] = [[("RED", 0), ("GRN", 1), ("BL1", 2)]]
assert om.set_shown(u2, 3, want, none, ok) == ({"RED": 0, "GRN": 1, "BL1": 2}, False)
assert om.set_shown(u2, 4, want, none, ok) == ({"RED": 0, "GRN": 1, "BL1": 2}, True)
# lum_of: the picture a tinted frame is drawn from: the gray filter's nearest within HOLD_AGE, else its own, and for a
# methane, UV or polarizer frame another filter's beside it, or none (gray on its own)
f3 = [(0, "", "CB3", 0), (0, "", "IR3", 100), (0, "", "CB1", 1000), (0, "", "MT1", 1050), (0, "", "MT1", 5000)]
assert om.lum_of(f3, 1, "CB3", ok, ok) == 0      # IR3 shows CB3 beside it
assert om.lum_of(f3, 2, "CB3", ok, ok) == 2      # no CB3 near: its own
assert om.lum_of(f3, 3, "CB3", ok, ok) == 2      # MT1: the CB1 beside it
assert om.lum_of(f3, 4, "CB3", ok, ok) is None   # MT1 alone: gray
assert om.lum_of(f3, 1, "CB3", lambda j: j != 0, ok) == 1   # (the CB3 not whole: its own)
assert om.held_band("MT3") and om.held_band("CL1/UV3") and om.held_band("P120/GRN") and not om.held_band("CB3")
assert not om.held_band("CL1/CL2") and not om.held_band("IR3")
print("methane, UV and polarizer frames play their moment through the filter beside them; ok")

# ---------- 2. step_frame's time limit ----------
fs3 = ["CB3", "MT1", "CB3"]
assert om.step_frame(fs3, 1, "CB3", ok, ok, [0, 30, 60]) == 0
assert om.step_frame(fs3, 1, "CB3", ok, ok, [0, 1000, 2000]) == 1
assert om.step_frame(fs3, 1, "CB3", ok, ok) == 0   # (no times: as before)
print("a gray movie's step holds only within HOLD_AGE; ok")

# ---------- 3. tinted_frame ----------
H = W = 200
colour = np.zeros((H, W, 4), np.uint8)
colour[50:150, 50:150] = (200, 140, 60, 255)            # an orange disk, flat
grey = np.zeros((H, W, 4), np.uint8)
grey[40:160, 40:160, 3] = 255
grey[40:160, 40:160, 0] = 170
grey[90:110, 90:110, 0] = 60                            # a dark spot the set doesn't have
out = om.tinted_frame(colour, grey, 2.2).astype(int)
lin = lambda v: calibration.decode(np.asarray(v, np.float32) / 255, 2.2)
# the frame's alpha, the frame's detail (the spot), the set's hue
assert (out[..., 3] == grey[..., 3]).all()
assert out[100, 100, :3].sum() < out[70, 70, :3].sum() / 2
r = lin(out[70, 70, :3]); c = lin([200, 140, 60])
assert np.allclose(r / r.sum(), c / c.sum(), atol=0.02), (r, c)
# brought to the set's brightness where both are lit
assert abs(int(out[70, 70, 0]) - 200) <= 3, out[70, 70]
# a frame much dimmer than the set (another scene) moves only so far: both are on the pass's display scale
dim = grey.copy(); dim[40:160, 40:160, 0] = 40
assert om.tinted_frame(colour, dim, 2.2)[70, 70, 0] < 120
# off the set (the frame's edge past it): the set's mean hue, not gray
e = lin(out[45, 45, :3])
assert e[0] > e[2] * 2, e
print("a tinted frame keeps its detail in the set's hue; ok")

# ---------- 4. the page leaves tinted frames to the server ----------
src = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
assert "(e.table.tint || []).includes(e.n)" in src
print("ok")
