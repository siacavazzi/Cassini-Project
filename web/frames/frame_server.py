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
  /health                      "ok" plus where the frames come from
  anything else                a file from --site, if given (the replay page and its data)

<ID> is a frame id from the catalog, e.g. N1500060789_2. Frames are sent with
Access-Control-Allow-Origin: * so a page hosted elsewhere can show them.
"""
import argparse
import io
import os
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

# data_source lives in the repo root: two folders up from this file, the folder it is run from, or CASSINI_REPO
for repo in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."), os.getcwd(), os.environ.get("CASSINI_REPO", "")):
    if repo and os.path.exists(os.path.join(repo, "data_source.py")):
        sys.path.insert(0, os.path.abspath(repo))
        break
import data_source  # noqa: E402

FRAME_ID = re.compile(r"^([NW])\d{10}_\d+$")
SIZES = (128, 256, 384, 512, 768, 1024)
FOLDERS = {"N": "nac_data", "W": "wac_data"}

# data_source keeps one open file per process and seeks in it, so reads take turns
_read_lock = threading.Lock()


def archive_png(frame_id):
    with _read_lock:
        return data_source.read_bytes(f"{FOLDERS[frame_id[0]]}/{frame_id}.png")


def webp(frame_id, size, cache):
    path = os.path.join(cache, str(size), frame_id + ".webp")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    im = Image.open(io.BytesIO(archive_png(frame_id)))
    im = im.convert("L") if im.mode in ("L", "I", "I;16", "P", "1") else im.convert("RGB")
    if max(im.size) > size:
        im.thumbnail((size, size), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=80, method=4)
    data = out.getvalue()
    # written next to its final name and renamed, so a half written file is never served
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{threading.get_ident()}.part"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, path)
    return data


def make_handler(site, cache):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site or os.devnull, **kwargs)

        revalidate = False

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            if self.revalidate:
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def do_OPTIONS(self):
            # Chrome asks before a public https page may load from a server on this machine
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()

        def send_bytes(self, data, mime, cache_forever=True):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            if cache_forever:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self.send_bytes(f"ok {data_source.get_source()}\n".encode(), "text/plain", False)
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
    server = ThreadingHTTPServer((args.host, args.port), make_handler(site, args.cache))
    print(f"Serving on http://{args.host}:{args.port}/" + (f" (site: {site})" if site else ""))
    server.serve_forever()


if __name__ == "__main__":
    main()
