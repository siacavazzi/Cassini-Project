"""Pre-process's limit is on frames, the count the page's bar shows (prebuild.Segments, POST /prebuild most=): a
stretch over the page's most= (Settings > Playback) fails saying how many frames it has, most=0 is no limit, the
server's own ceiling (SEGMENT_MAX, CASSINI_SEGMENT_MAX) holds over the page's, the limit is not part of a stretch's
id, and the status says frames apart from pictures. A finished stretch lets go of its makers, and only the last
SEGMENT_KEEP finished stretches are kept. Run: python web/test_segment_limit.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import tempfile  # noqa: E402
import time  # noqa: E402
import prebuild  # noqa: E402


def frame(c):
    pass


frame.frame = True


def other(c):
    pass


def stretch(minute, most=None):
    q = {"from": [f"1970-01-01T00:{minute:02d}:00"], "until": [f"1970-01-01T00:{minute:02d}:30"]}
    if most is not None:
        q["most"] = [str(most)]
    return prebuild.segment_options(q)


# 8,000 frames, each with a composite or a pass picture: 16,000 pictures
plan = [(f"N{k}_1", float(k), 1, frame) for k in range(8000)] + [(f"S{k}", float(k), 1, other) for k in range(8000)]
prebuild.segment_items = lambda o: plan
seg = prebuild.Segments(tempfile.mkdtemp(), live=lambda: 0)


def run(o):
    j = seg.submit(o)
    for _ in range(2000):
        j = seg.status(j["id"])
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.01)
    raise AssertionError(j)


j = run(stretch(1, 6000))
assert j["state"] == "failed" and j["frames"] == 8000 and "8,000 frames" in j["error"] and "6,000" in j["error"], j
assert prebuild.Segments.key(stretch(1, 6000)) == prebuild.Segments.key(stretch(1, 0)) == prebuild.Segments.key(stretch(1))
j = run(stretch(1, 0))   # no limit; the failed stretch asked again is made
assert j["state"] == "done" and j["frames"] == 8000 and j["total"] == 16000 and j["done"] == 16000 and j["through"].endswith("00:01:30"), j
assert all(x[3] is None for x in seg.jobs[j["id"]]["items"])
assert run(stretch(2, 10000))["state"] == "done"

prebuild.SEGMENT_MAX = 7000   # the server's ceiling over the page's no limit
j = run(stretch(3, 0))
assert j["state"] == "failed" and "up to 7,000" in j["error"] and "Settings" not in j["error"], j
prebuild.SEGMENT_MAX = 0

for m in range(4, 4 + prebuild.SEGMENT_KEEP + 5):
    run(stretch(m))
assert len(seg.jobs) <= prebuild.SEGMENT_KEEP + 1, len(seg.jobs)
print("ok limit")

# Stop ends a long pass at its next picture (make_pass stopped=), and the stretch asked again while the stopped run is
# still letting go is a new run, queued behind it, which its own Stop stops
om = prebuild.obs_mosaic
om.plan = lambda u, cache: {"display_scale": 1.0}
om.tile = lambda u, j, cache, scale=None: time.sleep(0.01)
om.movie_webp = lambda fid, size, cache, *a, **k: time.sleep(0.01)
long_pass = {"key": ("T", "OBS", "N", 0), "kind": "movie", "mosaic": False, "movie": True,
             "frames": [(None, f"N{1000 + j}_1", "CL1", 100.0 + j) for j in range(3000)]}
work = lambda c, made=None, stopped=None: prebuild.make_pass(long_pass, c, (512,), None, None, made, stopped)
work.pass_key = long_pass["key"]
plan[:] = [("T_OBS_N_0", 100.0, 3000, work)]
first = seg.submit(stretch(40))
time.sleep(0.5)
seg.stop(first["id"])
again = seg.submit(stretch(40))
assert again["id"] == first["id"] and again["state"] == "queued", again   # not the stopping run's "making"
t = time.monotonic()
while seg.status(first["id"])["state"] == "queued" and time.monotonic() - t < 5:
    time.sleep(0.02)
assert time.monotonic() - t < 2, "the stopped run let go within a picture or two"
time.sleep(0.3)
seg.stop(again["id"])
t = time.monotonic()
while seg.status(again["id"])["state"] != "stopped" and time.monotonic() - t < 5:
    time.sleep(0.02)
st = seg.status(again["id"])
assert st["state"] == "stopped" and st["done"] < 3000 and time.monotonic() - t < 2, st
print("ok stop")
