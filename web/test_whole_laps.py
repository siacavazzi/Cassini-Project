"""Synthetic check of Whole mosaics (obs_mosaic.lap_of, lap_ends, lap_end, kind_of lap_ends): a mosaic movie's
frames that finish a lap are the last before the camera comes back to a place it has taken in this lap, in any
filter, and the pass's last frame; repeats of a place in a row count once. Also export.plan leaves out the other
frames of a mosaic movie with whole=1. Run: python web/test_whole_laps.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om

def unit(places, filters, kind="mosaic_movie"):
    fr = [(f"p{i}", f"N{1500000000 + i}_1", f, 1000.0 + 30 * i, 600, 0, 0, 1e6) for i, f in enumerate(filters)]
    return {"key": ("JUPITER", "OBS", "N", 0), "frames": fr, "place": places, "kind": kind, "repeats": 3,
            "mosaic": True, "movie": False, "jump_frac": 1.0}

# a 2x2 in three filters, three laps: each place takes RED, GRN, BL1 before the camera moves on
F = ["RED", "GRN", "BL1"]
u = unit([p for _ in range(3) for p in range(4) for _f in F], F * 12)
assert om.lap_ends(u) == [11, 23, 35], om.lap_ends(u)
assert om.lap_of(u)[11] == 1 and om.lap_of(u)[12] == 2

# a place taken twice in a row (one filter) is one visit; a frame SPICE could not place does not end a lap
u = unit([0, 0, 1, None, 2, 3, 0, 1, 2, 3, 3], ["CB2"] * 11)
assert om.lap_ends(u) == [5, 10], om.lap_ends(u)

# a last lap that stops short still ends at the pass's last frame
u = unit([0, 1, 2, 3, 0, 1], ["CB2"] * 6)
assert om.lap_ends(u) == [3, 5], om.lap_ends(u)

# not a mosaic movie: no lap ends
assert om.lap_ends(unit([0, 1, 2, 3], ["CB2"] * 4, kind="mosaic")) == []

# lap_end and kind_of by frame id
u = unit([0, 1, 2, 3] * 2, ["CB2"] * 8)
ids = [f[1] for f in u["frames"]]
om.unit_of = lambda fid: (u, ids.index(fid)) if fid in ids else None
om.units = lambda *k: [u]
assert [om.lap_end(i) for i in ids] == [False, False, False, True, False, False, False, True]
assert om.lap_end("N1_1") is None
k = om.kind_of(ids[0])
assert k["lap_ends"] == [ids[3], ids[7]], k

# export: whole=1 keeps a mosaic movie's lap ends only, and keeps the film's name otherwise
import export
assert "whole" not in export.options({"from": ["2000-11-28T00:00"], "until": ["2000-11-29T00:00"]})["movie"]
opt = export.options({"from": ["2000-11-28T00:00"], "until": ["2000-11-29T00:00"], "whole": ["1"], "fade": ["40"]})
assert opt["movie"]["whole"] and opt["movie"]["fade"] == 0
assert export._lap_end(ids[3]) and not export._lap_end(ids[2]) and export._lap_end("N1_1")
print("whole laps ok")
