#!/usr/bin/env python3
"""
Image regression benchmark: a fixed set of pictures (image_bench_items.json, about 50 stills, colour composites,
movies and mosaics from 1999 to 2017, the cases earlier changes fixed or broke and plain ones that must not change)
made by two commits through the pre-build's own makers, then compared picture by picture. The rule it serves is in
docs/image-benchmark.md: every change to how pictures are made attaches this report to its pull request.

  python web/frames/image_bench.py run --base origin/main --candidate HEAD [--target ringsFB-mosaic,...]
                                        [--notes NOTES.json] [--hosts local,mini] [--out DIR]

Nothing here makes a picture itself. Each commit gets a detached worktree of its own (never a server's or the
farm's) and a scratch cache of its own, and each item is made in a fresh process running that commit's code:
  still      frame_server.processed_webp(id, 1024, centre=prebuild.centred(id)), what a camera window shows
  composite  frame_server.color_webp(set, 1024, centre=...) for the window's filter set holding the frame
  pass       prebuild.make_pass for the frame's pass (its plan, every tile, the solve the pre-build does), then the
             pass as the window shows it: a mosaic's finished picture at 1024 and full size (obs_mosaic.mosaic_webp),
             a mosaic movie's last rolling picture, a movie's every frame (obs_mosaic.movie_webp) and, for a pass the
             page cannot even itself, its exposure-evened frames (prebuild.make_evened)
A long pass's tiles are made first by several processes at once (obs_mosaic.plan, then obs_mosaic.tile over runs of
tiles cut where a pointing starts, so no tile is registered to one another process is making), which is the same
call the pre-build makes, only spread over the cores.

A commit's results (the pictures' bytes, the makers' reports, timings) are kept under <root>/results/<commit>-<set>
(<set>: a hash of the item list and the inputs), so a base built once is never built again; only the candidate is.
The scratch cache is removed once its pictures are taken out (--keep-cache keeps it).

The report (<out>/index.html, report.md, summary.json): each item identical (same bytes) or changed; for a changed
picture the share of pixels that moved and by how much, a base | candidate | difference sheet and 1:1 crops of where
it changed most; and numbers measured the same way on both sides (clipped white, crushed black, brightness, colour,
detail energy, the lit area's centre; seam step against the picture's own texture on mosaics, seam_bench.measure).
A change the pull request does not name as its target (--target) is "unexplained" until --notes explains it.

Machines: --hosts local,mini splits the items between this Mac and the Mini (ssh), each building its share in its
own worktree and sending back only the results. The machines' inputs come from ~/.cassini-bench.json (an example:
web/frames/image_bench.example.json) or, for local, the CASSINI_* environment.

Other commands:
  build --rev REV [--items a,b]      one commit's results (cached), on this machine
  compare A B --out DIR              the report from two results folders
  items [--rev REV]                  the item list as that commit's code resolves it (passes, frames, kinds)
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import html
import io
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ITEMS = os.path.join(HERE, "image_bench_items.json")
CONFIG = os.path.expanduser(os.environ.get("CASSINI_BENCH_CONFIG", "~/.cassini-bench.json"))
INPUTS = ("CASSINI_DATA", "CASSINI_KERNELS", "CASSINI_GEOMETRY_CACHE", "CASSINI_SPICE_CACHE", "CASSINI_CISSCAL",
          "CASSINI_INDEX_CACHE")
SHARD_FROM = 40     # tiles: a pass with more is tiled by several processes first
SHARD_MIN = 12      # tiles: the least a process is given
SIZE = 1024
TOOL_VERSION = "bench-v1"   # bump when what a result holds changes (results of older versions are rebuilt)

# What counts as a picture changed, and as worse by measure (docs/image-benchmark.md). A picture whose bytes are the
# same is identical; one whose pixels differ by at most PIXEL_NOISE levels nowhere is "same" (an encoder's rounding).
PIXEL_NOISE = 2
MOVED = 8            # levels: a pixel moved by more than this counts in "moved"
GUARDS = {           # measure: (how much worse is flagged, what worse means)
    "clipped": (0.002, "share of the lit picture at white (254+) in any channel, up"),
    "crushed": (0.002, "share of the picture's covered area at black (<=1) where the base had light, up"),
    "detail": (0.15, "detail energy (mean |Laplacian| over mean brightness), up by this share: over-sharpened or over-stretched"),
    "seam": (0.10, "seam step over the picture's own texture (seam95 / flat95), up by this share"),
    "centre": (8.0, "the lit area's centre moved by more than this many pixels (of 1024)"),
    "lit": (0.02, "share of the picture with light in it, down (holes, black squares)"),
}


# ---------------------------------------------------------------- shared helpers

def load_items(path=ITEMS):
    with open(path) as fh:
        return json.load(fh)["items"]


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd or REPO, check=True, capture_output=True, text=True).stdout.strip()


def free_slots(reserve=0):
    """The cores free now: the machine's cores less the 1-minute load (rounded up), at least 2."""
    n = os.cpu_count() or 4
    return max(2, n - math.ceil(os.getloadavg()[0]) - reserve)


def machine_config(name="local"):
    """{"python", "env", "root", ...} for a machine: ~/.cassini-bench.json's entry, else (local) this Python and
    the CASSINI_* environment."""
    cfg = {}
    if os.path.exists(CONFIG):
        with open(CONFIG) as fh:
            cfg = json.load(fh).get("hosts", {}).get(name, {})
    if name == "local":
        cfg.setdefault("python", sys.executable)
        cfg.setdefault("root", os.path.expanduser("~/cassini-build/image-bench"))
        env = {k: os.environ[k] for k in INPUTS if os.environ.get(k)}
        env.update({k: os.path.expanduser(v) for k, v in cfg.get("env", {}).items()})
        cfg["env"] = env
        cfg["root"] = os.path.expanduser(cfg["root"])
        cfg["python"] = os.path.expanduser(cfg["python"])
    return cfg


