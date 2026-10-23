"""Times a mosaic movie's server work, piece by piece, on this machine: its plan, each tile (with the time spent
reading the archive, data_source._read_at, apart from the rest), and the rolling mosaic each frame asks for
(obs_mosaic.rolling_webp), first made and then from the cache.

    python web/frames/bench_rolling.py N0969...  --cache /Volumes/LaCie/claude_scratch_spk/bench-rolling --tiles 40

Run it with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE). A new
--cache folder times everything cold; the same one again times it warm. Prints one JSON line per step and a
summary.
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obs_mosaic  # noqa: E402
import data_source  # noqa: E402
import color_image  # noqa: E402

_read = threading.local()
_orig_read_at = data_source._read_at


def _timed_read_at(f, size, offset):
    t0 = time.perf_counter()
    try:
        return _orig_read_at(f, size, offset)
    finally:
        _read.s = getattr(_read, "s", 0.0) + time.perf_counter() - t0
        _read.b = getattr(_read, "b", 0) + size


data_source._read_at = _timed_read_at
obs_mosaic.tiles_ahead = lambda *a, **k: None   # nothing made in the background while timing
obs_mosaic.rolling_ahead = lambda *a, **k: None


def reads():
    s, b = getattr(_read, "s", 0.0), getattr(_read, "b", 0)
    _read.s, _read.b = 0.0, 0
    return s, b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obs", default="ISS_C23JU_6ATM2X2B115_PRIME")
    ap.add_argument("--target", default="JUPITER")
    ap.add_argument("--cam", default="N")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--tiles", type=int, default=40, help="how many of the pass's tiles to time")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--profile", action="store_true", help="print where the rolling mosaics' time goes (cProfile)")
    args = ap.parse_args()
    data_source.KEEP_SPICE_CACHE = True
    us = [u for u in obs_mosaic.units(args.target, args.obs, args.cam) if u.get("kind") == "mosaic_movie"] \
        or obs_mosaic.units(args.target, args.obs, args.cam)
    u = max(us, key=lambda v: len(v["frames"]))
    fr = u["frames"]
    print(json.dumps({"pass": list(map(str, u["key"])), "kind": u.get("kind"), "frames": len(fr),
                      "places": len(set(p for p in obs_mosaic.places(u) if p is not None)),
                      "span_s": fr[-1][3] - fr[0][3]}), flush=True)
    reads()
    t0 = time.perf_counter()
    p = obs_mosaic.plan(u, args.cache)
    rs, rb = reads()
    print(json.dumps({"step": "plan", "s": round(time.perf_counter() - t0, 2), "read_s": round(rs, 2), "read_mb": round(rb / 1e6, 1)}), flush=True)
    N = min(args.tiles, len(fr))
    tiles = []
    for n in range(N):
        t0 = time.perf_counter()
        obs_mosaic.tile(u, n, args.cache, p["display_scale"])
        s = time.perf_counter() - t0
        rs, rb = reads()
        tiles.append((s, rs, rb))
        print(json.dumps({"step": "tile", "n": n, "id": fr[n][1], "filter": fr[n][2], "s": round(s, 3),
                          "read_s": round(rs, 3), "read_mb": round(rb / 1e6, 2)}), flush=True)
    rolls, again = [], []
    if args.profile:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    for n in range(N):
        t0 = time.perf_counter()
        made = obs_mosaic.rolling_webp(fr[n][1], args.size, args.cache, wait=True)
        s = time.perf_counter() - t0
        t0 = time.perf_counter()
        obs_mosaic.rolling_webp(fr[n][1], args.size, args.cache, wait=True)
        s2 = time.perf_counter() - t0
        rolls.append(s)
        again.append(s2)
        rep = made[1] if made else {}
        print(json.dumps({"step": "rolling", "n": n, "filter": fr[n][2], "place": obs_mosaic.places(u)[n], "s": round(s, 3),
                          "cached_s": round(s2, 3), "tiles_drawn": rep.get("mosaic"), "places": rep.get("places"),
                          "rolled": [len(v) for v in obs_mosaic._rolled.values()]}), flush=True)
    if args.profile:
        import pstats
        prof.disable()
        pstats.Stats(prof).sort_stats("cumulative").print_stats(40)
        pstats.Stats(prof).sort_stats("tottime").print_stats(20)
    med = lambda xs: round(statistics.median(xs), 3) if xs else None
    print(json.dumps({"summary": {
        "tile_s_median": med([t[0] for t in tiles]), "tile_read_s_median": med([t[1] for t in tiles]),
        "tile_read_mb_median": med([t[2] / 1e6 for t in tiles]),
        "rolling_make_s_median": med(rolls), "rolling_make_s_max": round(max(rolls), 3) if rolls else None,
        "rolling_cached_s_median": med(again)}}), flush=True)


if __name__ == "__main__":
    main()
