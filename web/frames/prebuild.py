#!/usr/bin/env python3
"""
Pre-builds the frame server's picture cache ahead of any request, so serving the mission costs disk and bandwidth
instead of CPU. Every picture is made by the frame server's own makers (frame_server.webp, color_webp,
processed_webp; obs_mosaic.plan, tile, _mosaic_at) into the same cache folders and names a request would use, so
the server (or a static copy of the cache) finds it there. Nothing here processes a picture itself.

Phases (each its own run; a run picks up where the last one stopped, since a made file is never made again):
  frames      /frames/<ID>.webp at 512 and 1024 px, every frame of the mission (frame_server.FRAME_VERSION). No
              processing in them, so safe to build before the look is final
  composites  /frames/color.webp?ids=R,G,B for every filter set the page makes (its findSets rule), at 1024 (which
              also writes full) and 512, in the default look (balanced, natural colors)
  mosaics     every mosaic pass's plan and tiles (obs_mosaic), then what the window shows at each of its frames,
              1024 and 512: its mosaic so far, or a mosaic movie's rolling picture
  movies      the same for every movie pass: its steadied frames (movie_webp), then the planes the page's own steps
              start from (make_planes: each frame alone, color=0, at 1024; a filled pass's also before detail, _d0)
  processed   /frames/processed/<ID>.webp at 1024, 512 and 256, every frame, centred as Auto center asks
  strips      a movie pass's steadied frames at 128 (the movie strip)
  chains      every movie pass's stabilization and exposure chains (small JSON files; no pictures), which the page's
              Stabilize and Even exposure read

Made to share the Mac Mini with the live and preview servers: run it under `nice -n 19 taskpolicy -b` (low CPU and
disk priority), one process with a few threads. It waits while the 1-minute load is over --max-load, while the
live server's (or a --watch preview's) /health answers slower than a
second, while the LaCie (--disk) moves more than --max-tps transfers a second, or while the pause file exists (touch it to hold the job,
remove it to go on), or while the cache's disk has less than --min-free GB free. The holds are asked on a thread of
their own, so a slow check never holds the workers back. --procs N runs the phase as N processes of one thread
each (the makers are mostly Python: threads take turns on one core), each its own stretch of the items.
status.json (and a page reading it, index.html) in --status says how far it is.

  CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
    nice -n 19 taskpolicy -b python web/frames/prebuild.py frames --cache /Volumes/cassini-cache \\
    --status web/cassini-os/prebuild
  ... prebuild.py composites --sample 200      times 200 spread-out items into a scratch cache and prints the
                                                seconds and bytes per item (and the totals they mean)
"""
import argparse
import bisect
import collections
import concurrent.futures
import contextvars
import datetime
import functools
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_server  # noqa: E402  (puts the repo on the path, loads the pipeline)
import calibration  # noqa: E402
import obs_mosaic  # noqa: E402
import reel  # noqa: E402

PHASES = ("frames", "composites", "mosaics", "movies", "processed", "strips", "chains")


@functools.lru_cache(None)
def frame_ids():
    """Every frame of the index, in time order."""
    idx, _ = reel.load_index()
    return idx["id"].tolist()


@functools.lru_cache(None)
def page_sets():
    """The filter sets the camera windows ask composites of, with their ids in the order the page puts in the URL:
    reel.load_index's sets, which are the page's (one rule, sets_passes; the page reads them from the data, or
    works them out the same way in head-quiet.html findSets)."""
    idx, sets = reel.load_index()
    ids = idx["id"].tolist()
    return [[ids[q] for q in s["use"]] for s in sets]


@functools.lru_cache(None)
def mosaic_passes():
    """Every pass the windows play as a mosaic or a mosaic movie, in time order."""
    return [u for u in all_passes() if u["mosaic"] or u.get("kind") == "mosaic_movie"]


@functools.lru_cache(None)
def all_passes():
    """Every pass of every observation (obs_mosaic.units), in time order."""
    idx, _ = reel.load_index()
    seen, out = set(), []
    for r in idx[["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"]].itertuples(index=False):
        key = (r.TARGET_NAME, r.OBSERVATION_ID, "N" if r.INSTRUMENT_ID == "ISSNA" else "W")
        if key in seen or not isinstance(key[1], str):
            continue
        seen.add(key)
        out += [u for u in obs_mosaic.units(*key) if u["frames"]]
    return out


def movie_passes():
    """Every pass the windows play as a movie (its frames steadied one by one, not a mosaic), in time order."""
    return [u for u in all_passes() if u.get("kind") == "movie" or (u.get("movie") and not u["mosaic"])]


def centred(frame_id):
    """Auto center (on by default in a camera window, center=1): the view the server's centre_of gives the frame's
    pass (centred on the body, or north up where it is), which names the cache folder the window's picture is
    in; None where Auto center leaves the pass as it is (the window then asks for the picture as it is)."""
    try:
        view = obs_mosaic.centre_view(frame_id)
    except Exception:   # noqa: BLE001  (not centred: the window shows the picture as it is)
        return None
    return view if view.get("centre") or view.get("north") else None


def items(phase):
    """(name, work) of every item of the phase, in time order; work() makes it (a made file is found, not made).
    Composites and processed frames are made as a camera window asks for them, with Auto center (center=1, the
    default): built without it, the windows found none of them in the cache (2026-10-26)."""
    if phase == "frames":
        # 128: a pass's filmstrip
        return [(i, lambda c, i=i: [frame_server.webp(i, s, c) for s in (1024, 512, 128)]) for i in frame_ids()]
    if phase == "composites":
        # 1024 first: it also writes full, and keeps the composite in memory for the 512 one
        return [("_".join(s), lambda c, s=s: [frame_server.color_webp(s, z, c, centre=centred(s[-1])) for z in (1024, 512)])
                for s in page_sets()]
    if phase == "processed":
        # every frame: a window shows a frame processed on its own until its filter set is complete; 256 is the
        # pass strip's (the windows asked it about as often as 1024 on 8790, 2026-10-26), cheap from the frame in memory
        return [(i, lambda c, i=i: [frame_server.processed_webp(i, z, c, centre=centred(i)) for z in (1024, 512, 256)])
                for i in frame_ids()]
    if phase == "mosaics":
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c)) for u in mosaic_passes()]
    if phase == "chains":
        # a movie pass's stabilization and exposure chains (steady1-, exposure4-c11s0-plan4.json), which the page
        # holds to SPICE and evens out itself (Settings > Processing, Stabilize / Even exposure): no frames are made
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_chains(u, c)) for u in movie_passes()]
    if phase in ("movies", "strips"):
        # strips: a movie pass's steadied frames at 128, the movie strip under a window
        if phase == "strips":
            return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c, (128,))) for u in movie_passes()]
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c) + make_planes(u, c)) for u in movie_passes()]
    raise ValueError(phase)