def set_key(items, env):
    """The hash naming a commit's results: the item list and the inputs' sizes (a different archive or calibration
    folder makes different pictures from the same code)."""
    h = hashlib.sha256(json.dumps(items, sort_keys=True).encode())
    for k in INPUTS:
        p = env.get(k)
        h.update(f"{k}={os.path.getsize(p) if p and os.path.isfile(p) else ''}".encode())
    h.update(TOOL_VERSION.encode())
    return h.hexdigest()[:10]


def job_env(cfg, workers=2):
    env = dict(os.environ)
    env.update(cfg["env"])
    env.update({"CASSINI_KEEP_SPICE_CACHE": "1", "PYTHONUNBUFFERED": "1", "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1",
                "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
                "CASSINI_WORKERS": str(workers), "CASSINI_MOVIE_WORKERS": str(workers), "CASSINI_ROLL_WORKERS": "1"})
    return env


# ---------------------------------------------------------------- the worker: runs inside one commit's code

def _setup(code):
    """Import the commit's pipeline as prebuild.main sets it up (made in order here, the SPICE cache kept)."""
    sys.path.insert(0, code)
    import prebuild  # noqa: E402  (frame_server, obs_mosaic, the pipeline)
    om, fs = prebuild.obs_mosaic, prebuild.frame_server
    om.tiles_ahead = lambda *a, **k: None
    om.rolling_ahead = lambda *a, **k: None
    ds = fs.data_source
    ds.KEEP_SPICE_CACHE = True
    if ds.using_zip():
        ds._zip_index()
    return prebuild, om, fs


def _data(made):
    """A maker's answer as (bytes, report)."""
    if made is None:
        return None, {}
    if isinstance(made, (bytes, bytearray)):
        return bytes(made), {}
    data, rep = (made + (None,))[:2] if isinstance(made, tuple) else (made, None)
    return (bytes(data) if data else None), (rep if isinstance(rep, dict) else {})


def _pass(om, frame):
    found = om.unit_of(frame)
    if not found:
        raise LookupError(f"{frame} is in no pass")
    return found[0]


def _cuts(om, u):
    """Where a pass's tiles can be split between processes: tile indexes that start a pointing (registered to no
    earlier tile), so no process makes a tile another one is registering to."""
    n = len(u["frames"])
    if n <= SHARD_FROM or not hasattr(om, "_register_to"):
        return []
    starts = [j for j in range(1, n) if om._register_to(u, j) is None]
    cuts, last = [], 0
    for j in starts:
        if j - last >= SHARD_MIN and n - j >= SHARD_MIN:
            cuts.append(j)
            last = j
    return cuts


def work_resolve(args):
    prebuild, om, fs = _setup(args.code)
    import reel
    idx, _ = reel.load_index()
    when = dict(zip(idx["id"].tolist(), idx["seconds_1970"].astype(float).tolist()))
    out = {"versions": fs.picture_versions(), "items": {}}
    sets = None
    for it in json.load(open(args.items))["items"]:
        r = {"kind": it["kind"], "frame": it["frame"]}
        try:
            if it["frame"] not in when:
                raise LookupError("frame not in the index")
            r["time"] = datetime.datetime.utcfromtimestamp(when[it["frame"]]).strftime("%Y-%m-%dT%H:%M:%S")
            if it["kind"] == "composite":
                sets = sets or prebuild.page_sets()
                have = [list(s) for s in sets if it["frame"] in s]
                if not have:
                    raise LookupError("no filter set holds this frame")
                r["set"] = have[0]
            elif it["kind"] == "pass":
                u = _pass(om, it["frame"])
                r.update(key="_".join(map(str, u["key"])), frames=len(u["frames"]), mosaic=bool(u["mosaic"]),
                         pass_kind=u.get("kind"), cuts=_cuts(om, u))
        except Exception as e:   # noqa: BLE001  (reported, the rest go on)
            r["error"] = f"{type(e).__name__}: {e}"[:300]
        out["items"][it["name"]] = r
    json.dump(out, open(args.out, "w"), indent=1)


def work_plan(args):
    prebuild, om, fs = _setup(args.code)
    om.plan(_pass(om, args.frame), args.cache)


def work_tiles(args):
    prebuild, om, fs = _setup(args.code)
    u = _pass(om, args.frame)
    p = om.plan(u, args.cache)
    for j in range(args.start, args.stop):
        om.tile(u, j, args.cache, p["display_scale"])


def _write(folder, name, made, reports):
    data, rep = _data(made)
    if data:
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(data)
    reports[name] = rep
    return data


