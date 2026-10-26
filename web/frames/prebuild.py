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
  movies      the same for every movie pass: its steadied frames (movie_webp)
  processed   /frames/processed/<ID>.webp at 1024 for movie mode, every frame not in a filter set

Made to share the Mac Mini with the live and preview servers: run it under `nice -n 19 taskpolicy -b` (low CPU and
disk priority), one process with a few threads. It waits while the 1-minute load is over --max-load, while the
live server's (or a --watch preview's) /health answers slower than a
second, while the LaCie (--disk) moves more than --max-tps transfers a second, or while the pause file exists (touch it to hold the job,
remove it to go on). status.json (and a page reading it, index.html) in --status says how far it is.

  CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
    nice -n 19 taskpolicy -b python web/frames/prebuild.py frames --cache /Volumes/cassini-cache \\
    --status web/cassini-os/prebuild
  ... prebuild.py composites --sample 200      times 200 spread-out items into a scratch cache and prints the
                                                seconds and bytes per item (and the totals they mean)
"""
import argparse
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
import threading
import time
import traceback
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_server  # noqa: E402  (puts the repo on the path, loads the pipeline)
import calibration  # noqa: E402
import obs_mosaic  # noqa: E402
import reel  # noqa: E402

PHASES = ("frames", "composites", "mosaics", "movies", "processed")
SET_GAP = 300   # head-quiet.html findSets


@functools.lru_cache(None)
def frame_ids():
    """Every frame of the index, in time order."""
    idx, _ = reel.load_index()
    return idx["id"].tolist()


@functools.lru_cache(None)
def page_sets():
    """The filter sets the camera windows ask composites of, with their ids in the order the page puts in the URL:
    head-quiet.html findSets and pickChannels, on the same index (reel.load_index's own sets differ: the page also
    takes CB1 as red)."""
    idx, _ = reel.load_index()
    cams = ["N" if c == "ISSNA" else "W" for c in idx["INSTRUMENT_ID"]]
    inst, ids, targets, obs = idx["INSTRUMENT_ID"].tolist(), idx["id"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist()
    f1s, f2s, t = idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(), idx["seconds_1970"].tolist()
    sets, run = [], {}

    def close(cam):
        r = run.pop(cam, None)
        if not r or len(r["rows"]) < 2:
            return
        by = dict(zip(r["filters"], r["rows"]))
        blue = next((f for f in ("BL1", "BL2", "VIO") if f in by), None)
        red = next((f for f in ("RED", "CB1") if f in by), None)
        if red and "GRN" in by and blue:
            use = [by[red], by["GRN"], by[blue]]
        else:
            w = sorted(r["rows"], key=lambda q: -reel.wavelength(inst[q], f1s[q] + f2s[q]))
            use = [w[0], w[len(w) // 2], w[-1]] if len(w) >= 3 else w
        sets.append([ids[q] for q in use])

    for q in range(len(ids)):
        cam, f = cams[q], reel.colour_filter(f1s[q], f2s[q])
        r = run.get(cam)
        if not f:
            close(cam)
            continue
        if r and targets[q] == r["target"] and obs[q] == r["obs"] and t[q] - r["last"] <= SET_GAP and f not in r["filters"]:
            r["rows"].append(q); r["filters"].append(f); r["last"] = t[q]
        else:
            close(cam)
            run[cam] = {"target": targets[q], "obs": obs[q], "rows": [q], "filters": [f], "last": t[q]}
    for cam in list(run):
        close(cam)
    return sets


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


def items(phase):
    """(name, work) of every item of the phase, in time order; work() makes it (a made file is found, not made)."""
    if phase == "frames":
        # 128: a pass's filmstrip
        return [(i, lambda c, i=i: [frame_server.webp(i, s, c) for s in (1024, 512, 128)]) for i in frame_ids()]
    if phase == "composites":
        # 1024 first: it also writes full, and keeps the composite in memory for the 512 one
        return [("_".join(s), lambda c, s=s: [frame_server.color_webp(s, z, c) for z in (1024, 512)]) for s in page_sets()]
    if phase == "processed":
        in_sets = {i for s in page_sets() for i in s}
        return [(i, lambda c, i=i: frame_server.processed_webp(i, 1024, c)) for i in frame_ids() if i not in in_sets]
    if phase == "mosaics":
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c)) for u in mosaic_passes()]
    if phase == "movies":
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c))
                for u in all_passes() if u.get("kind") == "movie" or (u.get("movie") and not u["mosaic"])]
    raise ValueError(phase)


def make_pass(u, cache, sizes=(1024, 512), within=None, style=None):
    """What a window shows as it plays through the pass, at every frame at 1024 and 512, after the pass's plan and
    every tile (as web/frames/warm_pass.py does for one observation): a mosaic movie's rolling picture
    (rolling_webp, wait=True, in frame order, so each grows from the one before and is named after every tile
    drawn, the name a window asks for), a mosaic's mosaic so far, a movie's steadied frame.
    within (t0, t1), seconds since 1970: only the pictures of frames taken then (a stretch of the timeline, segment
    below), after every tile up to the last of them (and every rolling picture before them, each grown from the
    last). style: the page's Settings > Movie choices, as the window puts them in its request ({trail, laps,
    center, color}; the defaults when None)."""
    style = style or {}
    t0, t1 = within or (-float("inf"), float("inf"))
    last = max((j for j, f in enumerate(u["frames"]) if f[3] <= t1), default=-1)
    if last < 0:
        return 0
    p = obs_mosaic.plan(u, cache)
    for j in range(last + 1):
        obs_mosaic.tile(u, j, cache, p["display_scale"])
    kind, n = u.get("kind"), 0
    for j, f in enumerate(u["frames"][:last + 1]):
        if f[3] < t0 and kind != "mosaic_movie":
            continue
        n += f[3] >= t0
        for size in sizes:
            if kind == "mosaic_movie":
                obs_mosaic.rolling_webp(f[1], size, cache, style.get("laps", 1), wait=True,
                                        fade=(style.get("fade", 0), style.get("persist", 0)))
                # a window asks a mosaic movie's frames of /frames/mosaic too (its pass lane, the Mosaic switch)
                if within:
                    obs_mosaic._mosaic_at(u, j, size, cache)
            elif u["mosaic"]:
                obs_mosaic._mosaic_at(u, j, size, cache)
            else:
                obs_mosaic.movie_webp(f[1], size, cache, style.get("trail", 0), style.get("color", True), wait=True, ahead=0,
                                      centre=style.get("center", True))
    return n


# ---------- sharing the Mini ----------

def busy(args):
    """Why the job should wait now, or None."""
    if args.pause and os.path.exists(os.path.expanduser(args.pause)):
        return "paused (pause file)"
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
            prev = os.path.join(args.status, f"status-{args.phase}.json")
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
        for name in (f"status-{self.args.phase}.json", "status.json"):
            part = os.path.join(self.args.status, name + ".part")
            with open(part, "w") as fh:
                json.dump(self.s, fh)
            os.replace(part, os.path.join(self.args.status, name))


def run(args):
    todo = items(args.phase)
    if args.first:
        todo = todo[args.first:]
    status = Status(args, len(todo) + args.first)
    status.update(done=args.first, state="running")
    errors = open(os.path.join(args.status or args.cache, f"errors-{args.phase}.jsonl"), "a")
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
                why = busy(args) if i % 20 == 0 else None
                while why:
                    status.update(state="waiting", why_waiting=why)
                    time.sleep(30)
                    why = busy(args)
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
    status.update(state="done")


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
            times.append((took, out if args.phase == "mosaics" else 1))
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
SEGMENT_MAX = 6000      # pictures in one stretch (a busy day near Saturn has ~1,500)
SEGMENT_SIZES = (512, 768, 1024)


def segment_options(q):
    """The stretch and the page's choices from a POST /prebuild query (parse_qs): from/until (UTC, ISO), cams (N,
    W or NW), sizes (the windows' picture sizes), look/colors (as on every picture route), mosaics/steady/color
    (Settings > Cameras and Movie), processed (processed single frames), center (Auto center: center=1 as the
    windows ask) and trail/laps/fade/persist (the movie style). ValueError for anything else."""
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
        fade = obs_mosaic.fade_style(int(get("fade", "0") or 0), int(get("persist", str(obs_mosaic.FADE_PERSIST)) or 0))
    except ValueError:
        raise ValueError("sizes=, trail=, laps=, fade= and persist= take numbers")
    if not cams or not sizes:
        raise ValueError("cams= takes N, W or NW")
    on = lambda k: get(k, "1") != "0"
    return {"from": t0, "until": t1, "cams": cams, "sizes": sizes,
            "look": get("look", calibration.LOOKS[0]), "colors": get("colors", calibration.COLORS[0]),
            "mosaics": on("mosaics"), "steady": on("steady"), "processed": on("processed"), "center": on("center"),
            "style": {"trail": max(0, min(obs_mosaic.TRAIL, trail)), "laps": max(1, min(obs_mosaic.TRAIL, laps)),
                      "fade": fade[0], "persist": fade[1],
                      "center": on("center"), "color": on("color")}}


@functools.lru_cache(None)
def frame_times():
    """Each frame's time, seconds since 1970, by id."""
    idx, _ = reel.load_index()
    return dict(zip(idx["id"].tolist(), idx["seconds_1970"].astype(float).tolist()))


def segment_items(o):
    """(name, time, pictures, work) for every picture the camera windows ask for in the stretch o
    (segment_options), in time order: each frame (at the windows' sizes, and 128 for a pass's filmstrip), each
    filter set's composite (at the frame that completes it, when the window shows it), and each mosaic, mosaic
    movie or movie pass with frames in the stretch (make_pass within it)."""
    import frame_server
    idx, _ = reel.load_index()
    t0, t1, cams, sizes = o["from"], o["until"], o["cams"], o["sizes"]

    def centre(frame_id):
        """Auto center (o["center"]): the pass's centred view, as the server's centre_of works it out, or None (the
        window then asks for the picture as it is)."""
        if not o.get("center"):
            return None
        try:
            view = obs_mosaic.centre_view(frame_id)
        except Exception:   # noqa: BLE001  (not centred: the window shows the picture as it is)
            return None
        return view if view.get("centre") else None

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
        out.append((r.id, float(r.seconds_1970), 1, lambda c, i=r.id: single(i, c)))
        if isinstance(r.OBSERVATION_ID, str):
            keys.setdefault((r.TARGET_NAME, r.OBSERVATION_ID, cam), None)
    times = frame_times()
    for s in page_sets():
        ready = max(times[i] for i in s)
        if t0 <= ready <= t1 and s[0][0] in cams:
            out.append(("_".join(s), ready, 1, lambda c, s=s: [frame_server.color_webp(s, z, c, centre=centre(s[-1])) for z in sizes]))
    for key in keys:
        for u in obs_mosaic.units(*key):
            n = sum(t0 <= f[3] <= t1 for f in u["frames"])
            if not n:
                continue
            movie = u.get("kind") != "mosaic_movie" and not u["mosaic"]
            if (o["mosaics"] if not movie else o["steady"] and (u.get("kind") == "movie" or u.get("movie"))):
                first = next(f[3] for f in u["frames"] if f[3] >= t0)
                work = lambda c, u=u: make_pass(u, c, sizes, (t0, t1), o["style"])
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
        return hashlib.sha1(json.dumps(o, sort_keys=True).encode()).hexdigest()[:16]

    def submit(self, o):
        jid = self.key(o)
        with self.lock:
            job = self.jobs.get(jid)
            if job and job["state"] not in ("failed", "stopped"):
                return self._public(job)
            job = {"id": jid, "state": "queued", "options": o, "items": [], "total": 0, "done": 0, "errors": 0,
                   "finished": [], "asked": time.time(), "took": None, "why_waiting": None, "error": None,
                   "stop": False, "recent": collections.deque(maxlen=60)}
            self.jobs[jid] = job
            self.queue.append(jid)
        self.wake.set()
        return self._public(job)

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
                self.queue.remove(jid)
            return self._public(job)

    def _public(self, job):
        """What the page reads: state (queued, planning, making, waiting (held by the pause file), finishing, done, failed, stopped), pictures done of total, how
        far in time every picture is made (through, UTC), seconds left and the place in line."""
        out = {k: job[k] for k in ("id", "state", "total", "done", "errors", "took", "why_waiting", "error")}
        through = job["options"]["from"]
        for item, ok in zip(job["items"], job["finished"]):
            if not ok:
                break
            through = item[1]
        if job["finished"] and all(job["finished"]):
            through = job["options"]["until"]
        out["through"] = datetime.datetime.fromtimestamp(through, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        r = job["recent"]
        if job["state"] == "making" and len(r) > 1 and r[-1][0] > r[0][0] and r[-1][1] > r[0][1]:
            out["eta"] = (job["total"] - job["done"]) / ((r[-1][1] - r[0][1]) / (r[-1][0] - r[0][0]))
        if job["state"] == "queued":
            out["ahead"] = self.queue.index(job["id"])
        return out

    def _worker(self):
        while True:
            self.wake.wait(5)
            self.wake.clear()
            while True:
                with self.lock:
                    if not self.queue:
                        break
                    job = self.jobs[self.queue[0]]
                try:
                    self._run(job)
                except Exception as e:   # noqa: BLE001  (a stretch that fails says why; the next one goes on)
                    job["state"], job["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
                    traceback.print_exc()
                with self.lock:
                    if self.queue and self.queue[0] == job["id"]:
                        self.queue.pop(0)

    def _run(self, job):
        o, t_start = job["options"], time.monotonic()
        job["state"] = "planning"
        items = segment_items(o)
        total = sum(x[2] for x in items)
        if total > SEGMENT_MAX:
            job["state"], job["error"], job["total"] = "failed", f"{total:,} pictures in that stretch; pre-process up to {SEGMENT_MAX:,} at a time", total
            return
        with self.lock:
            job.update(items=items, total=total, finished=[False] * len(items), state="making")

        def one(k):
            if job["stop"]:
                return k, "stopped"
            try:
                job["items"][k][3](self.cache)
                return k, None
            except Exception as e:   # noqa: BLE001  (counted and logged; the stretch goes on)
                return k, f"{type(e).__name__}: {e}"

        with calibration.looking(o["look"]), calibration.coloring(o["colors"]), \
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
                    k, err = f.result()
                    if err == "stopped":
                        continue
                    if err:
                        print(f"prebuild segment {job['id']} {items[k][0]}: {err}", flush=True)
                    with self.lock:
                        job["finished"][k] = True
                        job["done"] += items[k][2]
                        job["errors"] += bool(err)
                        job["recent"].append((time.monotonic(), job["done"]))
        # the makers start the next tiles and mosaic-movie pictures of a pass in the background (obs_mosaic
        # tiles_ahead, rolling_ahead): done once those threads for the stretch's passes are through too (up to 2 min)
        keys = {k for k in (getattr(it[3], "pass_key", None) for it in items) if k}
        until = time.monotonic() + 120
        while keys and not job["stop"] and time.monotonic() < until:
            with obs_mosaic._lock:
                busy_keys = {k for k in keys if k in obs_mosaic._ahead_running or any(r[0] == k for r in obs_mosaic._roll_ahead)}
            if not busy_keys:
                break
            job["state"] = "finishing"
            time.sleep(1)
        job["took"] = time.monotonic() - t_start
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
    (sample if args.sample else run)(args)


if __name__ == "__main__":
    main()