def only(phase, todo, path):
    """todo cut to the items that use a frame listed in path (one frame id a line): the frame itself (frames,
    processed), a filter set holding it (composites), a pass taking it (mosaics, movies, strips). A remake after a fix
    to some frames: the items' made files are found, not made, so the fix's version bump (or removing the old files)
    comes first."""
    with open(path) as fh:
        # one frame id a line, maybe followed by more columns (lost_lines_frames.txt: "id,own|repeat")
        ids = {line.replace(",", " ").split()[0] for line in fh if line.strip() and not line.startswith("#")}
    if phase in ("frames", "processed"):
        return [t for t in todo if t[0] in ids]
    if phase == "composites":
        def set_ids(name):   # N1352055787_2_N1352055720_2 -> its frame ids (each one underscore)
            parts = name.split("_")
            return ["_".join(parts[k:k + 2]) for k in range(0, len(parts), 2)]
        return [t for t in todo if any(i in ids for i in set_ids(t[0]))]
    names = {"_".join(map(str, u["key"])) for u in all_passes() if any(f[1] in ids for f in u["frames"])}
    return [t for t in todo if t[0] in names]


WATCH_PAD = 3 * 3600   # s around a watched observation: what a window plays around a Moment, its neighbours too


def watched_first(todo):
    """todo with the items of the most watched stretches first (the Moments strip, web/replay/moments.csv, and
    Highlights, web/replay/highlights.csv: each observation's frames, WATCH_PAD either side), in time order, then
    the rest in time order. A Moment plays every frame of its stretch, its neighbours' too: by observation alone,
    most of what played on 8790 was still made on demand (2026-10-26). An item's time is its frame's (a set's last
    frame's, a pass's first frame's)."""
    import bisect
    import csv
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "replay")
    watched = set()
    for name in ("moments.csv", "highlights.csv"):
        try:
            with open(os.path.join(here, name)) as fh:
                for row in csv.DictReader(fh):
                    watched.update((row.get("obs") or "").split())
        except OSError:
            pass
    idx, _ = reel.load_index()
    time_of = dict(zip(idx["id"].tolist(), idx["seconds_1970"].astype(float).tolist()))
    spans = {}
    for o, t in zip(idx["OBSERVATION_ID"].tolist(), idx["seconds_1970"].astype(float).tolist()):
        if o in watched:
            a, b = spans.get(o, (t, t))
            spans[o] = (min(a, t), max(b, t))
    windows = []
    for a, b in sorted((a - WATCH_PAD, b + WATCH_PAD) for a, b in spans.values()):
        if windows and a <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], b)
        else:
            windows.append([a, b])
    starts = [w[0] for w in windows]
    pass_time = {}

    def when(name):
        last = "_".join(name.split("_")[-2:])   # a frame id (N1352055787_2), or a set's last one
        if last in time_of:
            return time_of[last]
        if not pass_time:   # a pass: TARGET_OBSERVATION_CAMERA_PASS
            pass_time.update({"_".join(map(str, u["key"])): u["frames"][0][3] for u in all_passes()})
        return pass_time.get(name)

    def hit(name):
        t = when(name)
        k = bisect.bisect_right(starts, t) - 1 if t is not None else -1
        return k >= 0 and t <= windows[k][1]
    marks = [hit(t[0]) for t in todo]
    first = [t for t, m in zip(todo, marks) if m]
    return first + [t for t, m in zip(todo, marks) if not m], len(first)


def make_pass(u, cache, sizes=(1024, 512), within=None, style=None, made=None, stopped=None):
    """What a window shows as it plays through the pass, at every frame at 1024 and 512, after the pass's plan and
    every tile (as web/frames/warm_pass.py does for one observation): a mosaic movie's rolling picture
    (rolling_webp, wait=True, in frame order, so each grows from the one before and is named after every tile
    drawn, the name a window asks for), a mosaic's mosaic so far, a movie's steadied frame.
    within (t0, t1), seconds since 1970: only the pictures of frames taken then (a stretch of the timeline, segment
    below), after every tile up to the last of them (and every rolling picture before them, each grown from the
    last). style: the page's Settings > Movie choices, as the window puts them in its request ({trail, laps,
    center, color}; the defaults when None). made(t): called as each frame of the stretch has its pictures, with
    the frame's time (a stretch's progress, Segments), so a long pass counts up frame by frame. stopped(): true once
    the stretch is stopped, so a long pass ends at the next picture instead of making the rest of it."""
    style = style or {}
    t0, t1 = within or (-float("inf"), float("inf"))
    last = max((j for j, f in enumerate(u["frames"]) if f[3] <= t1), default=-1)
    if last < 0:
        return 0
    p = obs_mosaic.plan(u, cache)
    for j in range(last + 1):
        if stopped and stopped():
            return 0
        obs_mosaic.tile(u, j, cache, p["display_scale"])
    kind, n = u.get("kind"), 0
    for j, f in enumerate(u["frames"][:last + 1]):
        if stopped and stopped():
            return n
        if f[3] < t0 and kind != "mosaic_movie":
            continue
        for size in sizes:
            if kind == "mosaic_movie":
                # (only the rolling picture: a window plays a mosaic movie rolling and never asks for its pass's mosaic
                # so far, which made for every frame took a Jupiter stretch's Pre-process 107 s on the Mini, 2026-10-27)
                obs_mosaic.rolling_webp(f[1], size, cache, style.get("laps", 1), wait=True,
                                        fade=(style.get("fade", 0), style.get("persist", 0)))
            elif u["mosaic"]:
                obs_mosaic._mosaic_at(u, j, size, cache)
            else:
                obs_mosaic.movie_webp(f[1], size, cache, style.get("trail", 0), style.get("color", True), wait=True, ahead=0,
                                      centre=style.get("center", True), steady=style.get("steady", 0),
                                      exposure=style.get("exposure", 0))
        if f[3] >= t0:
            n += 1
            if made:
                made(f[3])
    return n


