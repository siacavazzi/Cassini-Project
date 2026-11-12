"""Synthetic check of obs_mosaic.newest_tile, where a mosaic picture's newest tile lies for the camera windows' mark:
frame n's own tile as fractions of the picture's view rect; a tile moved by panel registration has its outline moved
with it; a frame with no place in the picture marks the newest tile the picture draws; nothing placed marks nothing.
Run: python web/test_newest_tile.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

u = {"key": ("SATURN", "ISS_000RI_TEST001_PRIME", "N", 0), "frames": [[None, f"N100000000{j}_1", "CL1", 0] for j in range(4)]}
sq = lambda x, y, s=100: [[x, y], [x + s, y], [x + s, y + s], [x, y + s]]
tiles = [{"n": 0, "id": "N1000000000_1", "filter": "GRN", "offset": [0, 0], "outline": sq(0, 0)},
         {"n": 1, "id": "N1000000001_1", "filter": "GRN", "offset": [110, 0], "spice_place": [100, 0], "outline": sq(100, 0)},
         {"n": 2, "id": "N1000000002_1", "filter": "UV3", "offset": [0, 100], "outline": sq(0, 100)},
         {"n": 3, "id": "N1000000003_1", "filter": "GRN"}]   # (SPICE could not place it)
rect = [0, 0, 200, 200]
made = lambda ts: (None, ts, rect, {}, ["GRN"], "x")
checks = 0


def check(name, got, want):
    global checks
    assert got == want, f"{name}: {got} != {want}"
    checks += 1
    print(f"{name}: {got}")


check("frame 0's own tile", om.newest_tile(u, 0, made(tiles[:1]), None)["poly"], [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]])
check("a moved tile's outline moves with it", om.newest_tile(u, 1, made(tiles[:2]), None)["poly"],
      [[0.55, 0], [1.05, 0], [1.05, 0.5], [0.55, 0.5]])
check("a filter the picture does not draw still marks its own place", om.newest_tile(u, 2, made(tiles[:3]), None)["id"], "N1000000002_1")
check("a frame with no place marks the newest tile drawn", om.newest_tile(u, 3, made(tiles), None)["n"], 1)
check("nothing placed marks nothing", om.newest_tile(u, 3, made(tiles[3:]), None), None)
print(f"{checks} checks ok")
