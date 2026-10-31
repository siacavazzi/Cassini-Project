"""Times a mosaic's first view on this machine, step by step, as the frame server makes it: the picture a camera
window asks for (obs_mosaic.mosaic_webp, its tiles made ahead left out), then the tile maps the server works out
behind it (_map_later, here in the foreground), then the same layout again. For each step: the tile reports read from
the cache, the plan, the surface check (the kernels loaded, tile pictures read, sky fields, tiles kept as taken), the
panels, the picture, the tile maps worked out and written.

    python web/frames/bench_first_view.py --cache /Volumes/cassini-v47/cache N1500060003_2 N1500061579_1
    python web/frames/bench_first_view.py --cache /Volumes/cassini-v47/cache --pick 6 --year 2005

--pick: that many mosaic passes of --year whose plan is in the cache and whose tile maps are not (no window has shown
them yet; --any: shown or not), half of them clouded (Saturn, Titan: no surface check), each at its last frame. --code:
the frame code to time (a worktree's web/frames, for the code a server runs); this one's by default. Run it with the
frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE, CASSINI_SPICE_CACHE). It reads what
the cache holds and writes only what a first view writes (tile maps, surface pictures). Prints one JSON line a frame.
"""
import argparse
import calendar
import collections
import json
import os
import random
import sys
import threading
import time

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("frames", nargs="*", help="frame ids (a frame of each pass, the first view at it)")
ap.add_argument("--cache", required=True)
ap.add_argument("--code", default=os.path.dirname(os.path.abspath(__file__)))
ap.add_argument("--size", type=int, default=512)
ap.add_argument("--pick", type=int, default=0)
ap.add_argument("--year", type=int, default=2005)
ap.add_argument("--any", action="store_true", help="--pick among every built pass, shown before or not")
args = ap.parse_args()
sys.path.insert(0, os.path.abspath(os.path.expanduser(args.code)))
import frame_server  # noqa: E402  (puts the repo on the path, loads the pipeline)
import calibration  # noqa: E402
import obs_mosaic  # noqa: E402
import reel  # noqa: E402
import label_handler  # noqa: E402
import reproject  # noqa: E402
from PIL import Image  # noqa: E402

took, count = collections.defaultdict(float), collections.Counter()
_stack = threading.local()


def timed(mod, name, label):
    fn = getattr(mod, name)

    def wrap(*a, **k):
        stack = _stack.__dict__.setdefault("s", [])
        stack.append(label)
        t0 = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            took[label] += time.perf_counter() - t0
            count[label] += 1
            stack.pop()
    setattr(mod, name, wrap)


def inside(label):
    return label in _stack.__dict__.get("s", [])


timed(obs_mosaic, "_made_through", "made_through")
timed(obs_mosaic, "plan", "plan")
timed(obs_mosaic, "_tile_made", "tile_reports")
if hasattr(obs_mosaic, "_kept_reports"):
    timed(obs_mosaic, "_kept_reports", "reports_file")
timed(obs_mosaic, "layout", "layout")
timed(obs_mosaic, "surface_pictures", "surface")
timed(obs_mosaic, "_ets", "surface_geometry_db")
timed(obs_mosaic, "panel_places", "panels")
timed(obs_mosaic, "_mosaic_at", "picture")
timed(obs_mosaic, "tile_map", "tile_maps")
timed(reproject, "sky_view", "surface_sky_view")
timed(reproject, "sky_field", "surface_sky_field")
timed(reproject, "warp_sky", "surface_warp")

_with_kernels = obs_mosaic._with_kernels


def with_kernels(t):
    was = getattr(label_handler, "cur_year", None)
    t0 = time.perf_counter()
    try:
        return _with_kernels(t)
    finally:
        took["surface_kernels"] += time.perf_counter() - t0
        count["surface_kernels"] += 1
        if getattr(label_handler, "cur_year", None) != was:
            count["surface_kernel_loads"] += 1


obs_mosaic._with_kernels = with_kernels
_open = Image.open


def image_open(*a, **k):
    t0 = time.perf_counter()
    try:
        im = _open(*a, **k)
        im.load()
        return im
    finally:
        where = "surface" if inside("surface") else "panels" if inside("panels") else "picture" if inside("picture") else "other"
        took[f"{where}_tile_pictures_read"] += time.perf_counter() - t0
        count[f"{where}_tile_pictures_read"] += 1


Image.open = image_open
obs_mosaic.Image.open = image_open
_cached = reel._cached


def cached(path, make):
    there = os.path.exists(path)
    out = _cached(path, make)
    if not there and os.sep + obs_mosaic.MAPS_DIR + os.sep in path:
        count["tile_maps_written"] += 1
    return out