def make_planes(u, cache, centre=True):
    """The frames the page's movie steps start from (steady-local.html, Settings > Processing > Steady movies on this
    computer), as it asks for them: each frame alone at SPICE's places with no gain and no trail (color=0, trail=0,
    steady=0, exposure=0), at 1024, Auto center as the window has it; and for a filled pass (Titan, Jupiter), the
    same before its detail filter (sharpen False, detail=0, files _d0), which the page sharpens itself after its
    exposure, trail or colour mix. Returns 0: make_pass has counted the pass's frames."""
    filled = bool(obs_mosaic.plan(u, cache)["display_scale"].get("filled"))
    for f in u["frames"]:
        for sharpen in ((True, False) if filled else (True,)):
            obs_mosaic.movie_webp(f[1], 1024, cache, 0, False, wait=True, ahead=0, centre=centre, sharpen=sharpen)
    return 0


def make_chains(u, cache):
    """A movie pass's stabilization chain and exposure chain, as the window plays it by default (colour, Auto
    center, not stabilized), after the pass's plan and every tile: the small files a window's Stabilize and Even
    exposure read, worked out once over the whole pass (obs_mosaic.steady_chain, exposure_chain). A made chain is
    found, not made. The pass's frames."""
    p = obs_mosaic.plan(u, cache)
    for j in range(len(u["frames"])):
        obs_mosaic.tile(u, j, cache, p["display_scale"])
    obs_mosaic.steady_chain(u, cache, p)
    obs_mosaic.exposure_chain(u, cache, p, True, True, 0)
    return len(u["frames"])


# ---------- sharing the Mini ----------

def busy(args):
    """Why the job should wait now, or None."""
    if args.pause and os.path.exists(os.path.expanduser(args.pause)):
        return "paused (pause file)"
    if getattr(args, "min_free", 0):
        free = shutil.disk_usage(args.cache).free / 1e9
        if free < args.min_free:
            return f"disk {free:.0f} GB free < {args.min_free:.0f}"
    load = os.getloadavg()[0]
    if load > args.max_load:
        return f"load {load:.1f} > {args.max_load}"
    for url in filter(None, [args.live] + (args.watch or "").split(",")):
        t0 = time.monotonic()
        try:
            urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5).read()
        except Exception:
            continue   # a server down is no reason to wait
        if time.monotonic() - t0 > 1:
            return f"{url} slow"
    if args.disk:
        # the LaCie is a USB spinning disk: past ~100 transfers a second the previews' pictures stall
        # (2026-10-23), so the job waits while it is that busy (its own reads and writes count too)
        try:
            out = subprocess.run(["iostat", "-d", "-w", "2", "-c", "2", args.disk], capture_output=True, text=True, timeout=10).stdout
            kb, tps, mb = map(float, out.strip().splitlines()[-1].split()[:3])
            if tps > args.max_tps:
                return f"{args.disk} busy ({tps:.0f} transfers/s)"
        except Exception:
            pass
    return None


class Holds:
    """busy(args), asked on a thread of its own every few seconds: its checks take a while (a /health round trip,
    the 2 s iostat sample), and asked on the thread that hands out the work they held every worker back (the
    LaCie's iostat every 20 frames held the frames phase to 9.3 a second, 2026-10-26). why() is the last answer."""
    EVERY = 5

    def __init__(self, args):
        self.args, self.last = args, busy(args)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.EVERY)
            try:
                self.last = busy(self.args)
            except Exception:
                self.last = None

    def why(self):
        return self.last


class Status:
    def __init__(self, args, total):
        self.args, self.lock = args, threading.Lock()
        self.s = {"phase": args.phase, "total": total, "done": 0, "made_s": 0.0, "errors": 0, "started": time.time(),
                  "state": "starting", "why_waiting": None, "last": None, "cache": args.cache, "updated": time.time()}
        self.recent = collections.deque(maxlen=200)   # (time, done) for the rate
        self.last_write = 0
        if args.status:
            os.makedirs(args.status, exist_ok=True)
            page = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prebuild.html")
            shutil.copyfile(page, os.path.join(args.status, "index.html"))
            prev = os.path.join(args.status, f"status-{args.phase}{_shard_tag(args)}.json")
            if os.path.exists(prev):
                with open(prev) as fh:
                    old = json.load(fh)
                self.s["errors"] = old.get("errors", 0)

    def update(self, **kw):
        with self.lock:
            self.s.update(kw)
            self.s["updated"] = time.time()
            self.recent.append((time.time(), self.s["done"]))
            if time.time() - self.last_write > 5 or kw.get("state") in ("done", "stopped"):
                self.write()

    def write(self):
        if len(self.recent) > 1 and self.recent[-1][0] > self.recent[0][0]:
            rate = (self.recent[-1][1] - self.recent[0][1]) / (self.recent[-1][0] - self.recent[0][0])
            self.s["rate_per_s"] = rate
            self.s["eta_s"] = (self.s["total"] - self.s["done"]) / rate if rate > 0 else None
        self.last_write = time.time()
        if not self.args.status:
            return
        tag = _shard_tag(self.args)
        for name in (f"status-{self.args.phase}{tag}.json",) + (() if tag else ("status.json",)):
            part = os.path.join(self.args.status, name + ".part")
            with open(part, "w") as fh:
                json.dump(self.s, fh)
            os.replace(part, os.path.join(self.args.status, name))


