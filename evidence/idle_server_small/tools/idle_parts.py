#!/usr/bin/env python3
"""idle_parts.py --wt CHECKOUT --site SITE --cache DIR --part PART [--cap-gb 10] [--max-s 900]

One of the frame server's start-up warm-ups (frame_server.main's daemon threads) run alone in this process, as main
runs it, with the process's physical footprint beside it: after each step, and for the thumbnails after each
highlight. A watchdog stops the process (exit 3) when the footprint passes --cap-gb or the run passes --max-s, and
before it does prints what holds the memory: the bytes of numpy arrays reachable from each module global of the
pipeline (a cache, an index), the largest first.

PART: index (the zip index only, which main loads before any thread), prebuild (reel.target_of, obs_mosaic's
observations and rows, warm_prebuild), stacking (color_image.stacking.load_index), thumbs (warm_thumbs, one
highlight at a time), icons (warm_icons), all (every one, in main's order, one after another)."""
import argparse, ctypes, gc, json, os, sys, threading, time, types

ap = argparse.ArgumentParser()
ap.add_argument("--wt", required=True); ap.add_argument("--site", required=True); ap.add_argument("--cache", required=True)
ap.add_argument("--part", required=True); ap.add_argument("--cap-gb", type=float, default=10); ap.add_argument("--max-s", type=float, default=900)
ap.add_argument("--holders", action="store_true", help="print the holders at the end even when the cap was not reached")
ap.add_argument("--thumbs", help="only these highlights of the thumbs part (their numbers among the thumbnails, comma separated)")
ap.add_argument("--stacks-every", type=float, default=0, help="every so many seconds, the footprint and what each working thread is in")
a = ap.parse_args()
wt = os.path.abspath(a.wt)
sys.path.insert(0, os.path.join(wt, "web", "frames"))
sys.argv = [os.path.join(wt, "web", "frames", "frame_server.py")]


