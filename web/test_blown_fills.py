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
assert all("offset" not in t and "blown" in t for t in laid[-3:])
got = om.blown_fills(laid)
assert [t["n"] for t in got] == [102], got           # one per place, the least saturated
assert got[0]["fill"] and got[0]["offset"] == [2, -131] and got[0]["box"] == BOX and "why" not in got[0]
print("a saturated hole inside the mosaic is filled by", got[0]["id"], "; ok")

# the same place with a tile that shows a picture there: nothing filled
assert om.blown_fills(laid + [tile(103, 0, -120, "RED")]) == []
# at the mosaic's edge (no tile to its right): nothing filled
edge = [t for t in grid if t["offset"][0] < 900] + [om._silhouette(tile(104, 920, -130, saturated=0.97, lit=1.0))]
assert om.blown_fills(edge) == []
# a mosaic movie's own base (rolling) and a pass with no silhouettes draw as before
assert om.blown_fills(grid) == []
print("silhouettes at the edge or under a shown tile stay out; ok")
