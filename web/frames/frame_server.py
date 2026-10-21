#!/usr/bin/env python3
"""
Serves Cassini camera frames to the replay viewer, straight out of the data folder or
data.zip (read through data_source, so nothing has to be unzipped).

  CASSINI_DATA=/Volumes/LaCie/cassiniprojectJAN05.zip python web/frames/frame_server.py
  CASSINI_DATA=... python web/frames/frame_server.py --site ~/Development/cassini-os

Run it from the repo folder so data_source finds the zip index it already built (zip_index/);
copied elsewhere, point CASSINI_REPO at the repo.

Routes:
  /frames/<ID>.webp?size=256   the frame as WebP, longest side 128-1024 px (default 512),
                               made on first request and cached on disk
  /frames/<ID>.png             the archive PNG as it is
  /frames/color.webp?ids=R,G,B&size=512
                               colour composite of two or three frames of one filter set, made on
                               first request and cached like the frames: R,G,B in that order, or
                               two ids (longer wavelength first) for a two-filter composite with
                               green made from both. Made by the pipeline's color path
                               (color_image.load_aligned): repeat exposures stacked, every channel
                               on one brightness scale, aligned to the middle one in time, pixels
                               lost in downlink transparent. The X-Composite header (and a .json
                               next to the cached image) says how each channel was made
  /health                      "ok" plus where the frames come from
  anything else                a file from --site, if given (the replay page and its data)

<ID> is a frame id from the catalog, e.g. N1500060789_2. The camera page picks which frames
make a filter set (web/cassini-os/src/head-quiet.html, findSets). Frames are sent with
Access-Control-Allow-Origin: * so a page hosted elsewhere can show them.
"""
import argparse
import io
import os
import re
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

# data_source lives in the repo root: two folders up from this file, the folder it is run from, or CASSINI_REPO
for repo in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."), os.getcwd(), os.environ.get("CASSINI_REPO", "")):
    if repo and os.path.exists(os.path.join(repo, "data_source.py")):
        sys.path.insert(0, os.path.abspath(repo))
        break
import data_source  # noqa: E402

# for composites: the pipeline's calibration, alignment and label reading. Loaded here, in the main
# thread, with matplotlib (pulled in by label_handler) kept off the screen
os.environ.setdefault("MPLBACKEND", "Agg")
import json  # noqa: E402
import numpy as np  # noqa: E402
import color_image  # noqa: E402

FRAME_ID = re.compile(r"^([NW])\d{10}_\d+$")
SIZES = (128, 256, 384, 512, 768, 1024)
FOLDERS = {"N": "nac_data", "W": "wac_data"}

# data_source keeps one open file per process and seeks in it, so reads take turns. Every read
# from the archive goes through _read_member, composites' labels and line prefixes included.
_read_lock = threading.Lock()
_read_member = data_source._read_member


def _locked_read_member(i):
    with _read_lock:
        return _read_member(i)


data_source._read_member = _locked_read_member
# composites take a second or two of CPU each; at most two at once so frames keep flowing
_color_slots = threading.Semaphore(2)
# requests that take longer than this many seconds are logged
SLOW = float(os.environ.get("FRAME_SERVER_SLOW", "2"))


def archive_png(frame_id):
    return data_source.read_bytes(f"{FOLDERS[frame_id[0]]}/{frame_id}.png")


# one lock per file being made, so a window's request and another's look-ahead for the same picture make it
# once (the second waits and reads the first one's file) instead of both taking a composite slot
_making = {}
_making_lock = threading.Lock()


def cached(path, make):
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    with _making_lock:
        lock = _making.setdefault(path, threading.Lock())
    try:
        with lock:
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    return fh.read()
            return _make_file(path, make)
    finally:
        with _making_lock:
            if _making.get(path) is lock and not lock.locked():
                del _making[path]


def _make_file(path, make):
    data = make()
    # written next to its final name and renamed, so a half written file is never served
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{threading.get_ident()}.part"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, path)
    return data


def encode(im, size):
    if max(im.size) > size:
        im.thumbnail((size, size), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=80, method=4)
    return out.getvalue()


def webp(frame_id, size, cache):
    def make():
        im = Image.open(io.BytesIO(archive_png(frame_id)))
        im = im.convert("L") if im.mode in ("L", "I", "I;16", "P", "1") else im.convert("RGB")
        return encode(im, size)
    return cached(os.path.join(cache, str(size), frame_id + ".webp"), make)


