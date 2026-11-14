"""pass_check.py CACHE IDS [NAMES...]: the named passes (or the 4 smallest of the slice's mosaic and movie passes) made by
prebuild.make_pass into CACHE, as a build process makes them; prints what was handed on and taken where the code counts it."""
import argparse, sys, time
sys.path.insert(0, "web/frames")
import prebuild, obs_mosaic, calibration, stacking
cache, ids, names = sys.argv[1], sys.argv[2], sys.argv[3:]
obs_mosaic.tiles_ahead = lambda *a, **k: None
obs_mosaic.rolling_ahead = lambda *a, **k: None
if hasattr(prebuild, "_scope"):
    prebuild._scope[0] = (None, ids)
args = argparse.Namespace(phase="movies", only=ids, years=None, since=None, until=None)
P = {"_".join(map(str, u["key"])): u for u in prebuild.all_passes() if u["mosaic"] or u.get("kind") in ("movie", "mosaic_movie") or u.get("movie")}
todo = set(n for ph in ("mosaics", "movies") for n, _ in prebuild.chosen(argparse.Namespace(phase=ph, only=ids, years=None, since=None, until=None)))
if not names:
    names = sorted(todo, key=lambda n: (len(P[n]["frames"]), n))
    names = [n for n in names if 4 <= len(P[n]["frames"])][:4]
took = [0]
if hasattr(stacking, "_handed_take"):
    real = stacking._handed_take
    def counted(*a):
        r = real(*a); took[0] += r is not None; return r
    stacking._handed_take = counted
import collections, threading
T = collections.Counter(); N = collections.Counter(); lock = threading.Lock()
real_hdr = stacking.load_hdr
def timed_hdr(path, window=120, max_frames=8, valid=False, clipped=False, **kw):
    t0 = time.perf_counter(); r = real_hdr(path, window, max_frames, valid, clipped, **kw); dt = time.perf_counter() - t0
    k = ("plan" if threading.current_thread() is not threading.main_thread() else "tile") + (" valid" if valid else " plain")
    with lock: T[k] += dt; N[k] += 1
    return r
stacking.load_hdr = timed_hdr
import atexit
atexit.register(lambda: print("load_hdr:", {k: (N[k], round(T[k], 1)) for k in sorted(T)}, flush=True))
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    for n in names:
        t0 = time.time(); u = P[n]
        got = prebuild.make_pass(u, cache)
        print(f"{n}: {len(u['frames'])} frames, kind {u.get('kind')}, {time.time() - t0:.1f} s, taken from the plan so far: {took[0]}", flush=True)
