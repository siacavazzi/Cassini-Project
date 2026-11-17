"""calibration.let_go (the calibration's kept tables let go) and where the pre-build asks for it (prebuild.make_pass,
once a pass's tiles are made, only in a pre-build making one pass at a time):
- each of the six kept makers is cleared, and what one makes afterwards is what it made before (the WAC distortion
  correction's plan and a frame corrected with it, to the bit);
- make_pass asks after the last tile and before the pass's solve and pictures, once, and not at all when the switch
  is off (a server's stretch, several passes at once).
Run: python web/test_calibration_let_go.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic  # noqa: E402
import prebuild  # noqa: E402
import calibration  # noqa: E402
import dark_current as dc  # noqa: E402
import flat_field as ff  # noqa: E402
import geometric_correction as gc  # noqa: E402

# ---- the six makers are cleared; a plan made again is the plan
rng = np.random.default_rng(7)
frame = rng.uniform(0, 1, (256, 256)).astype(np.float32)
before, bad = gc.geomcorr(frame, 200.7)
plan = gc._plan(256, 200.7)
assert gc._plan.cache_info().currsize >= 1 and gc._map.cache_info().currsize >= 1
cleared = []
real = {}
for mod, name in ((dc, "_parameters"), (dc, "_dark"), (ff, "_map"), (ff, "_correction")):
    kept = getattr(mod, name)
    real[(mod, name)] = kept.cache_clear
    kept.cache_clear = lambda mod=mod, name=name: (cleared.append((mod.__name__, name)), real[(mod, name)]())[1]
try:
    calibration.let_go()
finally:
    for (mod, name), clear in real.items():
        getattr(mod, name).cache_clear = clear
assert sorted(cleared) == [("dark_current", "_dark"), ("dark_current", "_parameters"), ("flat_field", "_correction"),
                           ("flat_field", "_map")], cleared
assert gc._plan.cache_info().currsize == 0 and gc._map.cache_info().currsize == 0
again, bad2 = gc.geomcorr(frame, 200.7)
assert again.tobytes() == before.tobytes() and bad2.tobytes() == bad.tobytes()
plan2 = gc._plan(256, 200.7)
assert plan2 is not plan and plan2[0] == plan[0] and plan2[1] == plan[1]
assert all(a.tobytes() == b.tobytes() for a, b in zip([plan[2][0], *plan[2][1], plan[2][2], *plan[2][3]],
                                                      [plan2[2][0], *plan2[2][1], plan2[2][2], *plan2[2][3]]))
print("let_go: the six kept makers cleared; a plan made again is the same plan, a frame corrected again the same frame")

# ---- where make_pass asks
did = []
obs_mosaic.plan = lambda u, cache: did.append("plan") or {"display_scale": {}}
obs_mosaic.tile = lambda u, j, cache, scale: did.append(f"tile{j}")
obs_mosaic.keep_reports = lambda u, cache, p: did.append("reports")
obs_mosaic.solve_places = lambda u, cache: did.append("solve")
obs_mosaic._mosaic_made = lambda u, j, size, cache: False
obs_mosaic._mosaic_at = lambda u, j, size, cache: did.append("mosaic")
obs_mosaic.movie_webp = lambda fid, size, cache, *a, **k: did.append("movie")
obs_mosaic.rolling_webp = lambda fid, size, cache, *a, **k: did.append("rolling")
obs_mosaic.tile_map = lambda fid, cache: None
calibration.let_go, let_go = (lambda: did.append("let go")), calibration.let_go


def unit(kind):
    return {"kind": kind, "mosaic": kind in ("mosaic", "mosaic_movie"), "tossup": False,
            "frames": [(None, f"F{j}", "CL1", 100.0 + j) for j in range(3)]}


try:
    for kind in ("mosaic", "movie", "mosaic_movie"):
        for on in (True, False):
            del did[:]
            prebuild._let_go[0] = on
            assert prebuild.make_pass(unit(kind), "/c") == 3
            assert did.count("let go") == (1 if on else 0), (kind, on, did)
            if on:
                at = did.index("let go")
                assert did[:at] == ["plan", "tile0", "tile1", "tile2"], did       # (after the last tile)
                assert not any(x.startswith("tile") or x == "plan" for x in did[at + 1:]) and len(did) > at + 1
finally:
    calibration.let_go = let_go
    prebuild._let_go[0] = False
print("make_pass: asked once, after the last tile and before the solve and the pictures; never with the switch off")
print("ok")
