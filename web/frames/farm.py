#!/usr/bin/env python3
"""
Build farm: one picture-cache build split across several machines (the Mac Mini and a laptop), each running
prebuild.py on its own slices of the mission, then checked and merged into one cache. Nothing here makes a picture:
every unit of work is a `prebuild.py <phase> --years ...` (or --from/--until) run, exactly as a single-machine build
would run it, so the bytes are the pipeline's own. The runbook is docs/cache-build-runbook.md.

The farm is a folder ("shared") on the hub, the machine that holds the data drive (the Mini and its T7):

  <shared>/farm.json        the machines and the build's settings (an example: web/frames/farm.example.json)
  <shared>/plan.json        the units, heaviest first, and the commit the build runs on (farm.py plan)
  <shared>/claims/<unit>/   a unit taken by a machine (mkdir is the lock); owner.json says which
  <shared>/done/<unit>.json a unit finished: each phase's exit code and seconds
  <shared>/logs/<machine>/  phases.log ("<unit> <phase> start/done ... exit rc", as the r48 rebuild wrote) and
                            one prebuild log per phase and unit
  <shared>/stop-<machine>   touch it: that machine finishes its current unit and stops

Each unit is registered with the Mini's job list (farm.json "job"; ~/agents/bin/job, shown on the dashboard's
Active jobs panel) as farm-<machine>-<unit>: started when claimed, updated per phase, done or failed at the end.
A helper machine registers its units on the hub over SSH.

A machine other than the hub reaches the shared folder over SSH (machine "shared": "ssh://lazarus@mini/<path>"), so
no SMB mount or saved password is needed. It builds into its own cache on its own disk and ships each finished unit
back to the hub (rsync over SSH), into a folder beside the hub's cache (build-cache-incoming-<machine>), optionally freeing its disk as it goes.

Who takes what: units are taken from one ordered list, so the build balances itself whatever each machine's real
speed turns out to be. A machine with "end": "heavy" takes the heaviest unit left, one with "end": "light" the
lightest; the two meet in the middle, so the slow machine never starts a big year last. A unit can be pinned to a
machine ("only"): the whole-mission frames phase, which mostly reads the archive, goes to the hub.

  farm.py plan    --shared S                        units from Image_index.csv, written to plan.json
  farm.py run     --shared S --machine mbp          take units and build them until none is left
  farm.py status  --shared S                        who has what, how long each took, what is left
  farm.py verify  --cache C [--units ...]           every phase recorded with no errors, under this code's versions
  farm.py compare A B [--sample N]                  the bytes of files both caches hold (two machines, same slice)
  farm.py merge   --into C SRC ...                  move or copy files C lacks, join slices.json
  farm.py doctor  --shared S --machine mbp          inputs present, free space, commit and Python packages match
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import slices  # noqa: E402  (stdlib only; prebuild/frame_server are imported only where versions are needed)

REQUIRED_INPUTS = ("CASSINI_DATA", "CASSINI_KERNELS", "CASSINI_GEOMETRY_CACHE", "CASSINI_SPICE_CACHE", "CASSINI_CISSCAL")
KERNEL_PROBE_MIN = 20   # mission kernels a year's meta-kernel loads (2017: 109); without the kernels zip only the 3 USGS extras load


def fingerprint(env):
    """Sizes of the build's inputs as this machine sees them: the zips' bytes, the calibration folder's files and bytes."""
    out = {}
    for k in ("CASSINI_DATA", "CASSINI_KERNELS"):
        p = env.get(k)
        out[k] = os.path.getsize(p) if p and os.path.isfile(p) else None
    root = env.get("CASSINI_CISSCAL")
    if root and os.path.isdir(root):
        n = b = 0
        for d, _, fs in os.walk(root):
            for f in fs:
                n += 1
                b += os.path.getsize(os.path.join(d, f))
        out["CASSINI_CISSCAL"] = [n, b]
    else:
        out["CASSINI_CISSCAL"] = None
    return out


def preflight_problems(env, want, kernels_loaded=None):
    """Why this machine must not build: an input missing, an input that differs from the hub's (plan.json "inputs"),
    or a year whose meta-kernel loads too few kernels (kernels_loaded: {year: count})."""
    problems = [f"{k} missing ({env.get(k) or 'not set'})" for k in REQUIRED_INPUTS if not (env.get(k) and os.path.exists(env[k]))]
    have = fingerprint(env)
    for k, v in (want or {}).items():
        if v is not None and have.get(k) != v:
            problems.append(f"{k} differs from the hub's: {have.get(k)} here, {v} there")
    for year, n in sorted((kernels_loaded or {}).items()):
        if n < KERNEL_PROBE_MIN:
            problems.append(f"only {n} SPICE kernels load for {year} (the hub loads ~100): the kernels are not usable here")
    return problems


