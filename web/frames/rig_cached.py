#!/usr/bin/env python3
"""
Cloud rig for timing cached playback: the real frame_server.py and obs_mosaic.py (every route, cache path, pass plan,
tile, layout and background thread), the real image index (Image_index.csv) and geometry cache (CASSINI_GEOMETRY_CACHE,
a copy of the Mini's geometry.sqlite), with only the archive swapped for synthetic frames: color_image.load_aligned,
color_image.processed_frame, stacking.load_hdr and the archive PNGs make a lit disk with the frame's id written on
it, placed where the geometry cache puts the body. So passes are judged, planned and tiled as on the Mini; a picture
just takes milliseconds to make instead of seconds, and once made it is served from the cache exactly as on the Mini.

  CASSINI_GEOMETRY_CACHE=geometry.sqlite python web/frames/rig_cached.py --site web/cassini-os --cache /tmp/rigcache --port 8812
  RIG_DELAY=0.2   seconds each frame takes to make (a slower, more Mini-like cold server)
  RIG_PROFILE=1   profile every thread with yappi; GET /rig/profile answers the top functions (and resets them)
  GET /rig/counts the files the server looked for (stat) and opened in its cache, and the threads it started, since
                  the last /rig/counts (every thread's, a request's and the background work it started)
"""
import argparse
import builtins
import collections
import hashlib
import io
import json
import os
import sys
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("MPLBACKEND", "Agg")
import frame_server as fs  # noqa: E402

color_image, obs_mosaic, stacking = fs.color_image, fs.obs_mosaic, fs.color_image.stacking
DELAY = float(os.environ.get("RIG_DELAY", "0"))
N = 1024
try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except OSError:
    FONT = ImageFont.load_default()
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)


def fid_of(path):
    return os.path.basename(path).split(".")[0]


def where(fid):
    g = fs.reel.geometry([fid]).get(fid)
    return g if g and g[2] else (0.0, 0.0, None)


def frame(fid):
    """A frame of fid: a lit disk where the geometry cache puts the body (x, y: full resolution pixels of the
    centring shift), bands that differ by frame, the id written in a corner; float 0-1."""
    x, y, z = where(fid)
    h = int(hashlib.md5(fid.encode()).hexdigest()[:6], 16)
    cx, cy, r = N / 2 - x, N / 2 - y, N * 0.36
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / r ** 2
    light = np.clip(((xx - cx) * -0.5 + (yy - cy) * -0.4) / r + np.sqrt(np.clip(1 - d2, 0, 1)) * 0.8, 0, 1)
    band = np.sin((yy - cy) / N * (6 + h % 5)) * 0.5 + 0.5
    v = np.where(d2 < 1, light * (0.6 + 0.4 * band), 0.01 + 0.004 * ((h + xx.astype(np.int32) * 7 + yy.astype(np.int32) * 13) % 5))
    im = Image.fromarray(np.clip(v * 235, 0, 255).astype(np.uint8))
    ImageDraw.Draw(im).text((24, N - 64), fid, fill=200, font=FONT)
    return np.asarray(im, np.float32) / 255


def load_hdr(path, repeat_window=None, *a, **k):
    time.sleep(DELAY)
    return None, frame(fid_of(path)) * 0.05, None


def load_aligned(paths, hdr=False, scale=None, repeat_window=120):
    time.sleep(DELAY * len(paths))
    imgs = [(frame(fid_of(p)) * 255).astype(np.uint8) for p in paths]
    return imgs, np.ones((N, N), bool), None, {"calibrated": True, "stacked": [1] * len(paths),
                                                "aligned": ["reference"] + ["aligned"] * (len(paths) - 1), "rig": True}


