"""Makes every picture the camera windows ask for during one observation ahead of time, into a frame server's
cache, so playing it is all cache hits: each frame (frame_server.webp), each pass's plan and tiles, and per pass
what the window shows: a mosaic movie's picture at every frame (obs_mosaic.rolling_webp, every tile in, so the
names match what a window asks for once the pass is made), a mosaic's at every frame (mosaic_webp), a movie's
frames (movie_webp). Uses the server's own makers and cache paths; run it with the server's environment and
its --cache.

    python web/frames/warm_pass.py --cache /Volumes/LaCie/claude_scratch_spk/cache-rate3 \\
        --target JUPITER --obs ISS_C23JU_6ATM2X2B115_PRIME
"""
import argparse
import concurrent.futures
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obs_mosaic  # noqa: E402
import frame_server  # noqa: E402
import data_source  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--target", default="JUPITER")
    ap.add_argument("--obs", default="ISS_C23JU_6ATM2X2B115_PRIME")
    ap.add_argument("--cams", default="NW")
    ap.add_argument("--sizes", default="512,1024", help="window picture sizes")
    ap.add_argument("--frame-sizes", default="128,512,1024", help="plain frame sizes (128: filmstrip)")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    data_source.KEEP_SPICE_CACHE = True
    obs_mosaic.tiles_ahead = lambda *a, **k: None      # everything is made here, in order
    obs_mosaic.rolling_ahead = lambda *a, **k: None
    sizes = [int(s) for s in args.sizes.split(",")]
    fsizes = [int(s) for s in args.frame_sizes.split(",")]
    pool = concurrent.futures.ThreadPoolExecutor(args.workers)
    t00 = time.time()
    for cam in args.cams:
        for u in obs_mosaic.units(args.target, args.obs, cam):
            fr, kind = u["frames"], u.get("kind")
            if not fr:
                continue
            t0 = time.time()
            # every frame of the pass as the catalog has it (repeat exposures too, which the pass leaves out)
            idx, _ = obs_mosaic.reel.load_index()
            t = idx["seconds_1970"].astype(float)
            rows = idx[(idx["OBSERVATION_ID"] == args.obs) & (idx["TARGET_NAME"] == args.target)
                       & (idx["INSTRUMENT_ID"] == ("ISSNA" if cam == "N" else "ISSWA"))
                       & (t >= fr[0][3] - 1) & (t <= u["last"] + 1)]
            list(pool.map(lambda i: [frame_server.webp(i, s, args.cache) for s in fsizes], rows["id"].tolist()))
            p = obs_mosaic.plan(u, args.cache)
            list(pool.map(lambda n: obs_mosaic.tile(u, n, args.cache, p["display_scale"]), range(len(fr))))
            made = 0
            for n, f in enumerate(fr):
                for s in sizes:
                    try:
                        if kind == "mosaic_movie":
                            r = obs_mosaic.rolling_webp(f[1], s, args.cache, 1, wait=True)
                        elif u.get("mosaic"):
                            r = obs_mosaic.mosaic_webp(f[1], s, args.cache, ahead=0)
                        elif kind == "movie" or u.get("movie"):
                            r = obs_mosaic.movie_webp(f[1], s, args.cache, wait=True, ahead=0)
                        else:
                            r = None
                        made += bool(r and r[0])
                    except Exception as e:
                        print(json.dumps({"frame": f[1], "size": s, "failed": f"{type(e).__name__}: {e}"[:200]}), flush=True)
            print(json.dumps({"pass": list(map(str, u["key"])), "kind": kind, "frames": len(fr), "pictures": made,
                              "s": round(time.time() - t0, 1)}), flush=True)
    print(json.dumps({"done_s": round(time.time() - t00, 1)}), flush=True)


if __name__ == "__main__":
    main()
