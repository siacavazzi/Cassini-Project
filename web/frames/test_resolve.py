#!/usr/bin/env python3
"""
Tests of the cache-only resolver (resolve.py) and the frame server's --public mode (public site, WP1).

  python web/frames/test_resolve.py
      the guard alone (no archive needed): inside resolve.cache_only() no file is written, no folder made or removed,
      no thread started, and code outside it is untouched

  python web/frames/test_resolve.py --normal http://127.0.0.1:8960 --public http://127.0.0.1:8910 --cache DIR \\
         --urls OUT_DIR [--urls OUT_DIR ...] [--public-pid PID] [--requests 1000]
      against a cache the normal server (--normal, on that --cache) made while the zero-origin harness played sessions
      on it (--urls: the harness's --out folders, whose request logs give the sampled URLs of every route). For each
      sampled picture URL, in its canonical form (web/public/keys.py): the normal server sends a finished picture
      (a stand-in it would ask for again is skipped, and counted), resolve() names a file of the cache whose bytes and
      X-* report are what the normal server sent, and --public sends the same bytes and report; Auto center's 404s
      answer the same X-Center; table routes answer the same JSON (where the normal server has it worked out).
      Refused URLs answer 404 (405 for POST and PUT). --public makes nothing (the cache is unchanged by its answers
      and by resolve()) and its thread count stays flat over --requests requests. Run it with the archive environment
      the servers use (CASSINI_DATA, CASSINI_KERNELS, ...): resolve() reads the index of the frames as they do.
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "public"))

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL", what, flush=True)
    return ok


# ---------- the guard (no archive needed) ----------
def test_guard():
    import resolve
    check(resolve.resolve("/frames/N1500060789_2.webp", {}, tempfile.mkdtemp()).kind == "none",
          "resolve() answers none on an empty cache")
    d = tempfile.mkdtemp()
    stopped = []
    for name, act in [
        ("write", lambda: open(os.path.join(d, "a"), "wb").close()),
        ("append", lambda: open(os.path.join(d, "a"), "a").close()),
        ("os.open create", lambda: os.close(os.open(os.path.join(d, "b"), os.O_WRONLY | os.O_CREAT))),
        ("mkdir", lambda: os.makedirs(os.path.join(d, "x", "y"))),
        ("thread", lambda: threading.Thread(target=lambda: None).start()),
    ]:
        try:
            with resolve.cache_only(d):
                act()
        except resolve.NotMade:
            stopped.append(name)
    check(len(stopped) == 5, f"cache_only stops writes, folders and threads (stopped {stopped})")
    check(not os.listdir(d), "nothing was made in the folder")
    # a maker's broad except cannot swallow it
    try:
        with resolve.cache_only(d):
            try:
                open(os.path.join(d, "c"), "w")
            except Exception:
                pass
        check(False, "NotMade passes through a maker's except Exception")
    except resolve.NotMade:
        pass
    # reading is allowed, and outside cache_only everything works
    p = os.path.join(d, "r")
    with open(p, "w") as fh:
        fh.write("x")
    with resolve.cache_only(d):
        with open(p) as fh:
            check(fh.read() == "x", "reading inside cache_only")
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
    # a thread started outside (the server's own) is not affected by a request in cache_only on another thread
    seen = []

    def other():
        with open(os.path.join(d, "o"), "w") as fh:
            fh.write("ok")
        seen.append(True)
    with resolve.cache_only(d):
        pass
    th = threading.Thread(target=other)
    th.start()
    th.join()
    check(seen == [True], "other threads write as before")
    print("guard: ok" if not failures else "guard: FAILED", flush=True)


# ---------- against servers and a cache ----------
def get(url, method="GET", timeout=600):
    req = urllib.request.Request(url, method=method, data=b"" if method in ("POST", "PUT") else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def reports(headers):
    """The X-* reports as JSON objects (the page reads them as JSON; key order is the server's)."""
    out = {}
    for k, v in headers.items():
        if k.startswith("x-") and k not in ("x-hdr",):
            try:
                out[k] = json.loads(v)
            except ValueError:
                out[k] = v
    return out


def sampled(dirs):
    """The frames-host URLs the harness sessions asked for (path with query), in order, once each."""
    seen = collections.OrderedDict()
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "S*.json"))):
            with open(f) as fh:
                log = json.load(fh)
            for r in log.get("requests", []):
                k = r.get("k") or {}
                if k.get("cls") != "frames" or r.get("method") != "GET":
                    continue
                u = urlsplit(r["url"])
                seen.setdefault(u.path + ("?" + u.query if u.query else ""), None)
    return list(seen)