def run(args):
    todo = items(args.phase)
    if getattr(args, "only", None):
        todo = only(args.phase, todo, args.only)
        print(f"{len(todo)} items use the listed frames", flush=True)
    if getattr(args, "watched_first", False):
        todo, n = watched_first(todo)
        print(f"{n} items of watched observations first", flush=True)
    if getattr(args, "queue", None):
        return run_queue(args, todo)
    if args.first:
        todo = todo[args.first:]
    if args.shard:
        # one stretch of the items (k of n, from 0), for a process of its own (procs below)
        k, n = map(int, args.shard.split("/"))
        todo = todo[len(todo) * k // n:len(todo) * (k + 1) // n]
        args.first = 0
    status = Status(args, len(todo) + args.first)
    status.update(done=args.first, state="running")
    errors = open(os.path.join(args.status or args.cache, f"errors-{args.phase}{_shard_tag(args)}.jsonl"), "a")
    holds = Holds(args)
    # every thread may be drawing its own mosaic movie: each keeps its last pictures to grow the next from
    obs_mosaic.rolled_room(args.threads + 1)
    make(args, todo, status, errors, holds)
    status.update(state="done")


def make(args, todo, status, errors, holds):
    """todo's items made on args.threads threads, waiting while holds says to, each counted into status and each
    error written to errors (run, run_queue)."""
    pending, i = set(), 0
    with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]), \
            concurrent.futures.ThreadPoolExecutor(args.threads) as pool:
        def one(name, work):
            t0 = time.monotonic()
            try:
                work(args.cache)
                return name, time.monotonic() - t0, None
            except Exception as e:
                return name, time.monotonic() - t0, f"{type(e).__name__}: {e}"[:300]
        while i < len(todo) or pending:
            while i < len(todo) and len(pending) < args.threads * 2:
                why = holds.why()
                while why:
                    status.update(state="waiting", why_waiting=why)
                    time.sleep(Holds.EVERY)
                    why = holds.why()
                status.update(state="running", why_waiting=None)
                pending.add(pool.submit(contextvars.copy_context().run, one, *todo[i]))
                i += 1
            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                name, took, err = f.result()
                if err:
                    errors.write(json.dumps({"item": name, "error": err, "at": time.time()}) + "\n")
                    errors.flush()
                with status.lock:
                    status.s["done"] += 1
                    status.s["made_s"] += took
                    status.s["errors"] += bool(err)
                status.update(last=name)


PASS_PHASES = ("mosaics", "movies", "strips", "chains")
BALANCE = 8   # stretches per process (procs --balanced): enough small ones that the processes run out together


def stretches(args):
    """procs --balanced: the phase's items, as run takes them (--only, --watched-first), cut into consecutive
    stretches of about the same work, BALANCE for each process, and written as the files of a queue folder in the
    order the processes take them (run_queue): the watched observations' first, then biggest first, so the longest
    passes start at once and every process runs out of work at about the same time. A pass's work is its frames,
    any other item's one. Cut by count into one stretch a process (--shard), the busiest stretch of the mission ran
    on long after the rest: worked out from the passes' frames on one core, 64 processes take 0.84 h over the movie
    passes and 0.51 h over the mosaics that way, 0.47 h and 0.14 h balanced (2026-10-27). (folder, items)."""
    todo = items(args.phase)
    if getattr(args, "only", None):
        todo = only(args.phase, todo, args.only)
    first = 0
    if getattr(args, "watched_first", False):
        todo, first = watched_first(todo)
    size = {"_".join(map(str, u["key"])): len(u["frames"]) for u in all_passes()} if args.phase in PASS_PHASES else {}
    work = [size.get(name, 1) for name, _ in todo]
    each = sum(work) / max(1, args.procs * BALANCE)
    parts, start, w = [], 0, 0
    for k, x in enumerate(work):
        if k > start and (w >= each or k == first):   # a stretch ends at its share, and where the watched items end
            parts.append((start < first, w, start, k))
            start, w = k, 0
        w += x
    if start < len(todo):
        parts.append((start < first, w, start, len(todo)))
    parts.sort(key=lambda p: (not p[0], -p[1], p[2]))
    folder = os.path.join(args.status, f"queue-{args.phase}") if args.status else tempfile.mkdtemp(prefix="prebuild-queue-")
    shutil.rmtree(os.path.join(folder, "todo"), ignore_errors=True)   # a queue left by an earlier run (names only)
    shutil.rmtree(os.path.join(folder, "taken"), ignore_errors=True)
    for d in ("todo", "taken"):
        os.makedirs(os.path.join(folder, d))
    for n, (_, _, a, b) in enumerate(parts):
        with open(os.path.join(folder, "todo", f"{n:06d}"), "w") as fh:
            fh.write("".join(name + "\n" for name, _ in todo[a:b]))
    print(f"{len(todo)} items in {len(parts)} stretches of about {each:.0f} {'frames' if size else 'items'}, biggest first", flush=True)
    return folder, len(todo)


def take(queue, me):
    """The item names of the queue's next stretch, now this process's (moved into taken, which only one process
    can do), or None when none is left."""
    for f in sorted(os.listdir(os.path.join(queue, "todo"))):
        mine = os.path.join(queue, "taken", f"{f}-{me}")
        try:
            os.rename(os.path.join(queue, "todo", f), mine)
        except FileNotFoundError:   # another process took it first
            continue
        with open(mine) as fh:
            return [line for line in fh.read().splitlines() if line]
    return None


def run_queue(args, todo):
    """One process of procs --balanced: makes the queue's stretches (stretches), the next one each time it is done
    with the last, as run makes its items, until none is left. todo: the phase's items, as run takes them."""
    by_name = dict(todo)
    status = Status(args, 0)
    status.update(state="running")
    errors = open(os.path.join(args.status or args.cache, f"errors-{args.phase}{_shard_tag(args)}.jsonl"), "a")
    holds = Holds(args)
    obs_mosaic.rolled_room(args.threads + 1)
    while True:
        names = take(args.queue, _shard_tag(args).lstrip("-") or str(os.getpid()))
        if names is None:
            break
        part = [(name, by_name[name]) for name in names if name in by_name]
        with status.lock:
            status.s["total"] += len(part)
        make(args, part, status, errors, holds)
    status.update(state="done")


def _shard_tag(args):
    return "-" + args.shard.replace("/", "of") if getattr(args, "shard", None) else ""