class RU(ctypes.Structure):
    _fields_ = [("u", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in "abcdefgHijklmnopqr"]


lp = ctypes.CDLL("/usr/lib/libproc.dylib")


def foot():
    r = RU(); lp.proc_pid_rusage(os.getpid(), 2, ctypes.byref(r)); return r.H / 1e6


T0 = time.monotonic()
peak = [0.0]


def say(msg):
    print(f"{time.monotonic() - T0:7.1f} s  {foot():8.0f} MB  {msg}", flush=True)


def holders(top=25):
    """bytes of numpy arrays reachable from each module global of the repo's modules (not through modules, classes,
    functions or frames), the largest first; an array reached from several globals counts for each"""
    import numpy as np
    gc.collect()
    live = [o for o in gc.get_objects() if isinstance(o, np.ndarray)]
    own = sum(o.nbytes for o in live if o.flags.owndata)
    print(f"  live numpy arrays: {len(live)}, {own / 1e6:.0f} MB owned (footprint {foot():.0f} MB)", flush=True)
    stop = (types.ModuleType, type, types.FunctionType, types.BuiltinFunctionType, types.CodeType, types.FrameType,
            types.MethodType, str, bytes, int, float, bool, type(None))
    rows = []
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if not f.startswith(wt):
            continue
        for g, v in list(vars(mod).items()):
            if g.startswith("__") or isinstance(v, stop):
                continue
            seen, todo, total, count, entries = set(), [v], 0, 0, None
            try:
                entries = len(v)
            except Exception:
                pass
            while todo and len(seen) < 400000:
                o = todo.pop()
                if id(o) in seen or isinstance(o, stop):
                    continue
                seen.add(id(o))
                if isinstance(o, np.ndarray):
                    b = o
                    while isinstance(b.base, np.ndarray):
                        b = b.base
                    if id(b) not in seen or b is o:
                        seen.add(id(b)); total += b.nbytes; count += 1
                    continue
                try:
                    todo.extend(gc.get_referents(o))
                except Exception:
                    pass
            if total > 20e6:
                rows.append((total, f"{name}.{g}", type(v).__name__, entries, count))
    for total, where, kind, entries, count in sorted(rows, reverse=True)[:top]:
        print(f"  {total / 1e6:9.0f} MB  {where}  ({kind}{'' if entries is None else f', {entries} entries'}, {count} arrays)", flush=True)
    big = sorted((o for o in live if o.flags.owndata), key=lambda o: -o.nbytes)[:12]
    print("  largest arrays: " + ", ".join(f"{o.shape} {o.dtype} {o.nbytes / 1e6:.0f} MB" for o in big), flush=True)


def stacks(depth=7):
    """what each thread that is in the repo's code is doing: its innermost repo functions, innermost first"""
    me, out = threading.get_ident(), []
    for tid, f in sys._current_frames().items():
        if tid == me:
            continue
        c = []
        while f is not None and len(c) < depth:
            if f.f_code.co_filename.startswith(wt):
                c.append(f"{f.f_code.co_name}:{f.f_lineno}")
            f = f.f_back
        if c and c[0].split(":")[0] not in ("_yield", "wait", "result"):
            out.append(" < ".join(c))
    return out


last_stacks = [0.0]


def watchdog():
    while True:
        time.sleep(0.25)
        f = foot()
        peak[0] = max(peak[0], f)
        if a.stacks_every and time.monotonic() - last_stacks[0] >= a.stacks_every:
            last_stacks[0] = time.monotonic()
            for line in stacks():
                say("  in " + line)
        over = f > a.cap_gb * 1000
        late = time.monotonic() - T0 > a.max_s
        if over or late:
            say(f"STOPPED: {'footprint over the cap of %g GB' % a.cap_gb if over else 'over %g s' % a.max_s}; what holds it:")
            for line in stacks(12):
                print("  thread in " + line, flush=True)
            try:
                holders()
            finally:
                sys.stdout.flush()
                os._exit(3)


threading.Thread(target=watchdog, daemon=True).start()
say("start")
import frame_server as fs   # noqa: E402
import data_source, reel, obs_mosaic, color_image   # noqa: E402
say("imported")
site, cache = os.path.abspath(a.site), os.path.abspath(a.cache)
data_source.KEEP_SPICE_CACHE = True
data_source._zip_index() if data_source.using_zip() else None
say("zip index")


def part_prebuild():
    reel.target_of(); say("reel.target_of")
    obs_mosaic._observations(); say("obs_mosaic._observations")
    obs_mosaic._row_of(); say("obs_mosaic._row_of")
    fs.warm_prebuild(); say("warm_prebuild (prebuild.sets_ready)")


def part_stacking():
    color_image.stacking.load_index(); say("stacking.load_index")


def part_thumbs():
    with open(os.path.join(site, "data", "highlights.json")) as fh:
        hints = [e["thumb"] for e in json.load(fh) if e.get("kind") != "milestone" and e.get("thumb")]
    say(f"{len(hints)} highlights")
    only = {int(x) for x in a.thumbs.split(",")} if a.thumbs else None
    for n, hint in enumerate(hints):
        if only is not None and n not in only:
            continue
        hint = {k: hint[k] for k in ("mosaic", "color", "frame") if hint.get(k)}
        kind = "+".join(hint)
        if os.path.exists(os.path.join(cache, fs.THUMB_VERSION, fs.thumb_key(hint, fs.THUMB_SIZE) + ".webp")):
            say(f"thumb {n} {kind}: in the cache already")
            continue
        t, before = time.monotonic(), foot()
        try:
            _, what = fs.thumb_webp(hint, fs.THUMB_SIZE, cache)
            note = json.dumps(what)[:120]
        except Exception as e:   # as warm_thumbs: one that cannot be made must not stop the others
            note = f"FAILED {type(e).__name__}: {e}"[:160]
        say(f"thumb {n} {kind} {hint.get('mosaic') or hint.get('frame') or hint['color'][0]}: {time.monotonic() - t:.0f} s, "
            f"{foot() - before:+.0f} MB, peak so far {peak[0]:.0f} MB; {note}")


def part_icons():
    fs.warm_icons(site, cache); say("warm_icons")


parts = {"index": lambda: None, "prebuild": part_prebuild, "stacking": part_stacking, "thumbs": part_thumbs,
         "icons": part_icons}
for p in (["prebuild", "stacking", "thumbs", "icons"] if a.part == "all" else a.part.split(",")):
    parts[p]()
gc.collect()
say(f"DONE {a.part}: peak {peak[0]:.0f} MB")
if a.holders:
    holders()
