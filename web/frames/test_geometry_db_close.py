#!/usr/bin/env python3
"""
Checks that each thread's geometry cache connection (bootleg_autonav._geometry_db) is closed when the thread ends:
400 short threads, as the frame server's request threads, must leave no .sqlite or -wal file open.

  python web/frames/test_geometry_db_close.py
"""
import os, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
db = os.path.join(tempfile.mkdtemp(), "geometry.sqlite")
os.environ["CASSINI_GEOMETRY_CACHE"] = db
import bootleg_autonav as ba  # noqa: E402
ba.GEOMETRY_CACHE = db


def open_files():
    return len(os.listdir("/dev/fd"))


def request():
    ba._geometry_db().execute("SELECT count(*) FROM target").fetchone()


before = open_files()
for _ in range(400):
    t = threading.Thread(target=request)
    t.start()
    t.join()
left = open_files() - before
assert left <= 2, f"{left} files left open by 400 finished threads"
request()   # the main thread's own connection still works
print(f"ok: 400 threads, {left} files left open")