def procs(args):
    """The phase as args.procs processes of one thread each, each making its own stretch of the items (--shard),
    and their status files added up into the phase's own. The pictures' makers are mostly Python, so threads of one
    process take turns on one core: composites ran 1.2 a second on 9 threads, ~8 on 9 processes (2026-10-26).
    --balanced: each process takes the next of many stretches of about the same work as it finishes the last
    (stretches, run_queue) instead of one stretch of its own."""
    n = args.procs
    argv = [a for a in sys.argv[1:]]
    for flag in ("--procs", "--threads", "--first"):
        while flag in argv:
            j = argv.index(flag)
            del argv[j:j + 2]
    total = None
    if args.balanced:
        queue, total = stretches(args)
        argv = [a for a in argv if a != "--balanced"] + ["--queue", queue]
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    kids = [subprocess.Popen([sys.executable, sys.argv[0]] + argv + ["--threads", "1", "--shard", f"{k}/{n}"],
                             env=env) for k in range(n)]
    status = Status(args, 0) if args.status else None
    while True:
        alive = [p for p in kids if p.poll() is None]
        if status:
            parts = []
            for k in range(n):
                try:
                    with open(os.path.join(args.status, f"status-{args.phase}-{k}of{n}.json")) as fh:
                        parts.append(json.load(fh))
                except (OSError, ValueError):
                    pass
            if parts:
                waiting = [p.get("why_waiting") for p in parts if p.get("state") == "waiting"]
                status.s.update(total=total if total is not None else sum(p["total"] for p in parts),
                                errors=sum(p["errors"] for p in parts),
                                made_s=sum(p["made_s"] for p in parts), procs=n,
                                state="waiting" if waiting and len(waiting) == len(parts) else "running",
                                why_waiting=waiting[0] if waiting else None)
                status.update(done=sum(p["done"] for p in parts))
        if not alive:
            break
        time.sleep(5)
    if status:
        status.update(state="done" if all(p.returncode == 0 for p in kids) else "stopped")
    sys.exit(max(p.returncode for p in kids))