def work_item(args):
    """One item's pictures, as the window shows them, into args.out/<name>.webp; meta.json holds the makers'
    reports, the seconds, and for a mosaic the tiles' edges (seam_bench.edges) for the seam numbers."""
    t0 = time.time()
    prebuild, om, fs = _setup(args.code)
    it = json.loads(args.item)
    os.makedirs(args.out, exist_ok=True)
    reports, meta = {}, {"name": it["name"], "kind": it["kind"]}
    if it["kind"] == "still":
        _write(args.out, "still.webp", fs.processed_webp(it["frame"], SIZE, args.cache, centre=prebuild.centred(it["frame"])), reports)
    elif it["kind"] == "composite":
        s = it["set"]
        _write(args.out, "composite.webp", fs.color_webp(s, SIZE, args.cache, centre=prebuild.centred(s[-1])), reports)
    else:
        u = _pass(om, it["frame"])
        frames = u["frames"]
        meta.update(key="_".join(map(str, u["key"])), pass_kind=u.get("kind"), mosaic=bool(u["mosaic"]))
        last = frames[-1]
        if u["mosaic"] or u.get("kind") == "mosaic_movie":
            prebuild.make_pass(u, args.cache, (SIZE,), within=(last[3], last[3]))
            if u.get("kind") == "mosaic_movie":
                _write(args.out, "rolling.webp", om.rolling_webp(last[1], SIZE, args.cache, 1, wait=True), reports)
            else:
                _write(args.out, "mosaic.webp", om.mosaic_webp(last[1], SIZE, args.cache), reports)
                full = _write(args.out, "mosaic_full.webp",
                              om.mosaic_webp(last[1], fs.FULL, args.cache, None, fmt="webp",
                                             out=min(om.CANVAS, fs.FULL_MAX)), reports)
                if full:
                    try:   # where the tiles' edges lie on the full picture, for the seam numbers
                        import importlib.util
                        import numpy as np
                        from PIL import Image
                        spec = importlib.util.spec_from_file_location("bench_seam", os.path.join(HERE, "seam_bench.py"))
                        sb = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(sb)
                        shape = Image.open(io.BytesIO(full)).size[::-1]
                        edge = sb.edges(u, om.layout(u, len(frames) - 1, args.cache), args.cache, shape)
                        Image.fromarray((edge * 255).astype(np.uint8)).save(os.path.join(args.out, "edges.png"))
                    except Exception as e:   # noqa: BLE001  (no seam numbers for this commit's code)
                        meta["edges_error"] = f"{type(e).__name__}: {e}"[:300]
        else:
            prebuild.make_pass(u, args.cache, (SIZE,))
            for j, f in enumerate(frames):
                _write(args.out, f"frame{j:03d}.webp",
                       om.movie_webp(f[1], SIZE, args.cache, 0, True, wait=True, ahead=0, centre=True), reports)
            if hasattr(prebuild, "make_evened") and not om.page_evens(u, args.cache, True, True):
                prebuild.make_evened(u, args.cache, (SIZE,))
                for j, f in enumerate(frames):
                    _write(args.out, f"evened{j:03d}.webp",
                           om.movie_webp(f[1], SIZE, args.cache, 0, True, wait=True, ahead=0, centre=True,
                                         exposure=om.EXPOSURE_SMOOTH), reports)
    meta["reports"] = reports
    meta["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(args.out, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1, default=str)


# ---------------------------------------------------------------- building one commit

class Builder:
    """One commit's results on this machine: its worktree, the item jobs run as processes over the free cores."""

    def __init__(self, rev, cfg, names=None, slots=None, keep_cache=False, log=print):
        self.cfg, self.log, self.keep_cache = cfg, log, keep_cache
        self.root = cfg["root"]
        self.sha = git("rev-parse", rev + "^{commit}")
        self.items = load_items()
        self.key = set_key(self.items, cfg["env"])
        self.names = names
        self.slots = slots or free_slots()
        self.result = os.path.join(self.root, "results", f"{self.sha[:12]}-{self.key}")
        self.wt = os.path.join(self.root, "wt", self.sha[:12])
        self.cache = os.path.join(self.root, "cache", self.sha[:12])

    def done_items(self):
        try:
            with open(os.path.join(self.result, "build.json")) as fh:
                return set(json.load(fh).get("built", []))
        except OSError:
            return set()

    def worktree(self):
        if not os.path.exists(os.path.join(self.wt, "web", "frames", "prebuild.py")):
            os.makedirs(os.path.dirname(self.wt), exist_ok=True)
            subprocess.run(["git", "worktree", "add", "--detach", "-f", self.wt, self.sha], cwd=REPO, check=True,
                           capture_output=True)
        return self.wt

    def worker(self, *args, timeout=None):
        """Run a worker command (this file, the commit's code) in a fresh process; (rc, seconds, last lines)."""
        cmd = [self.cfg["python"], os.path.abspath(__file__), "work", *args, "--code", os.path.join(self.wt, "web", "frames"),
               "--cache", self.cache]
        t0 = time.time()
        p = subprocess.run(cmd, cwd=self.wt, env=job_env(self.cfg), capture_output=True, text=True, timeout=timeout)
        tail = (p.stdout + p.stderr).strip().splitlines()[-12:]
        return p.returncode, time.time() - t0, tail

    def build(self):
        want = [it for it in self.items if self.names is None or it["name"] in self.names]
        have = self.done_items()
        todo = [it for it in want if it["name"] not in have]
        if not todo:
            self.log(f"{self.sha[:12]}: all {len(want)} items already built ({self.result})")
            return self.result
        self.worktree()
        os.makedirs(self.result, exist_ok=True)
        os.makedirs(self.cache, exist_ok=True)
        t0 = time.time()
        res = os.path.join(self.result, "resolve.json")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"items": todo}, fh)
        rc, s, tail = self.worker("resolve", "--items", fh.name, "--out", res)
        if rc:
            raise RuntimeError(f"resolve failed on {self.sha[:12]}:\n" + "\n".join(tail))
        resolved = json.load(open(res))
        self.log(f"{self.sha[:12]}: {len(todo)} items resolved in {s:.0f} s; {self.slots} processes")
        jobs = self._jobs(todo, resolved["items"])
        failures = self._run(jobs)
        built = sorted(have | {it["name"] for it in todo if it["name"] not in failures})
        info = {"commit": self.sha, "set": self.key, "tool": TOOL_VERSION, "versions": resolved["versions"],
                "resolved": {**self._old_resolved(), **resolved["items"]}, "built": built, "failed": failures,
                "seconds": round(time.time() - t0), "slots": self.slots, "machine": os.uname().nodename,
                "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        with open(os.path.join(self.result, "build.json"), "w") as fh:
            json.dump(info, fh, indent=1)
        self.log(f"{self.sha[:12]}: built {len(todo) - len(failures)} of {len(todo)} items in {info['seconds'] / 60:.1f} min"
                 + (f"; failed: {', '.join(failures)}" if failures else ""))
        if not self.keep_cache and not failures:
            shutil.rmtree(self.cache, ignore_errors=True)
        return self.result

    def _old_resolved(self):
        try:
            with open(os.path.join(self.result, "build.json")) as fh:
                return json.load(fh).get("resolved", {})
        except OSError:
            return {}

    def _jobs(self, todo, resolved):
        """[(name, cost, deps, args)]: an item's job, after its pass's plan and tile runs when it is long."""
        jobs = []
        for it in todo:
            r = resolved.get(it["name"], {})
            if r.get("error"):
                continue
            item = {**it, **{k: r[k] for k in ("set",) if k in r}}
            if it["kind"] == "pass":
                n, cuts = r["frames"], r.get("cuts") or []
                deps = []
                if cuts:
                    plan = f"{it['name']}:plan"
                    # (first: its pass's whole chain waits on it)
                    jobs.append((plan, 100 * n, [], ["plan", "--frame", it["frame"]]))
                    edges = [0] + cuts + [n]
                    for a, b in zip(edges, edges[1:]):
                        jobs.append((f"{it['name']}:tiles{a}", 50 * n + (b - a), [plan],
                                     ["tiles", "--frame", it["frame"], "--start", str(a), "--stop", str(b)]))
                        deps.append(f"{it['name']}:tiles{a}")
                cost = (3 if cuts else 8) * n + (60 if r.get("mosaic") else 0)
            else:
                deps, cost = [], 20
            jobs.append((it["name"], cost, deps, ["item", "--item", json.dumps(item), "--out", os.path.join(self.result, it["name"])]))
        return jobs

    def _run(self, jobs):
        """Run jobs over self.slots processes, costliest ready first; {item: why} for the items that failed."""
        pending = {j[0]: j for j in jobs}
        done, failed, running = set(), {}, {}
        lock = threading.Lock()
        with concurrent.futures.ThreadPoolExecutor(self.slots) as pool:
            while pending or running:
                with lock:
                    for name in [n for n, j in pending.items() if any(d in failed for d in j[2])]:
                        failed[name] = "a step before it failed"
                        pending.pop(name)
                    ready = sorted((j for j in pending.values() if all(d in done for d in j[2])), key=lambda j: -j[1])
                    while ready and len(running) < self.slots:
                        j = ready.pop(0)
                        pending.pop(j[0])
                        running[pool.submit(self.worker, *j[3])] = j
                if not running:
                    break
                fin, _ = concurrent.futures.wait(list(running), return_when=concurrent.futures.FIRST_COMPLETED)
                for f in fin:
                    j = running.pop(f)
                    try:
                        rc, s, tail = f.result()
                    except Exception as e:   # noqa: BLE001
                        rc, s, tail = 1, 0, [repr(e)]
                    if rc:
                        failed[j[0]] = "\n".join(tail)
                        self.log(f"  FAILED {j[0]} ({s:.0f} s):\n    " + "\n    ".join(tail[-6:]))
                    else:
                        done.add(j[0])
                        self.log(f"  {j[0]} {s:.0f} s ({len(done)} done, {len(pending)} waiting, {len(running)} running)")
        return {n.split(":")[0]: w for n, w in failed.items()}


# ---------------------------------------------------------------- several machines

def remote_build(host, sha, names, log=print):
    """Build names of commit sha on host (~/.cassini-bench.json "hosts"), then copy its results here. The host runs
    this same file (copied over) against its own clone, fetched to sha."""
    cfg = machine_config(host)
    ssh, root, repo, py = cfg["ssh"], cfg["root"], cfg["repo"], cfg["python"]
    tool = f"{root}/tool"
    subprocess.run(["ssh", ssh, f"mkdir -p {shlex.quote(tool)}"], check=True)
    subprocess.run(["rsync", "-a", __file__, ITEMS, os.path.join(HERE, "seam_bench.py"), f"{ssh}:{tool}/"], check=True)
    subprocess.run(["ssh", ssh, f"git -C {shlex.quote(repo)} cat-file -e {sha}^{{commit}} 2>/dev/null || "
                                f"git -C {shlex.quote(repo)} fetch -q origin {sha}"], check=True)
    env = " ".join(f"{k}={shlex.quote(v)}" for k, v in cfg.get("env", {}).items())
    cmd = (f"cd {shlex.quote(repo)} && {env} CASSINI_BENCH_CONFIG=/nonexistent CASSINI_BENCH_REPO={shlex.quote(repo)} "
           f"{shlex.quote(py)} {tool}/image_bench.py build --rev {sha} --root {shlex.quote(root)} --items {','.join(names)} --python {shlex.quote(py)}")
    log(f"{host}: building {len(names)} items of {sha[:12]}")
    p = subprocess.run(["ssh", ssh, cmd], capture_output=True, text=True)
    for line in (p.stdout + p.stderr).strip().splitlines()[-40:]:
        log(f"  [{host}] {line}")
    if p.returncode:
        raise RuntimeError(f"{host} build failed")
    remote_result = [ln.split("RESULT ")[1] for ln in p.stdout.splitlines() if ln.startswith("RESULT ")][-1]
    return cfg, remote_result


def merge_result(into, src):
    """Copy the items of results folder src into into (both of the same commit and set) and join their build.json."""
    os.makedirs(into, exist_ok=True)
    a = json.load(open(os.path.join(into, "build.json"))) if os.path.exists(os.path.join(into, "build.json")) else None
    b = json.load(open(os.path.join(src, "build.json")))
    for name in b["built"]:
        if os.path.isdir(os.path.join(src, name)):
            shutil.rmtree(os.path.join(into, name), ignore_errors=True)
            shutil.copytree(os.path.join(src, name), os.path.join(into, name))
    if a:
        a["built"] = sorted(set(a["built"]) | set(b["built"]))
        a["resolved"].update(b["resolved"])
        a["failed"] = {**{k: v for k, v in a.get("failed", {}).items() if k not in b["built"]}, **b.get("failed", {})}
        a.setdefault("machines", [a.get("machine")]).append(b.get("machine"))
        a["seconds"] = max(a.get("seconds", 0), b.get("seconds", 0))
    with open(os.path.join(into, "build.json"), "w") as fh:
        json.dump(a or b, fh, indent=1)


def build_commit(rev, hosts, cfg, names=None, slots=None, keep_cache=False, log=print):
    """A commit's results on this machine, built here or split across hosts."""
    b = Builder(rev, cfg, names, slots, keep_cache, log)
    want = [it["name"] for it in b.items if names is None or it["name"] in names]
    left = [n for n in want if n not in b.done_items()]
    remote = [h for h in hosts if h != "local"]
    if not left or not remote:
        return b.build()
    # the remote machines take every (k+1)-th item of the list (it mixes heavy and light items), this Mac the rest
    shares = {h: left[1 + i::2 + len(remote)] for i, h in enumerate(remote)}
    mine = [n for n in left if not any(n in s for s in shares.values())]
    out = {}

    def far(h):
        try:
            cfg, path = remote_build(h, b.sha, shares[h], log)
            tmp = tempfile.mkdtemp(prefix="bench-")
            subprocess.run(["rsync", "-a", f"{cfg['ssh']}:{path}/", tmp + "/"], check=True)
            out[h] = tmp
        except Exception as e:   # noqa: BLE001  (its items are built here instead)
            log(f"{h}: {e}; building its items here")
            out[h] = None
    threads = [threading.Thread(target=far, args=(h,)) for h in remote if shares[h]]
    for t in threads:
        t.start()
    b.names = set(mine)
    b.build() if mine else None
    for t in threads:
        t.join()
    for h, tmp in out.items():
        if tmp:
            merge_result(b.result, tmp)
            shutil.rmtree(tmp, ignore_errors=True)
    missing = [n for n in want if n not in b.done_items()]
    if missing:
        b.names = set(missing)
        b.build()
    return b.result


# ---------------------------------------------------------------- measuring and comparing

def decode(path):
    import numpy as np
    from PIL import Image
    im = Image.open(path)
    return np.asarray(im.convert("RGBA"))


def measures(rgba, edges=None, base_lit=None):
    """Numbers measured the same way on any picture (RGBA uint8): lit share, clipped and crushed shares, brightness,
    colour, detail energy, the lit area's centre (px of a 1024 picture), seams (when the tiles' edges are known)."""
    import cv2
    import numpy as np
    a = rgba[..., 3] > 0
    rgb = rgba[..., :3].astype(np.float32)
    lum = rgb.mean(axis=2)
    lit = a & (lum > 8)
    n = max(int(a.sum()), 1)
    out = {"lit": round(float(lit.sum()) / n, 4)}
    out["clipped"] = round(float((rgba[..., :3].max(axis=2)[lit] >= 254).sum()) / max(int(lit.sum()), 1), 5)
    if base_lit is not None and base_lit.shape == lum.shape:
        out["crushed"] = round(float((base_lit & a & (rgba[..., :3].max(axis=2) <= 1)).sum()) / max(int(base_lit.sum()), 1), 5)
    out["mean"] = round(float(lum[a].mean()) if a.any() else 0.0, 2)
    out["p99"] = round(float(np.percentile(lum[a], 99)) if a.any() else 0.0, 1)
    out["chroma"] = round(float((rgb.max(axis=2) - rgb.min(axis=2))[lit].mean()) if lit.any() else 0.0, 2)
    lap = np.abs(cv2.Laplacian(lum, cv2.CV_32F, ksize=3))
    inner = cv2.erode(a.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    out["detail"] = round(float(lap[inner & lit].mean() / max(lum[lit].mean(), 1.0)) if (inner & lit).any() else 0.0, 4)
    if lit.any():
        ys, xs = np.nonzero(lit)
        w = lum[lit]
        k = SIZE / max(rgba.shape[:2])
        out["centre"] = [round(float((xs * w).sum() / w.sum() - rgba.shape[1] / 2) * k, 1),
                         round(float((ys * w).sum() / w.sum() - rgba.shape[0] / 2) * k, 1)]
    if edges is not None and edges.shape == lum.shape:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("bench_seam", os.path.join(HERE, "seam_bench.py"))
            sb = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sb)
            m, _ = sb.measure(rgba, edges)
            out.update({k: m[k] for k in ("seam95", "flat95")})
            if m["seam95"] is not None and m["flat95"]:
                out["seam"] = round(m["seam95"] / m["flat95"], 3)
        except Exception:   # noqa: BLE001
            pass
    return out


def worse(item_kind, base, cand):
    """{measure: why} for the guards a candidate picture trips against its base (GUARDS)."""
    out = {}
    if cand.get("clipped", 0) - base.get("clipped", 0) > GUARDS["clipped"][0]:
        out["clipped"] = f"clipped {base['clipped']:.2%} -> {cand['clipped']:.2%}"
    if cand.get("crushed", 0) > GUARDS["crushed"][0]:
        out["crushed"] = f"{cand['crushed']:.2%} of the base's light now black"
    if base.get("detail") and cand.get("detail", 0) > base["detail"] * (1 + GUARDS["detail"][0]):
        out["detail"] = f"detail {base['detail']} -> {cand['detail']} (+{cand['detail'] / base['detail'] - 1:.0%})"
    if base.get("seam") and cand.get("seam") and cand["seam"] > base["seam"] * (1 + GUARDS["seam"][0]):
        out["seam"] = f"seam/texture {base['seam']} -> {cand['seam']}"
    if base.get("centre") and cand.get("centre"):
        d = math.hypot(cand["centre"][0] - base["centre"][0], cand["centre"][1] - base["centre"][1])
        if d > GUARDS["centre"][0]:
            out["centre"] = f"lit area's centre moved {d:.0f} px"
    if base.get("lit", 0) - cand.get("lit", 0) > GUARDS["lit"][0]:
        out["lit"] = f"lit share {base['lit']:.1%} -> {cand['lit']:.1%}"
    return out


def diff(a, b):
    """How two pictures of one size differ: the largest change, the share of covered pixels moved more than MOVED
    levels, the mean change, and where it is largest (y, x)."""
    import cv2
    import numpy as np
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    cover = (a[..., 3] > 0) | (b[..., 3] > 0)
    n = max(int(cover.sum()), 1)
    blur = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 16)
    y, x = np.unravel_index(int(np.argmax(blur)), blur.shape)
    return {"max": int(d.max()), "moved": round(float((d > MOVED).sum()) / n, 5), "mean": round(float(d[cover].mean()) if cover.any() else 0.0, 3),
            "at": [int(y), int(x)]}, d


