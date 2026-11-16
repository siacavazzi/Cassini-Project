"""Check the ISS neighbours pointing (spice_extra/iss_smithed): JPL's per-image corrected pointing carried over to the
other frames of the same observations, so none mixes corrected and raw pointing. Its CK is loaded before USGS's,
holds one segment per frame of its list, none of them a frame the USGS kernels cover, and a frame of the list that
the geometry cache answered before the CK was added is worked out again (once). Run: python web/test_iss_neighbours.py"""
import os
import sys
import sqlite3
import tempfile
import types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["CASSINI_GEOMETRY_CACHE"] = os.path.join(tempfile.mkdtemp(), "geometry.sqlite")
os.environ.pop("CASSINI_ISS_NEIGHBOURS", None)
os.environ.pop("CASSINI_USGS_TITAN", None)
sys.path.insert(0, ROOT)
import spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

ck = ba.extra_kernels()[0]
assert os.path.basename(ck) == ba.ISS_NEIGHBOURS_CK
frames = ba.iss_neighbours_frames()
assert len(frames) > 50000 and not frames & ba.usgs_titan_frames(), len(frames)
assert list(sp.ckobj(ck)) == [-82000]
handle, ids = sp.dafopr(ck), []
sp.dafbfs(handle)
while sp.daffna():
    ids.append(sp.dafgn())
sp.dafcls(handle)
assert sorted(ids) == sorted(frames), (len(ids), len(frames))

# a carried frame cached without the tag is worked out again; once stored it is tagged and answered from the cache
row = lambda frame: (frame, ba.GEOMETRY_VERSION, 1.0, 2.0, 3.0, 4.0, 5.0, "CASSINI_ISS_NAC", "SATURN", 6.0, None)
label = lambda frame: types.SimpleNamespace(info={"path": frame + ".png", "TARGET_NAME": "SATURN"})
carried = "N1492052831_3"   # 2005-04-13 ring movie ISS_006RI_LPHRLFMOV001: raw beside smithed frames 27 px off
other = "N1492052646_1"     # its smithed neighbour: the mission kernels' own
assert carried in frames and other not in frames
assert ba.pointing_tag(carried) == ba.pointing_tags()[1] and ba.pointing_tags()[1].startswith(ba.ISS_NEIGHBOURS_TAG + "-") and ba.pointing_tag(other) is None
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
ba._geometry_db()
db.executemany("INSERT INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [row(carried), row(other)])
db.commit()
assert ba.cached_target(label(carried)) is None
assert ba.cached_target(label(other)) == [1.0, 2.0, 3.0, 4.0]
ba._store_rows([row(carried), row(other)])
assert ba.cached_target(label(carried)) == [1.0, 2.0, 3.0, 4.0]
assert db.execute("SELECT frame, kernels FROM pointing").fetchall() == [(carried, ba.pointing_tags()[1])]

# switched off: no CK, no frames
os.environ["CASSINI_ISS_NEIGHBOURS"] = "0"
ba._iss_frames = None
assert os.path.basename(ba.extra_kernels()[0]) != ba.ISS_NEIGHBOURS_CK and ba.iss_neighbours_frames() == set()
print("ok")

# a pass holding a repointed frame takes its own folder (obs_mosaic.REPOINTED), so it is made again; others keep theirs
os.environ["CASSINI_ISS_NEIGHBOURS"] = "1"
ba._iss_frames = None
sys.path.insert(0, os.path.join(ROOT, "web", "frames"))
import obs_mosaic as om  # noqa: E402
om._repointed_frames = None
u = lambda ids: {"key": ("SATURN", "X", "N", 0), "frames": [("p", i, "CL1/CL2", 0.0, 650.0, 0, 0, 1e6) for i in ids]}
assert om._repointed(u([other, carried])) and not om._repointed(u([other]))
assert om.folder(u([other, carried]), "/c").endswith("_sp1")
print("repointed passes: ok")

# the tag follows the CK's content: a regenerated CK is a new tag, so rows kept with the old one are worked out again
ba._tags = None
was = ba.pointing_tags()[1]
ba._tags = None
real = ba._content_tag
ba._content_tag = lambda name, paths: real(name, paths) + ("x" if name == ba.ISS_NEIGHBOURS_TAG else "")
assert ba.pointing_tags()[1] != was
ba._content_tag, ba._tags = real, None
print("pointing tags follow the kernels' content: ok")