def sample(args):
    """Times args.sample items spread over the mission into a scratch cache, and what they add up to."""
    todo = items(args.phase)
    random.seed(1)
    picked = random.sample(todo, min(args.sample, len(todo)))
    os.makedirs(args.cache, exist_ok=True)
    times = []
    with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
        for k, (name, work) in enumerate(picked):
            t0 = time.monotonic()
            try:
                out = work(args.cache)
            except Exception as e:
                print(f"{name}: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                continue
            took = time.monotonic() - t0
            times.append((took, out if args.phase in ("mosaics", "chains") else 1))
            print(f"{k + 1}/{len(picked)} {name} {took:.2f} s", flush=True)
    by_dir = collections.Counter()
    files = collections.Counter()
    for root, _, fs in os.walk(args.cache):
        rel = os.path.relpath(root, args.cache).split(os.sep)
        key = "/".join(rel[:2]) if args.phase != "mosaics" else rel[0] + "/" + (rel[2] if len(rel) > 2 else "")
        for f in fs:
            by_dir[key] += os.path.getsize(os.path.join(root, f))
            files[key] += 1
    secs = sorted(t for t, _ in times)
    total_bytes = sum(by_dir.values())
    out = {"phase": args.phase, "items": len(todo), "sampled": len(times),
           "s_median": secs[len(secs) // 2] if secs else None, "s_mean": sum(secs) / len(secs) if secs else None,
           "s_p90": secs[int(len(secs) * 0.9)] if secs else None,
           "bytes_per_item": total_bytes / max(1, len(times)), "frames_in_sample": sum(n for _, n in times),
           "est_hours_one_thread": sum(secs) / max(1, len(secs)) * len(todo) / 3600,
           "est_gb": total_bytes / max(1, len(times)) * len(todo) / 1e9,
           "by_folder": {k: {"bytes": v, "files": files[k]} for k, v in sorted(by_dir.items())}}
    if args.phase == "mosaics":
        out["frames_in_passes"] = sum(len(u["frames"]) for u in mosaic_passes())
    print(json.dumps(out, indent=1))
    if args.status:
        os.makedirs(args.status, exist_ok=True)
        with open(os.path.join(args.status, f"sample-{args.phase}.json"), "w") as fh:
            json.dump(out, fh, indent=1)


# ---------- one stretch of the timeline, made ahead for the page (the frame server's POST /prebuild) ----------
# Cassini OS: highlight a stretch of the timeline and press Pre-process; the frame server makes every picture the
# camera windows will ask for in that stretch, with the makers above (the same files the windows' requests find),
# and the stretch then plays as a movie at the frame rate the person picks, from the cache. One stretch is made at
# a time at full speed (SEGMENT_THREADS): someone asked for it and is waiting, so it gives way only to the server's
# own picture requests (frame_server.live_requests: the camera windows' pictures go first), never to the machine's
# load, which other jobs and previews on the Mini set off. It holds while the pause file exists (SEGMENT_PAUSE: the
# Mini held for one heavy job at a time), and says so.

SEGMENT_THREADS = max(2, min(4, (os.cpu_count() or 4) // 2))
SEGMENT_PAUSE = "~/prebuild.pause"
SEGMENT_YIELD = 1.0     # seconds at most a picture of the stretch waits for the server's own requests to clear
# frames in one stretch at most (the frames the bar counts; a busy day near Saturn has ~1,500): 0 is no limit. The
# page asks its own (Settings > Playback, most=); this is the ceiling over it, for a server that needs one (the public
# site, CASSINI_SEGMENT_MAX). A stretch's pictures are made a few at a time and its plan is a small row per picture
# (~0.6 KB), so a stretch of 100,000 frames (~200,000 pictures) holds ~120 MB while it is made.
SEGMENT_MAX = int(os.environ.get("CASSINI_SEGMENT_MAX", "0") or 0)
ETA_WINDOW, ETA_LEAST = 60.0, 8.0   # seconds of pace the time left is worked out from, and the least that says anything
SEGMENT_KEEP = 12       # finished stretches the server keeps the status of (a stretch asked again past them is made again from the cache)
SEGMENT_SIZES = (512, 768, 1024)
SEGMENT_ANSWER = 0.3    # seconds POST /prebuild waits for its stretch to be made before it answers how far it is


def segment_options(q):
    """The stretch and the page's choices from a POST /prebuild query (parse_qs): from/until (UTC, ISO), cams (N,
    W or NW), sizes (the windows' picture sizes), look/colors (as on every picture route), mosaics/steady/color
    (Settings > Cameras and Movie), processed (processed single frames), center (Auto center: center=1 as the
    windows ask), off (the pipeline steps turned off, calibration.STEPS), trail/laps/fade/persist (the movie style)
    and most (frames in the stretch at most, 0 for no limit; not part of the stretch's id). ValueError for anything else."""
    get = lambda k, d=None: q.get(k, [d])[0]
    when = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=datetime.timezone.utc).timestamp()
    try:
        t0, t1 = when(get("from", "")), when(get("until", ""))
    except ValueError:
        raise ValueError("from= and until= take UTC times, 2006-09-15T14:32:00")
    if not t1 > t0:
        raise ValueError("until= must come after from=")
    cams = "".join(c for c in "NW" if c in (get("cams") or "NW"))
    try:
        sizes = sorted({min(SEGMENT_SIZES, key=lambda z: abs(z - int(x))) for x in (get("sizes") or "1024").split(",") if x})
        trail, laps = int(get("trail", "0") or 0), int(get("laps", "1") or 1)
        steady, exposure = int(get("steady_smooth", "0") or 0), int(get("exposure", "0") or 0)
        most = max(0, int(get("most", "0") or 0))
        fade = obs_mosaic.fade_style(int(get("fade", "0") or 0), int(get("persist", str(obs_mosaic.FADE_PERSIST)) or 0))
    except ValueError:
        raise ValueError("sizes=, trail=, laps=, fade=, persist= and most= take numbers")
    if not cams or not sizes:
        raise ValueError("cams= takes N, W or NW")
    on = lambda k: get(k, "1") != "0"
    off = [s for s in calibration.STEPS if s in (get("off") or "").split(",")]
    return {"from": t0, "until": t1, "cams": cams, "sizes": sizes, "most": most,
            "look": get("look", calibration.LOOKS[0]), "colors": get("colors", calibration.COLORS[0]),
            # the pipeline steps turned off (Settings > Processing), only when any are, so a stretch's id is as before
            **({"off": off} if off else {}),
            "mosaics": on("mosaics"), "steady": on("steady"), "processed": on("processed"), "center": on("center"),
            "style": {"trail": max(0, min(obs_mosaic.TRAIL, trail)), "laps": max(1, min(obs_mosaic.TRAIL, laps)),
                      "fade": fade[0], "persist": fade[1],
                      "center": on("center"), "color": on("color"),
                      # image stabilization (Settings > Movie), only when on, so a stretch's id is as before
                      **({"steady": max(0, min(obs_mosaic.STEADY_MOST, steady))} if steady else {}),
                      **({"exposure": obs_mosaic.exposure_of(exposure)} if exposure else {})}}


@functools.lru_cache(None)
def sets_ready():
    """page_sets in the order they are ready (the time of a set's last frame, when its composite can be made; sets
    ready at the same time in page_sets' order), and those times (seconds since 1970): a stretch finds its sets by
    bisection instead of going through all ~45,000 of the mission (a tenth of a second on each Pre-process). Made as
    the frame server starts (frame_server.warm_prebuild), from the rows of the frames it keeps for the mosaics."""
    idx, row = obs_mosaic._row_of()
    t = idx["seconds_1970"].to_numpy()
    ready = sorted(((float(max(t[row[i]] for i in s)), s) for s in page_sets()), key=lambda x: x[0])
    return [r for r, _ in ready], [s for _, s in ready]


def segment_items(o):
    """(name, time, pictures, work) for every picture the camera windows ask for in the stretch o
    (segment_options), in time order: each frame (at the windows' sizes, and 128 for a pass's filmstrip), each
    filter set's composite (at the frame that completes it, when the window shows it), and each mosaic, mosaic
    movie or movie pass with frames in the stretch (make_pass within it)."""
    import frame_server
    idx, _ = reel.load_index()
    t0, t1, cams, sizes = o["from"], o["until"], o["cams"], o["sizes"]

    def centre(frame_id):
        """Auto center (o["center"]): the pass's view as the server's centre_of gives it (centred), or None."""
        return centred(frame_id) if o.get("center") else None

    def single(i, c):
        """A frame on its own as the window shows it: processed (Settings > Cameras > Processed single frames),
        centred when Auto center centres its pass, at the windows' sizes; and the archive frame (the stand-in
        under a composite, the filmstrip's 128)."""
        if o.get("processed", True):
            for z in sizes:
                frame_server.processed_webp(i, z, c, centre=centre(i))
        return [frame_server.webp(i, z, c) for z in (*sizes, 128)]
    t = idx["seconds_1970"].to_numpy()
    lo, hi = t.searchsorted(t0, "left"), t.searchsorted(t1, "right")
    rows = idx.iloc[lo:hi]
    out, keys = [], {}
    for r in rows[["id", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "seconds_1970"]].itertuples(index=False):
        cam = "N" if r.INSTRUMENT_ID == "ISSNA" else "W"
        if cam not in cams:
            continue
        work = lambda c, i=r.id: single(i, c)
        work.frame = True   # one of the frames the bar counts (Segments: the stretch's frames, its limit)
        out.append((r.id, float(r.seconds_1970), 1, work))
        if isinstance(r.OBSERVATION_ID, str):
            keys.setdefault((r.TARGET_NAME, r.OBSERVATION_ID, cam), None)
    readies, sets = sets_ready()
    for k in range(bisect.bisect_left(readies, t0), bisect.bisect_right(readies, t1)):
        ready, s = readies[k], sets[k]
        if s[0][0] in cams:
            out.append(("_".join(s), ready, 1, lambda c, s=s: [frame_server.color_webp(s, z, c, centre=centre(s[-1])) for z in sizes]))
    for key in keys:
        for u in obs_mosaic.units(*key):
            n = sum(t0 <= f[3] <= t1 for f in u["frames"])
            if not n:
                continue
            movie = u.get("kind") != "mosaic_movie" and not u["mosaic"]
            if (o["mosaics"] if not movie else o["steady"] and (u.get("kind") == "movie" or u.get("movie"))):
                first = next(f[3] for f in u["frames"] if f[3] >= t0)
                work = lambda c, made=None, stopped=None, u=u: make_pass(u, c, sizes, (t0, t1), o["style"], made, stopped)
                work.pass_key = u["key"]
                out.append(("_".join(map(str, u["key"])), first, n, work))
    out.sort(key=lambda x: x[1])
    return out


class Segments:
    """The stretches asked for, made one at a time in the order asked. A stretch asked for again (the same
    options) is the same job: its status, or a new run when it failed or was stopped."""

    def __init__(self, cache, live=None):
        self.cache, self.lock, self.jobs, self.queue = cache, threading.Lock(), {}, []
        # live(): how many picture requests the server is answering now (frame_server.live_requests)
        self.live = live or (lambda: 0)
        self.wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    @staticmethod
    def key(o):
        import hashlib
        o = {k: v for k, v in o.items() if k != "most"}   # the limit is not part of what is made
        return hashlib.sha1(json.dumps(o, sort_keys=True).encode()).hexdigest()[:16]

    def submit(self, o, wait=0.0):
        """The stretch o asked for: its job as the page reads it (_public). wait: seconds to wait for a new job to
        be made before answering (SEGMENT_ANSWER from POST /prebuild): a stretch whose pictures are all in the cache is
        made in a tenth of a second, and answered made, so the page says it is ready at once; a longer one is answered
        as far as it got."""
        jid = self.key(o)
        with self.lock:
            job = self.jobs.get(jid)
            # (a stretch stopped but still letting go of its last pictures is asked again as a new run, queued behind it)
            if job and job["state"] not in ("failed", "stopped") and not job["stop"]:
                return self._public(job)
            job = {"id": jid, "state": "queued", "options": o, "items": [], "total": 0, "frames": 0, "done": 0, "errors": 0, "first": 0,
                   "finished": [], "partial": {}, "asked": time.time(), "took": None, "why_waiting": None, "error": None,
                   "stop": False, "recent": collections.deque(maxlen=2000)}
            self.jobs[jid] = job
            self.queue.append(job)
            self._forget()
        self.wake.set()
        until = time.monotonic() + wait
        while job["state"] not in ("done", "failed", "stopped") and time.monotonic() < until:
            time.sleep(0.01)
        with self.lock:
            return self._public(job)

    def _forget(self):
        """Only the last SEGMENT_KEEP finished stretches are kept (with the lock held): a long session of stretches
        does not pile up their plans."""
        ended = [j for j, x in self.jobs.items() if x["state"] in ("done", "failed", "stopped")]
        for j in ended[:max(0, len(ended) - SEGMENT_KEEP)]:
            del self.jobs[j]

    def status(self, jid):
        with self.lock:
            job = self.jobs.get(jid)
            return self._public(job) if job else None

    def stop(self, jid):
        with self.lock:
            job = self.jobs.get(jid)
            if not job:
                return None
            job["stop"] = True
            if job["state"] == "queued":
                job["state"] = "stopped"
                self.queue.remove(job)
            return self._public(job)

    def _public(self, job):
        """What the page reads: state (queued, planning, making, waiting (held by the pause file), finishing, done, failed, stopped), pictures done of total, how
        far in time every picture is made (through, UTC), seconds left and the place in line."""
        out = {k: job[k] for k in ("id", "state", "total", "frames", "done", "errors", "took", "why_waiting", "error")}
        through = job["options"]["from"]
        if job["finished"] and all(job["finished"]):
            through = job["options"]["until"]
        elif job["items"]:
            # up to the first picture not made yet: an item not finished holds it at its time, a pass being made at
            # its last frame made (make_pass's made), so the line moves through a long pass with its frames
            # (from the first item not finished, job["first"], so a stretch of 100,000 pictures reads as fast as one of 100)
            limit, items, fin = job["options"]["until"], job["items"], job["finished"]
            while job["first"] < len(fin) and fin[job["first"]]:
                job["first"] += 1
            for k in range(job["first"], len(items)):
                if items[k][1] >= limit:
                    break
                if not fin[k]:
                    limit = min(limit, job["partial"].get(k, items[k][1]))
            through = max(through, limit)
        out["through"] = datetime.datetime.fromtimestamp(through, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        # seconds left from the pace of the last ETA_WINDOW seconds, once there are ETA_LEAST of them: the pictures found
        # in the cache come by the hundred a second, so a stretch's first second says nothing of the ones to be made
        r, now = job["recent"], time.monotonic()
        r = [x for x in r if x[0] >= now - ETA_WINDOW]
        if job["state"] == "making" and len(r) > 1 and r[-1][0] - r[0][0] >= ETA_LEAST and r[-1][1] > r[0][1]:
            out["eta"] = (job["total"] - job["done"]) / ((r[-1][1] - r[0][1]) / (r[-1][0] - r[0][0]))
        if job["state"] == "queued":
            out["ahead"] = self.queue.index(job)
        return out

    def _worker(self):
        while True:
            self.wake.wait(5)
            self.wake.clear()
            while True:
                with self.lock:
                    if not self.queue:
                        break
                    job = self.queue[0]
                try:
                    self._run(job)
                except Exception as e:   # noqa: BLE001  (a stretch that fails says why; the next one goes on)
                    job["state"], job["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
                    traceback.print_exc()
                with self.lock:
                    if self.queue and self.queue[0] is job:
                        self.queue.pop(0)

    def _run(self, job):
        o, t_start = job["options"], time.monotonic()
        job["state"] = "planning"
        items = segment_items(o)
        total, frames = sum(x[2] for x in items), sum(bool(getattr(x[3], "frame", False)) for x in items)
        limits = [m for m in (o.get("most") or 0, SEGMENT_MAX) if m > 0]
        most = min(limits) if limits else 0
        if most and frames > most:
            job["state"], job["total"], job["frames"] = "failed", total, frames
            job["error"] = (f"{frames:,} frames in that stretch; pre-process up to {most:,} at a time"
                            + (" (Settings > Playback)" if most == o.get("most") else ""))
            return
        with self.lock:
            job.update(items=items, total=total, frames=frames, finished=[False] * len(items), state="making")

        def one(k):
            if job["stop"]:
                return k, "stopped", 0
            work, told = job["items"][k][3], [0]

            def made(t):
                # a pass counts its frames as they are made (a mosaic movie's can take minutes when its tiles are
                # not made yet), so the bar never sits still through it
                with self.lock:
                    told[0] += 1
                    job["done"] += 1
                    job["partial"][k] = t
                    job["recent"].append((time.monotonic(), job["done"]))
            try:
                if getattr(work, "pass_key", None):
                    work(self.cache, made, lambda: job["stop"])
                    if job["stop"] and told[0] < job["items"][k][2]:
                        return k, "stopped", told[0]   # ended part way: what it made is counted, the rest is not
                else:
                    work(self.cache)
                return k, None, told[0]
            except Exception as e:   # noqa: BLE001  (counted and logged; the stretch goes on)
                return k, f"{type(e).__name__}: {e}", told[0]

        # each thread may hold a mosaic movie for all its frames, and the windows play theirs in the same process:
        # room for all of them to keep their last pictures (obs_mosaic._rolled)
        obs_mosaic.rolled_room(SEGMENT_THREADS + 2)
        with calibration.looking(o["look"]), calibration.coloring(o["colors"]), calibration.stepping(o.get("off", ())), \
                concurrent.futures.ThreadPoolExecutor(SEGMENT_THREADS) as pool:
            pending, i = set(), 0
            while i < len(items) or pending:
                while i < len(items) and len(pending) < SEGMENT_THREADS * 2 and not job["stop"]:
                    while os.path.exists(os.path.expanduser(SEGMENT_PAUSE)) and not job["stop"]:
                        job["state"], job["why_waiting"] = "waiting", "held"
                        time.sleep(3)
                    job["state"], job["why_waiting"] = "making", None
                    # the camera windows' own pictures first: a moment's pause while the server answers them
                    until = time.monotonic() + SEGMENT_YIELD
                    while self.live() > 0 and time.monotonic() < until and not job["stop"]:
                        time.sleep(0.05)
                    pending.add(pool.submit(contextvars.copy_context().run, one, i))
                    i += 1
                if not pending:
                    break
                done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:
                    k, err, told = f.result()
                    if err == "stopped":
                        continue
                    if err:
                        print(f"prebuild segment {job['id']} {items[k][0]}: {err}", flush=True)
                    with self.lock:
                        job["finished"][k] = True
                        job["done"] += max(0, items[k][2] - told)
                        job["errors"] += bool(err)
                        job["recent"].append((time.monotonic(), job["done"]))
        # the makers start the next tiles and mosaic-movie pictures of a pass in the background (obs_mosaic
        # tiles_ahead, rolling_ahead): done once those threads for the stretch's passes are through too (up to 2 min)
        keys = {k for k in (getattr(it[3], "pass_key", None) for it in items) if k}
        until = time.monotonic() + 120
        while keys and not job["stop"] and time.monotonic() < until:
            with obs_mosaic._lock:
                busy_keys = {k for k in keys if any(r[0] == k for r in obs_mosaic._ahead_running) or any(r[0] == k for r in obs_mosaic._roll_ahead)}
            if not busy_keys:
                break
            job["state"] = "finishing"
            time.sleep(1)
        job["took"] = time.monotonic() - t_start
        with self.lock:
            # the plan's makers (and what they hold) are let go: only the times and counts stay for the status
            job["items"] = [(x[0], x[1], x[2], None) for x in items]
            job["state"] = "stopped" if job["stop"] else "done"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=PHASES + ("count",))
    ap.add_argument("--cache", required=True, help="the frame server's --cache folder to fill")
    ap.add_argument("--status", help="folder for status.json and the progress page (e.g. web/cassini-os/prebuild)")
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--first", type=int, default=0, help="skip this many items (they are made)")
    ap.add_argument("--sample", type=int, help="only time this many items, spread over the mission")
    ap.add_argument("--max-load", type=float, default=float(os.cpu_count() or 8) * 0.8)
    ap.add_argument("--live", default="http://127.0.0.1:8765", help="the live server, waited for while slow ('' for none)")
    ap.add_argument("--watch", default="", help="more servers to wait for while slow, comma separated (previews)")
    ap.add_argument("--disk", help="BSD name of the LaCie (diskutil list), waited for while busier than --max-tps")
    ap.add_argument("--max-tps", type=float, default=100)
    ap.add_argument("--pause", default="~/prebuild.pause", help="while this file exists the job waits")
    ap.add_argument("--min-free", type=float, default=0, help="GB: the job waits while the cache's disk has less free")
    ap.add_argument("--only", help="file of frame ids: only the items using them (a remake after a fix)")
    ap.add_argument("--watched-first", action="store_true", help="the Moments and Highlights observations' items first")
    ap.add_argument("--procs", type=int, default=0, help="run the phase as this many processes of one thread each")
    ap.add_argument("--balanced", action="store_true",
                    help="with --procs: the items in many stretches of about the same work (a pass's frames), biggest "
                         "first, each process taking the next as it finishes the last")
    ap.add_argument("--shard", help=argparse.SUPPRESS)   # k/n: one process's stretch (--procs)
    ap.add_argument("--queue", help=argparse.SUPPRESS)   # a --balanced process's queue folder (stretches)
    args = ap.parse_args()
    if args.phase == "count":
        sets, passes = page_sets(), mosaic_passes()
        print(json.dumps({"frames": len(frame_ids()), "sets": len(sets), "set_frames": sum(map(len, sets)),
                          "mosaic_passes": len(passes), "mosaic_frames": sum(len(u["frames"]) for u in passes)}))
        return
    obs_mosaic.tiles_ahead = lambda *a, **k: None      # everything is made here, in order (warm_pass.py)
    obs_mosaic.rolling_ahead = lambda *a, **k: None
    data_source = frame_server.data_source
    data_source.KEEP_SPICE_CACHE = True
    data_source._zip_index() if data_source.using_zip() else None
    (sample if args.sample else procs if args.procs > 1 else run)(args)


if __name__ == "__main__":
    main()
