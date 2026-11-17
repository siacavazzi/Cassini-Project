"""A filter's mosaic is kept, and grown from, only for the same tiles at the same places (obs_mosaic._places_tag in
its name; filter_mosaic, _grown). Stand-in tiles and a stand-in _over that marks where each tile is drawn:
- _places_tag: nothing for tiles at SPICE's places or with no move, one name per set of moves, the tiles' order and
  the unmoved ones no part of it, a turn part of it;
- filter_mosaic's file: the name it had before for unmoved tiles, another for each set of moves;
- _grown: a mosaic drawn with a tile at one place, then asked for with one more tile after a solve moved that tile,
  has the tile where it is now and nowhere else (kept by its count alone it stayed where it was first drawn: checked
  too, with the names as they were).
Run: python web/test_grown_places.py"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

om.SHARED_SEAMS = False


def tile(n, x, y, move=None, turn=None):
    t = {"n": n, "filter": "CL1/CL2", "box": [0, 0, 4, 4], "offset": [float(x), float(y)]}
    if move is not None:
        t["spice_place"] = [float(x), float(y)]
        t["offset"] = [x + move[0], y + move[1]]
    if turn is not None:
        t["turn"] = turn
    return t


# ---- the tag
plain = [tile(j, 10 * j, 0) for j in range(5)]
assert om._places_tag(plain) == ""
assert om._places_tag([tile(j, 10 * j, 0, (0.0, 0.0)) for j in range(5)]) == ""          # solved, none moved
a = [tile(0, 0, 0, (0.0, 0.0)), tile(1, 10, 0, (3.43, 0.45)), tile(2, 20, 0, (-1.75, -0.75))]
ta = om._places_tag(a)
assert ta.startswith("-m") and len(ta) == 10, ta
assert om._places_tag(list(reversed(a))) == ta                                            # (the order no part of it)
assert om._places_tag(a + [tile(3, 30, 0), tile(4, 40, 0, (0.0, 0.0))]) == ta             # (nor the unmoved)
assert om._places_tag([tile(0, 0, 0, (0.0, 0.0)), tile(1, 10, 0, (3.43, 0.45)), tile(2, 20, 0, (-1.75, -0.74))]) != ta
assert om._places_tag([tile(0, 0, 0, (0.0, 0.0)), tile(1, 10, 0, (3.43, 0.45))]) != ta    # (fewer moved tiles)
assert om._places_tag(a[:2] + [tile(2, 20, 0, (-1.75, -0.75), turn=0.002)]) != ta          # (a turn)
assert om._places_tag([tile(1, 1234.56, -789.01, (3.43, 0.45))]) == om._places_tag([tile(1, 10, 0, (3.43, 0.45))])
print("the tag: by the moved tiles' moves alone")

# ---- the files
u, p = {"key": ("X", "T", "N", 0)}, {"k": 1.0, "display_scale": {"gamma": 2.2}, "colour": None}
rect = (0.0, 0.0, 400.0, 16.0)
drew = []
om._mine = lambda u, p, tiles, f: [t for t in tiles if t["filter"] == f and "offset" in t]
om.dim_places = lambda *a, **k: set()
om._window = lambda u, p, mine, rect, cache: ([], [])     # (a mosaic composed whole: empty here, the first tiles' own)


def over(u, p, rgba, t, rect, cache, match=True, kept=None):
    x, y = round(t["offset"][0]), round(t["offset"][1])
    rgba[y:y + 4, x:x + 4] = (t["n"] + 1, 0, 0, 255)
    drew.append(t["n"])


om._over = over
where = lambda rgba, n: sorted(set(np.nonzero((rgba[..., 0] == n + 1).any(axis=0))[0] // 4 * 4))

with tempfile.TemporaryDirectory() as cache:
    om.drawn = lambda u, c: cache
    os.makedirs(os.path.join(cache, "filters-level"))
    files = lambda: sorted(os.listdir(os.path.join(cache, "filters-level")))
    few = [tile(j, 12 * j, 0) for j in range(3)]
    om.filter_mosaic(u, p, "CL1/CL2", few, rect, cache)
    assert files() == ["CL1_CL2-3-0_0_400_16.png"], files()                                   # (as it was named)
    om.filter_mosaic(u, p, "CL1/CL2", few[:2] + [tile(2, 24, 0, (2.0, 0.0))], rect, cache)
    om.filter_mosaic(u, p, "CL1/CL2", few[:2] + [tile(2, 24, 0, (5.0, 1.0))], rect, cache)
    om.filter_mosaic(u, p, "CL1/CL2", few[:2] + [tile(2, 24, 0, (2.0, 0.0))], rect, cache)   # (found, not another)
    assert len(files()) == 3 and sum("-m" in f for f in files()) == 2, files()
    print("the files: one a set of places")

for fixed in (True, False):
    with tempfile.TemporaryDirectory() as cache:
        om.drawn = lambda u, c: cache
        os.makedirs(os.path.join(cache, "filters-level"))
        om._grown_last.clear()
        real = om._places_tag
        if not fixed:
            om._places_tag = lambda mine: ""       # (the names as they were: by count alone)
        try:
            n = om.GROW_FROM + 2
            first = [tile(j, 12 * j, 0, (0.0, 0.0)) for j in range(n)]
            del drew[:]
            one = om.filter_mosaic(u, p, "CL1/CL2", first, rect, cache)
            assert where(one, n - 1) == [12 * (n - 1)] and where(one, n - 2) == [12 * (n - 2)]
            # a solve on one more tile moves the tile before last by 8 px
            second = first[:n - 1] + [tile(n - 1, 12 * (n - 1), 0, (0.0, 8.0)), tile(n, 12 * n, 0, (0.0, 0.0))]
            del drew[:]
            two = om.filter_mosaic(u, p, "CL1/CL2", second, rect, cache)
            rows = sorted(set(np.nonzero((two[..., 0] == n).any(axis=1))[0]))                 # (rows holding tile n - 1)
            if fixed:
                assert rows == [8, 9, 10, 11], rows                    # where the solve has it now, and only there
                assert drew == [n - 1, n], drew        # (grown from the mosaic of the tiles before it, still good)
            else:
                assert rows == [0, 1, 2, 3] and drew == [n], (rows, drew)   # (where it was first drawn: the fault)
            # the same places again: found, nothing drawn
            del drew[:]
            again = om.filter_mosaic(u, p, "CL1/CL2", second, rect, cache)
            assert (again == two).all() and not drew
        finally:
            om._places_tag = real
    print("grown after a solve moved a tile: "
          + ("drawn where it is now" if fixed else "(names by count alone: it stayed where it was first drawn)"))
print("ok")
