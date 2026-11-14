"""Check the USGS Titan pointing (spice_extra/usgs_titan): its kernels are loaded after a year's kernels, cover every
frame of its image list (plus the WAC frames taken at the same moment, and the frames its correction is carried
over to), and a frame of the list that the geometry cache answered before the
kernels were added is worked out again (once). Run: python web/test_usgs_titan.py"""
import os
import sys
import sqlite3
import tempfile
import atexit, shutil  # noqa: E402
# every temporary folder and file this test makes goes in one folder of its own, removed when the test ends, passed
# or failed (test runs left GBs of folders in TMPDIR, and the Mini's boot drive filled, 2026-11-13)
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)
import types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["CASSINI_GEOMETRY_CACHE"] = os.path.join(tempfile.mkdtemp(), "geometry.sqlite")
os.environ.pop("CASSINI_USGS_TITAN", None)
sys.path.insert(0, ROOT)
import spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

neighbours_ck, ck, spk = ba.extra_kernels()  # in load order: USGS's own last, so they win
frames = ba.usgs_titan_frames()
nac = {line.strip() for line in open(os.path.join(ba.USGS_TITAN_DIR, "images.lis")) if line.strip()}
assert len(nac) == 6896 and all(f.startswith("N") for f in nac), len(nac)
carried = {line.strip() for line in open(os.path.join(ba.USGS_TITAN_DIR, "neighbours.lis")) if line.strip()}
assert len(frames) == 6896 + 44 + len(carried) and not carried & nac
# the carried-over correction: one segment per frame of neighbours.lis, in the same frame as USGS's
assert list(sp.ckobj(neighbours_ck)) == [-82000]
handle, ids = sp.dafopr(neighbours_ck), []
sp.dafbfs(handle)
while sp.daffna():
    ids.append(sp.dafgn())
sp.dafcls(handle)
assert sorted(ids) == sorted(carried), (len(ids), len(carried))
# one segment per image: Cassini's attitude (-82000) and Cassini (-82) relative to Titan (606)
assert list(sp.ckobj(ck)) == [-82000] and list(sp.spkobj(spk)) == [-82]
assert sp.wncard(sp.ckcov(ck, -82000, False, "INTERVAL", 0.0, "SCLK")) == len(nac)

# a USGS frame cached without the USGS tag is worked out again; once stored it is tagged and answered from the cache
row = lambda frame: (frame, ba.GEOMETRY_VERSION, 1.0, 2.0, 3.0, 4.0, 5.0, "CASSINI_ISS_NAC", "TITAN", 6.0, None)
label = lambda frame: types.SimpleNamespace(info={"path": frame + ".png", "TARGET_NAME": "TITAN"})
usgs, other = "N1477358900_1", "N1477358900_9"
assert usgs in frames and other not in frames
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
ba._geometry_db()
db.executemany("INSERT INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [row(usgs), row(other)])
db.commit()
assert ba.cached_target(label(usgs)) is None
assert ba.cached_target(label(other)) == [1.0, 2.0, 3.0, 4.0]
ba._store_rows([row(usgs), row(other)])
assert ba.cached_target(label(usgs)) == [1.0, 2.0, 3.0, 4.0]
assert db.execute("SELECT frame FROM pointing").fetchall() == [(usgs,)]

# switched off: no extra kernels, no frames, and the cache answers as before
os.environ["CASSINI_USGS_TITAN"] = "0"
ba._usgs_frames = None
assert ba.extra_kernels() == [] and ba.usgs_titan_frames() == set()
print("ok")
