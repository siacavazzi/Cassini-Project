#!/usr/bin/env python3
"""
Times the frame server's answers for pictures already in its cache. Replays either the picture requests of a movie
mode run (web/cassini-os/bench/movie_rate.cjs OUT.json, its timed run's urls) or every frame of one pass in order
(--pass: its frames from /frames/movie/<id>.json, asked for by --routes) against a server, over one kept-alive
connection and over six at once (what a browser opens to one server), and reports each kind of picture's time to
answer, and how that grows through a pass (the first and the last quarter of the requests). Run it after a warm-up
(a movie_rate.cjs WARM=1 run, or this once with --repeat 1), so every answer is a cache hit and nothing is made.
Against the cloud rig (rig_cached.py) it also reports the files the server looked for and opened per request.

  python web/frames/bench_cached.py --run OUT.json http://localhost:8790 [--repeat 2] [--clients 1,6]
  python web/frames/bench_cached.py --pass W1537023863_1 --routes mosaic,processed http://localhost:8790
    routes: mosaic (/frames/mosaic/<id>.webp), processed (/frames/processed/<id>.webp, centred), rolling (the
    mosaic movie route), movie (a steady movie's frame), frame (/frames/<id>.webp); all at --size (512)
"""
import argparse
import collections
import http.client
import json
import threading
import time
from urllib.parse import urlparse

ROUTES = {"mosaic": "/frames/mosaic/{id}.webp?size={size}", "processed": "/frames/processed/{id}.webp?size={size}&center=1",
          "rolling": "/frames/movie/{id}.webp?size={size}&mode=rolling", "movie": "/frames/movie/{id}.webp?size={size}",
          "frame": "/frames/{id}.webp?size={size}"}


def kind_of(path):
    u = urlparse(path)
    p, q = u.path, u.query
    if p.startswith("/frames/movie/"):
        return "movie.json" if p.endswith(".json") else "rolling" if "mode=rolling" in q else "movie"
    if p.startswith("/frames/mosaic/"):
        return "mosaic.json" if p.endswith(".json") else "mosaic"
    if p == "/frames/color.webp":
        return "color.channel" if "channel=" in q else "color"
    if p.startswith("/frames/processed/"):
        return "processed"
    return "frame"


def get(base, path):
    host = urlparse(base)
    conn = http.client.HTTPConnection(host.hostname, host.port or 80, timeout=120)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def replay(base, paths, clients):
    """Each path asked once, by `clients` connections taking the next path in turn; [(index, kind, seconds, status,
    bytes)] and the seconds it all took."""
    host = urlparse(base)
    todo, lock, out = collections.deque(enumerate(paths)), threading.Lock(), []

    def worker():
        conn = http.client.HTTPConnection(host.hostname, host.port or 80, timeout=120)
        while True:
            with lock:
                if not todo:
                    break
                i, path = todo.popleft()
            t = time.perf_counter()
            try:
                conn.request("GET", path)
                r = conn.getresponse()
                body = r.read()
                status = r.status
            except (OSError, http.client.HTTPException):
                conn.close()
                conn = http.client.HTTPConnection(host.hostname, host.port or 80, timeout=120)
                body, status = b"", 0
            with lock:
                out.append((i, kind_of(path), time.perf_counter() - t, status, len(body)))
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(clients)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return out, time.perf_counter() - t0


def pct(a, p):
    a = sorted(a)
    return a[min(len(a) - 1, int(len(a) * p))] if a else None


def counts(base):
    """The rig's file and thread counts since it was last asked (None from a real frame server)."""
    try:
        status, body = get(base, "/rig/counts")
        return json.loads(body) if status == 200 else None
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="the frame server, e.g. http://localhost:8790")
    ap.add_argument("--run", help="a movie_rate.cjs OUT.json: replay its timed run's picture requests")
    ap.add_argument("--pass", dest="pass_id", help="a frame of a pass: ask for every frame of its pass in order")
    ap.add_argument("--routes", default="mosaic", help="with --pass: " + ", ".join(ROUTES))
    ap.add_argument("--size", default="512")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--clients", default="1,6")
    ap.add_argument("--settle", type=float, default=2.0, help="seconds to wait between rounds (background work)")
    ap.add_argument("--out", help="write the results here as JSON")
    args = ap.parse_args()
    if args.run:
        runs = json.load(open(args.run))["runs"]
        paths = []
        for r in runs:
            if r["label"].startswith("timed"):
                paths = [u[2] for u in r["urls"]]
        paths = [p for p in paths if p.startswith("/frames/")]
        source = args.run
    else:
        status, body = get(args.base, f"/frames/movie/{args.pass_id}.json")
        if status != 200:
            raise SystemExit(f"{args.pass_id} is in no pass ({status})")
        info = json.loads(body)
        paths = [ROUTES[r].format(id=fr[0], size=args.size) for fr in info["frames"] for r in args.routes.split(",")]
        source = f"{info['observation']} pass {info['pass']} ({len(info['frames'])} frames), {args.routes}"
    report = {"base": args.base, "source": source, "requests": len(paths), "rounds": []}
    print(f"{len(paths)} picture requests: {source}")
    counts(args.base)
    for clients in map(int, args.clients.split(",")):
        for rep in range(args.repeat):
            got, took = replay(args.base, paths, clients)
            time.sleep(args.settle)   # what the requests started in the background, counted with them
            files = counts(args.base)
            by, early, late = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
            for i, kind, s, status, n in got:
                by[kind].append(s * 1000)
                (early if i < len(paths) / 4 else late if i >= 3 * len(paths) / 4 else {}).setdefault(kind, []).append(s * 1000)
            bad = sum(1 for g in got if g[3] not in (200, 404))
            row = {"clients": clients, "round": rep + 1, "seconds": round(took, 2), "per_second": round(len(got) / took, 1), "errors": bad,
                   "kinds": {k: {"n": len(v), "p50": round(pct(v, .5), 1), "p95": round(pct(v, .95), 1), "max": round(max(v), 1),
                                 "total_s": round(sum(v) / 1000, 2),
                                 "first_quarter_p50": round(pct(early[k], .5), 1) if early.get(k) else None,
                                 "last_quarter_p50": round(pct(late[k], .5), 1) if late.get(k) else None}
                             for k, v in sorted(by.items())}}
            if files is not None:
                row["files_per_request"] = {k: round(v / len(got), 2) for k, v in sorted(files.items())}
            report["rounds"].append(row)
            print(f"{clients} connection(s), round {rep + 1}: {len(got)} in {took:.2f} s = {row['per_second']}/s, {bad} errors; "
                  + "; ".join(f"{k} {v['n']} p50 {v['p50']} p95 {v['p95']} max {v['max']} ms (first quarter {v['first_quarter_p50']}, "
                              f"last {v['last_quarter_p50']})" for k, v in row["kinds"].items()), flush=True)
            if files is not None:
                print("   per request: " + ", ".join(f"{k} {v}" for k, v in row["files_per_request"].items()), flush=True)
    if args.out:
        json.dump(report, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