def composite(ids):
    """RGBA composite of the frames ids (R,G,B, or longer and shorter wavelength), 1024 px, made by the
    pipeline's color path (color_image.load_aligned: repeat exposures stacked, calibrated, aligned),
    and a report of how each channel was made."""
    imgs, valid, _, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
    chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
    if len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    report["ids"] = list(ids)
    return Image.fromarray(np.dstack(chans + [alpha]), "RGBA"), report


def color_webp(ids, size, cache):
    """The composite as WebP, and its report (also kept in the cache, next to the image)."""
    # bumped whenever the way composites are made changes, so older ones are not served again
    base = os.path.join(cache, "color-v4", str(size), "_".join(ids))
    report = {}
    def make():
        with _color_slots:
            im, made = composite(ids)
        report.update(made)
        cached(base + ".json", lambda: json.dumps(made).encode())
        print("composite", json.dumps(made))
        return encode(im, size)
    data = cached(base + ".webp", make)
    if not report and os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            report = json.load(fh)
    return data, report


def make_handler(site, cache):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site or os.devnull, **kwargs)

        revalidate = False

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "X-Composite")
            if self.revalidate:
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def do_OPTIONS(self):
            # Chrome asks before a public https page may load from a server on this machine
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()

        def send_bytes(self, data, mime, cache_forever=True, headers=None):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            took = time.monotonic() - self.started
            if took > SLOW:   # a picture this slow keeps a camera window waiting: say so in the log
                print(f"slow {took:.1f} s {self.path}", flush=True)
            if cache_forever:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.started = time.monotonic()
            url = urlparse(self.path)
            if url.path == "/health":
                return self.send_bytes(f"ok {data_source.get_source()}\n".encode(), "text/plain", False)
            if url.path == "/frames/color.webp":
                query = parse_qs(url.query)
                ids = query.get("ids", [""])[0].split(",")
                if not 2 <= len(ids) <= 3 or not all(FRAME_ID.match(i) for i in ids) or len({i[0] for i in ids}) > 1:
                    return self.send_error(400, "ids= takes two or three frame ids from one camera")
                size = min(SIZES, key=lambda s: abs(s - int(query.get("size", ["512"])[0])))
                try:
                    data, report = color_webp(ids, size, cache)
                    return self.send_bytes(data, "image/webp", headers={"X-Composite": json.dumps(report)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
            m = re.match(r"^/frames/([^/]+)\.(webp|png)$", url.path)
            if m:
                frame_id, kind = m.groups()
                if not FRAME_ID.match(frame_id):
                    return self.send_error(400, "Not a frame id")
                try:
                    if kind == "png":
                        return self.send_bytes(archive_png(frame_id), "image/png")
                    size = int(parse_qs(url.query).get("size", ["512"])[0])
                    size = min(SIZES, key=lambda s: abs(s - size))
                    return self.send_bytes(webp(frame_id, size, cache), "image/webp")
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
            if not site:
                return self.send_error(404)
            # pages and their JSON change with every rebuild, so browsers must check before reusing them;
            # frames, textures and track files keep the default heuristic caching
            self.revalidate = url.path.endswith(("/", ".html", ".json"))
            return super().do_GET()

        def log_message(self, fmt, *args):
            if os.environ.get("FRAME_SERVER_QUIET") != "1":
                super().log_message(fmt, *args)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to let other machines on the network in")
    ap.add_argument("--site", help="folder with the replay page to serve at /")
    ap.add_argument("--cache", default=os.path.join(os.getcwd(), "frame_cache"), help="where made WebP files are kept")
    args = ap.parse_args()
    site = os.path.abspath(os.path.expanduser(args.site)) if args.site else None
    print(f"Frames from {data_source.get_source()}, cache in {args.cache}")
    data_source._zip_index() if data_source.using_zip() else None  # build or load the zip index up front
    # the first composite would otherwise wait while stacking reads the whole image index (all ~443k rows)
    threading.Thread(target=color_image.stacking.load_index, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(site, args.cache))
    print(f"Serving on http://{args.host}:{args.port}/" + (f" (site: {site})" if site else ""))
    server.serve_forever()


if __name__ == "__main__":
    main()
