"""ring_moves keeps ring_places' "too little ring" outcome with the pass. For a ringed body's mosaic pass with fewer than
RING_FIT_MIN ring tiles, ring_places reads every tile and its ring geometry to answer ({}, None), and ring_moves kept
nothing: every layout() of the pass read them all again (3 to 6.5 s a call on 271SA NHEMMAP001's 36 tiles, on every
mosaic request, 2026-11-16). The outcome is kept in the pass's ring file ("short": the tiles it was found on); the same
tiles or fewer are not read again, more tiles are, and nothing is kept while a tile's picture or time is missing.
Run: python web/test_ring_short_kept.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import json  # noqa: E402
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp(prefix="ring-short-")
known = set()
geometry = lambda gx, gy, fid: (gx, gy)
geometry.knows = lambda fid: fid in known
om._ring_geometry = lambda u: geometry
om.calibration.step = lambda name: True
om._pointing_root = lambda u, n, roots: n   # (each tile its own pointing)
calls, answer = [], [({}, None)]


def ring_places(u, tiles, picture, fixed=None, ref=None):
    calls.append(sorted(t["n"] for t in tiles))
    for t in tiles:
        picture(t["n"])     # (as the real one: every tile's picture is read)
    return answer[0]


om.ring_places = ring_places
u = {"key": ("SATURN", "ISS_271SA_NHEMMAP001_VIMS", "W", 0), "frames": [(None, f"W{1871800000 + j}_1", "CL1/CL2", float(j)) for j in range(6)]}
p = {"display_scale": {"gamma": 1.0}}
there = om._tiles(u, cache, p["display_scale"])
os.makedirs(there)
tile = lambda n, **k: {"n": n, "id": u["frames"][n][1], "offset": [10.0 * n, 5.0], "box": [0, 0, 512, 512], **k}


def made(n):
    om.Image.fromarray(np.zeros((4, 4, 4), np.uint8), "RGBA").save(os.path.join(there, f"{n}.png"))
    known.add(u["frames"][n][1])


path = os.path.join(om.folder(u, cache), om.RING_FILE + om.PLAN_FILE)
moves = lambda tiles: om.ring_moves(u, cache, p, tiles)

# a tile's picture not made yet: read every time, nothing kept
made(0); made(1)
known.add(u["frames"][2][1])
assert moves([tile(0), tile(1), tile(2)]) == {} and len(calls) == 1 and not os.path.exists(path)
# a tile's time not in the geometry cache yet: the same
made(2); known.discard(u["frames"][2][1])
assert moves([tile(0), tile(1), tile(2)]) == {} and len(calls) == 2 and not os.path.exists(path)
# every tile read and known: kept, and the same tiles, or fewer of them, are not read again
known.add(u["frames"][2][1])
assert moves([tile(0), tile(1), tile(2)]) == {} and len(calls) == 3
rec = json.load(open(path))
assert rec["ref"] is None and rec["tiles"] == {} and [k[0] for k in rec["short"]] == [0, 1, 2], rec
for tiles in ([tile(0), tile(1), tile(2)], [tile(0), tile(2)], [tile(1)]):
    assert moves(tiles) == {} and len(calls) == 3, (tiles, calls)
# a tile that sits elsewhere, or whose rings were redrawn since, is another tile: read again
assert moves([tile(0), {**tile(1), "offset": [99.0, 5.0]}]) == {} and len(calls) == 4
# the pass grown by a tile: read again, and the larger set kept
made(3)
assert moves([tile(0), tile(1), tile(2), tile(3)]) == {} and len(calls) == 5
assert [k[0] for k in json.load(open(path))["short"]] == [0, 1, 2, 3]
assert moves([tile(0), tile(1), tile(2)]) == {} and len(calls) == 5
# a pass that does fit later: its reference and moves are kept as before, and never written over by a "short"
made(4)
ref = np.arange(8, dtype=float)
answer[0] = ({4: {"move": [1.5, -2.0], "ncc": [0.1, 0.9], "found": [2, -2], "ok": True}}, ref)
got = moves([tile(n) for n in range(5)])
assert len(calls) == 6 and got == {4: [1.5, -2.0]}, got
rec = json.load(open(path))
assert rec["ref"] and "4" in rec["tiles"], rec
om._keep_ring_short(path, [om._ring_tried(tile(0))])
assert json.load(open(path))["ref"], "a reference was written over"
print("ok")
