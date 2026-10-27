"""A stretch made ahead (prebuild.make_pass within it, prebuild.Segments): a mosaic movie makes only its rolling
pictures (a window plays it rolling and never asks for its pass's mosaic so far, which took a Jupiter stretch 107 s on
the Mini), a mosaic its mosaics so far, a movie its steadied frames; and a pass counts up frame by frame as its frames
are made, the stretch's "through" moving with them, so the bar never sits still through a long pass.
Run: python web/test_segment_progress.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import prebuild  # noqa: E402

om, calls = prebuild.obs_mosaic, []
om.plan = lambda u, cache: {"display_scale": 1.0}
om.tile = lambda u, j, cache, scale=None: None
om.rolling_webp = lambda fid, size, cache, laps=1, wait=False, fade=(0, 0): calls.append(("rolling", fid, size))
om._mosaic_at = lambda u, j, size, cache, *a, **k: calls.append(("mosaic", u["frames"][j][1], size))
om.movie_webp = lambda fid, size, cache, *a, **k: calls.append(("movie", fid, size))


def unit(kind, mosaic):
    # frames (path, id, filter, t, ...) every 10 s from t = 100
    return {"key": ("T", "OBS", "N", 0), "kind": kind, "mosaic": mosaic, "movie": kind == "movie",
            "frames": [(None, f"N{1000 + j}_1", "CL1", 100.0 + 10 * j) for j in range(6)]}


def made_in(u, within, sizes=(512, 1024)):
    calls.clear()
    times = []
    n = prebuild.make_pass(u, "/nowhere", sizes, within, None, times.append)
    return n, times, list(calls)


# a mosaic movie in the stretch 125-145 s: every rolling picture from the pass's start (each grows from the one
# before), no pass mosaic at all; its two frames in the stretch counted as they are made
n, times, got = made_in(unit("mosaic_movie", True), (125, 145))
assert n == 2 and times == [130.0, 140.0], (n, times)
assert {c[0] for c in got} == {"rolling"}, got
assert [c[1] for c in got if c[2] == 512] == ["N1000_1", "N1001_1", "N1002_1", "N1003_1", "N1004_1"], got

# a mosaic: its mosaics so far for the frames in the stretch only, at both sizes
n, times, got = made_in(unit(None, True), (125, 145))
assert n == 2 and times == [130.0, 140.0]
assert got == [("mosaic", "N1003_1", 512), ("mosaic", "N1003_1", 1024), ("mosaic", "N1004_1", 512), ("mosaic", "N1004_1", 1024)], got

# a movie: its steadied frames in the stretch
n, times, got = made_in(unit("movie", False), (125, 145))
assert n == 2 and {c[0] for c in got} == {"movie"} and len(got) == 4, got

# the whole pass (the pre-build's own phases, no stretch): every frame
n, times, got = made_in(unit("mosaic_movie", True), None, (1024, 512))
assert n == 6 and len(got) == 12 and {c[0] for c in got} == {"rolling"}, (n, got)

# Segments: a frame, a pass of 4 frames that stops half way until let go, another frame. While the pass is half made,
# done counts its 2 frames made and "through" stands at its last frame made; once let go, all 6, through the end.
go, half = threading.Event(), threading.Event()


def frame(c):
    return None


def a_pass(c, made=None):
    made(110.0)
    made(115.0)
    half.set()
    go.wait(10)
    made(130.0)
    made(140.0)


a_pass.pass_key = ("T", "OBS", "N", 0)
items = [("N1_1", 100.0, 1, frame), ("T_OBS_N_0", 105.0, 4, a_pass), ("N2_1", 120.0, 1, frame)]
prebuild.segment_items = lambda o: list(items)
o = prebuild.segment_options({"from": ["1970-01-01T00:01:40"], "until": ["1970-01-01T00:03:20"]})
seg = prebuild.Segments(tempfile.mkdtemp(), live=lambda: 0)
job = seg.submit(o)
assert half.wait(10)
time.sleep(0.3)   # the frames after it finish meanwhile (other threads)
st = seg.status(job["id"])
assert st["state"] == "making" and st["total"] == 6 and st["done"] == 4, st
assert st["through"] == "1970-01-01T00:01:55", st   # the pass's last frame made (115 s), not its start
go.set()
for _ in range(200):
    st = seg.status(job["id"])
    if st["state"] == "done":
        break
    time.sleep(0.05)
assert st["state"] == "done" and st["done"] == 6 and st["through"] == "1970-01-01T00:03:20", st
print("ok")