def canonical_url(ans, path):
    """The canonical request a key stands for: the path and the canonical parameters."""
    q = "&".join(f"{k}={v}" for k, v in sorted(ans["params"].items()))
    return path + ("?" + q if q else "")


def snapshot(cache):
    out = {}
    for root, dirs, files in os.walk(cache):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


def settle(cache, quiet=20, most=600):
    """Waits until nothing in the cache changes for quiet seconds (the normal server's look-ahead finishing)."""
    t0, last = time.time(), snapshot(cache)
    calm = time.time()
    while time.time() - t0 < most:
        time.sleep(5)
        now = snapshot(cache)
        if now != last:
            last, calm = now, time.time()
        elif time.time() - calm >= quiet:
            return now
    return last


def threads_of(pid):
    out = subprocess.run(["ps", "-M", "-p", str(pid)], capture_output=True, text=True).stdout
    return max(0, len(out.strip().splitlines()) - 1)


def test_servers(args):
    import keys
    import resolve
    urls = sampled(args.urls)
    print(f"{len(urls)} sampled frames-host URLs", flush=True)
    seen_canonical, tally = set(), collections.Counter()
    picks = []
    for u in urls:
        ans = keys.canonical("GET", u)
        if ans["refused"] or ans["store"] not in ("r2", "table"):
            tally["not r2/table"] += 1
            continue
        c = canonical_url(ans, urlsplit(u).path)
        if ans["route"] == "mosaic_kind":
            c += ("&" if "?" in c else "?") + "warm=1"   # (the key drops warm=, which is what makes it this table)
        if c in seen_canonical:
            continue
        seen_canonical.add(c)
        picks.append((ans, c))
    by_route = collections.Counter(a["route"] for a, _ in picks)
    print("canonical URLs by route:", dict(by_route), flush=True)

    # the normal server's answers first (it may still be making pictures ahead: let it settle)
    normal = {}
    with ThreadPoolExecutor(8) as ex:
        for (ans, c), res in zip(picks, ex.map(lambda p: get(args.normal + p[1]), picks)):
            normal[c] = res
    before = settle(args.cache)
    # ask again: a picture the first ask answered with a stand-in may be made now
    for ans, c in picks:
        st, h, body = normal[c]
        if st != 200 or "immutable" not in h.get("cache-control", "immutable" if ans["store"] == "table" else ""):
            normal[c] = get(args.normal + c)
    before = settle(args.cache)

    resolve.prepare()
    checked = collections.Counter()
    for ans, c in picks:
        st, h, body = normal[c]
        path, query = urlsplit(c).path, parse_qs(urlsplit(c).query)
        if ans["store"] == "table":
            if st != 200 or (body.startswith(b"{") and json.loads(body).get("working")):
                tally["table not worked out by the normal server"] += 1
                continue
            pst, _, pbody = get(args.public + c)
            check(pst == 200 and json.loads(pbody) == json.loads(body), f"table {c}: --public answers the server's JSON")
            checked["table " + ans["route"]] += 1
            continue
        if st == 404 and h.get("x-center"):
            a = resolve.resolve(path, query, args.cache)
            check(a.kind == "negative" and json.loads(a.headers.get("X-Center", "null")) == json.loads(h["x-center"]),
                  f"negative {c}: resolve() answers Auto center's 404 ({a.kind})")
            pst, ph, _ = get(args.public + c)
            check(pst == 404 and json.loads(ph.get("x-center", "null")) == json.loads(h["x-center"]),
                  f"negative {c}: --public sends Auto center's 404")
            checked["marker " + ans["route"]] += 1
            continue
        if st != 200 or "immutable" not in h.get("cache-control", ""):
            tally[f"normal server {st} {'stand-in' if st == 200 else ''} ({ans['route']})"] += 1
            continue
        a = resolve.resolve(path, query, args.cache)
        if not check(a.kind == "file", f"{c}: resolve() names a file ({a.kind})"):
            continue
        data = resolve.read(a)
        check(data == body, f"{c}: resolve()'s file is the normal server's bytes ({a.path})")
        check(reports({k.lower(): v for k, v in a.headers.items()}) == reports(h), f"{c}: resolve()'s report is the server's")
        pst, ph, pbody = get(args.public + c)
        check(pst == 200 and pbody == body, f"{c}: --public sends the same bytes ({pst})")
        check(reports(ph) == reports(h), f"{c}: --public sends the same X-* reports")
        check(ph.get("content-type") == h.get("content-type"), f"{c}: --public sends the same Content-Type")
        checked[ans["route"]] += 1
    print("checked:", dict(checked), flush=True)
    print("skipped:", dict(tally), flush=True)
    check(sum(checked.values()) > 0, "some URLs were checked")

    # refused: 404 (405 for POST and PUT), and counted by the server
    for method, u, want in [("GET", "/export/plan.json?from=0&to=1", 404), ("GET", "/reel/bodies.json", 404),
                            ("GET", "/frames/N1454725799_1.tif", 404), ("GET", "/frames/N1454725799_1.webp?look=classic", 404),
                            ("GET", "/frames/N1454725799_1.webp?bogus=1", 404), ("GET", "/stats/usage.json", 404),
                            ("GET", "/frames/mosaic/N1454725799_1/full.json", 404), ("GET", "/prebuild/0123456789abcdef.json", 404),
                            ("POST", "/export", 405), ("PUT", "/export/0123456789abcdef/sound.wav", 405), ("POST", "/flags", 405)]:
        st, _, _ = get(args.public + u, method)
        check(st == want, f"refused {method} {u}: {st}, wanted {want}")
    st, _, body = get(args.public + "/health")
    check(st == 200 and body.strip() == b"ok public", "/health answers ok public")
    st, _, _ = get(args.public + "/usage", "POST")
    check(st == 204, "the usage beacon answers 204, as the Worker does")

    # the thread count stays flat over many requests, and nothing is made
    if args.public_pid:
        t0 = threads_of(args.public_pid)
        mix = [c for _, c in picks] or ["/health"]
        work = [mix[i % len(mix)] for i in range(args.requests)]
        with ThreadPoolExecutor(16) as ex:
            list(ex.map(lambda c: get(args.public + c)[0], work))
        time.sleep(3)
        t1 = threads_of(args.public_pid)
        print(f"--public threads: {t0} before, {t1} after {args.requests} requests", flush=True)
        check(t1 <= t0 + 2, f"--public's thread count stays flat ({t0} -> {t1})")
    after = snapshot(args.cache)
    made = sorted(set(after) - set(before))
    changed = sorted(p for p in set(after) & set(before) if after[p] != before[p])
    check(not made and not changed, f"nothing in the cache was made or changed by resolve() and --public "
                                    f"({len(made)} new, {len(changed)} changed: {(made + changed)[:5]})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--normal")
    ap.add_argument("--public")
    ap.add_argument("--cache")
    ap.add_argument("--urls", action="append", default=[])
    ap.add_argument("--public-pid", type=int)
    ap.add_argument("--requests", type=int, default=1000)
    args = ap.parse_args()
    test_guard()
    if args.normal and args.public and args.cache:
        test_servers(args)
    print("ok" if not failures else f"{len(failures)} FAILED", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
