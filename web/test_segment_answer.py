"""Pre-process answers fast (prebuild.Segments, POST /prebuild): a stretch made in a moment (every picture in the
cache) is answered made, so the page says Ready at once instead of "Starting…" for a second; a longer one is answered
after the wait asked for (SEGMENT_ANSWER), as far as it got; one asked again is answered at once. And a stretch finds
its filter sets by bisection (prebuild.sets_ready): the same sets, in the same order, as going through all of them.
Run: python web/test_segment_answer.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import random  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import prebuild  # noqa: E402

segment_items, go = prebuild.segment_items, threading.Event()


def quick(c):
    time.sleep(0.005)


def slow(c):
    go.wait(10)


def stretch(a, b):
    return prebuild.segment_options({"from": [f"1970-01-01T00:0{a}:00"], "until": [f"1970-01-01T00:0{b}:00"]})


plans = {}
prebuild.segment_items = lambda o: plans[o["from"]]
seg = prebuild.Segments(tempfile.mkdtemp(), live=lambda: 0)

# made in a moment: answered made, as soon as it is
plans[60.0] = [(f"N{k}_1", 60.0 + k, 1, quick) for k in range(20)]
t = time.monotonic()
job = seg.submit(stretch(1, 2), 0.3)
took = time.monotonic() - t
assert job["state"] == "done" and job["done"] == 20, job
assert took < 0.25, took

# asked again: the same job, answered at once
t = time.monotonic()
again = seg.submit(stretch(1, 2), 0.3)
assert again["id"] == job["id"] and again["state"] == "done" and time.monotonic() - t < 0.05

# longer: answered after the wait, as far as it got; made on after the answer
plans[120.0] = [(f"N{k}_1", 120.0 + k, 1, quick if k < 3 else slow) for k in range(8)]
t = time.monotonic()
job = seg.submit(stretch(2, 3), 0.3)
took = time.monotonic() - t
assert job["state"] == "making" and job["total"] == 8 and 3 <= job["done"] < 8, job
assert 0.28 < took < 0.6, took
go.set()
for _ in range(200):
    st = seg.status(job["id"])
    if st["state"] == "done":
        break
    time.sleep(0.02)
assert st["state"] == "done" and st["done"] == 8, st

# no wait asked (the default): answered at once, queued
plans[180.0] = [("N1_1", 180.0, 1, quick)]
t = time.monotonic()
job = seg.submit(stretch(3, 4))
assert job["state"] in ("queued", "planning") and time.monotonic() - t < 0.05, job

# the filter sets of a stretch, by bisection, as the whole list gone through finds them (the real index)
prebuild.segment_items = segment_items
idx, row = prebuild.obs_mosaic._row_of()
times = idx["seconds_1970"].to_numpy()
readies, sets = prebuild.sets_ready()
assert len(sets) == len(prebuild.page_sets()) and readies == sorted(readies)
everyone = [(float(max(times[row[i]] for i in s)), s) for s in prebuild.page_sets()]
random.seed(7)
for _ in range(25):
    q = random.randrange(len(times))
    t0, t1 = float(times[q]) - random.choice([0, 30]), float(times[q]) + random.choice([600, 3600, 86400])
    scan = sorted([(r, s) for r, s in everyone if t0 <= r <= t1], key=lambda x: x[0])
    lo, hi = prebuild.bisect.bisect_left(readies, t0), prebuild.bisect.bisect_right(readies, t1)
    assert list(zip(readies[lo:hi], sets[lo:hi])) == scan, (t0, t1)
print("ok")
