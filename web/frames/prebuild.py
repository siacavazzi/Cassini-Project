#!/usr/bin/env python3
"""
Pre-builds the frame server's picture cache ahead of any request, so serving the mission costs disk and bandwidth
instead of CPU. Every picture is made by the frame server's own makers (frame_server.webp, color_webp,
processed_webp; obs_mosaic.plan, tile, _mosaic_at) into the same cache folders and names a request would use, so
the server (or a static copy of the cache) finds it there. Nothing here processes a picture itself.

Phases (each its own run; a run picks up where the last one stopped, since a made file is never made again):
  frames      /frames/<ID>.webp at 512 and 1024 px, every frame of the mission. No version: safe to build any time
  composites  /frames/color.webp?ids=R,G,B for every filter set the page makes (its findSets rule), at 1024 (which
              also writes full) and 512, in the default look (balanced, natural colors)
  mosaics     every mosaic pass's plan and tiles (obs_mosaic), then its mosaic so far at each of its frames, 1024
              and 512
  processed   /frames/processed/<ID>.webp at 1024 for movie mode, every frame not in a filter set

Made to share the Mac Mini with the live and preview servers: run it under `nice -n 19 taskpolicy -b` (low CPU and
disk priority), one process with a few threads. It waits while the 1-minute load is over --max-load, while the
live server's /health answers slower than a second, or while the pause file exists (touch it to hold the job,
remove it to go on). status.json (and a page reading it, index.html) in --status says how far it is.

  CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
    nice -n 19 taskpolicy -b python web/frames/prebuild.py frames --cache /Volumes/LaCie/cassini-cache \\
    --status web/cassini-os/prebuild
  ... prebuild.py composites --sample 200      times 200 spread-out items into a scratch cache and prints the
                                                seconds and bytes per item (and the totals they mean)
"""
import argparse
import collections
import concurrent.futures
import contextvars
import functools
import json
import os
import random
import shutil
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

PHASES = ("frames", "composites", "mosaics", "processed")
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
    """Every pass obs_mosaic calls a mosaic, in time order."""
    idx, _ = reel.load_index()
    seen, out = set(), []
    for r in idx[["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"]].itertuples(index=False):
        key = (r.TARGET_NAME, r.OBSERVATION_ID, "N" if r.INSTRUMENT_ID == "ISSNA" else "W")
        if key in seen or not isinstance(key[1], str):
            continue
        seen.add(key)
        out += [u for u in obs_mosaic.units(*key) if u["mosaic"]]
    return out


def items(phase):
    """(name, work) of every item of the phase, in time order; work() makes it (a made file is found, not made)."""
    if phase == "frames":
        return [(i, lambda c, i=i: [frame_server.webp(i, s, c) for s in (1024, 512)]) for i in frame_ids()]
    if phase == "composites":
        # 1024 first: it also writes full, and keeps the composite in memory for the 512 one
        return [("_".join(s), lambda c, s=s: [frame_server.color_webp(s, z, c) for z in (1024, 512)]) for s in page_sets()]
    if phase == "processed":
        in_sets = {i for s in page_sets() for i in s}
        return [(i, lambda c, i=i: frame_server.processed_webp(i, 1024, c)) for i in frame_ids() if i not in in_sets]
    if phase == "mosaics":
        return [("_".join(map(str, u["key"])), lambda c, u=u: make_pass(u, c)) for u in mosaic_passes()]
    raise ValueError(phase)


def make_pass(u, cache):
    """The pass's plan, every tile, then its mosaic so far at every frame at 1024 and 512: what mosaic_webp makes as
    a window plays through it."""
    p = obs_mosaic.plan(u, cache)
    for j in range(len(u["frames"])):
        obs_mosaic.tile(u, j, cache, p["display_scale"])
    for j in range(len(u["frames"])):
        for size in (1024, 512):
            obs_mosaic._mosaic_at(u, j, size, cache)
    return len(u["frames"])


# ---------- sharing the Mini ----------

def busy(args):
    """Why the job should wait now, or None."""
    if args.pause and os.path.exists(os.path.expanduser(args.pause)):
        return "paused (pause file)"
    load = os.getloadavg()[0]
    if load > args.max_load:
        return f"load {load:.1f} > {args.max_load}"
    if args.live:
        t0 = time.monotonic()
        try:
            urllib.request.urlopen(args.live.rstrip("/") + "/health", timeout=5).read()
        except Exception:
            return None   # the live server down is no reason to wait
        if time.monotonic() - t0 > 1:
            return "live server slow"
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
    ap.add_argument("--pause", default="~/prebuild.pause", help="while this file exists the job waits")
    args = ap.parse_args()
    if args.phase == "count":
        sets, passes = page_sets(), mosaic_passes()
        print(json.dumps({"frames": len(frame_ids()), "sets": len(sets), "set_frames": sum(map(len, sets)),
                          "mosaic_passes": len(passes), "mosaic_frames": sum(len(u["frames"]) for u in passes)}))
        return
    data_source = frame_server.data_source
    data_source.KEEP_SPICE_CACHE = True
    data_source._zip_index() if data_source.using_zip() else None
    (sample if args.sample else run)(args)


if __name__ == "__main__":
    main()