def over_black(rgba):
    import numpy as np
    al = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3].astype(np.float32) * al + 0.5).astype(np.uint8)


def sheet(a, b, d, path, title, crop_at=None):
    """base | candidate | difference (x4, hot where changed), 1024 px each at most, and a 1:1 crop row of the
    place that changed most when the pictures are bigger than that."""
    import numpy as np
    from PIL import Image, ImageDraw
    ims = [Image.fromarray(over_black(a)), Image.fromarray(over_black(b))]
    heat = np.clip(d.astype(np.float32) * 4, 0, 255).astype(np.uint8)
    hm = np.stack([heat, np.clip(heat.astype(np.int16) - 128, 0, 255).astype(np.uint8) * 2, np.zeros_like(heat)], axis=2)
    ims.append(Image.fromarray(hm))
    w = min(1024, ims[0].width)
    k = w / ims[0].width
    small = [im.resize((w, max(1, round(im.height * k))), Image.LANCZOS) if k != 1 else im for im in ims]
    rows = [small]
    if crop_at is not None and k < 1:
        y, x = crop_at
        half = 256
        y0, x0 = max(0, min(y - half, a.shape[0] - 2 * half)), max(0, min(x - half, a.shape[1] - 2 * half))
        rows.append([im.crop((x0, y0, x0 + 2 * half, y0 + 2 * half)) for im in ims])
    H = 28 + sum(r[0].height + 6 for r in rows)
    W = sum(im.width for im in rows[0]) + 12
    out = Image.new("RGB", (max(W, sum(im.width for im in rows[-1]) + 12), H), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    dr.text((6, 6), title + "    base | candidate | difference x4", fill=(230, 230, 230))
    y = 28
    for r in rows:
        x = 0
        for im in r:
            out.paste(im, (x, y))
            x += im.width + 6
        y += r[0].height + 6
    out.save(path, quality=88)


def compare(base_dir, cand_dir, out, targets=(), notes=None, log=print):
    """The report: summary.json, report.md and index.html in out, with a sheet for every changed picture."""
    import numpy as np
    from PIL import Image
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    B, C = (json.load(open(os.path.join(d, "build.json"))) for d in (base_dir, cand_dir))
    items = load_items()
    notes = notes or {}
    rows = []
    for it in items:
        name = it["name"]
        row = {"name": name, "group": it["group"], "watch": it.get("watch", ""), "frame": it["frame"],
               "time": (C["resolved"].get(name) or {}).get("time") or it.get("t"), "target": name in targets,
               "note": notes.get(name, ""), "pictures": {}}
        bd, cd = os.path.join(base_dir, name), os.path.join(cand_dir, name)
        if name not in B["built"] or name not in C["built"]:
            row["status"] = "not built"
            row["why"] = "; ".join(f"{side}: {(S.get('failed') or {}).get(name) or (S['resolved'].get(name) or {}).get('error') or 'not built'}"[:200]
                                   for side, S in (("base", B), ("candidate", C)) if name not in S["built"])
            rows.append(row)
            continue
        bm, cm = (json.load(open(os.path.join(d, "meta.json"))) for d in (bd, cd))
        row["seconds"] = [bm.get("seconds"), cm.get("seconds")]
        row["pass"] = [bm.get("key"), cm.get("key")]
        names = sorted(set(f for f in os.listdir(bd) if f.endswith(".webp")) | set(f for f in os.listdir(cd) if f.endswith(".webp")))
        changed, flagged, worst = [], {}, None
        edges = {}
        for side, d in (("base", bd), ("cand", cd)):
            if os.path.exists(os.path.join(d, "edges.png")):
                edges[side] = np.asarray(Image.open(os.path.join(d, "edges.png"))) > 0
        for f in names:
            pb, pc = os.path.join(bd, f), os.path.join(cd, f)
            pic = {}
            if not (os.path.exists(pb) and os.path.exists(pc)):
                pic["status"] = "only in base" if os.path.exists(pb) else "only in candidate"
                changed.append(f)
                row["pictures"][f] = pic
                continue
            same_bytes = open(pb, "rb").read() == open(pc, "rb").read()
            a, b = decode(pb), decode(pc)
            ma = measures(a, edges.get("base") if f == "mosaic_full.webp" else None)
            base_lit = (a[..., 3] > 0) & (a[..., :3].astype(np.float32).mean(axis=2) > 8)
            mb = measures(b, edges.get("cand") if f == "mosaic_full.webp" else None, base_lit)
            pic["base"], pic["cand"] = ma, mb
            if same_bytes:
                pic["status"] = "identical"
            elif a.shape != b.shape:
                pic["status"] = "changed"
                pic["diff"] = {"shape": [list(a.shape[:2]), list(b.shape[:2])]}
                changed.append(f)
            else:
                dd, dmap = diff(a, b)
                pic["diff"] = dd
                if dd["max"] <= PIXEL_NOISE:
                    pic["status"] = "same"
                else:
                    pic["status"] = "changed"
                    changed.append(f)
                    if worst is None or dd["moved"] > worst[0]:
                        worst = (dd["moved"], f, a, b, dmap, dd["at"])
            if pic["status"] == "changed":
                w = worse(it["kind"], ma, mb)
                if w:
                    pic["worse"] = w
                    for k, v in w.items():
                        flagged.setdefault(k, f"{f}: {v}")
            row["pictures"][f] = pic
        if worst is not None:
            sp = os.path.join("sheets", f"{name}.jpg")
            try:
                sheet(worst[2], worst[3], worst[4], os.path.join(out, sp), f"{name} {worst[1]}", worst[5])
                row["sheet"] = sp
            except Exception as e:   # noqa: BLE001
                row["sheet_error"] = repr(e)
        # a pass's pictures of different shapes (its frames re-split): a sheet of its first picture side by side
        if worst is None and changed:
            f = next((x for x in changed if x in row["pictures"] and "base" in row["pictures"][x]), None)
            if f:
                a, b = decode(os.path.join(bd, f)), decode(os.path.join(cd, f))
                h = min(a.shape[0], b.shape[0])
                sp = os.path.join("sheets", f"{name}.jpg")
                ia, ib = Image.fromarray(over_black(a)), Image.fromarray(over_black(b))
                both = Image.new("RGB", (ia.width + ib.width + 6, max(ia.height, ib.height)), (24, 24, 24))
                both.paste(ia, (0, 0))
                both.paste(ib, (ia.width + 6, 0))
                both.save(os.path.join(out, sp), quality=88)
                row["sheet"] = sp
        row["changed"] = changed
        row["of"] = len(names)
        row["worse"] = flagged
        row["status"] = "changed" if changed else "identical"
        rows.append(row)
    summary = verdict(rows)
    summary.update(base=B["commit"], candidate=C["commit"], base_versions=B["versions"], candidate_versions=C["versions"],
                   seconds={"base": B.get("seconds"), "candidate": C.get("seconds")}, tool=TOOL_VERSION,
                   at=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), targets=sorted(targets), rows=rows)
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    with open(os.path.join(out, "report.md"), "w") as fh:
        fh.write(report_md(summary))
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write(report_html(summary))
    log(f"report: {out}/index.html ({summary['verdict']})")
    return summary


