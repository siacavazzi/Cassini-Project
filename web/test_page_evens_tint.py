"""obs_mosaic.page_evens agrees with the page's want() (steady-local.html): a colour pass with a frame drawn in its set's
colour (the steady table's "tint") is evened by the server for that frame, so the pass is not one the page evens by
itself, and the pre-build makes its exposure= frames (prebuild.make_evened). Before, the tint was not looked at: a
Jupiter WAC movie (C23RI RMOV001, all 71 frames tinted) had no evened frames in the cache, and a Pre-process drew
them on demand, one at a time (the slow end of its bar).
Run: python web/test_page_evens_tint.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402
import prebuild  # noqa: E402

table = {}
om.plan = lambda u, cache: {}
om.steady_chain = lambda u, cache, p: {}
om.exposure_chain = lambda u, cache, p, *how: {}
om._steady_table = lambda u, n, cache, centre, colour: dict(table)
om.calibration.step = lambda name: True
u = {"key": ("JUPITER", "ISS_C23RI_RMOV001_PRIME", "W", 0), "frames": [(None, f"W{j}_1", "RED", float(j)) for j in range(3)]}

base = {"local": True, "exposure": {"local": True}, "colour": True, "sets": {"by": {}}, "tint": []}
table.update(base)
assert om.page_evens(u, "/nowhere") is True
table.update(tint=[0, 1, 2])   # every frame drawn in its set's colour: the server evens them
assert om.page_evens(u, "/nowhere") is False
assert om.page_evens(u, "/nowhere", colour=False) is True   # grey frames: no tint, the page evens them
table.update(tint=[1])         # one tinted frame is enough: the window asks the pass's frames with exposure=
assert om.page_evens(u, "/nowhere") is False

# make_evened makes the tinted pass's evened frames, at both sizes, and none for a pass the page evens
made = []
om.movie_webp = lambda fid, size, cache, *a, **k: made.append((fid, size, k.get("exposure")))
prebuild.make_evened(u, "/nowhere")
assert len(made) == 6 and {m[2] for m in made} == {om.EXPOSURE_SMOOTH}, made
made.clear()
table.update(tint=[])
prebuild.make_evened(u, "/nowhere")
assert made == [], made
print("ok")
