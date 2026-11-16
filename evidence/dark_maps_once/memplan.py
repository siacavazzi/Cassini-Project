#!/usr/bin/env python3
"""memplan.py PHASE NAME --cache DIR [--wt CHECKOUT] [--tm]: a pass's plan alone (the item stops when
obs_mosaic.pass_scale returns), with the process's physical footprint sampled every 20 ms beside what every thread
is doing, so the plan's memory growth can be put to the code that was running as it grew. --tm: tracemalloc too
(Python's and numpy's own allocations; OpenCV's are not seen), with the snapshot at the highest traced size printed
by where it was allocated."""
import argparse, collections, ctypes, os, sys, threading, time, tracemalloc
ap = argparse.ArgumentParser()
ap.add_argument("phase"); ap.add_argument("name"); ap.add_argument("--cache", required=True)
ap.add_argument("--wt", default=os.environ.get("WT")); ap.add_argument("--tm", action="store_true")
a = ap.parse_args()
wt = os.path.abspath(a.wt)
sys.path.insert(0, os.path.join(wt, "web", "frames"))
sys.argv = [os.path.join(wt, "web", "frames", "prebuild.py")]


class RU(ctypes.Structure):
    _fields_ = [("u", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in "abcdefgHijklmnopqr"]


lp = ctypes.CDLL("/usr/lib/libproc.dylib")


def foot():
    r = RU(); lp.proc_pid_rusage(os.getpid(), 2, ctypes.byref(r)); return r.H / 1e6


me = [None]
samples = []     # (time, footprint, traced, {thread: chain})
stop = [False]
best = [0, None]


def chains():
    out = {}
    for tid, f in sys._current_frames().items():
        if tid == me[0]:
            continue
        chain = []
        while f is not None:
            if f.f_code.co_filename.startswith(wt):
                chain.append(f"{f.f_code.co_name}:{f.f_lineno}")
            f = f.f_back
        if chain:
            out[tid] = chain
    return out


def watch():
    me[0] = threading.get_ident()
    while not stop[0]:
        traced = tracemalloc.get_traced_memory()[0] / 1e6 if a.tm else 0.0
        samples.append((time.monotonic(), foot(), traced, chains()))
        if a.tm and traced > best[0] + 150:
            best[0], best[1] = traced, tracemalloc.take_snapshot()
        time.sleep(0.02)


import prebuild, calibration, obs_mosaic  # noqa: E402
prebuild._scope[0] = (None, os.environ["ONLY"]) if os.environ.get("ONLY") else None
obs_mosaic.tiles_ahead = lambda *x, **k: None
obs_mosaic.rolling_ahead = lambda *x, **k: None
todo = dict(prebuild.items(a.phase))
obs_mosaic.rolled_room(2)


class Planned(Exception):
    pass


_scale = obs_mosaic.pass_scale
after = {}


def scale(*x, **k):
    out = _scale(*x, **k)
    after["foot"] = foot()
    if a.tm:
        after["traced"] = tracemalloc.get_traced_memory()
        after["snap"] = tracemalloc.take_snapshot()
    raise Planned()


obs_mosaic.pass_scale = scale
if a.tm:
    tracemalloc.start(10)
base = foot()
threading.Thread(target=watch, daemon=True).start()
try:
    with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
        todo[a.name](a.cache)
except Planned:
    pass
stop[0] = True
time.sleep(0.1)
print(f"{a.name}: footprint before the plan {base:.0f} MB, when pass_scale returned {after.get('foot', 0):.0f} MB, "
      f"highest {max(s[1] for s in samples):.0f} MB; {len(samples)} samples")
if a.tm:
    print(f"traced when pass_scale returned {after['traced'][0] / 1e6:.0f} MB, highest traced {after['traced'][1] / 1e6:.0f} MB")
# the growth between samples, put to what each working thread was in (the innermost repo function, and its two callers)
grew = collections.defaultdict(float)
grew3 = collections.defaultdict(float)
for (t0, m0, _, _), (t1, m1, _, ch) in zip(samples, samples[1:]):
    d = m1 - m0
    if d <= 0 or not ch:
        continue
    work = [c for c in ch.values() if not c[0].startswith(("scale:", "<module>"))] or list(ch.values())
    for c in work:
        grew[c[0]] += d / len(work)
        grew3["<".join(c[:3])] += d / len(work)
print("growth by the innermost repo function running (MB):")
for k, v in sorted(grew.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {v:8.0f}  {k}")
print("growth by the innermost three (MB):")
for k, v in sorted(grew3.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {v:8.0f}  {k}")
print("over the plan:")
for i in range(0, len(samples), max(1, len(samples) // 40)):
    t, m, tr, ch = samples[i]
    print(f"   {t - samples[0][0]:7.2f} s  {m:6.0f} MB  traced {tr:6.0f}  " + " | ".join(c[0] for c in ch.values()))
if a.tm:
    for label, snap in (("at the highest traced size", best[1]), ("when pass_scale returned", after.get("snap"))):
        if snap is None:
            continue
        print(f"tracemalloc {label}:")
        stats = snap.statistics("traceback")
        for s in stats[:14]:
            print(f"  {s.size / 1e6:8.1f} MB in {s.count} blocks")
            for fr in s.traceback.format()[-12:]:
                print("      " + fr.strip()) if "File" in fr else None
