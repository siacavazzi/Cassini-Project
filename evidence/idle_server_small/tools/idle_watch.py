#!/usr/bin/env python3
"""idle_watch.py --out DIR [--cap-gb 10] [--max-s 900] [--quiet-s 120] [--check URL ...] -- server command...

Starts a frame server and sends it NO requests (apart from --check, at the very end): its physical footprint and CPU
seconds every 2 s into DIR/footprint.csv (seconds since start, MB, CPU seconds, threads), its output into
DIR/server.log with the time of each line. Stops the server when its footprint passes --cap-gb (so a runaway cannot
take the Mac's memory), after --max-s, or once it has used under 2 CPU seconds over --quiet-s (idle: warm-ups done).
--check URL (several): once idle (or at --max-s), each URL is asked for once and its status, bytes and seconds go to
DIR/checks.txt; the footprint goes on being sampled meanwhile."""
import argparse, ctypes, os, signal, subprocess, sys, threading, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True); ap.add_argument("--cap-gb", type=float, default=10)
ap.add_argument("--max-s", type=float, default=900); ap.add_argument("--quiet-s", type=float, default=120)
ap.add_argument("--min-s", type=float, default=180, help="not stopped as idle before this")
ap.add_argument("--check", action="append", default=[])
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
os.makedirs(a.out, exist_ok=True)


class RU(ctypes.Structure):
    _fields_ = [("u", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in "abcdefgHijklmnopqr"]


lp = ctypes.CDLL("/usr/lib/libproc.dylib")


def foot(pid):
    r = RU()
    return r.H / 1e6 if lp.proc_pid_rusage(pid, 2, ctypes.byref(r)) == 0 else None


def cpu_threads(pid):
    """(CPU seconds, threads) from ps"""
    out = subprocess.run(["ps", "-M", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.split("\n")
    try:
        t = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        parts = [float(x) for x in t.replace("-", ":").split(":")]
        s = 0.0
        for x in parts:
            s = s * 60 + x
        return s, max(0, len([l for l in out if l.strip()]) - 1)
    except ValueError:
        return None, 0


t0 = time.monotonic()
log = open(os.path.join(a.out, "server.log"), "w")
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)


def pump():
    for line in p.stdout:
        log.write(f"{time.monotonic() - t0:7.1f} s  {line}"); log.flush()


threading.Thread(target=pump, daemon=True).start()
csv = open(os.path.join(a.out, "footprint.csv"), "w")
csv.write("seconds,footprint_mb,cpu_seconds,threads\n")
hist, why, checked_at, peak = [], None, None, 0.0


def checks():
    with open(os.path.join(a.out, "checks.txt"), "w") as fh:
        for url in a.check:
            t = time.monotonic()
            try:
                with urllib.request.urlopen(url, timeout=600) as r:
                    body = r.read()
                    fh.write(f"{r.status} {len(body)} bytes {time.monotonic() - t:.2f} s  {url}\n")
            except Exception as e:   # noqa: BLE001
                fh.write(f"FAILED {type(e).__name__}: {e} {time.monotonic() - t:.2f} s  {url}\n")
            fh.flush()


check_thread = None
while p.poll() is None:
    time.sleep(2)
    t = time.monotonic() - t0
    f = foot(p.pid)
    c, n = cpu_threads(p.pid)
    if f is None or c is None:
        continue
    peak = max(peak, f)
    csv.write(f"{t:.1f},{f:.0f},{c:.1f},{n}\n"); csv.flush()
    hist.append((t, c))
    if f > a.cap_gb * 1000:
        why = f"stopped at the cap: footprint {f:.0f} MB over {a.cap_gb:g} GB after {t:.0f} s"
        break
    old = [h for h in hist if h[0] <= t - a.quiet_s]
    idle = bool(old) and c - old[-1][1] < 2 and t >= a.min_s
    if (idle or t > a.max_s) and a.check and check_thread is None:
        check_thread = threading.Thread(target=checks, daemon=True); check_thread.start()
        after = t
        continue
    if check_thread is not None:
        if check_thread.is_alive():
            continue
        if checked_at is None:
            checked_at = t
        # (after the checks: until it is idle again, whatever they started in the background, or 10 minutes more)
        if (t < checked_at + a.quiet_s or c - old[-1][1] >= 2) and t < checked_at + 600:
            continue
        why = f"idle, checked at {after:.0f} to {checked_at:.0f} s and idle again after {t:.0f} s: peak footprint {peak:.0f} MB, {c:.0f} CPU seconds"
        break
    if idle:
        why = f"idle after {t:.0f} s: peak footprint {peak:.0f} MB, {c:.0f} CPU seconds"
        break
    if t > a.max_s:
        why = f"stopped at {a.max_s:g} s, still working: footprint {f:.0f} MB (peak {peak:.0f}), {c:.0f} CPU seconds"
        break
if why is None:
    why = f"the server exited by itself with {p.returncode} after {time.monotonic() - t0:.0f} s (peak {peak:.0f} MB)"
for sig in (signal.SIGTERM, signal.SIGKILL):
    try:
        os.killpg(p.pid, sig)
    except (ProcessLookupError, PermissionError):   # (gone already; macOS answers EPERM for a group of zombies)
        break
    try:
        p.wait(timeout=5)
        break
    except subprocess.TimeoutExpired:
        pass
with open(os.path.join(a.out, "result.txt"), "w") as fh:
    fh.write(why + "\n")
print(why, flush=True)
