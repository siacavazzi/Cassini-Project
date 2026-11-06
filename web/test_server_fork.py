"""The frame server forks (git for /version.json, ffmpeg for an export) while other request threads multiply matrices.
With threaded OpenBLAS that deadlocks in its fork handler with the GIL held, and the server stops answering (8866,
2026-11-06). frame_server sets one BLAS thread before numpy loads; this runs, in a fresh process that imports
frame_server first, two threads doing float32 matrix products and one forking git, and fails if they stall."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHILD = r"""
import os, sys, threading, time, subprocess
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, os.path.dirname(sys.argv[1]))
import frame_server  # noqa: F401  (sets the BLAS thread count before numpy loads)
import numpy as np
stop, done = time.time() + 8, {"dot": 0, "fork": 0}
def dots():
    a = np.random.rand(1200, 1200).astype(np.float32)
    while time.time() < stop:
        a @ a; done["dot"] += 1
def forks():
    while time.time() < stop:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10); done["fork"] += 1
ts = [threading.Thread(target=dots, daemon=True) for _ in range(2)] + [threading.Thread(target=forks, daemon=True)]
for t in ts: t.start()
for t in ts: t.join()
print(done["dot"], done["fork"])
assert os.environ.get("OPENBLAS_NUM_THREADS") == "1", "frame_server leaves OpenBLAS threaded"
"""
env = {k: v for k, v in os.environ.items() if k not in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
try:
    out = subprocess.run([sys.executable, "-c", CHILD, os.path.join(HERE, "frames")], env=env, capture_output=True,
                         text=True, timeout=60)
except subprocess.TimeoutExpired:
    raise SystemExit("matrix products and forks deadlocked (no answer in 60 s)")
assert out.returncode == 0, out.stderr[-2000:]
dots, forks = map(int, out.stdout.split()[-2:])
assert dots > 0 and forks > 0, out.stdout
print(f"{dots} matrix products and {forks} forks in 8 s with no deadlock; ok")
