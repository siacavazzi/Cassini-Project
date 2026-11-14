"""obs_mosaic.tinted_frame old against new on the real color movie frames of a slice: every frame of the slice's movie
passes drawn by movie_frame (as the pre-build's make_pass asks), each tinted_frame call run through both, their
bytes compared and their time taken.  tint_check.py CACHE IDS K N OUT   (process K of N; from the checkout under test,
whose obs_mosaic holds both for the run: tinted_frame (new), tinted_frame_old (the form at 2bdee523, copied in) and a
TINT_COUNT = {"skipped": 0, "no_clip": 0} that the new one counts in; results in real_frames.json)"""
import argparse, json, os, sys, time
sys.path.insert(0, "web/frames")
import numpy as np
import prebuild, obs_mosaic, calibration

cache, ids, k, n, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
old, new = obs_mosaic.tinted_frame_old, obs_mosaic.tinted_frame
stats = {"calls": 0, "same": 0, "differ": 0, "old_s": 0.0, "new_s": 0.0, "wide_skipped": 0, "no_clip": 0, "frames": 0, "errors": 0, "differing": []}


def both(colour, grey, gamma=2.2, same=False):
    c0, g0 = colour.copy(), grey.copy()
    t0 = time.perf_counter(); a = old(colour, grey, gamma, same); t1 = time.perf_counter()
    assert np.array_equal(c0, colour) and np.array_equal(g0, grey)     # (neither changes what it is given)
    before = dict(obs_mosaic.TINT_COUNT)
    t2 = time.perf_counter(); b = new(colour, grey, gamma, same); t3 = time.perf_counter()
    stats["calls"] += 1; stats["old_s"] += t1 - t0; stats["new_s"] += t3 - t2
    stats["wide_skipped"] += obs_mosaic.TINT_COUNT["skipped"] - before["skipped"]
    stats["no_clip"] += obs_mosaic.TINT_COUNT["no_clip"] - before["no_clip"]
    if a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes():
        stats["same"] += 1
    else:
        stats["differ"] += 1
        stats["differing"].append([int((a != b).sum()), int(np.abs(a.astype(int) - b.astype(int)).max())])
    return a


obs_mosaic.tinted_frame = both
obs_mosaic.tiles_ahead = lambda *a, **kw: None
obs_mosaic.rolling_ahead = lambda *a, **kw: None
prebuild._scope[0] = (None, ids)
args = argparse.Namespace(phase="movies", only=ids, years=None, since=None, until=None)
names = {name for name, _ in prebuild.chosen(args)}
passes = [u for u in prebuild.movie_passes() if "_".join(map(str, u["key"])) in names]
t0 = time.time()
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    for j, u in enumerate(passes):
        if j % n != k:
            continue
        for f in range(len(u["frames"])):
            try:
                obs_mosaic.movie_frame(u, f, cache, 0, True, centre=True, steady=0, exposure=0)
                stats["frames"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"{u['key']} {f}: {type(e).__name__}: {e}"[:200], flush=True)
stats["wall"] = time.time() - t0
json.dump(stats, open(out, "w"))
print(k, {a: (round(b, 1) if isinstance(b, float) else b) for a, b in stats.items() if a != "differing"}, flush=True)
