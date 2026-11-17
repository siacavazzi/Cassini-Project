#!/usr/bin/env python3
"""memtrace.py PHASE NAME --cache DIR [--wt CHECKOUT]: one prebuild item made as the build makes it, with the process's
physical footprint sampled every 50 ms beside what the main thread is doing (the outermost build step on its stack
and its innermost repo function), so the peak can be put to a step. Prints the peak per step and the samples round
the highest."""
import argparse, collections, ctypes, os, sys, threading, time
ap = argparse.ArgumentParser()
ap.add_argument("phase"); ap.add_argument("name"); ap.add_argument("--cache", required=True)
ap.add_argument("--wt", default=os.environ.get("WT"))
a = ap.parse_args()
wt = os.path.abspath(a.wt)
sys.path.insert(0, os.path.join(wt, "web", "frames"))
sys.argv = [os.path.join(wt, "web", "frames", "prebuild.py")]


class RU(ctypes.Structure):
    _fields_ = [("u", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in "abcdefgHijklmnopqr"]


lp = ctypes.CDLL("/usr/lib/libproc.dylib")


def foot():
    r = RU(); lp.proc_pid_rusage(os.getpid(), 2, ctypes.byref(r)); return r.H / 1e6


STEPS = ("pass_scale", "_tile_made", "steady_chain", "exposure_chain", "make_evened", "make_planes", "solve_places",
         "_mosaic_at", "rolling_webp", "movie_webp", "tile_map", "full_view")
main_id = threading.main_thread().ident
samples = []
stop = [False]


every = []   # per sample: every other thread's innermost repo functions (with line numbers), for the growth table


def watch():
    me = threading.get_ident()
    while not stop[0]:
        frames = sys._current_frames()
        f = frames.get(main_id)
        step, inner, chain = "other", "", []
        while f is not None:
            n = f.f_code.co_name
            if f.f_code.co_filename.startswith(wt):
                chain.append(n)
                if n in STEPS:
                    step = n
            f = f.f_back
        chains = []
        for tid, f in frames.items():
            if tid == me:
                continue
            c = []
            while f is not None and len(c) < 3:
                if f.f_code.co_filename.startswith(wt):
                    c.append(f"{f.f_code.co_name}:{f.f_lineno}")
                f = f.f_back
            if c and not c[0].startswith(("result", "wait", "map")):
                chains.append("<".join(c))
        samples.append((time.monotonic(), foot(), step, "<".join(chain[:4])))
        every.append(chains)
        time.sleep(0.05)


import prebuild, calibration, obs_mosaic  # noqa: E402
prebuild._scope[0] = (None, os.environ["ONLY"]) if os.environ.get("ONLY") else None
obs_mosaic.tiles_ahead = lambda *x, **k: None
if os.environ.get("LETGO") and hasattr(prebuild, "_let_go"):
    prebuild._let_go[0] = True   # (as prebuild.main sets it for a build making one pass at a time)
obs_mosaic.rolling_ahead = lambda *x, **k: None
todo = dict(prebuild.items(a.phase))
obs_mosaic.rolled_room(2)
base = foot()
threading.Thread(target=watch, daemon=True).start()
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    todo[a.name](a.cache)
stop[0] = True
peak = collections.defaultdict(float); where = {}
for t, m, step, chain in samples:
    if m > peak[step]:
        peak[step], where[step] = m, chain
print(f"{a.name}: footprint before the pass {base:.0f} MB; {len(samples)} samples")
for step, m in sorted(peak.items(), key=lambda kv: -kv[1]):
    print(f"  {step:16s} peak {m:6.0f} MB   at {where[step]}")
top = max(range(len(samples)), key=lambda i: samples[i][1])
print("round the highest sample:")
for t, m, step, chain in samples[max(0, top - 6):top + 7]:
    print(f"   {t - samples[0][0]:7.2f} s  {m:6.0f} MB  {step:14s} {chain}")
# the footprint's growth over the pass, a line every 5% of the samples
print("over the pass:")
for i in range(0, len(samples), max(1, len(samples) // 24)):
    t, m, step, chain = samples[i]
    print(f"   {t - samples[0][0]:7.1f} s  {m:6.0f} MB  {step}")
# where the footprint grew: each rise between two samples put to what the threads were in (shared when several)
grew, by_step = collections.defaultdict(float), collections.defaultdict(float)
jumps = []
for i in range(1, len(samples)):
    d = samples[i][1] - samples[i - 1][1]
    if d <= 0:
        continue
    by_step[samples[i][2]] += d
    for c in every[i] or ["(no repo code running)"]:
        grew[c] += d / max(1, len(every[i]))
    jumps.append((d, samples[i][0] - samples[0][0], samples[i][1], samples[i][2], " | ".join(every[i])[:230]))
print("rises of the footprint, summed, by build step (MB):", {k: round(v) for k, v in sorted(by_step.items(), key=lambda kv: -kv[1])})
print("... and by what was running (MB):")
for k, v in sorted(grew.items(), key=lambda kv: -kv[1])[:22]:
    print(f"  {v:8.0f}  {k}")
print("the largest single rises:")
for d, t, m, step, c in sorted(jumps, reverse=True)[:14]:
    print(f"  +{d:5.0f} MB at {t:6.1f} s -> {m:5.0f} MB  {step:12s} {c}")