def verdict(rows):
    """The automatic part of the merge rule (docs/image-benchmark.md): every item built on both; no picture outside
    the target worse by measure unless explained; every change outside the target explained. What it cannot judge
    (does the target look better, does a change look worse) is left to eyes: "needs eyes" lists those items."""
    unbuilt = [r["name"] for r in rows if r["status"] == "not built"]
    changed = [r for r in rows if r["status"] == "changed"]
    collateral = [r for r in changed if not r["target"]]
    unexplained = [r["name"] for r in collateral if not r["note"]]
    worse_out = [r["name"] for r in collateral if r["worse"] and not r["note"]]
    worse_target = [r["name"] for r in changed if r["target"] and r["worse"]]
    fails = []
    if unbuilt:
        fails.append(f"{len(unbuilt)} items not built on both commits: {', '.join(unbuilt)}")
    if worse_out:
        fails.append(f"worse by measure outside the target, unexplained: {', '.join(worse_out)}")
    if unexplained:
        fails.append(f"changed outside the target, unexplained: {', '.join(unexplained)}")
    v = "FAIL" if fails else ("NEEDS EYES" if changed else "PASS (nothing changed)")
    return {"verdict": v, "fails": fails, "identical": sum(r["status"] == "identical" for r in rows),
            "changed": [r["name"] for r in changed], "collateral": [r["name"] for r in collateral],
            "worse_target": worse_target, "unbuilt": unbuilt, "items": len(rows)}