def processed_frame(paths, max_offset=600, hdr=False, scale=None, repeat_window=120):
    """As color_image.processed_frame: the frame north up in the middle of a canvas of its diagonal (RGBA), and
    frame_offset = where the frame's middle sits from the body's centre (the geometry cache's shift, turned)."""
    imgs, valid, _, report = load_aligned(paths, hdr, scale, repeat_window)
    side = 2 * obs_mosaic.HALF
    canvas = np.zeros((side, side, 4), np.uint8)
    o = (side - N) // 2
    g = imgs[0]
    canvas[o:o + N, o:o + N, 0] = canvas[o:o + N, o:o + N, 1] = canvas[o:o + N, o:o + N, 2] = g
    canvas[o:o + N, o:o + N, 3] = 255
    x, y, z = where(fid_of(paths[0]))
    if z is None:
        report.update(centred=False, why="SPICE has no place for the frame (rig)")
        return canvas, None, report
    report.update(frame_offset=[round(-float(x), 1), round(-float(y), 1)], offset_px=round(float(np.hypot(x, y)), 1), centred=True)
    return canvas, None, report


def archive_png(fid):
    time.sleep(DELAY)
    b = io.BytesIO()
    Image.fromarray((frame(fid) * 255).astype(np.uint8)).save(b, "PNG", compress_level=1)
    return b.getvalue()


color_image.load_aligned = load_aligned
color_image.processed_frame = processed_frame
stacking.load_hdr = load_hdr
fs.archive_png = archive_png

# what the server does with its cache: stats (os.path.exists/isfile, os.stat) and opens of files in it, by the
# kind of file, and the threads it starts
COUNTS, _count_lock, CACHE = collections.Counter(), threading.Lock(), [None]
_stat, _open, _start = os.stat, builtins.open, threading.Thread.start


def _kind(path):
    p = str(path)
    if not CACHE[0] or not p.startswith(CACHE[0]):
        return None
    base = os.path.basename(p)
    return ("tile.json" if "/tiles-" in p and base.endswith(".json") else "tile.png" if "/tiles-" in p else
            "plan" if base.startswith(("plan", "movie_footprint")) else
            "picture.json" if base.endswith(".json") else "picture" if base.endswith((".webp", ".png")) else "other")


def _counted_stat(path, *a, **k):
    kind = _kind(path) if isinstance(path, (str, bytes, os.PathLike)) else None
    if kind:
        with _count_lock:
            COUNTS["stat " + kind] += 1
    return _stat(path, *a, **k)


def _counted_open(file, mode="r", *a, **k):
    kind = _kind(file) if isinstance(file, (str, os.PathLike)) and "r" in mode else None
    if kind:
        with _count_lock:
            COUNTS["open " + kind] += 1
    return _open(file, mode, *a, **k)


def _counted_start(self):
    with _count_lock:
        COUNTS["threads"] += 1
    return _start(self)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8812)
    ap.add_argument("--site", required=True)
    ap.add_argument("--cache", required=True)
    args = ap.parse_args()
    fs.reel.load_index()
    fs.reel.target_of()
    CACHE[0] = os.path.abspath(args.cache)
    os.stat, builtins.open, threading.Thread.start = _counted_stat, _counted_open, _counted_start
    profiling = os.environ.get("RIG_PROFILE") == "1"
    handler = fs.make_handler(os.path.abspath(args.site), CACHE[0], os.path.join(CACHE[0], "flags"))
    base_get = handler.get

    def counts(self):
        if self.path.startswith("/rig/counts"):
            self.started = time.monotonic()
            with _count_lock:
                out = dict(COUNTS)
                COUNTS.clear()
            return self.send_bytes(json.dumps(out).encode(), "application/json", False)
        return base_get(self)
    handler.get = counts
    if profiling:
        import yappi
        yappi.set_clock_type("wall")
        yappi.start(builtins=False, profile_threads=True)
        base_get = handler.get   # (counts, above)

        def get(self):
            if self.path.startswith("/rig/profile"):
                self.started = time.monotonic()
                stats = yappi.get_func_stats()
                stats.sort("tsub" if "self" in self.path else "ttot")
                out = io.StringIO()
                stats.print_all(out=out, columns={0: ("name", 60), 1: ("ncall", 10), 2: ("tsub", 9), 3: ("ttot", 9), 4: ("tavg", 9)})
                yappi.clear_stats()
                return self.send_bytes(out.getvalue().encode()[:400000], "text/plain", False)
            return base_get(self)
        handler.get = get
    srv = fs.Server(("127.0.0.1", args.port), handler)
    print(f"rig serving on {args.port}, cache {args.cache}, geometry {os.environ.get('CASSINI_GEOMETRY_CACHE')}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