reel._cached = cached
_print = print


def quiet_print(*a, **k):
    if a and str(a[0]).startswith("surface: tile ") and "kept as taken" in str(a[0]):
        count["surface_kept_as_taken"] += 1
        return
    _print(*a, **k)


obs_mosaic.print = quiet_print
obs_mosaic.tiles_ahead = lambda *a, **k: None   # the tiles made ahead: timed on their own below
later = []
obs_mosaic._map_later = lambda u, n, cache: later.append((u, n))


def step():
    out = {k: round(v, 3) for k, v in sorted(took.items())}
    out.update({f"{k}_n": v for k, v in sorted(count.items())})
    took.clear()
    count.clear()
    return out


def picked(n, year):
    idx, _ = reel.load_index()
    t = idx["seconds_1970"].astype(float)
    rows = idx[(t >= calendar.timegm((year, 1, 1, 0, 0, 0))) & (t < calendar.timegm((year + 1, 1, 1, 0, 0, 0)))]
    keys = dict.fromkeys((r.TARGET_NAME, r.OBSERVATION_ID, "N" if r.INSTRUMENT_ID == "ISSNA" else "W")
                         for r in rows[["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"]].itertuples(index=False)
                         if isinstance(r.OBSERVATION_ID, str))
    passes = [u for key in keys for u in obs_mosaic.units(*key) if u["frames"] and u["mosaic"]
              and u.get("kind") == "mosaic" and time.gmtime(u["frames"][0][3]).tm_year == year]
    cold = [u for u in passes if os.path.exists(os.path.join(obs_mosaic.folder(u, args.cache), obs_mosaic.PLAN_FILE))
            and (args.any or not os.path.isdir(os.path.join(obs_mosaic.folder(u, args.cache), obs_mosaic.MAPS_DIR)))]
    random.seed(1)
    clouded = [u for u in cold if obs_mosaic.clouded(u)]
    clear = [u for u in cold if not obs_mosaic.clouded(u)]
    k = min(len(clear), n - n // 2)
    out = random.sample(clear, k) + random.sample(clouded, min(len(clouded), n - k))
    print(json.dumps({"passes": len(passes), "never_shown": len(cold), "clear": len(clear), "clouded": len(clouded)}), flush=True)
    return [u["frames"][-1][1] for u in out]


def main():
    frame_server.data_source.KEEP_SPICE_CACHE = True   # (as the frame server runs)
    t0 = time.perf_counter()
    reel.target_of(), obs_mosaic._observations(), obs_mosaic._row_of()   # (the server makes these at its start)
    print(json.dumps({"start_s": round(time.perf_counter() - t0, 1), "kernels_year": getattr(label_handler, "cur_year", None)}), flush=True)
    frames = args.frames + (picked(args.pick, args.year) if args.pick else [])
    with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
        for fid in frames:
            found = obs_mosaic.unit_of(fid)
            if not found or not found[0]["mosaic"]:
                print(json.dumps({"frame": fid, "error": "not in a mosaic pass"}), flush=True)
                continue
            u, n = found
            row = {"frame": fid, "pass": "_".join(map(str, u["key"])), "tiles": len(u["frames"]), "n": n,
                   "clouded": obs_mosaic.clouded(u), "kernels_year_before": getattr(label_handler, "cur_year", None)}
            step()
            later.clear()
            t0 = time.perf_counter()
            made = obs_mosaic.mosaic_webp(fid, args.size, args.cache, ahead=0)
            row["view_s"] = round(time.perf_counter() - t0, 3)
            row["view"] = step()
            row["picture"] = bool(made)
            # the tile maps the server works out behind the picture (_map_later: the layout at each tile up to n)
            t0 = time.perf_counter()
            for v, m in later:
                for j in range(m + 1):
                    obs_mosaic.tile_map(v["frames"][j][1], args.cache)
            row["maps_s"] = round(time.perf_counter() - t0, 3)
            row["maps"] = step()
            # a later request for the same mosaic (the next frame's, a hover): its layout again
            t0 = time.perf_counter()
            obs_mosaic.layout(u, n, args.cache)
            row["layout_again_s"] = round(time.perf_counter() - t0, 3)
            row["layout_again"] = step()
            # the tiles made ahead (tiles_ahead: every tile of the pass, found made): the rest of the reports read
            t0 = time.perf_counter()
            for j in range(len(u["frames"])):
                obs_mosaic.tile(u, j, args.cache)
            row["ahead_s"] = round(time.perf_counter() - t0, 3)
            row["ahead"] = step()
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
