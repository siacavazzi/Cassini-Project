"""obs_mosaic.one_source: a sequence the pictures place under STEADY_MIXED of goes whole on SPICE's smoothed path (one
source of pointing, Sam 2026-11-18); one they place most of keeps its places, its unmatched frames put between them (from_pictures). Run: python web/test_steady_one_sequence.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import obs_mosaic as om  # noqa: E402

made = [{"n": n, "t": 100.0 * n, "offset": [10.0 * n + (3.0 if n % 2 else -3.0), 0.0]} for n in range(10)]   # SPICE: 10 px a frame, scattered 3 px
chain = {n: [10.0 * n + 0.5, 0.0] for n in range(10)}
mostly = {n: ("linked to [0]" if n < 8 else "held from the tile before (no match)") for n in range(10)}
places, hows = om.one_source(chain, mostly, made)
assert all(places[n] == chain[n] for n in range(8)) and all(not h.startswith("held") for h in hows.values())
few = {n: ("linked to [0]" if n < 3 else "held from the tile before (no match)") for n in range(10)}
places, hows = om.one_source(chain, few, made)
assert all(h.startswith("held on SPICE's smoothed path") for h in hows.values()), hows
steps = [places[n + 1][0] - places[n][0] for n in range(9)]
assert max(abs(s - 10.0) for s in steps) < 1.0, steps   # (the smoothed path: SPICE's 3 px scatter out, no hop)
print("a sequence the pictures place under half of goes whole on SPICE's smoothed path: ok")

# (a sequence the pictures place most of: its unmatched frames go between the pictures' own places, not SPICE's step)
mixed = {n: ("held from the tile before (no match)" if n in (3, 4, 9) else "linked to [0]") for n in range(10)}
spicey = {**chain, 3: [33.0, 2.0], 4: [37.0, -2.0], 9: [99.0, 4.0]}   # (held: SPICE's scattered step)
places, hows = om.one_source(spicey, mixed, made)
assert abs(places[3][0] - (chain[2][0] + (chain[5][0] - chain[2][0]) / 3)) < 1e-6 and places[3][1] == 0.0, places[3]
assert abs(places[4][0] - (chain[2][0] + 2 * (chain[5][0] - chain[2][0]) / 3)) < 1e-6, places[4]
assert abs(places[9][0] - (chain[8][0] + 10.0)) < 1e-6 and places[9][1] == 0.0, places[9]   # (past the end: their step)
assert all(places[n] == chain[n] for n in range(10) if n not in (3, 4, 9))
assert not any(str(h).startswith("held") for h in hows.values()), hows
steps = [places[n + 1][0] - places[n][0] for n in range(9)]
assert max(abs(s - 10.0) for s in steps) < 1e-6, steps
print("a sequence the pictures place most of: its unmatched frames go between the pictures' places: ok")

# (by time, not frame number: frame 1 taken just after frame 0, frame 2 long after)
uneven = [{"n": 0, "t": 0.0, "offset": [0.0, 0.0]}, {"n": 1, "t": 10.0, "offset": [0.0, 0.0]},
          {"n": 2, "t": 100.0, "offset": [0.0, 0.0]}]
places, hows = om.from_pictures({0: [0.0, 0.0], 1: [55.0, 0.0], 2: [100.0, 0.0]}, {0: "first", 1: "held", 2: "linked"},
                                {1}, {0: 0.0, 1: 10.0, 2: 100.0})
assert abs(places[1][0] - 10.0) < 1e-6, places
print("an unmatched frame goes between the pictures' places by when it was taken: ok")

# (pictures that disagree with themselves: the whole sequence on SPICE's smoothed path, even when they place most of it)
places, hows = om.one_source(chain, {n: "linked to [0]" for n in range(10)}, made, {"res_p90": 12.0})
assert all(h.startswith("held on SPICE's smoothed path") for h in hows.values()), hows
places, hows = om.one_source(chain, {n: "linked to [0]" for n in range(10)}, made, {"res_p90": 0.4})
assert places is chain
print("a sequence whose pictures disagree goes whole on SPICE's smoothed path: ok")