def kernel_probe(python, env, years):
    """{year: kernels loaded} by the pipeline's own loader (bootleg_autonav.load_kernels) in a fresh process."""
    out = {}
    for y in years:
        code = ("import sys; sys.path.insert(0, '.'); import bootleg_autonav as b, spiceypy as sp, io, contextlib\n"
                f"with contextlib.redirect_stdout(io.StringIO()): b.load_kernels({y}, {y})\n"
                "print(sp.ktotal('ALL'))")
        got = subprocess.run([python, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
        try:
            out[y] = int(got.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            out[y] = 0
    return out


def plan_years(plan):
    ys = set()
    for u in plan["units"]:
        for a, b in unit_spans(u):
            if a:
                ys.add(int(a[:4]))
            if b:
                ys.add(int(b[:4]) - (1 if b[5:10] == "01-01" else 0))
    return sorted(ys) or [2004]


PHASES = ["composites", "processed", "mosaics", "movies", "strips", "chains"]   # per unit, in this order (r48's)
SKIP_SHIP = ("slices.json", "status.json", "shard-status", "farm-ship")          # never shipped or merged as files
SPLIT_SHARE = 0.06      # a year heavier than this share of the mission is built as two halves (Jan-Jun, Jul-Dec)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- the shared folder: a local path on the hub, ssh://user@host/path elsewhere ----------

class Shared:
    def __init__(self, where):
        self.ssh = None
        if where.startswith("ssh://"):
            host, _, path = where[len("ssh://"):].partition("/")
            self.ssh, self.root = host, "/" + path
        else:
            self.root = os.path.abspath(os.path.expanduser(where))

    def _remote(self, cmd, data=None):
        got = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", self.ssh, cmd],
                             input=data, capture_output=True, timeout=120)
        return got.returncode, got.stdout

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def read(self, *parts):
        """A file's text, or None if there is none."""
        if self.ssh:
            rc, out = self._remote(f"cat {shlex.quote(self.path(*parts))} 2>/dev/null")
            return out.decode() if rc == 0 else None
        try:
            with open(self.path(*parts)) as fh:
                return fh.read()
        except OSError:
            return None

    def write(self, text, *parts):
        """Written whole (a .part moved over it), so a reader never sees half of one."""
        p = self.path(*parts)
        if self.ssh:
            q = shlex.quote(p)
            rc, _ = self._remote(f"mkdir -p {shlex.quote(os.path.dirname(p))} && cat > {q}.part && mv {q}.part {q}",
                                 text.encode())
            if rc:
                raise OSError(f"could not write {p} on {self.ssh}")
            return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".part", "w") as fh:
            fh.write(text)
        os.replace(p + ".part", p)

    def append(self, text, *parts):
        p = self.path(*parts)
        if self.ssh:
            self._remote(f"mkdir -p {shlex.quote(os.path.dirname(p))} && cat >> {shlex.quote(p)}", text.encode())
            return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as fh:
            fh.write(text)

    def claim(self, unit):
        """True if this call took the unit (mkdir is atomic on the hub's disk, locally or over SSH)."""
        p = self.path("claims", unit)
        if self.ssh:
            rc, _ = self._remote(f"mkdir -p {shlex.quote(self.path('claims'))} && mkdir {shlex.quote(p)}")
            return rc == 0
        os.makedirs(self.path("claims"), exist_ok=True)
        try:
            os.mkdir(p)
            return True
        except FileExistsError:
            return False

    def listing(self, *parts):
        if self.ssh:
            rc, out = self._remote(f"ls -1 {shlex.quote(self.path(*parts))} 2>/dev/null")
            return out.decode().split() if rc == 0 else []
        try:
            return sorted(os.listdir(self.path(*parts)))
        except OSError:
            return []

    def exists(self, *parts):
        if self.ssh:
            return self._remote(f"test -e {shlex.quote(self.path(*parts))}")[0] == 0
        return os.path.exists(self.path(*parts))


def load_json(shared, name):
    text = shared.read(name)
    if text is None:
        raise SystemExit(f"{shared.path(name)} is missing")
    return json.loads(text)


# ---------- the plan: units of work, heaviest first ----------

def pictures_by_month(index=os.path.join(REPO, "Image_index.csv")):
    """{(year, month): pictures} from the catalogue's seconds_1970 (the time prebuild's --years cuts on)."""
    out = {}
    with open(index, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                t = datetime.datetime.fromtimestamp(float(row["seconds_1970"]), datetime.timezone.utc)
            except (KeyError, ValueError):
                continue
            out[(t.year, t.month)] = out.get((t.year, t.month), 0) + 1
    return out


def make_units(months, year_cost=None, split_share=SPLIT_SHARE):
    """A unit per year (a heavy year as two halves), weighted by pictures times the year's cost factor (seconds per
    picture measured on an earlier build, relative; 1 where not given). Heaviest first."""
    year_cost = {int(k): float(v) for k, v in (year_cost or {}).items()}
    years = {}
    for (y, m), n in months.items():
        years.setdefault(y, [0, 0])[m > 6] += n
    total = sum(year_cost.get(y, 1.0) * (a + b) for y, (a, b) in years.items())
    units = []
    for y, (a, b) in sorted(years.items()):
        c = year_cost.get(y, 1.0)
        if c * (a + b) > split_share * total and a and b:
            units.append({"unit": f"{y}a", "from": f"{y}-01-01", "until": f"{y}-07-01", "pictures": a, "weight": c * a})
            units.append({"unit": f"{y}b", "from": f"{y}-07-01", "until": f"{y + 1}-01-01", "pictures": b, "weight": c * b})
        else:
            units.append({"unit": str(y), "years": str(y), "pictures": a + b, "weight": c * (a + b)})
    units.sort(key=lambda u: (-u["weight"], u["unit"]))
    return units


def git(*args, cwd=REPO):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def packages_hash(python):
    """sha1 of `pip freeze`: two machines building one cache must run the same packages."""
    try:
        out = subprocess.run([python, "-m", "pip", "freeze", "--all"], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = sorted(l for l in out.splitlines() if l and not l.startswith(("-e ", "pip==", "setuptools==", "wheel==")))
    return hashlib.sha1("\n".join(lines).encode()).hexdigest()[:12]


def cmd_plan(args):
    shared = Shared(args.shared)
    farm = load_json(shared, "farm.json")
    units = make_units(pictures_by_month(args.index), farm.get("year_cost"), farm.get("split_share", SPLIT_SHARE))
    for pin in farm.get("whole_mission", []):          # e.g. {"phase": "frames", "only": "mini"}
        units.insert(0, {"unit": f"all-{pin['phase']}", "phases": [pin["phase"]], "only": pin["only"],
                         "pictures": sum(u["pictures"] for u in units), "weight": 0, "hours": pin.get("hours", 1.0)})
    hub = next((dict(m.get("env", {})) for m in farm["machines"].values() if not m.get("ship_to")), {})
    hub = {k: os.path.expanduser(str(v)) for k, v in hub.items()}
    plan = {"made": now(), "inputs": fingerprint(hub) if hub else {}, "commit": git("rev-parse", "HEAD"), "packages": packages_hash(os.path.expanduser(farm.get("python", sys.executable))),
            "phases": farm.get("phases", PHASES), "units": units}
    if args.dry_run:
        print(json.dumps(plan, indent=1))
    else:
        shared.write(json.dumps(plan, indent=1), "plan.json")
    est = estimate(plan, farm)
    print(f"{len(units)} units, {sum(u['pictures'] for u in units if 'phases' not in u):,} pictures, commit "
          f"{plan['commit'][:8]}; heaviest: " + ", ".join(u["unit"] for u in units[:5]))
    for name, h in est["machines"].items():
        print(f"  {name}: {est['share'][name]:.0%} of the work, ~{h:.1f} h")
    print(f"  whole build: ~{est['hours']:.1f} h (from farm.json's s_per_picture and speeds; refine after the samples)")


def estimate(plan, farm):
    """Hours each machine works if they take units as `run` does, from farm.json's s_per_picture (the hub's wall
    seconds per picture, all phases) and each machine's speed relative to the hub."""
    sp = float(farm.get("s_per_picture", 0.8))
    ms = farm["machines"]
    free = {n: 0.0 for n in ms}
    share = {n: 0.0 for n in ms}
    left = [u for u in plan["units"]]
    pinned = [u for u in left if u.get("only")]
    for u in pinned:
        free[u["only"]] += u.get("hours", 1.0)
        left.remove(u)
    left.sort(key=lambda u: -u["weight"])
    while left:
        n = min(free, key=lambda k: free[k])
        u = left.pop(-1 if ms[n].get("end") == "light" else 0)
        free[n] += u["weight"] * sp / 3600 / float(ms[n].get("speed", 1))
        share[n] += u["weight"]
    total = sum(share.values()) or 1
    return {"machines": free, "share": {n: s / total for n, s in share.items()}, "hours": max(free.values())}


# ---------- the Mini dashboard's job list (~/agents/bin/job; minidash :8787 "Active jobs") ----------

def job(shared, farm, *args):
    """Registers a unit with the hub's job helper (farm.json "job": {"cmd", "thread"}), on the hub itself or over
    SSH from a helper machine, so every slice shows on the Mini's dashboard. Best effort: never stops the build."""
    cfg = farm.get("job")
    if not cfg:
        return
    cmd = [cfg.get("cmd", "~/agents/bin/job"), *map(str, args)]
    try:
        if shared.ssh:
            subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", shared.ssh,
                            " ".join(shlex.quote(c) if i else c for i, c in enumerate(cmd))],
                           capture_output=True, timeout=60)
        else:
            subprocess.run([os.path.expanduser(cmd[0]), *cmd[1:]], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def unit_eta(farm, machine, unit):
    """Local "YYYY-MM-DD HH:MM" this unit should end by, from farm.json's s_per_picture and the machine's speed."""
    hours = unit.get("hours") or unit.get("weight", 0) * float(farm.get("s_per_picture", 0.8)) / 3600 / \
        float(machine.get("speed", 1))
    return (datetime.datetime.now() + datetime.timedelta(hours=max(hours, 0.25))).strftime("%Y-%m-%d %H:%M")


# ---------- run: take units and build them ----------

def prebuild_cmd(machine, unit, phase, python):
    cmd = [python, "-u", os.path.join(HERE, "prebuild.py"), phase, "--cache", machine["cache"],
           "--status", machine.get("status", os.path.join(machine["cache"], "..", "status-" + machine["name"])),
           "--disk", "", "--live", machine.get("live", ""), "--max-load", str(machine.get("max_load", 60)),
           "--min-free", str(machine.get("min_free", 50)), "--pause", machine.get("pause", "~/prebuild.pause")]
    procs = int(machine.get("procs", 0))
    if procs > 1:
        cmd += ["--procs", str(procs), "--balanced"]
    if machine.get("watched_first", True) and phase != "frames":
        cmd += ["--watched-first"]
    if unit.get("years"):
        cmd += ["--years", unit["years"]]
    elif unit.get("from"):
        cmd += ["--from", unit["from"], "--until", unit["until"]]
    return cmd


def candidates(plan, me, machine):
    """The units this machine may take, in the order it takes them: those pinned to it, then the heaviest first (or
    the lightest first, for "end": "light")."""
    pinned = [u for u in plan["units"] if u.get("only") == me]
    rest = [u for u in plan["units"] if not u.get("only")]
    return pinned + (rest[::-1] if machine.get("end") == "light" else rest)


def next_unit(shared, plan, me, machine, busy=()):
    """The unit this machine should build next: its own unfinished claim first (a restart), else the heaviest (or,
    for "end": "light", the lightest) unit nobody has taken that it may take. busy: units this run is building now
    (another slot's), never handed out twice."""
    done = {n[:-5] for n in shared.listing("done") if n.endswith(".json")}
    claimed = set(shared.listing("claims"))
    for u in plan["units"]:
        if u["unit"] in claimed and u["unit"] not in done and u["unit"] not in busy:
            owner = json.loads(shared.read("claims", u["unit"], "owner.json") or "{}")
            if owner.get("machine") == me:
                return u
    for u in candidates(plan, me, machine):
        if u["unit"] in claimed or u["unit"] in done:
            continue
        if shared.claim(u["unit"]):
            shared.write(json.dumps({"machine": me, "host": socket.gethostname(), "at": now()}), "claims", u["unit"], "owner.json")
            return u
        claimed.add(u["unit"])
    return None


def check_code(plan, machine, python):
    """Refuses to build on another commit or other packages than the plan's: two machines' bytes must match."""
    head = git("rev-parse", "HEAD")
    if plan.get("commit") and head != plan["commit"]:
        raise SystemExit(f"this checkout is at {head[:8]}, the plan's commit is {plan['commit'][:8]}")
    if [l for l in git("status", "--porcelain", "--untracked-files=no").splitlines() if not l.endswith(".DS_Store")]:
        raise SystemExit("this checkout has local changes: the build must run on the plan's commit as it is")
    got = packages_hash(python)
    if plan.get("packages") and got != plan["packages"]:
        raise SystemExit(f"Python packages differ from the plan's ({got} vs {plan['packages']}): "
                         f"pip install -r the hub's freeze (doctor shows it)")


class Shipper:
    """Copies finished units' files from this machine's cache to the hub (rsync over SSH), in the background while
    the next unit builds. With "free": true, the files of units already copied are then deleted here, at the next
    unit boundary (nothing is building then), so the disk only ever holds about two units."""

    def __init__(self, machine, logfile):
        self.m, self.log = machine, logfile
        self.thread, self.manifests = None, []

    def _dest(self):
        """Makes the hub's folder for this machine's files (rsync won't make a missing parent), once."""
        dest = self.m["ship_to"].rstrip("/")
        if not getattr(self, "_made", False):
            host, sep, path = dest.partition(":")
            if sep and "/" not in host:
                subprocess.call(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {shlex.quote(path)}"])
            else:
                os.makedirs(dest, exist_ok=True)
            self._made = True
        return dest + "/"

    def _rsync(self, extra, files_from=None):
        src = self.m["cache"].rstrip("/") + "/"
        cmd = [self.m.get("rsync", "rsync"), "-a", "--partial", "-e", "ssh -o BatchMode=yes"] + extra
        if files_from:
            cmd += ["--files-from", files_from]
        else:
            cmd += [f"--exclude={x}" for x in SKIP_SHIP] + ["--exclude=*.part*", "--exclude=*.tmp"]
        cmd += [src, self._dest()]
        with open(self.log, "a") as fh:
            fh.write(f"{now()} {' '.join(map(shlex.quote, cmd))}\n")
            fh.flush()
            return subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)

    def _manifest(self):
        """The files in the cache now (finished units only: called between units), as a --files-from list."""
        root = self.m["cache"]
        path = os.path.join(root, "..", f"farm-ship-{self.m['name']}-{len(self.manifests)}.txt")
        n = 0
        with open(path, "w") as fh:
            for d, dirs, fs in os.walk(root):
                dirs[:] = [x for x in dirs if x not in SKIP_SHIP]
                for f in fs:
                    if f in SKIP_SHIP or ".part" in f or f.endswith(".tmp"):
                        continue
                    fh.write(os.path.relpath(os.path.join(d, f), root) + "\n")
                    n += 1
        return path, n

    def free(self):
        """Deletes here the files of units already copied, once a dry run (rsync -n) says the hub holds every one of
        them as it is here. Done in Python, not with --remove-source-files, which macOS's openrsync gets wrong."""
        for path in list(self.manifests):
            root = self.m["cache"]
            with open(path) as fh:
                rels = [r for r in fh.read().splitlines() if os.path.exists(os.path.join(root, r))]
            with open(path, "w") as fh:
                fh.write("".join(r + "\n" for r in rels))
            cmd = [self.m.get("rsync", "rsync"), "-ani", "-e", "ssh -o BatchMode=yes", "--files-from", path,
                   root.rstrip("/") + "/", self._dest()]
            got = subprocess.run(cmd, capture_output=True, text=True)
            pending = [l for l in got.stdout.splitlines() if l[:2] in (">f", "<f")]
            if got.returncode or pending:
                with open(self.log, "a") as fh:
                    fh.write(f"{now()} not freeing {path}: rc {got.returncode}, {len(pending)} file(s) not on the hub yet\n")
                continue
            for r in rels:
                os.remove(os.path.join(root, r))
            os.replace(path, path + ".freed")
            self.manifests.remove(path)

    def boundary(self, final=False):
        """Between units (nothing building): wait for the last copy, free what it copied, send slices.json, then
        copy what the unit just made, in the background (or now, after the last unit)."""
        if not self.m.get("ship_to"):
            return
        if self.thread:
            self.thread.join()
            self.thread = None
        if self.m.get("free"):
            self.free()
        sj = os.path.join(self.m["cache"], "slices.json")
        if os.path.exists(sj):
            subprocess.call([self.m.get("rsync", "rsync"), "-a", "-e", "ssh -o BatchMode=yes", sj,
                             self._dest() + "slices.json"])
        if self.m.get("free"):
            path, n = self._manifest()
            if not n:
                os.remove(path)
                return
            self.manifests.append(path)
            job = lambda: self._rsync([], files_from=path)
        else:
            job = lambda: self._rsync([])
        if final:
            job()
            if self.m.get("free"):
                self.free()
        else:
            self.thread = threading.Thread(target=job, daemon=True)
            self.thread.start()


def keep_errors(machine, logdir, unit, phase):
    """prebuild's per-item error files (status/errors-<phase>-<k>of<n>.jsonl) are rewritten by the next run of the
    phase; a copy per unit and phase keeps the failed items' names for the report."""
    status = machine.get("status")
    if not status or not os.path.isdir(status):
        return
    lines = []
    for f in sorted(os.listdir(status)):
        if f.startswith(f"errors-{phase}-") and f.endswith(".jsonl"):
            with open(os.path.join(status, f)) as fh:
                lines += [l for l in fh if l.strip()]
    if lines:
        with open(os.path.join(logdir, f"errors-{unit}-{phase}.jsonl"), "w") as fh:
            fh.writelines(lines)


def build_unit(shared, farm, plan, me, machine, unit, python, env, logdir, dry_run=False):
    """Every phase of one unit, in order, each retried once; its result written to done/<unit>.json."""
    result = {"unit": unit["unit"], "machine": me, "started": now(), "phases": {}}
    phases = unit.get("phases", plan.get("phases", PHASES))
    name = f"farm-{me}-{unit['unit']}"
    if not dry_run:
        extra = ["--tmux", machine["tmux"]] if machine.get("tmux") and not shared.ssh else []
        extra += ["--pid", str(os.getpid())] if not shared.ssh else []
        extra += ["--thread", farm["job"]["thread"]] if farm.get("job", {}).get("thread") else []
        job(shared, farm, "start", name, f"cache build: unit {unit['unit']} on {me} ({unit.get('pictures', 0):,} pictures)",
            "--eta", unit_eta(farm, machine, unit), *extra)
    for k, phase in enumerate(phases):
        if not dry_run:
            job(shared, farm, "update", name, f"{phase} ({k + 1}/{len(phases)})", "--pct", int(100 * k / len(phases)))
        cmd = prebuild_cmd(machine, unit, phase, python)
        if dry_run:
            print(" ".join(map(shlex.quote, cmd)))
            continue
        for attempt in (1, 2):    # one retry: a made file is never made again, so a rerun picks up where it stopped
            t0 = time.time()
            shared.append(f"{unit['unit']} {phase} start {now()} {me}\n", "logs", me, "phases.log")
            with open(os.path.join(logdir, f"{phase}-{unit['unit']}.log"), "a") as fh:
                rc = subprocess.call(cmd, cwd=REPO, env=env, stdout=fh, stderr=subprocess.STDOUT)
            took = int(time.time() - t0)
            shared.append(f"{unit['unit']} {phase} done {now()} ({took}s) exit {rc} {me}\n", "logs", me, "phases.log")
            if rc == 0:
                break
        result["phases"][phase] = {"exit": rc, "seconds": took, "attempts": attempt}
        keep_errors(machine, logdir, unit["unit"], phase)
    if dry_run:
        return
    result["finished"] = now()
    shared.write(json.dumps(result, indent=1), "done", f"{unit['unit']}.json")
    bad = [p for p, r in result["phases"].items() if r["exit"]]
    secs = sum(r["seconds"] for r in result["phases"].values())
    if bad:
        job(shared, farm, "fail", name, f"{', '.join(bad)} failed after a retry (see farm status)")
    else:
        job(shared, farm, "done", name, f"all {len(phases)} phases in {secs / 3600:.1f} h")


def cmd_run(args):
    """Takes units and builds them. With slots > 1 (--slots or the machine's "slots") it builds that many units at once,
    each with procs / slots processes and its own status folder, so one unit's single-process tail (its biggest mosaic or
    movie pass) leaves the other cores to the next unit. Several slots never free the disk while shipping: a unit still
    building may need files a finished one shares."""
    shared = Shared(args.shared)
    farm, plan = load_json(shared, "farm.json"), load_json(shared, "plan.json")
    me = args.machine
    machine = dict(farm["machines"][me], name=me)
    python = os.path.expanduser(machine.get("python", farm.get("python", sys.executable)))
    if not args.dry_run:
        check_code(plan, machine, python)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", CASSINI_KEEP_SPICE_CACHE="1",
               **{k: os.path.expanduser(str(v)) for k, v in machine.get("env", {}).items()})
    if not args.dry_run:
        # Sam's rule (2026-11-08): never build without the full SPICE kernels or any other crucial input. Without the
        # kernels zip the pipeline's loader quietly loads 3 kernels instead of ~100 and the pictures come out wrong
        # (the 2017 test build's laptop months). Checked before any unit is claimed; a failure stops the machine loudly.
        years = plan_years(plan)
        probe = kernel_probe(python, env, sorted({years[0], years[-1]}))
        problems = preflight_problems(env, plan.get("inputs"), probe)
        print(f"preflight: kernels loaded {probe}")
        if problems:
            job(shared, farm, "fail", f"farm-{me}-preflight", "; ".join(problems)[:400])
            raise SystemExit("PREFLIGHT FAILED, nothing built:\n  " + "\n  ".join(problems))
    for k in ("cache", "status", "pause", "logs"):
        if machine.get(k):
            machine[k] = os.path.expanduser(machine[k])
    logdir = machine.get("logs") or os.path.join(machine["cache"], "..", "logs-" + me)
    os.makedirs(logdir, exist_ok=True)
    os.makedirs(machine["cache"], exist_ok=True)   # prebuild's free-space hold reads it before it writes anything
    slots = max(1, int(args.slots or machine.get("slots", 1)))
    if slots > 1:
        machine["free"] = False
    shipper = Shipper(machine, os.path.join(logdir, "ship.log"))
    lock, busy = threading.Lock(), set()

    def worker(k):
        m = dict(machine)
        if slots > 1:
            m["procs"] = max(1, -(-int(machine.get("procs", 1)) // slots))
            m["status"] = os.path.join(machine.get("status") or os.path.join(machine["cache"], "..", "status-" + me), f"slot{k}")
        while True:
            if shared.exists(f"stop-{me}"):
                print(f"slot {k}: stop-{me} is there: stopping")
                return
            with lock:
                unit = next_unit(shared, plan, me, machine, busy) if not args.dry_run else \
                    (candidates(plan, me, machine) or [None])[0]
                if unit is None:
                    print(f"slot {k}: no unit left")
                    return
                busy.add(unit["unit"])
            build_unit(shared, farm, plan, me, m, unit, python, env, logdir, args.dry_run)
            if args.dry_run:
                return
            with lock:
                busy.discard(unit["unit"])
                shipper.boundary()

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(slots if not args.dry_run else 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if not args.dry_run:
        shipper.boundary(final=True)


# ---------- exec: any command, queued for whichever machine is free (renders, posters, checks) ----------
# Sam's rule (2026-11-09): render work uses both machines. A thread on the hub submits a command; every machine running
# `exec worker` takes the next one it may run, runs it in its own checkout with its own inputs (farm.json env), and
# sends back what the command wrote into $FARM_OUT. The laptop reaches the queue over SSH; the hub never needs to reach
# the laptop. A job runs only on a worker whose checkout is at the job's commit, after the same preflight as `run`.
#
#   <shared>/exec/queue/<id>.json     {"argv", "commit", "only", "name", "by", "at"}
#   <shared>/exec/claims/<id>/        taken (mkdir), owner.json
#   <shared>/exec/done/<id>.json      {"exit", "seconds", "machine", "out"}
#   <exec_results>/<id>/              what the job wrote to $FARM_OUT (farm.json "exec_results", on the hub)

def new_job_id(name):
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + re.sub(r"[^A-Za-z0-9_-]+", "-", name)[:40]


def cmd_exec(args):
    shared = Shared(args.shared)
    if args.action == "submit":
        if not args.argv:
            raise SystemExit("exec submit -- <command> ...")
        argv = args.argv[1:] if args.argv[0] == "--" else args.argv
        jid = new_job_id(args.name or os.path.basename(argv[0]))
        job_ = {"argv": argv, "commit": args.commit or git("rev-parse", "HEAD"), "only": args.only, "name": args.name or "",
                "by": args.by or "", "at": now()}
        shared.write(json.dumps(job_, indent=1), "exec", "queue", jid + ".json")
        print(jid)
        return
    if args.action == "status":
        done = {n[:-5] for n in shared.listing("exec", "done")}
        claims = set(shared.listing("exec", "claims"))
        for n in shared.listing("exec", "queue"):
            jid = n[:-5]
            d = json.loads(shared.read("exec", "done", n) or "{}")
            state = (f"exit {d.get('exit')} on {d.get('machine')} in {d.get('seconds')}s" if jid in done else
                     "running" if jid in claims else "waiting")
            print(f"{jid:<60} {state}")
        return
    exec_worker(shared, args)


def exec_worker(shared, args):
    farm = load_json(shared, "farm.json")
    me = args.machine
    machine = dict(farm["machines"][me], name=me)
    python = os.path.expanduser(machine.get("python", farm.get("python", sys.executable)))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               VECLIB_MAXIMUM_THREADS="1", CASSINI_KEEP_SPICE_CACHE="1",
               **{k: os.path.expanduser(str(v)) for k, v in machine.get("env", {}).items()})
    plan = json.loads(shared.read("plan.json") or "{}")
    probe = kernel_probe(python, env, [2004, 2017])
    problems = preflight_problems(env, plan.get("inputs"), probe)
    print(f"exec preflight: kernels loaded {probe}", flush=True)
    if problems:
        job(shared, farm, "fail", f"farm-{me}-exec-preflight", "; ".join(problems)[:400])
        raise SystemExit("PREFLIGHT FAILED, nothing run:\n  " + "\n  ".join(problems))
    head = git("rev-parse", "HEAD")
    work = os.path.expanduser(machine.get("exec_dir", os.path.join(machine["cache"], "..", "exec-" + me)))
    results = farm.get("exec_results", "")
    idle = 0
    while not shared.exists(f"stop-exec-{me}"):
        done = {n[:-5] for n in shared.listing("exec", "done")}
        claims = set(shared.listing("exec", "claims"))
        took = None
        for n in shared.listing("exec", "queue"):
            jid = n[:-5]
            if jid in done or jid in claims:
                continue
            j = json.loads(shared.read("exec", "queue", n) or "{}")
            if j.get("only") not in (None, "", "any", me) or (j.get("commit") and j["commit"] != head):
                continue
            p = shared.path("exec", "claims", jid)
            ok = shared._remote(f"mkdir -p {shlex.quote(shared.path('exec', 'claims'))} && mkdir {shlex.quote(p)}")[0] == 0 \
                if shared.ssh else (os.makedirs(shared.path("exec", "claims"), exist_ok=True) or _mkdir(p))
            if ok:
                took = (jid, j)
                break
        if not took:
            if args.once:
                return
            idle += 1
            time.sleep(min(60, 5 * idle))
            continue
        idle = 0
        jid, j = took
        shared.write(json.dumps({"machine": me, "at": now()}), "exec", "claims", jid, "owner.json")
        out = os.path.join(work, jid)
        os.makedirs(out, exist_ok=True)
        job(shared, farm, "start", f"exec-{me}-{jid[:40]}", f"{j.get('name') or j['argv'][0]} (by {j.get('by') or '?'})",
            "--eta", (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
        t0 = time.time()
        with open(os.path.join(out, "farm-exec.log"), "w") as fh:
            rc = subprocess.call(j["argv"], cwd=REPO, env=dict(env, FARM_OUT=out, FARM_JOB=jid), stdout=fh,
                                 stderr=subprocess.STDOUT)
        secs = int(time.time() - t0)
        dest = ""
        if results:
            dest = os.path.join(results, jid)
            if shared.ssh:
                host = shared.ssh
                subprocess.call(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {shlex.quote(dest)}"])
                subprocess.call([machine.get("rsync", "rsync"), "-a", "-e", "ssh -o BatchMode=yes", out + "/", f"{host}:{dest}/"])
            else:
                os.makedirs(dest, exist_ok=True)
                subprocess.call(["rsync", "-a", out + "/", dest + "/"])
        shared.write(json.dumps({"exit": rc, "seconds": secs, "machine": me, "out": dest or out, "finished": now()}, indent=1),
                     "exec", "done", jid + ".json")
        job(shared, farm, "done" if rc == 0 else "fail", f"exec-{me}-{jid[:40]}", f"exit {rc} in {secs}s, output {dest or out}")
        if args.once:
            return


def _mkdir(p):
    try:
        os.mkdir(p)
        return True
    except FileExistsError:
        return False


# ---------- status ----------

def cmd_status(args):
    shared = Shared(args.shared)
    plan = load_json(shared, "plan.json")
    done = {n[:-5]: json.loads(shared.read("done", n) or "{}") for n in shared.listing("done") if n.endswith(".json")}
    claimed = set(shared.listing("claims"))
    rows, left = [], 0
    for u in plan["units"]:
        name = u["unit"]
        d = done.get(name)
        if d:
            secs = sum(p["seconds"] for p in d["phases"].values())
            bad = [p for p, r in d["phases"].items() if r["exit"]]
            rows.append((name, d["machine"], "FAILED " + ",".join(bad) if bad else "done", f"{secs / 3600:.1f} h"))
        elif name in claimed:
            owner = json.loads(shared.read("claims", name, "owner.json") or "{}")
            rows.append((name, owner.get("machine", "?"), "building", "since " + owner.get("at", "?")))
        else:
            rows.append((name, "", "waiting", ""))
            left += 1
    for r in rows:
        print(f"{r[0]:>10}  {r[1]:<6} {r[2]:<20} {r[3]}")
    print(f"{len(done)} done, {len(claimed) - len(done)} building, {left} waiting")
    for m in shared.listing("logs"):
        text = shared.read("logs", m, "phases.log") or ""
        print(f"{m}: last: {text.strip().splitlines()[-1] if text.strip() else '(nothing yet)'}")


# ---------- verify, compare, merge ----------

def picture_versions():
    import frame_server   # the pipeline: only verify needs it
    return frame_server.picture_versions()


def unit_spans(unit):
    if unit.get("years"):
        return slices.parse_years(unit["years"])
    if unit.get("from"):
        return [(slices.utc(unit["from"]), slices.utc(unit["until"]))]
    return [(None, None)]


def check_cache(cache, units, phases, vers):
    """Problems with a cache: a unit's stretch some phase hasn't recorded under these versions, records with errors,
    records under other versions."""
    problems = []
    got = slices.covered(cache, vers)["phases"]
    records = slices.read(cache)["records"]
    other = {json.dumps(r.get("versions"), sort_keys=True) for r in records if r.get("versions") != vers}
    if other:
        problems.append(f"{len(other)} other version set(s) recorded (another commit built into this cache)")
    for u in units:
        for phase in u.get("phases", phases):
            have = [tuple(x) for x in got.get(phase, [])]
            for span in unit_spans(u):
                if slices.intersect(have, [span]) != [span]:
                    problems.append(f"{u['unit']} {phase}: not recorded")
    for r in records:
        if r.get("versions") == vers and r.get("errors"):
            problems.append(f"{r['phase']} {r.get('from')}..{r.get('until')}: {r['errors']} errors")
    return problems


def cmd_verify(args):
    units = None
    if args.shared:
        plan = load_json(Shared(args.shared), "plan.json")
        units, phases = plan["units"], plan.get("phases", PHASES)
    else:
        phases = args.phases.split(",")
    if args.units:
        want = set(args.units.split(","))
        units = [u for u in (units or []) if u["unit"] in want] or \
            [{"unit": w, "years": w} for w in want if w.isdigit()]
    problems = check_cache(args.cache, units or [{"unit": "mission"}], phases, picture_versions())
    for p in problems:
        print("PROBLEM", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


def walk_files(root):
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_SHIP]
        for f in fs:
            if f in SKIP_SHIP or ".part" in f or f.endswith(".tmp") or f.startswith("."):
                continue
            yield os.path.relpath(os.path.join(d, f), root)


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compare(a, b, sample=0, seed=1):
    """Files both caches hold, and those whose bytes differ (all of them, or a sample)."""
    both = sorted(set(walk_files(a)) & set(walk_files(b)))
    picked = both if not sample or sample >= len(both) else sorted(random.Random(seed).sample(both, sample))
    differ = [p for p in picked if os.path.getsize(os.path.join(a, p)) != os.path.getsize(os.path.join(b, p))
              or sha1(os.path.join(a, p)) != sha1(os.path.join(b, p))]
    return {"common": len(both), "checked": len(picked), "differ": differ}


def cmd_compare(args):
    got = compare(args.a, args.b, args.sample)
    print(f"{got['common']} files in both, {got['checked']} checked, {len(got['differ'])} differ")
    for p in got["differ"][:40]:
        print("  DIFFERS", p)
    sys.exit(1 if got["differ"] else 0)


def join_slices(into, srcs):
    """into/slices.json gets every source record it lacks (the same phase, stretch, versions and time)."""
    key = lambda r: json.dumps([r.get("phase"), r.get("from"), r.get("until"), r.get("versions"), r.get("at")], sort_keys=True)
    got = slices.read(into)
    have = {key(r) for r in got["records"]}
    added = 0
    for s in srcs:
        for r in slices.read(s)["records"]:
            if key(r) not in have:
                got["records"].append(r)
                have.add(key(r))
                added += 1
    os.makedirs(into, exist_ok=True)
    part = os.path.join(into, slices.NAME + ".part-merge")
    with open(part, "w") as fh:
        json.dump(got, fh, indent=1)
    os.replace(part, os.path.join(into, slices.NAME))
    return added


def merge(into, src, move=False, check=True, link=False):
    """src's files into `into`: a file `into` lacks is moved (same disk, --move) or copied; one it has is left as it
    is, and counted as differing if its size (or, with check, its bytes) differ. A folder `into` lacks entirely is
    moved in one rename."""
    out = {"moved": 0, "copied": 0, "linked": 0, "same": 0, "differ": []}
    for d, dirs, fs in os.walk(src, topdown=True):
        rel = os.path.relpath(d, src)
        keep = []
        for x in dirs:
            if x in SKIP_SHIP:
                continue
            target = os.path.normpath(os.path.join(into, rel, x))
            if move and not link and not os.path.exists(target):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                n = sum(len(f) for _, _, f in os.walk(os.path.join(d, x)))
                os.rename(os.path.join(d, x), target)
                out["moved"] += n
            else:
                keep.append(x)
        dirs[:] = keep
        for f in fs:
            if f in SKIP_SHIP or ".part" in f or f.endswith(".tmp") or f.startswith("."):   # rsync's temp files are .name.XXXX
                continue
            s, t = os.path.join(d, f), os.path.normpath(os.path.join(into, rel, f))
            if os.path.exists(t):
                if os.path.getsize(s) != os.path.getsize(t) or (check and sha1(s) != sha1(t)):
                    out["differ"].append(os.path.normpath(os.path.join(rel, f)))
                else:
                    out["same"] += 1
                continue
            os.makedirs(os.path.dirname(t), exist_ok=True)
            if link:   # a hard link: the source stays, so a later rsync into it finds the file and sends nothing again
                os.link(s, t)
                out["linked"] += 1
            elif move:
                os.rename(s, t)
                out["moved"] += 1
            else:
                shutil.copy2(s, t)
                out["copied"] += 1
    return out


def cmd_merge(args):
    for src in args.src:
        got = merge(args.into, src, move=args.move, check=not args.fast, link=args.link)
        print(f"{src}: {got['moved']} moved, {got['linked']} linked, {got['copied']} copied, {got['same']} already there, "
              f"{len(got['differ'])} differ (kept the target's)")
        for p in got["differ"][:40]:
            print("  DIFFERS", p)
    print(f"slices.json: {join_slices(args.into, args.src)} record(s) added")


# ---------- doctor ----------

def cmd_doctor(args):
    shared = Shared(args.shared)
    farm = load_json(shared, "farm.json")
    m = dict(farm["machines"][args.machine], name=args.machine)
    python = os.path.expanduser(m.get("python", farm.get("python", sys.executable)))
    ok = True
    print(f"repo {REPO} at {git('rev-parse', '--short', 'HEAD')}, packages {packages_hash(python)}, python {python}")
    plan = json.loads(shared.read("plan.json") or "{}")
    if plan:
        print(f"plan commit {plan.get('commit', '')[:8]}, packages {plan.get('packages')}")
    for k, v in m.get("env", {}).items():
        p = os.path.expanduser(str(v))
        if k in ("CASSINI_DATA", "CASSINI_KERNELS", "CASSINI_GEOMETRY_CACHE", "CASSINI_SPICE_CACHE", "CASSINI_CISSCAL"):
            there = os.path.exists(p)
            size = os.path.getsize(p) if there and os.path.isfile(p) else None
            print(f"{'ok ' if there else 'MISSING'} {k}={p}" + (f" ({size / 1e9:.1f} GB)" if size else ""))
            ok &= there
    for k in REQUIRED_INPUTS:
        if k not in m.get("env", {}):
            print(f"MISSING {k} (not set in farm.json env)")
            ok = False
    cache = os.path.expanduser(m["cache"])
    os.makedirs(cache, exist_ok=True)
    free = shutil.disk_usage(cache).free / 1e9
    need = float(m.get("need_gb", 0))
    print(f"{'ok ' if free >= need else 'LOW'} cache {cache}: {free:.0f} GB free (needs {need:.0f})")
    ok &= free >= need
    if m.get("ship_to"):
        host = m["ship_to"].split(":")[0]
        rc = subprocess.call(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "true"])
        print(f"{'ok ' if rc == 0 else 'NO SSH'} {host}")
        ok &= rc == 0
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--shared", required=True)
    p.add_argument("--index", default=os.path.join(REPO, "Image_index.csv"))
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("--shared", required=True)
    p.add_argument("--machine", required=True)
    p.add_argument("--dry-run", action="store_true", help="print the first unit's prebuild commands, take nothing")
    p.add_argument("--slots", type=int, default=0, help="units built at once (default: the machine's \"slots\", else 1)")
    p = sub.add_parser("status")
    p.add_argument("--shared", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--cache", required=True)
    p.add_argument("--shared", help="check every unit of this farm's plan")
    p.add_argument("--units", help="only these units (2004,2007a); with no --shared, years")
    p.add_argument("--phases", default=",".join(PHASES))
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--sample", type=int, default=0)
    p = sub.add_parser("merge")
    p.add_argument("--into", required=True)
    p.add_argument("--move", action="store_true", help="move files (same disk) instead of copying")
    p.add_argument("--fast", action="store_true", help="compare sizes only where both hold a file")
    p.add_argument("--link", action="store_true", help="hard-link files (same disk) and leave the source: for merging "
                                                        "while a machine still ships into it")
    p.add_argument("src", nargs="+")
    p = sub.add_parser("exec", help="a queue of commands either machine runs (renders, posters, checks)")
    p.add_argument("action", choices=["submit", "worker", "status"])
    p.add_argument("--shared", required=True)
    p.add_argument("--machine", help="worker: this machine's name in farm.json")
    p.add_argument("--only", help="submit: run only on this machine (default: any)")
    p.add_argument("--name", help="submit: a short name for the dashboard")
    p.add_argument("--by", help="submit: who asked (thread)")
    p.add_argument("--commit", help="submit: the commit the command needs (default: this checkout's)")
    p.add_argument("--once", action="store_true", help="worker: run at most one job, then stop")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p = sub.add_parser("doctor")
    p.add_argument("--shared", required=True)
    p.add_argument("--machine", required=True)
    args = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "status": cmd_status, "verify": cmd_verify, "compare": cmd_compare,
     "merge": cmd_merge, "doctor": cmd_doctor, "exec": cmd_exec}[args.cmd](args)


if __name__ == "__main__":
    main()
