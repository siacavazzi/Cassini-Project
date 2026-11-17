"""Geometry rows worked out with other pointing than the code's (bootleg_autonav.stale_frames) are listed, and leave the
list once refreshed: a tagged frame stored under an earlier tag, and a frame no longer tagged whose pointing row
still names extra kernels (its row is dropped when it is stored untagged). Run: python web/test_stale_pointing.py"""
import os
import sys
import sqlite3
import tempfile
import atexit, shutil  # noqa: E402
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["CASSINI_GEOMETRY_CACHE"] = os.path.join(tempfile.mkdtemp(), "geometry.sqlite")
sys.path.insert(0, ROOT)
import bootleg_autonav as ba  # noqa: E402

TAGGED, UNTAGGED = "N1500000000_1", "N1500000001_1"
ba.usgs_titan_frames = lambda: {TAGGED}
ba.iss_neighbours_frames = lambda: set()
ba.pointing_tags = lambda: ("usgs-new", "neighbours-new")
row = lambda frame: (frame, ba.GEOMETRY_VERSION, 1.0, 2.0, 3.0, 4.0, 5.0, "CASSINI_ISS_NAC", "TITAN", 6.0, None)
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
ba._geometry_db()
db.executemany("INSERT INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [row(TAGGED), row(UNTAGGED)])
# the tagged frame under an earlier kernel's tag; the other frame no longer tagged, its row still naming the kernels
db.executemany("INSERT INTO pointing VALUES (?, ?)", [(TAGGED, "usgs-old"), (UNTAGGED, "neighbours-old")])
db.commit()
assert ba.stale_frames() == [TAGGED, UNTAGGED], ba.stale_frames()

# the refresh: each worked out again (here stored as the fill stores them) and gone from the list
done = []


def fill(frames=None, **_):
    done.append(sorted(frames))
    ba._store_rows([row(f) for f in frames])


ba.build_geometry_cache = fill
assert ba.refresh_stale(quiet=True) == 2 and done == [[TAGGED, UNTAGGED]]
assert ba.stale_frames() == []
assert dict(db.execute("SELECT frame, kernels FROM pointing")) == {TAGGED: "usgs-new"}   # (the untagged row dropped)
assert ba.refresh_stale(quiet=True) == 0 and len(done) == 1   # (nothing left: no work at the next start)

# a stale frame the fill cannot work out (not in its index): its rows dropped, worked out on demand, not listed again
db.execute("INSERT OR REPLACE INTO pointing VALUES (?, ?)", (TAGGED, "usgs-old"))
db.commit()
ba.build_geometry_cache = lambda frames=None, **_: None
assert ba.refresh_stale(quiet=True) == 1 and ba.stale_frames() == []
assert db.execute("SELECT count(*) FROM target WHERE frame = ?", (TAGGED,)).fetchone() == (0,)
print("ok")
