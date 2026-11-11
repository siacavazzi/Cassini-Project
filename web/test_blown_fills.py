"""A place in a mosaic where every frame was left out as saturated (obs_mosaic._silhouette) is filled by the least
saturated of them, drawn under everything in the luminance base (blown_fills), when drawn tiles lie on all four sides
of it: 039RI PHOTLIT004 (2007), whose seven frames at Saturn's disk centre saturated 95-99%, drew a black square in
the disk. A silhouette at the mosaic's edge (Iapetus 049IA's white limb out in the sky) or at a place another tile
shows stays out. Tile reports as layout() sees them, 039RI's 3x3 grid.
Run: python web/test_blown_fills.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

BOX = [-540, -540, 1080, 1080]
def tile(n, x, y, f="IR2", **kw):
    return dict({"n": n, "id": f"W{n}", "filter": f, "offset": [x, y], "box": BOX, "outline": [[0, 0]] * 4}, **kw)

grid = [tile(10 * i + j, x, y) for i, x in enumerate((-920, 0, 920)) for j, y in enumerate((-1000, -130, 750))
        if (x, y) != (0, -130)]
middle = [tile(100, 3, -131, "IR2", saturated=0.9483, lit=1.0), tile(101, 2, -131, "BL1", saturated=0.9493, lit=1.0),
          tile(102, 2, -131, "VIO", saturated=0.946, lit=1.0)]
laid = grid + [om._silhouette(t) for t in middle]
DRAWN = {"IR2", "RED", "BL1", "VIO"}
assert all("offset" not in t and "blown" in t for t in laid[-3:])
got = om.blown_fills(laid, DRAWN)
assert list(got) == [102], got                       # one per place, the least saturated
assert got[102]["offset"] == [2, -131] and got[102]["box"] == BOX
print("a saturated hole inside the mosaic is filled by tile 102; ok")

# a frame saturated all over keeps its place as "blown" too (_tile_made), so a place whose every frame is 95-99% fills
allover = [{"n": 110, "id": "W110", "filter": "IR2", "saturated": 0.97, "why": "saturated all over (97%)",
            "blown": {"offset": [0, -130], "box": BOX}}]
assert list(om.blown_fills(grid + allover, DRAWN)) == [110]

# the same place with a drawn tile there: nothing filled; a tile of a filter not drawn (a polarizer) does not stop it
assert om.blown_fills(laid + [tile(103, 0, -120, "RED")], DRAWN) == {}
assert list(om.blown_fills(laid + [tile(104, 0, -120, "IRP0")], DRAWN)) == [102]
# at the mosaic's edge (no tile to its right): nothing filled, nor with a tile far out to its right (another strip)
edge = [t for t in grid if t["offset"][0] < 900] + [om._silhouette(tile(105, 920, -130, saturated=0.97, lit=1.0))]
assert om.blown_fills(edge, DRAWN) == {}
assert om.blown_fills(edge + [tile(106, 920 + 3000, -130)], DRAWN) == {}
assert om.blown_fills(grid, DRAWN) == {}
print("silhouettes at the edge, past it, or under a drawn tile stay out; ok")

# registered tiles round it (the global solve moved them 6 px right, 4 down): the fill moves with them
moved = [dict(t, offset=[t["offset"][0] + 6, t["offset"][1] + 4], spice_place=t["offset"]) for t in grid]
got = om.blown_fills(moved + [om._silhouette(t) for t in middle], DRAWN)
assert got[102]["offset"] == [8, -127] and got[102]["spice_place"] == [2, -131], got
print("the fill moves with the registered tiles round it; ok")

# an over-exposed tile alone at the mosaic's edge (260RI's RED frame, 80% saturated, 470 px past the rest) is left out,
# its place kept; one inside the mosaic, or with another filter at its place, stays
lone = tile(120, -1850, -130, "RED", saturated=0.80, lit=1.0)
out = om.lone_blown(grid + [lone])
assert "offset" not in out[-1] and "blown" in out[-1] and "left out" in out[-1]["why"], out[-1]
inside = tile(121, 0, -130, "RED", saturated=0.80, lit=1.0)
assert om.lone_blown(grid + [inside])[-1] is inside
paired = [lone, tile(122, -1850, -120, "BL1")]
assert om.lone_blown(grid + paired)[-2] is lone
assert om.lone_blown(grid + [tile(123, -1850, -130, "RED", saturated=0.2, lit=1.0)])[-1]["offset"] == [-1850, -130]
print("an over-exposed tile alone at the mosaic's edge is left out; ok")
