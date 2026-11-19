"""Every movie pass with a stabilization chain kept is stabilized with stabilization off (obs_mosaic.auto_steady,
steady_of): one source of pointing for a whole sequence (Sam 2026-11-18; until then only passes whose SPICE places
jumped, 133TI CLOUD002, or raw-attitude ones were, and 293EN ENCSET001 played SPICE's 3 to 26 px scatter). A pass with
no chain kept yet and a feature track are drawn as before.
Run: python web/test_steady_auto.py"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import obs_mosaic as om  # noqa: E402

tmp = tempfile.mkdtemp()


import bootleg_autonav as ba  # noqa: E402
OWN = {f"N{i}_1" for i in range(20)}
ba._own_frames = OWN   # every frame of these passes has its own measured pointing, unless raw= says otherwise


def run(spice, chain, track=False, keep_chain=True, raw=False, linked=1.0):
    d = tempfile.mkdtemp(dir=tmp)
    if keep_chain:
        hows = {"0": "first"}
        hows.update({str(n): "linked to [%d]" % (n - 1) if n <= linked * (len(chain) - 1) else "SPICE (no link)"
                     for n in range(1, len(chain))})
        with open(os.path.join(d, om.STEADY_FILE), "w") as fh:
            json.dump({"places": {str(n): xy for n, xy in enumerate(chain)}, "how": hows}, fh)
    ids = [f"N{i}_1" if not (raw and i == 3) else "N999_1" for i in range(len(spice))]
    u = {"key": ("TITAN", "X", "N", 0), "frames": [("p", f) for f in ids], **({"track": True} if track else {})}
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
shake = [[0.0, 40.0 + 0.3 * n + (2.5 if n % 2 else -2.5)] for n in range(20)]
# one source of pointing for a whole sequence (Sam 2026-11-18): every movie pass whose chain is kept plays steadied by
# default, whether SPICE jumps 14 px, shakes 2.5 px or follows the pictures, on its own pointing or not, and however few
# of its frames the pictures could place (the rest go on along SPICE's smoothed path, _chain_links); a setting stands
for spice in (jumpy, still, shake):
    for raw in (False, True):
        for linked in (1.0, 0.5, 0.0):
            assert run(spice, still, raw=raw, linked=linked) == (om.STEADY_SMOOTH, 4, 0), (raw, linked)
assert run(jumpy, still, keep_chain=False) == (0, 4, 0)                    # no chain kept yet: SPICE's places
assert run(jumpy, still, track=True) == (0, 0, 0)                          # a feature track: as before
print("every movie pass with a chain plays steadied: ok")

# prebuild.make_pass works out a movie's chain before its first frame, so auto_steady is decided for every frame
import prebuild  # noqa: E402
calls = []
was = (om.plan, om.tile, om.steady_chain, om.movie_webp)
om.plan = lambda u, cache: {"display_scale": {}}
om.tile = lambda u, j, cache, scale=None: calls.append("tile")
om.steady_chain = lambda u, cache, p=None: calls.append("chain")
om.movie_webp = lambda *a, **k: calls.append("frame")
try:
    prebuild.make_pass({"key": ("TITAN", "X", "N", 0), "frames": [("p", f"N{i}_1", "CB3", float(i), 938.0, 0, 0, 1e6) for i in range(3)],
                        "mosaic": False, "kind": "movie"}, "/c")
finally:
    om.plan, om.tile, om.steady_chain, om.movie_webp = was
assert calls.index("chain") < calls.index("frame") and calls.count("chain") == 1, calls
print("make_pass: chain before the first frame; ok")
