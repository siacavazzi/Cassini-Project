#!/usr/bin/env python3
"""
Checks that the frame server refuses to serve a site with no replay data (a fresh worktree: build_data.py not run),
and starts for one with mission.json or a single year's bodies.json:

  python web/frames/test_replay_data_check.py
"""
import os, subprocess, sys, tempfile
import atexit, shutil  # noqa: E402
# every temporary folder and file this test makes goes in one folder of its own, removed when the test ends, passed
# or failed (test runs left GBs of folders in TMPDIR, and the Mini's boot drive filled, 2026-11-13)
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["FRAME_SERVER_QUIET"] = "1"
import frame_server  # noqa: E402

tmp = tempfile.mkdtemp()
site = os.path.join(tmp, "site")
os.makedirs(os.path.join(site, "data", "models"))           # the tracked models only: what a fresh worktree has
msg = frame_server.replay_data_missing(site)
assert msg and "build_data.py" in msg and "--allow-no-replay-data" in msg, msg
assert frame_server.replay_data_missing(None) is None        # no --site: nothing to check

for name in ("mission.json", "bodies.json"):
    path = os.path.join(site, "data", name)
    open(path, "w").write("{}")
    assert frame_server.replay_data_missing(site) is None, name
    os.remove(path)

# the server itself stops before loading anything, with the message, unless told to go on
run = subprocess.run([sys.executable, os.path.join(HERE, "frame_server.py"), "--site", site, "--port", "0"],
                     capture_output=True, text=True, timeout=60)
assert run.returncode == 1 and "No replay data" in run.stderr, (run.returncode, run.stderr[-500:])
print("ok: a site without replay data is refused, one with mission.json or bodies.json is served")