def _fmt_measures(m):
    keys = ("lit", "clipped", "crushed", "mean", "p99", "chroma", "detail", "seam", "centre")
    return ", ".join(f"{k} {m[k]}" for k in keys if k in m)


def report_md(s):
    L = [f"# Image benchmark: {s['candidate'][:12]} against {s['base'][:12]}", "",
         f"**{s['verdict']}**. {s['items']} items: {s['identical']} identical, {len(s['changed'])} changed "
         f"({len(s['collateral'])} outside the target), {len(s['unbuilt'])} not built.", ""]
    for f in s["fails"]:
        L.append(f"- {f}")
    if s["worse_target"]:
        L.append(f"- target items with a measure worse (look at them): {', '.join(s['worse_target'])}")
    L += ["", f"Built in {(s['seconds']['base'] or 0) / 60:.0f} min (base) and {(s['seconds']['candidate'] or 0) / 60:.0f} min "
               f"(candidate). Targets: {', '.join(s['targets']) or 'none named'}.", "",
          "| item | group | status | pictures changed | moved (worst) | worse by measure | note |", "|---|---|---|---|---|---|---|"]
    for r in s["rows"]:
        moved = max((p.get("diff", {}).get("moved", 0) for p in r["pictures"].values() if isinstance(p.get("diff", {}).get("moved"), float)), default=0)
        tag = "target" if r["target"] else r["group"]
        st = r["status"] if r["status"] != "not built" else f"not built ({r.get('why', '')[:80]})"
        L.append(f"| {r['name']} | {tag} | {st} | {len(r.get('changed', []))}/{r.get('of', 0)} | "
                 f"{moved:.2%} | {'; '.join(r.get('worse', {}).values()) or ''} | {r['note']} |")
    L += ["", "Sheets: `sheets/<item>.jpg` (base | candidate | difference x4, with 1:1 crops of the place that changed most).", ""]
    return "\n".join(L)


