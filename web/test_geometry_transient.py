"""A transient SPICE failure (the run's, not the frame's) is never the geometry cache's answer for a frame: it is not
stored (find_target_cached retries once, then raises without storing), a stored one is worked out again
(cached_target), and a frame's own errors (no coverage, an unknown name, behind the camera) stay cached answers.
Run: python web/test_geometry_transient.py"""
import os
import sys
import sqlite3
import tempfile
import atexit, shutil  # noqa: E402
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)
import types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["CASSINI_GEOMETRY_CACHE"] = os.path.join(tempfile.mkdtemp(), "geometry.sqlite")
sys.path.insert(0, ROOT)
import bootleg_autonav as ba  # noqa: E402

OPEN = ("SpiceFILEOPENFAIL: ===== Attempt to reconnect logical unit to file "
        "'/x/spice_cache/cosp_1000/data/spk/050214R_SCPSE_04336_05015.bsp'.")
assert ba.transient(OPEN) and ba.transient("SpiceNOMOREUNITS: no more logical units") and ba.transient(OSError("disk"))
for own in ("SpiceSPKINSUFFDATA: ===== Insufficient ephemeris data", "NotFoundError: Spice returns not found for function: bodn2c",
            "ValueError: SATURN is behind the camera"):
    assert not ba.transient(own), own

row = lambda frame, error: (frame, ba.GEOMETRY_VERSION, None, None, None, None, None, None, None, None, error)
label = lambda frame: types.SimpleNamespace(info={"path": frame + ".png", "TARGET_NAME": "PHOEBE"})
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
ba._geometry_db()
db.executemany("INSERT INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               [row("N1465536850_1", OPEN), row("N1465536851_1", "SpiceSPKINSUFFDATA: no coverage")])
db.commit()
# a stored transient failure is not an answer (worked out again); the frame's own error still is
assert ba.cached_target(label("N1465536850_1")) is None
try:
    ba.cached_target(label("N1465536851_1"))
    raise AssertionError("a frame's own error is its answer")
except ValueError as e:
    assert "SPKINSUFFDATA" in str(e)

# find_target_cached: a transient failure is retried once (with the year's kernels loaded again) and never stored
calls, loads = [], []
real = ba.find_target


def flaky(lbl, *a):
    calls.append(1)
    if len(calls) == 1:
        raise RuntimeError(OPEN)
    lbl.geometry = {"et": 1.0, "camera": "CASSINI_ISS_NAC", "target": "PHOEBE", "center": ba.CCD_CENTER, "scale": 1.0}
    return [10.0, 20.0, 30.0, 0.0]


def failing(lbl, *a):
    calls.append(1)
    raise RuntimeError(OPEN)


try:
    ba.find_target = flaky
    ba.shown_place = lambda lbl, loc: loc
    ba.linearized = lambda lbl, loc: loc
    assert ba.find_target_cached(label("N1465536850_1"), lambda force=False: loads.append(force)) == [10.0, 20.0, 30.0, 0.0]
    assert len(calls) == 2 and loads == [False, True]   # (the retry loads the year afresh)
    got = db.execute("SELECT x, error FROM target WHERE frame = 'N1465536850_1'").fetchone()
    assert got == (10.0, None), got
    calls.clear()
    ba.find_target = failing
    try:
        ba.find_target_cached(label("N1465536852_1"), lambda force=False: None)
        raise AssertionError("a failure that persists is raised")
    except RuntimeError:
        pass
    assert len(calls) == 2
    assert db.execute("SELECT count(*) FROM target WHERE frame = 'N1465536852_1'").fetchone() == (0,)   # not stored
finally:
    ba.find_target = real
print("ok")
