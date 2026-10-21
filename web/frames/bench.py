#!/usr/bin/env python3
"""
Times the frame server's hot paths on the real archive, so speed changes can be measured
before and after. Nothing is written outside a temporary cache folder (or --cache).

  python web/frames/bench.py reel ENCELADUS --first 445 --count 20 [--profile]
      body reel pictures (reel.picture: stacked, calibrated, aligned, SPICE-centred), one at a
      time, seconds per picture; --profile adds where the time went
  python web/frames/bench.py frames --count 200 --threads 1,4
      plain frames as the viewer asks for them (/frames/<ID>.webp?size=512), frames per second
  python web/frames/bench.py composites --count 10
      camera-feed colour composites (/frames/color.webp), seconds each
  python web/frames/bench.py http --count 200 --clients 8
      the server itself on a spare port: latency of uncached and cached frames with several
      viewers at once
  python web/frames/bench.py sample OUT.zip ENCELADUS --first 445 --count 20
      a small zip of every archive file those reel pictures read (kernels left out), for
      testing the pipeline away from the archive

Run it from the repo with the server's environment (CASSINI_DATA, CASSINI_KERNELS...).
"""
import argparse
import cProfile
import io
import json
import os
import pstats
import random
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("FRAME_SERVER_QUIET", "1")
import frame_server  # noqa: E402
import reel  # noqa: E402
import data_source  # noqa: E402


def quiet():
    """The pipeline prints a lot per frame; keep it out of the timings."""
    return open(os.devnull, "w")


def stats(times):
    times = sorted(times)
    pick = lambda q: times[min(len(times) - 1, int(q * len(times)))]
    return f"mean {sum(times) / len(times):.3f} s, median {pick(0.5):.3f} s, p90 {pick(0.9):.3f} s, max {times[-1]:.3f} s"


def profile_report(prof, top=30):
    out = io.StringIO()
    st = pstats.Stats(prof, stream=out)
    st.sort_stats("cumulative").print_stats(top)
    st.sort_stats("tottime").print_stats(top)
    return out.getvalue()


def sample_ids(count, seed=1):
    idx, _ = reel.load_index()
    rows = random.Random(seed).sample(range(len(idx)), count)
    return [idx["id"][r] for r in rows]


def bench_reel(args, cache):
    data_source.KEEP_SPICE_CACHE = True
    shots = reel.shots(args.target.upper())[args.first:args.first + args.count]
    times, kinds = [], []
    prof = cProfile.Profile() if args.profile else None
    for n, s in enumerate(shots):
        start = time.perf_counter()
        stdout, sys.stdout = sys.stdout, quiet()
        try:
            if prof:
                prof.enable()
            _, made = reel.picture(s["ids"], cache)
        finally:
            if prof:
                prof.disable()
            sys.stdout.close()
            sys.stdout = stdout
        took = time.perf_counter() - start
        print(f"{args.first + n:5d} {s['kind']:5s} {len(s['ids'])} frames, stacked {made.get('stacked')}, "
              f"centred {made.get('centred')}: {took:.3f} s", flush=True)
        # the first picture of a year loads that year's kernels
        times.append(took)
        kinds.append(s["kind"])
    print(f"\n{len(times)} pictures: {stats(times)}")
    if len(times) > 1:
        print(f"without the first (kernel load): {stats(times[1:])}")
    for kind in sorted(set(kinds)):
        print(f"  {kind}: {stats([t for t, k in zip(times, kinds) if k == kind])}")
    if prof:
        print(profile_report(prof))


def bench_frames(args, cache):
    ids = sample_ids(args.count)
    for threads in [int(t) for t in args.threads.split(",")]:
        sub = os.path.join(cache, f"t{threads}")
        start = time.perf_counter()
        with ThreadPoolExecutor(threads) as pool:
            sizes = list(pool.map(lambda i: len(frame_server.webp(i, 512, sub)), ids))
        took = time.perf_counter() - start
        print(f"{threads} threads: {len(ids) / took:.1f} frames/s ({took / len(ids) * 1000:.1f} ms each, "
              f"{sum(sizes) / len(sizes) / 1024:.0f} KB)", flush=True)