def report_html(s):
    e = html.escape
    rows = []
    for r in s["rows"]:
        cls = {"identical": "same", "changed": "chg", "not built": "bad"}[r["status"]]
        if r["status"] == "changed" and r.get("worse"):
            cls = "bad"
        pics = []
        for f, p in r["pictures"].items():
            if p.get("status") in ("changed",) or (p.get("status") and p["status"].startswith("only")):
                d = p.get("diff", {})
                pics.append(f"<div class=p><b>{e(f)}</b> {e(p['status'])} " +
                            (f"max {d.get('max')} moved {d.get('moved', 0):.2%} mean {d.get('mean')}" if 'max' in d else e(json.dumps(d))) +
                            (f"<br>base: {e(_fmt_measures(p['base']))}<br>cand: {e(_fmt_measures(p['cand']))}" if 'base' in p else "") +
                            ("".join(f"<br><span class=w>worse: {e(v)}</span>" for v in p.get('worse', {}).values())) + "</div>")
        link = f"http://192.168.68.52:8765/?t={e(r['time'] or '')}&view=saturn&play=0" if r.get("time") else ""
        rows.append(f"<tr class={cls}><td><b>{e(r['name'])}</b><br><small>{e(r['frame'])} {e(r['time'] or '')}"
                    f"{' <a href=' + link + '>open</a>' if link else ''}</small></td>"
                    f"<td>{'target' if r['target'] else e(r['group'])}</td><td>{e(r['status'])}"
                    f"{'<br>' + str(len(r.get('changed', []))) + '/' + str(r.get('of', 0)) if r['status'] == 'changed' else ''}"
                    f"{'<br><small>' + e(r.get('why', '')) + '</small>' if r.get('why') else ''}</td>"
                    f"<td><small>{e(r['watch'])}</small>{''.join(pics)}{'<p class=n>note: ' + e(r['note']) + '</p>' if r['note'] else ''}</td>"
                    f"<td>{'<a href=' + e(r['sheet']) + '><img src=' + e(r['sheet']) + '></a>' if r.get('sheet') else ''}</td></tr>")
    fails = "".join(f"<li>{e(f)}</li>" for f in s["fails"])
    return f"""<!doctype html><meta charset=utf-8><title>Image benchmark</title>
<style>body{{font:14px system-ui;background:#111;color:#ddd;margin:16px}}table{{border-collapse:collapse;width:100%}}
td{{border-top:1px solid #333;padding:6px;vertical-align:top}}img{{max-width:640px;width:100%}}tr.same td:first-child{{border-left:4px solid #2a6}}
tr.chg td:first-child{{border-left:4px solid #db3}}tr.bad td:first-child{{border-left:4px solid #e44}}.w{{color:#f77}}.p{{margin-top:4px;font-size:12px}}
.n{{color:#9cf}}a{{color:#8bf}}</style>
<h1>Image benchmark: {e(s['candidate'][:12])} against {e(s['base'][:12])}</h1>
<p><b>{e(s['verdict'])}</b>. {s['items']} items: {s['identical']} identical, {len(s['changed'])} changed ({len(s['collateral'])} outside the
target), {len(s['unbuilt'])} not built. Targets: {e(', '.join(s['targets']) or 'none named')}.</p><ul>{fails}</ul>
<table>{''.join(rows)}</table>"""


