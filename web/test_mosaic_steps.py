"""Synthetic check of movie mode's mosaic steps (obs_mosaic.mosaic_steps, kind_of "mosaic_steps"): of a mosaic pass,
movie mode passes over the frames whose mosaic is the same picture as the frame before's (polarizer frames, a colour
filter before the pass's colour is whole, a clear frame where another filter is the grey one) and those whose
pointing's next frames add another filter to it (a clear tile drawn gray before its colour set), so each step is one
new place, finished; one filter over and over (a slow ring scan) is a new picture every frame. Hyperion 2005-09-26 (ISS_015HY_MORPHO001_PRIME): each place CL, UV3, IR1, IR3, P0, P60, P120.
Run: python web/test_mosaic_steps.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om

NM = {"CL1/CL2": 611, "UV3": 338, "IR1": 750, "IR3": 930, "GRN": 568, "RED": 649, "BL1": 451, "P0/GRN": 568, "P60/GRN": 568, "P120/GRN": 568}


def unit(places, filters, placed=None):
    """A pass of frames at places (900 px apart on a 3-wide grid) through filters; placed: which SPICE placed"""
    fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 30 * i, NM[f], -900.0 * (q % 3), -900.0 * (q // 3),
           1e6 if placed is None or placed[i] else 0.0) for i, (q, f) in enumerate(zip(places, filters))]
    return {"key": ("HYPERION", "OBS", "N", 0), "frames": fr, "z": 1e6, "kind": "mosaic", "mosaic": True, "movie": False,
            "jump_frac": 1.0, "repeats": 1}


def steps(u, p=None):
    return om.mosaic_steps(u, p)


# MORPHO001: five places of CL, UV3, IR1, IR3 and three polarizers: one step a place, at its colour set's last
# channel (the clear tile is drawn gray first, then the colour over it; the polarizers draw nothing)
M1 = ["CL1/CL2", "UV3", "IR1", "IR3", "P0/GRN", "P60/GRN", "P120/GRN"]
u = unit([q for q in range(5) for _ in M1], M1 * 5)
assert steps(u) == [3 + 7 * q for q in range(5)], steps(u)

# MORPHO003: UV3, GRN, IR3, then CL (grey is the filter taken most, the first of a tie: UV3): the clear frame
# draws nothing where UV3 is, so the step is at IR3
M3 = ["UV3", "GRN", "IR3", "CL1/CL2"]
u = unit([q for q in range(6) for _ in M3], M3 * 6)
assert steps(u) == [2 + 4 * q for q in range(6)], steps(u)

# a gray pass (one filter): every tile is a new place, every frame a step
u = unit(list(range(6)), ["CL1/CL2"] * 6)
assert steps(u) == list(range(6)), steps(u)

# true colour RED, GRN, BL1 a place: the step is the place's last colour frame; with the pass's plan given (its
# grey filter another than the count would pick) the rule follows the plan: the first RED frame comes before
# anything is drawn (the window shows the frame itself), so it is a step too
F = ["RED", "GRN", "BL1"]
u = unit([q for q in range(4) for _ in F], F * 4)
assert steps(u) == [2, 5, 8, 11], steps(u)
p = {"colour": ["RED", "GRN", "BL1"], "grey": "GRN", "luminance": {"filters": ["GRN", "BL1", "RED"]}}
assert steps(unit([q for q in range(4) for _ in F], F * 4), p) == [0, 2, 5, 8, 11]

# a frame SPICE could not place is drawn by no mosaic (layout counts placed tiles): never a step of its own, and
# the pass's frames before anything is drawn are steps (the window shows the frame itself)
u = unit([0, 0, 0, 1, 1, 1], ["CL1/CL2", "P0/GRN", "P60/GRN"] * 2, placed=[False, True, True, True, True, True])
assert steps(u) == [0, 1, 2, 3], steps(u)

# a place the camera comes back to later is a new step (the pointings are runs of frames, in time), and one filter
# taken again and again at one pointing (a scan creeping under SAME_PLACE a frame) is a new picture each time
u = unit([0, 1, 0], ["CL1/CL2"] * 3)
assert steps(u) == [0, 1, 2], steps(u)
u = unit([0] * 5, ["CL1/CL2"] * 5)
assert steps(u) == list(range(5)), steps(u)

# kind_of carries the ids of a mosaic pass's steps, and none for a movie or a mosaic movie
u = unit([q for q in range(2) for _ in M1], M1 * 2)
om._unit_of[u["frames"][0][1]] = (u, 0)
units = om.units
om.units = lambda *a: [u]
try:
    k = om.kind_of(u["frames"][0][1])
    assert k["mosaic_steps"] == [u["frames"][3][1], u["frames"][10][1]], k
    u["kind"] = "mosaic_movie"
    assert "mosaic_steps" not in om.kind_of(u["frames"][0][1])
    u["kind"], u["movie"], u["mosaic"] = "movie", True, False
    assert "mosaic_steps" not in om.kind_of(u["frames"][0][1])
finally:
    om.units = units
    om._unit_of.clear()
print("ok: mosaic steps")