def bench_composites(args, cache):
    _, sets = reel.load_index()
    idx = reel.load_index()[0]
    picked = random.Random(2).sample([s for s in sets if len(s["use"]) == 3], args.count)
    times = []
    for s in picked:
        ids = [idx["id"][q] for q in s["use"]]
        start = time.perf_counter()
        stdout, sys.stdout = sys.stdout, quiet()
        try:
            _, report = frame_server.color_webp(ids, 512, cache)
        finally:
            sys.stdout.close()
            sys.stdout = stdout
        times.append(time.perf_counter() - start)
        print(f"{','.join(ids)}: {times[-1]:.3f} s, stacked {report.get('stacked')}", flush=True)
    print(f"\n{len(times)} composites: {stats(times)}")


def bench_http(args, cache):
    import http.client
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", args.port), frame_server.make_handler(None, cache))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ids = sample_ids(args.count, seed=3)

    def run(label, reuse):
        lat = []
        lock = threading.Lock()
        queue = list(ids)

        def client():
            conn = None
            while True:
                with lock:
                    if not queue:
                        break
                    frame_id = queue.pop()
                if conn is None or not reuse:
                    conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=60)
                start = time.perf_counter()
                conn.request("GET", f"/frames/{frame_id}.webp?size=512")
                resp = conn.getresponse()
                resp.read()
                if resp.getheader("Connection", "").lower() == "close" or resp.version == 10:
                    conn.close()
                    conn = None
                took = time.perf_counter() - start
                with lock:
                    lat.append(took)

        start = time.perf_counter()
        workers = [threading.Thread(target=client) for _ in range(args.clients)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        wall = time.perf_counter() - start
        print(f"{label}: {len(lat) / wall:.0f} frames/s with {args.clients} viewers, latency {stats(lat)}", flush=True)

    run("uncached", True)
    run("cached, new connection each", False)
    run("cached, connection kept", True)
    server.shutdown()


def make_sample(args):
    """Records every archive file the pictures read and writes them into a small zip."""
    read = set()
    original = data_source.read_bytes

    def recording(path):
        read.add(data_source.relative(path))
        return original(path)

    data_source.read_bytes = recording
    data_source.KEEP_SPICE_CACHE = True
    with tempfile.TemporaryDirectory() as cache:
        for s in reel.shots(args.target.upper())[args.first:args.first + args.count]:
            stdout, sys.stdout = sys.stdout, quiet()
            try:
                reel.picture(s["ids"], cache)
            except Exception as e:
                print(f"failed {s['ids']}: {e}", file=stdout)
            finally:
                sys.stdout.close()
                sys.stdout = stdout
    data_source.read_bytes = original
    keep = sorted(p for p in read if not p.lower().startswith("cosp_1000/"))
    for name in ("wac_data/FORMAT.txt", "nac_data/FORMAT.txt"):
        if data_source.exists(name):
            keep.append(name)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_STORED) as z:
        for path in keep:
            z.writestr("data/" + path, data_source.read_bytes(path))
    print(f"{len(keep)} files, {os.path.getsize(args.out) / 1e6:.1f} MB in {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="what", required=True)
    for name in ("reel", "sample"):
        p = sub.add_parser(name)
        if name == "sample":
            p.add_argument("out")
        p.add_argument("target")
        p.add_argument("--first", type=int, default=0)
        p.add_argument("--count", type=int, default=20)
        p.add_argument("--profile", action="store_true")
    p = sub.add_parser("frames")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--threads", default="1,4")
    p = sub.add_parser("composites")
    p.add_argument("--count", type=int, default=10)
    p = sub.add_parser("http")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--clients", type=int, default=8)
    p.add_argument("--port", type=int, default=8790)
    ap.add_argument("--cache", help="cache folder (default: a new temporary one, deleted after)")
    args = ap.parse_args()
    print(f"Frames from {data_source.get_source()}, kernels from {data_source.get_kernel_source()}", flush=True)
    if args.what == "sample":
        return make_sample(args)
    with tempfile.TemporaryDirectory(dir=args.cache) as cache:
        {"reel": bench_reel, "frames": bench_frames, "composites": bench_composites, "http": bench_http}[args.what](args, cache)


if __name__ == "__main__":
    main()