# ---------------------------------------------------------------- command line

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("work", help=argparse.SUPPRESS)
    w.add_argument("what", choices=("resolve", "plan", "tiles", "item"))
    for k in ("--code", "--cache", "--items", "--out", "--frame", "--item"):
        w.add_argument(k)
    w.add_argument("--start", type=int)
    w.add_argument("--stop", type=int)
    for name in ("build", "run"):
        p = sub.add_parser(name)
        p.add_argument("--slots", type=int, help="processes at once (default: the free cores)")
        p.add_argument("--keep-cache", action="store_true")
        p.add_argument("--items", help="only these items (comma separated)")
        p.add_argument("--root", help="where worktrees, scratch caches and results go (default ~/cassini-build/image-bench)")
        p.add_argument("--python", help="the Python with the pipeline's packages (default: this one)")
        p.add_argument("--hosts", default="local", help="local,mini: split the items between this Mac and the Mini")
        if name == "build":
            p.add_argument("--rev", required=True)
        else:
            p.add_argument("--base", default="origin/main")
            p.add_argument("--candidate", default="HEAD")
            p.add_argument("--target", default="", help="the items this change means to change (comma separated)")
            p.add_argument("--notes", help="JSON {item: why it changed} for changes outside the target")
            p.add_argument("--out", help="the report's folder (default <root>/reports/<base>-<candidate>)")
    c = sub.add_parser("compare")
    c.add_argument("base")
    c.add_argument("candidate")
    c.add_argument("--out", required=True)
    c.add_argument("--target", default="")
    c.add_argument("--notes")
    i = sub.add_parser("items")
    i.add_argument("--rev", default="HEAD")
    args = ap.parse_args()

    if args.cmd == "work":
        {"resolve": work_resolve, "plan": work_plan, "tiles": work_tiles, "item": work_item}[args.what](args)
        return
    if os.environ.get("CASSINI_BENCH_REPO"):
        global REPO
        REPO = os.environ["CASSINI_BENCH_REPO"]
    if args.cmd == "compare":
        notes = json.load(open(args.notes)) if args.notes else {}
        s = compare(args.base, args.candidate, args.out, set(filter(None, args.target.split(","))), notes)
        sys.exit(1 if s["verdict"] == "FAIL" else 0)
    if args.cmd == "items":
        b = Builder(args.rev, machine_config("local"))
        b.worktree()
        out = os.path.join(b.root, f"items-{b.sha[:12]}.json")
        rc, s, tail = b.worker("resolve", "--items", ITEMS, "--out", out)
        print(open(out).read() if not rc else "\n".join(tail))
        return
    cfg = machine_config("local")
    if args.root:
        cfg["root"] = os.path.expanduser(args.root)
    if args.python:
        cfg["python"] = args.python
    names = set(args.items.split(",")) if args.items else None
    hosts = args.hosts.split(",")
    log = lambda m: print(f"{datetime.datetime.now():%H:%M:%S} {m}", flush=True)   # noqa: E731
    if args.cmd == "build":
        b = Builder(args.rev, cfg, names, args.slots, args.keep_cache, log)
        if hosts == ["local"]:
            path = b.build()
        else:
            path = build_commit(args.rev, hosts, cfg, names, args.slots, args.keep_cache, log)
        print(f"RESULT {path}", flush=True)
        return
    t0 = time.time()
    base = build_commit(args.base, hosts, cfg, names, args.slots, args.keep_cache, log)
    cand = build_commit(args.candidate, hosts, cfg, names, args.slots, args.keep_cache, log)
    out = args.out or os.path.join(cfg["root"], "reports", f"{os.path.basename(base)[:12]}-{os.path.basename(cand)[:12]}")
    notes = json.load(open(args.notes)) if args.notes else {}
    s = compare(base, cand, out, set(filter(None, args.target.split(","))), notes, log)
    log(f"done in {(time.time() - t0) / 60:.1f} min: {s['verdict']}")
    sys.exit(1 if s["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
