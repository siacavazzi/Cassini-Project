"""A movie pass whose SPICE places jump frame to frame against what its pictures show (its stabilization chain) is
stabilized with stabilization off (obs_mosaic.auto_steady, steady_of): 133TI CLOUD002's SPICE places jumped 24 to 54
px between frames 40 s apart while Titan held still (Sam 11-16). A pass whose SPICE places follow the chain, one
with no chain kept yet, and a feature track are drawn as before.
Run: python web/test_steady_auto.py"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import obs_mosaic as om  # noqa: E402

tmp = tempfile.mkdtemp()


def run(spice, chain, track=False, keep_chain=True):
    d = tempfile.mkdtemp(dir=tmp)
    if keep_chain:
        with open(os.path.join(d, om.STEADY_FILE), "w") as fh:
            json.dump({"places": {str(n): xy for n, xy in enumerate(chain)}}, fh)
    u = {"key": ("TITAN", "X", "N", 0), "frames": [None] * len(spice), **({"track": True} if track else {})}
    was = om.folder, om._plan_if_made, om.tile
    om.folder = lambda u, cache: d
    om._plan_if_made = lambda u, cache: {"display_scale": {}}
    om.tile = lambda u, n, cache, scale=None: {"offset": spice[n]}
    try:
        om._auto_steady.clear()
        return om.steady_of(u, 0, "cache"), om.steady_of(u, 4, "cache"), om.steady_of(u, 0)
    finally:
        om.folder, om._plan_if_made, om.tile = was


still = [[0.0, 40.0 + 0.3 * n] for n in range(20)]
jumpy = [[0.0, 40.0 + 0.3 * n + (14 if n % 3 else -14)] for n in range(20)]
assert run(jumpy, still) == (om.STEADY_SMOOTH, 4, 0), run(jumpy, still)   # jumps: steady by default; a setting stands
assert run(still, still) == (0, 4, 0)                                      # SPICE follows the pictures: as before
drift = [[0.0, 40.0 + 3.0 * n] for n in range(20)]
assert run(drift, still) == (0, 4, 0)                                      # a slow drift is no jump
assert run(jumpy, still, keep_chain=False) == (0, 4, 0)                    # no chain kept: SPICE's places
assert run(jumpy, still, track=True) == (0, 0, 0)                          # a feature track: as before
print("auto stabilization of passes SPICE places jump in: ok")
