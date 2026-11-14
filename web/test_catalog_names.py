"""Check that every target name in Image_index.csv that is a body SPICE can place resolves (bodn2c), the ones NAIF's
own table doesn't know through bootleg_autonav.CATALOG_NAMES, and that a frame the geometry cache holds as failed
for an unknown name is worked out again. Run: python web/test_catalog_names.py"""
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
sys.path.insert(0, ROOT)
import pandas as pd  # noqa: E402
import spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

# the catalog names that aren't a body (sky, stars, an asteroid, unknown) and the three moons whose SPK places
# are off their frames (bootleg_autonav.CATALOG_NAMES)
NOT_BODIES = {"SKY", "DARKSKY", "UNK", "NONE", "SPICA", "FOMALHAUT", "MASURSKY", "S8_2004", "S14_2004", "S18_2004"}
names = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), usecols=["TARGET_NAME"], low_memory=False)["TARGET_NAME"]
unknown = sorted(n for n in names.dropna().unique() if n not in NOT_BODIES and not ba._known(n))
assert not unknown, unknown
assert sp.bodn2c("HYROKKIN") == sp.bodn2c("HYRROKKIN") == 644
assert sp.bodn2c("K07S4") == sp.bodn2c("ANTHE") == 649

# a failed frame of a registered name is not answered from the cache; other failures still are
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
ba._geometry_db()
db.executemany("INSERT INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
    ("N1817552038_1", ba.GEOMETRY_VERSION, *[None] * 8, f"NotFoundError: {ba.UNKNOWN_NAME}"),
    ("N1000000000_1", ba.GEOMETRY_VERSION, *[None] * 8, f"NotFoundError: {ba.UNKNOWN_NAME}"),
    ("N1000000001_1", ba.GEOMETRY_VERSION, *[None] * 8, "ValueError: HYROKKIN is behind the camera")])
db.commit()
label = lambda frame, target: types.SimpleNamespace(info={"path": frame + ".png", "TARGET_NAME": target})
assert ba.cached_target(label("N1817552038_1", "HYROKKIN")) is None
for frame, target in (("N1000000000_1", "SKY"), ("N1000000001_1", "HYROKKIN")):
    try:
        ba.cached_target(label(frame, target))
        raise AssertionError(frame)
    except ValueError:
        pass
print("ok")
