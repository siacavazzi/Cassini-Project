"""obs_mosaic.one_source: a sequence the pictures place under STEADY_MIXED of goes whole on SPICE's smoothed path (one
source of pointing, Sam 2026-11-18); one they place most of keeps its places. Run: python web/test_steady_one_sequence.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import obs_mosaic as om  # noqa: E402

made = [{"n": n, "offset": [10.0 * n + (3.0 if n % 2 else -3.0), 0.0]} for n in range(10)]   # SPICE: 10 px a frame, scattered 3 px
chain = {n: [10.0 * n + 0.5, 0.0] for n in range(10)}
mostly = {n: ("linked to [0]" if n < 8 else "held from the tile before (no match)") for n in range(10)}
places, hows = om.one_source(chain, mostly, made)
assert places is chain and hows is mostly
few = {n: ("linked to [0]" if n < 3 else "held from the tile before (no match)") for n in range(10)}
places, hows = om.one_source(chain, few, made)
assert all(h.startswith("held on SPICE's smoothed path") for h in hows.values()), hows
steps = [places[n + 1][0] - places[n][0] for n in range(9)]
assert max(abs(s - 10.0) for s in steps) < 1.0, steps   # (the smoothed path: SPICE's 3 px scatter out, no hop)
print("a sequence the pictures place under half of goes whole on SPICE's smoothed path: ok")
