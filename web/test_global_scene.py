"""obs_mosaic.global_places on test_panel_register.py's scene: a 2x2 mosaic of one cratered surface whose pointings SPICE
put a few px off, each differently. The pointings land on one another within a fraction of a pixel (relative to the
first; the solve holds their average on SPICE), the second filter at a pointing moves with it, the pass's solve is kept,
a mosaic of fewer tiles takes its pointings' places from the whole pass's solve (the pre-build's, solve_places) and never
writes over it, and Settings > Processing's panels step off gives SPICE's places.
Run: python web/test_global_scene.py"""
import os
import runpy
import sys

os.environ["CASSINI_GLOBAL_PANELS"] = "1"
sys.argv = ["x"]
# the scene (surface, plan_, reports, tiles_in, u, p, err) from test_panel_register.py, without its checks
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "test_panel_register.py")).read()
scene = src[:src.index("cache = tempfile.mkdtemp()")].replace('os.environ["CASSINI_GLOBAL_PANELS"] = "0"', "")
g = {"__file__": os.path.join(here, "test_panel_register.py"), "__name__": "scene"}
exec(compile(scene, "test_panel_register_scene", "exec"), g)
om, tempfile, json, cal = g["om"], g["tempfile"], g["json"], g["cal"]
reports, plan_, err, tiles_in, u, p = g["reports"], g["plan_"], g["err"], g["tiles_in"], g["u"], g["p"]
assert om.GLOBAL_PANELS

cache = tempfile.mkdtemp()
tiles_in(cache)
moved = om.panel_places(u, cache, p, reports)
m0 = moved.get(0, [0, 0])
for i, (q, f) in enumerate(plan_):
    want = (err[0][0] - err[q][0] + m0[0], err[0][1] - err[q][1] + m0[1])
    got = moved.get(i, [0, 0])
    assert abs(got[0] - want[0]) < 0.35 and abs(got[1] - want[1]) < 0.35, (i, want, got)
assert moved[4] == moved[1], "the second filter moves with its pointing"
print("global: pointings land on one another")

# a mosaic of the first 3 tiles takes the whole pass's places, and the kept solve still holds all 5
fewer = om.panel_places(u, cache, p, reports[:3])
assert fewer == {n: v for n, v in moved.items() if n < 3}, (fewer, moved)
path = [f for f in os.listdir(om.folder(u, cache)) if f.startswith("global1-")]
assert len(path) == 1 and json.load(open(os.path.join(om.folder(u, cache), path[0])))["tiles"] == [0, 1, 2, 3, 4]
print("global: fewer tiles take the pass's solve")

# a fresh pass grown a tile at a time: a smaller solve is never kept over a larger one
cache2 = tempfile.mkdtemp()
tiles_in(cache2)
om.panel_places(u, cache2, p, reports)
om.panel_places(u, cache2, p, reports[:2])
kept = json.load(open(os.path.join(om.folder(u, cache2), path[0])))
assert kept["tiles"] == [0, 1, 2, 3, 4]
print("global: the larger solve is kept")

# a server that solved fewer tiles (kept in its memory) never writes over a larger solve another process (the
# pre-build) kept on disk meanwhile: it reads that one and draws from it
cache3 = tempfile.mkdtemp()
tiles_in(cache3)
small = om.panel_places(u, cache3, p, reports[:3])
full = json.load(open(os.path.join(om.folder(u, cache2), path[0])))
json.dump(full, open(os.path.join(om.folder(u, cache3), path[0]), "w"))
four = om.panel_places(u, cache3, p, reports[:4])
assert json.load(open(os.path.join(om.folder(u, cache3), path[0])))["tiles"] == [0, 1, 2, 3, 4]
assert four == {n: v for n, v in full["moves"].items() if int(n) < 4 and v != [0, 0]} or \
    four == {int(n): v for n, v in full["moves"].items() if int(n) < 4 and v != [0, 0]}, (four, full["moves"])
print("global: a larger solve on disk wins over a smaller one in memory")

with cal.stepping("panels"):
    assert om.panel_places(u, tempfile.mkdtemp(), p, reports) == {}
print("global: panels step off gives SPICE's places")
print("global scene: ok")
