#!/usr/bin/env python3
"""
Serves Cassini camera frames to the replay viewer, straight out of the data folder or
data.zip (read through data_source, so nothing has to be unzipped).

  CASSINI_DATA=/Volumes/LaCie/cassiniprojectJAN05.zip python web/frames/frame_server.py
  CASSINI_DATA=... python web/frames/frame_server.py --site ~/Development/cassini-os

Run it from the repo folder so data_source finds the zip index it already built (zip_index/);
copied elsewhere, point CASSINI_REPO at the repo.

CASSINI_GEOMETRY_CACHE=<file>.sqlite lets body reels centre frames from cached SPICE answers
instead of loading a year of kernels (seconds from a USB disk) whenever the year changes; fill
it once with `python bootleg_autonav.py geometry` (see bootleg_autonav.py).

Routes:
  /frames/<ID>.webp?size=256   the frame as WebP, longest side 128-1024 px (default 512),
                               made on first request and cached on disk
  ...?size=full                any picture route below at full resolution, for a picture looked at on its own
                               (full view): a frame or composite at its native size, losslessly for frames;
                               a pass's mosaic at its canvas size; never more than CASSINI_FULL_MAX px
                               (default 2048) on the longest side. Live feeds, bursts, reels and movies keep
                               the capped sizes. &format=png sends PNG instead, &download=1 as a named
                               attachment (Cassini_<ID>.png), so the picture can be saved and shared
  /frames/<ID>.png             the archive PNG as it is
  /frames/<ID>.png?download=1  the archive PNG as a named attachment (Cassini_<ID>_archive.png)
  /frames/color.webp?ids=R,G,B&size=512
                               colour composite of two or three frames of one filter set, made on
                               first request and cached like the frames: R,G,B in that order, or
                               two ids (longer wavelength first) for a two-filter composite with
                               green made from both. Made by the pipeline's color path
                               (color_image.load_aligned): repeat exposures stacked, every channel
                               on one brightness scale, aligned to the middle one in time, pixels
                               lost in downlink transparent. The X-Composite header (and a .json
                               next to the cached image) says how each channel was made
  ...&channel=0|1|2            one channel of that composite (0 red, 1 green, 2 blue), black and white, cut
                               from the same composite so it keeps the composite's shared brightness scale and
                               alignment: what a composite's channel looks like opened on its own (drill-down)
  ...&center=1                 Auto center (a camera window's setting): the picture centred on the body, north up,
                               by SPICE (color_image.processed_frame), at the frame's own scale (one frame square
                               round the body); whether to centre is decided once for the pass (obs_mosaic.centre_view,
                               the rule of a movie centred on its body).
                               A close-up pass (frames on a body too big for the view) is turned north up where it
                               is, so the surface holds still. 404 with X-Center {"centre": false, "why"} for a ring,
                               spoke or sky pass (Cassini kept those upright in the camera, the steady view) or a
                               frame SPICE has no place for, and the window shows the picture as it is. Also on
                               /frames/processed below
  /frames/processed/<ID>.webp?size=512
                               the frame alone made like a composite's channel (color_image.load_aligned with
                               one frame: repeat exposures stacked, lost pixels transparent, calibrated to I/F
                               and put on the pipeline's display scale, its own), for movie mode; cached like the
                               composites, X-Composite as theirs. size=full, format=png and download=1 as above
  /reel/bodies.json            every body with frames, most photographed first
  /reel/<TARGET>.json          the body's reel: its pictures in time order (web/frames/reel.py)
  /frames/reel/<TARGET>/<n>.webp?size=768&mosaic=1
                               picture n of the reel, made by the pipeline (color_image.processed_frame:
                               stacked, calibrated, aligned, centred on the body with north up by SPICE)
                               and drawn into the rolling mosaic with the pictures before it; made on
                               first request and cached. X-Reel says how it was made
  /frames/mosaic/<ID>.json     where each frame sits in that mosaic (obs_mosaic.tile_map): its pointings, each with
                               its frames by filter and its outline and centre as fractions of the picture
  /frames/mosaic/<ID>/frame.webp?ids=A,B,C&size=full   one frame of that mosaic on its own, on the mosaic's levels
                               and colours (obs_mosaic.pointing_picture; format=png, download=1 as below)
  /frames/mosaic/<ID>/full.json      that mosaic at native resolution (mosaic_native): its size, estimated MB, made yet
                               (&make=jpg|png: make it now); full.webp?crop=x0,y0,x1,y1 a part of it for the zoom lens
                               (fractions of the picture, at most CASSINI_NATIVE_CROP px); full.jpg / full.png all of it
                               (download=1), at most CASSINI_NATIVE_MAX px, kept in CASSINI_FULLRES_CACHE (not the cache)
  /frames/mosaic/<ID>.webp?size=512   (&warm=1: only start making the pass ahead of time, empty answer;
                               &tune=n:dx:dy,...&hide=n,...: the person's changes to its tiles from Cassini Studio,
                               pointings as /frames/mosaic/<ID>.json numbers them, moves as fractions of the picture)
                               the mosaic frame <ID> is a new tile of, made like a reel picture: 404 when
                               the frame is not a mosaic tile (mosaic.panels: same camera, observation and
                               filter, the pointing stepped across the body, panels overlap)
                               When the frame is in a mosaic pass (obs_mosaic: one camera and observation,
                               three or more pointings), instead the pass's mosaic so far, every tile and
                               filter, in false colour when it cycles three or more; asking for a frame of the
                               pass starts making its tiles. A movie pass (obs_mosaic: the camera creeps or
                               stares) is never a mosaic; warm=1 answers {"mosaic", "movie"} for the observation;
                               force=1 makes the pass's mosaic whatever obs_mosaic calls it (Mosaic switch)
  /frames/movie/<ID>.webp?size=512&trail=0&color=1&center=1
                               the frame played as a movie of its pass (obs_mosaic.movie_webp): the pass's tile
                               (processed_frame, centred north up by SPICE) on the pass's one display scale, drawn
                               where SPICE puts it in one view for the whole pass; color=1 draws the newest frames
                               of the pass's color filters together, trail=N the N earlier frames of its filter
                               fading under it; center=1 (the default) the body in the middle of every frame, when
                               its disk fits the view. 503 while the pass is being worked out (the window shows the frame)
  /frames/movie/<ID>.webp?mode=rolling&laps=1
                               a mosaic movie (a raster repeated over the same places): every place's newest tile
                               by this frame (laps=N: its N newest copies, older under newer), composed like the
                               pass's mosaic (obs_mosaic.rolling_webp), so it never empties when a lap begins
  /frames/movie/<ID>.json      the pass the frame is in: its frames [id, time, filter], cadence, movie/mosaic call
  /frames/thumb.webp?mosaic=<ID>&color=R,G,B&frame=<ID>&size=256
                               a highlight's thumbnail (any of the three, as data/highlights.json's "thumb" gives them):
                               the pass's mosaic when it has three or more tiles (in three or more filters when a
                               colour set is given too), else the colour composite, else the frame, each from its
                               route's maker above. The answer is kept under thumb-v1/, named by the hint and the
                               makers' versions, so a version bump makes it again; the server makes every highlight's
                               thumbnail as it starts, so the Highlights window finds them made. X-Thumb says which
  /export/plan.json?from=2006-09-15T14:32&until=2006-09-15T17:12&cams=NW&fps=auto&size=1024
                               a movie export's plan (web/frames/export.py): its pictures, when each shows in the
                               film, the film's length and size; nothing is made
  POST /export?...             (same options, plus sound=1 caption=1) starts making that film, or finds it made
                               or on its way; one film is made at a time. Answers the job's status, as
  /export/<JOB>.json           does: state queued/making/sound/done/failed, pictures done of total, seconds left
  PUT /export/<JOB>/sound.wav  the page's soundtrack for the film (made by the live sound's synth), added as AAC
  /export/<JOB>.mp4            the film (Range requests work, so it plays as it downloads); ?download=1 saves it
  POST /prebuild?from=2006-09-15T14:32:00&until=2006-09-15T17:12:00&cams=NW&sizes=512,1024&look=...
                               makes every picture the camera windows ask for in that stretch of the timeline ahead
                               of time (web/frames/prebuild.py segment_items: frames, composites, mosaic and movie
                               passes, with the page's look and movie style: mosaics, steady, color, trail, laps,
                               center), so it plays as a movie at any frame rate from the cache; one stretch at a
                               time, behind the server's own requests. Answers the job's status, as
  /prebuild/<JOB>.json         does: state queued/planning/making/waiting/finishing/done/failed/stopped, pictures done of
                               total, made through (UTC), seconds left
  POST /prebuild/<JOB>/stop    stops it (what is made stays made)
  /health                      "ok" plus where the frames come from
  POST /flags                  a picture flagged in Cassini OS (the ⚑ button or R in a picture window): JSON with
                               the picture as shown (a data: URL), what the window showed and an optional note.
                               Saved under --flags (default ~/Documents/flagged-pictures) as <name>/shown.png,
                               <name>/raw/<ID>.png (each frame's archive PNG) and <name>/flag.json, with one line
                               per flag in index.jsonl; answers {"name", "count"}
  POST /flags/<name>/undo      takes a flag back: its folder moves to undone/ and its index line goes
  /flags/                      every flag on one page, newest first, each with a link to its moment
  /flags/index.json            the flags as a list, newest first ({"count", "flags"})
  /flags/<name>/<file>         a flag's files
  anything else                a file from --site, if given (the replay page and its data)

<ID> is a frame id from the catalog, e.g. N1500060789_2. The camera page picks which frames
make a filter set (web/cassini-os/src/head-quiet.html, findSets). Frames are sent with
Access-Control-Allow-Origin: * so a page hosted elsewhere can show them.
"""
import argparse
import base64
import datetime
import email.utils
import html
import gzip
import hashlib
import io
import os
import re
import shutil
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
import contextvars  # noqa: E402
import json  # noqa: E402
import numpy as np  # noqa: E402
import calibration  # noqa: E402
import color_image  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402
import obs_mosaic  # noqa: E402
import mosaic_native  # noqa: E402
import export  # noqa: E402

FRAME_ID = re.compile(r"^([NW])\d{10}_\d+$")
SIZES = (128, 256, 384, 512, 768, 1024)
# size=full: the picture at full resolution, capped so a whole-pass mosaic cannot run away with the bandwidth
FULL = "full"
FULL_MAX = int(os.environ.get("CASSINI_FULL_MAX", "2048"))
# the sizes the camera windows ask for (head-quiet.html size()): true resolution, or full in full view
WINDOW_SIZES = (1024, FULL)
FOLDERS = {"N": "nac_data", "W": "wac_data"}

# composites take a second or two of CPU each; at most two at once so frames keep flowing
_color_slots = threading.Semaphore(2)
# the camera windows' and movie mode's mosaics take seconds each the first time and are often asked for ahead of
# need; their own slots, so they never keep a colour composite waiting
_mosaic_slots = threading.Semaphore(2)
# movie mode's processed frames: a frame takes a fraction of a second, and a movie asks for many ahead of
# the play head, so they get their own slots and never hold up the camera windows' composites
_movie_slots = threading.Semaphore(int(os.environ.get("FRAME_SERVER_MOVIE_SLOTS", 4)))
# requests that take longer than this many seconds are logged
SLOW = float(os.environ.get("FRAME_SERVER_SLOW", "2"))


def archive_png(frame_id):
    return data_source.read_bytes(f"{FOLDERS[frame_id[0]]}/{frame_id}.png")


# one lock per file being made, so a window's request and another's look-ahead for the same picture make it
# once (the second waits and reads the first one's file) instead of both taking a composite slot
_making = {}
_making_lock = threading.Lock()


def cached(path, make):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        pass
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
    part = f"{path}.{threading.get_ident()}.part"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(part, "wb") as fh:
            fh.write(data)
        os.replace(part, path)
    except OSError as e:
        # a full disk (or a cache folder that cannot be written) costs the cache, never the picture
        keep_failed(path, part, e)
    return data


_keep_failed = [0.0]


def keep_failed(path, part, e):
    """A made file could not be kept: the half written part goes, and the log says so (once a minute)."""
    try:
        os.remove(part)
    except OSError:
        pass
    if time.monotonic() - _keep_failed[0] > 60:
        _keep_failed[0] = time.monotonic()
        print(f"cannot keep {path} in the cache ({e}); sending it anyway", flush=True)


def size_of(query, default):
    """The size= asked for: FULL, or the nearest of SIZES."""
    asked = query.get("size", [str(default)])[0]
    if asked == FULL:
        return FULL
    try:
        return min(SIZES, key=lambda s: abs(s - int(asked)))
    except ValueError:
        return default


def encode(im, size, fmt="webp", quality=80):
    """im as WebP (or PNG), longest side at most size; a FULL picture keeps its size up to FULL_MAX, and a
    grey one is sent losslessly (an 8-bit frame is a few hundred KB that way)"""
    cap = FULL_MAX if size == FULL else size
    if max(im.size) > cap:
        im.thumbnail((cap, cap), Image.LANCZOS)
    out = io.BytesIO()
    if fmt == "png":
        im.save(out, "PNG", compress_level=6)
    elif size == FULL and im.mode == "L":
        im.save(out, "WEBP", lossless=True, quality=80, method=4)
    else:
        im.save(out, "WEBP", quality=94 if size == FULL else quality, method=4)
    return out.getvalue()


def picture_format(query):
    return "png" if query.get("format", [""])[0] == "png" else "webp"


def size_dir(size, fmt):
    return str(size) + ("-png" if fmt == "png" else "")


# plain frames at quality 95: at 80 WebP drops the faintest stars and specks of sparse frames (lit PSNR 29-30 dB on
# star fields), 90 keeps most of them (38+) and 95 is hard to tell from lossless (43+; Sam saw 90 vs 95), for 21 KB a
# 1024 px frame (p90 47 KB; 2.2 MB/s at the reel's worst, 24 fps from both cameras). The folder is named after the
# quality, so frames made at another quality are not served again
FRAME_QUALITY = 95
FRAME_VERSION = "frames-q95"


def webp(frame_id, size, cache, fmt="webp"):
    def make():
        im = Image.open(io.BytesIO(archive_png(frame_id)))
        im = im.convert("L") if im.mode in ("L", "I", "I;16", "P", "1") else im.convert("RGB")
        return encode(im, size, fmt, FRAME_QUALITY)
    return cached(os.path.join(cache, FRAME_VERSION, size_dir(size, fmt), f"{frame_id}.{fmt}"), make)


# the caches of the pictures drawn from I/F, one per display model (calibration.style), so the classic look keeps the
# pictures made before the balanced display model and raw colors the balanced ones made before natural color
COLOR_VERSIONS = {"balanced": "color-v28", "raw": "color-v11", "classic": "color-v5"}
PROC_VERSIONS = {"balanced": "proc-v8", "raw": "proc-v8", "classic": "proc-v2"}   # one frame: no colors to mix
# Auto center (center=1): the same pictures centred on the body by SPICE, cached beside them in folders of their own
CENTRE_VERSION = "ctr4"   # ctr2: the shift stops at the frame's data edge; ctr3: only when the body's disk is cut by it;
                          # ctr4: a close-up pass is turned north up where it is


def in_background(target, *args):
    """Runs target(*args) on a thread of its own, in the request's look and colors."""
    threading.Thread(target=contextvars.copy_context().run, args=(target, *args), daemon=True).start()


def composite(ids, channel=None, centre=None):
    """RGBA composite of the frames ids (R,G,B, or longer and shorter wavelength), 1024 px, made by the
    pipeline's color path (color_image.load_aligned: repeat exposures stacked, calibrated, aligned),
    and a report of how each channel was made. One id makes the frame alone, black and white (LA);
    channel=0|1|2 the composite's red, green or blue alone, black and white on the composite's scale (LA).
    centre: Auto center's view for the pass (obs_mosaic.centre_view), when the picture is centred on the body."""
    if channel is not None:
        im, report = _recent_composite(ids, centre)
        bands = im.split()
        return Image.merge("LA", (bands[channel], bands[-1])), dict(report, channel=channel)
    if centre:
        return centred(ids, centre)
    imgs, valid, _, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
    chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    report["ids"] = list(ids)
    if len(chans) == 1:
        return Image.fromarray(np.dstack([chans[0], alpha]), "LA"), report
    if len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    return Image.fromarray(np.dstack(chans + [alpha]), "RGBA"), report


def disk_in_frame(alpha, cx, cy, r):
    """True when the body's disk (centre cx, cy, radius r canvas pixels) lies on the frame's data: its centre and
    the four ends of its axes are inside the frame (alpha, the frame's coverage on the canvas)."""
    if not r or r <= 0:
        return False
    h, w = alpha.shape
    for x, y in ((cx, cy), (cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)):
        i, j = int(round(y)), int(round(x))
        if not (0 <= i < h and 0 <= j < w and alpha[i, j]):
            return False
    return True


def centred(ids, view):
    """The composite of ids (or one frame) centred on the body, north up: the pipeline's color path and SPICE
    placement (color_image.processed_frame: load_aligned as composite, then auto_center), cut to the square of
    view["side"] full resolution pixels round the body's centre (obs_mosaic.centre_view: one frame, the frame's own
    scale). RGBA (LA for one frame) and the report; LookupError when SPICE cannot place it."""
    image, _, report = color_image.processed_frame([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
    if "frame_offset" not in report:
        raise LookupError(report.get("why", "not placed by SPICE"))
    # processed_frame puts the frame's middle at the canvas middle; the body's centre is frame_offset from it
    h, w = image.shape[:2]
    side = int(view["side"])
    cx = (w - 1) / 2 - report["frame_offset"][0]
    cy = (h - 1) / 2 - report["frame_offset"][1]
    if not view.get("centre"):
        # north up only (a pass Auto center does not centre): the view stays on the frame's middle
        cx, cy = (w - 1) / 2, (h - 1) / 2
    left, top = round(cx - side / 2), round(cy - side / 2)
    # a body whose whole disk is in the frame goes to the middle, the sky round it black where the frame ends; a
    # body the frame cuts (caught at its edge, or bigger than it) is moved only as far as the frame's data goes,
    # so the view never takes in black beyond the frame's edge on a side where the frame could fill it and half the
    # picture does not go black (where the frame is narrower than the view, the view sits on the frame's middle)
    rows, cols = np.flatnonzero(image[..., 3].any(1)), np.flatnonzero(image[..., 3].any(0))
    if len(rows) and not disk_in_frame(image[..., 3], cx, cy, view.get("radius", 0)):
        def fit(start, lo, hi):
            return min(max(start, lo), hi - side) if hi - lo >= side else round((lo + hi) / 2 - side / 2)
        wanted = (left, top)
        left, top = fit(left, cols[0], cols[-1] + 1), fit(top, rows[0], rows[-1] + 1)
        report["centre_shift_capped"] = [int(left - wanted[0]), int(top - wanted[1])]
    out = np.zeros((side, side, 4), np.uint8)
    x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + side, w), min(top + side, h)
    if x0 < x1 and y0 < y1:
        out[y0 - top:y1 - top, x0 - left:x1 - left] = image[y0:y1, x0:x1]
    report = dict(report, ids=list(ids), centred_view={"side": side, "pass": view.get("pass"),
                                                          "centre": bool(view.get("centre"))})
    if len(ids) == 1:
        return Image.fromarray(np.ascontiguousarray(out[..., [0, 3]]), "LA"), report
    return Image.fromarray(out, "RGBA"), report


# the last few composites made, so a window opening each of a set's channels in turn runs load_aligned once
_recent, _recent_lock, RECENT = {}, threading.Lock(), 4


def _recent_composite(ids, centre=None):
    key = (calibration.style(), tuple(ids), centre and centre["side"])
    with _recent_lock:
        hit = _recent.pop(key, None)
        if hit:
            _recent[key] = hit
            return hit
    made = composite(ids, centre=centre)
    with _recent_lock:
        _recent[key] = made
        while len(_recent) > RECENT:
            _recent.pop(next(iter(_recent)))
    return made


def centre_folder(folder, centre):
    """The cache folder of the pictures in folder, centred by Auto center on a view of centre["side"] px."""
    return f"{folder}-{CENTRE_VERSION}-s{int(centre['side'])}" if centre else folder


def color_webp(ids, size, cache, fmt="webp", channel=None, centre=None):
    """The composite (or one of its channels) as WebP (or PNG), and its report (also kept in the cache, next to
    the image). centre: centred on the body (composite)."""
    # bumped whenever the way composites are made changes, so older ones are not served again
    folder = centre_folder(os.path.join(cache, COLOR_VERSIONS[calibration.style()]), centre)
    base = os.path.join(folder, size_dir(size, fmt), "_".join(ids) + ("" if channel is None else f"_c{channel}"))
    report = {}
    def make():
        with _color_slots:
            im, made = composite(ids, channel, centre) if channel is not None else _recent_composite(ids, centre)
        report.update(made)
        cached(base + ".json", lambda: json.dumps(made).encode())
        reel.keep_report(base + ".json", made)
        print("composite", json.dumps(made))
        # the camera windows' other sizes are encoded now too (a few tens of ms each), so a window that grows or
        # goes to full view gets the composite at once instead of making it again
        for other in WINDOW_SIZES if channel is None else ():   # a channel is asked for at the size it is shown
            if other != size:
                path = os.path.join(folder, size_dir(other, "webp"), "_".join(ids))
                if not os.path.exists(path + ".webp"):
                    _make_file(path + ".webp", lambda: encode(im, other))
                    if not os.path.exists(path + ".json"):
                        _make_file(path + ".json", lambda: json.dumps(made).encode())
        return encode(im, size, fmt)
    data = cached(f"{base}.{fmt}", make)
    if not report:
        report = reel.report_of(base + ".json", {})
    return data, report


def processed_webp(frame_id, size, cache, fmt="webp", centre=None):
    """One frame made like a composite's channel (composite with one id: repeat exposures stacked, lost pixels
    filled, calibrated to I/F and put on the pipeline's display scale), for movie mode; and its report. Cached
    like the composites. centre: centred on the body (composite)."""
    base = os.path.join(centre_folder(os.path.join(cache, PROC_VERSIONS[calibration.style()]), centre), size_dir(size, fmt), frame_id)
    report = {}
    def make():
        with _movie_slots:
            im, made = composite([frame_id], centre=centre)
        report.update(made)
        cached(base + ".json", lambda: json.dumps(made).encode())
        reel.keep_report(base + ".json", made)
        return encode(im, size, fmt)
    data = cached(f"{base}.{fmt}", make)
    if not report:
        report = reel.report_of(base + ".json", {})
    return data, report


# ---------- highlight thumbnails: one small picture per highlight, picked by the page's old rule and kept ----------
THUMB_VERSION = "thumb-v1"
THUMB_SIZE = 256


def thumb_hint(query):
    """The thumbnail hint in a /frames/thumb.webp query ({"mosaic", "color", "frame"}, as highlights.json has it);
    ValueError when an id is not a frame id."""
    hint = {}
    for k in ("mosaic", "frame"):
        v = query.get(k, [""])[0]
        if v:
            if not FRAME_ID.match(v):
                raise ValueError(f"{k}= takes a frame id")
            hint[k] = v
    ids = [i for i in query.get("color", [""])[0].split(",") if i]
    if ids:
        if not 2 <= len(ids) <= 3 or not all(FRAME_ID.match(i) for i in ids) or len({i[0] for i in ids}) > 1:
            raise ValueError("color= takes two or three frame ids from one camera")
        hint["color"] = ids
    return hint


def _count(v):
    try:
        return len(v) if isinstance(v, (list, tuple)) else int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _thumb_mosaic(frame_id, size, cache):
    """(WebP, report) of the mosaic the camera windows' route answers for frame_id, or None; nothing made ahead"""
    reel.target_of()   # the mosaic route's index, so the answer never depends on how long the server has been up
    made = obs_mosaic.mosaic_webp(frame_id, size, cache, _mosaic_slots, ahead=0)
    if made:
        return made
    # a movie plays as frames: no rolling mosaic either, as on the mosaic route
    found = obs_mosaic.unit_of(frame_id)
    if found and found[0]["movie"]:
        return None
    found = reel.mosaic_of(frame_id)
    return reel.shot_webp(*found, size, cache, True, _mosaic_slots) if found else None


def pick_thumb(hint, size, cache):
    """(WebP, what) of a highlight's thumbnail: the pass's mosaic when it has three or more tiles (and three or more
    filters when there is a colour set), else the colour set, else the frame; None when none can be made."""
    if hint.get("mosaic"):
        try:
            made = _thumb_mosaic(hint["mosaic"], size, cache)
        except (FileNotFoundError, LookupError):
            made = None
        if made:
            how = made[1]
            tiles = max(_count(how.get("of")), _count(how.get("mosaic")), _count(how.get("tiles")))
            if tiles >= 3 and (_count(how.get("filters")) >= 3 or not hint.get("color")):
                return made[0], {"picked": "mosaic", "id": hint["mosaic"], "tiles": tiles}
    if hint.get("color"):
        try:
            return color_webp(hint["color"], size, cache)[0], {"picked": "color", "ids": hint["color"]}
        except FileNotFoundError:
            pass
    if hint.get("frame"):
        try:
            return webp(hint["frame"], size, cache), {"picked": "frame", "id": hint["frame"]}
        except FileNotFoundError:
            pass
    return None


def thumb_versions():
    """the versions of the makers a thumbnail may come from: a bump of any of them makes the thumbnails again"""
    style = calibration.style()   # the request's look and colors (look=, colors=), as the page asks for them
    return [style, obs_mosaic.VERSIONS[style], reel.VERSIONS[style], COLOR_VERSIONS[style], FRAME_VERSION]


def thumb_key(hint, size):
    """the thumbnail's name in the cache: what it may be made of and the versions of the makers it comes from"""
    what = json.dumps([hint, size, thumb_versions()], sort_keys=True)
    return hashlib.sha1(what.encode()).hexdigest()[:20]


def thumb_webp(hint, size, cache):
    """(WebP, what) of the thumbnail, made once and kept under THUMB_VERSION; FileNotFoundError when none of its
    pictures can be made"""
    base = os.path.join(cache, THUMB_VERSION, thumb_key(hint, size))
    what = {}

    def make():
        made = pick_thumb(hint, size, cache)
        if not made:
            raise FileNotFoundError("no picture for this thumbnail")
        what.update(made[1])
        cached(base + ".json", lambda: json.dumps(made[1]).encode())
        return made[0]
    data = cached(base + ".webp", make)
    if not what and os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            what = json.load(fh)
    return data, what


def warm_thumbs(site, cache):
    """Makes every highlight's thumbnail (site/data/highlights.json) that is not in the cache yet, one at a time, so
    the Highlights window finds them made; after a maker's version bump this is where they are made again. In the
    default look; the others are made when a page asks for them."""
    try:
        with open(os.path.join(site, "data", "highlights.json")) as fh:
            hints = [e["thumb"] for e in json.load(fh) if e.get("kind") != "milestone" and e.get("thumb")]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return
    started, made, failed = time.monotonic(), 0, 0
    for hint in hints:
        hint = {k: hint[k] for k in ("mosaic", "color", "frame") if hint.get(k)}
        if os.path.exists(os.path.join(cache, THUMB_VERSION, thumb_key(hint, THUMB_SIZE) + ".webp")):
            continue
        try:
            thumb_webp(hint, THUMB_SIZE, cache)
            made += 1
        except Exception as e:   # one thumbnail that cannot be made must not stop the others
            failed += 1
            print(f"highlight thumbnail {hint}: {e}", flush=True)
    print(f"highlight thumbnails: {len(hints)} ({made} made, {failed} failed) in {time.monotonic() - started:.0f} s", flush=True)


# ---------- slow loads: the page reports a wait for data on the loading screen, kept to find out what held it ----------
# POST /jumplog takes the page's report (what loaded, each data file's timings, the picture requests under way, the
# page's long tasks); the server adds when, who and how busy it was, and appends it to <cache>/jump-log.jsonl.
# GET /jumplog answers the last 50 reports.
JUMPLOG_MAX = 256 * 1024
_jumplog_lock = threading.Lock()


def save_jumplog(cache, report, client):
    entry = {"server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "client": client,
             "server_threads": threading.active_count(), **report}
    os.makedirs(cache, exist_ok=True)
    with _jumplog_lock, open(os.path.join(cache, "jump-log.jsonl"), "a") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"slow load {report.get('seconds', '?')} s ({report.get('what', '')}) from {client}", flush=True)


def jumplog(cache, n=50):
    try:
        with open(os.path.join(cache, "jump-log.jsonl")) as fh:
            return [json.loads(line) for line in fh.readlines()[-n:]]
    except FileNotFoundError:
        return []


# ---------- flagged pictures: pictures that look wrong, kept with what was shown so they can be looked into later ----------
FLAG_NAME = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]+)?_[A-Za-z0-9_]+$")
FLAG_FILE = re.compile(r"^(shown\.(png|webp|jpg)|flag\.json|raw/[NW][0-9]{10}_[0-9]+\.png)$")
FLAG_MAX = 40 * 1024 * 1024   # a request bigger than this is refused (a 1024 px PNG is 1-2 MB)
_flag_lock = threading.Lock()
FLAGS_README = """Pictures flagged in Cassini OS (the flag button or R in a picture window).

index.jsonl   one line per flag, oldest first: the flag.json below plus "name" (its folder)
<name>/shown.png       the picture exactly as the window showed it (composite, mosaic, movie or reel picture)
<name>/raw/<ID>.png    the archive PNG of each frame in it, before any processing
<name>/flag.json       when it was flagged, the mission time and a link to that moment, the window and how it was
                       showing the picture (frame, colour composite, mosaic; the server's X-Composite / X-Reel
                       report), each frame's camera, filters, target and observation, the note and tags, and the
                       viewer's settings
undone/       flags taken back with Undo (moved here, not deleted)

Made by web/frames/frame_server.py; the page /flags/ on the frame server shows them all.
"""


def flag_entries(folder):
    try:
        with open(os.path.join(folder, "index.jsonl")) as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def save_flag(folder, flag):
    """Writes a flag (the JSON the page sent) into folder: its own folder with the picture as shown, the archive
    PNG of each frame and flag.json, and a line in index.jsonl. Returns the flag's name and how many there are."""
    image = flag.pop("image", None) or ""
    ids = [i for i in flag.get("ids") or [] if isinstance(i, str) and FRAME_ID.match(i)][:24]
    flag["ids"] = ids
    flag["received"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if isinstance(flag.get("note"), str):
        flag["note"] = flag["note"][:4000]
    label = re.sub(r"[^A-Za-z0-9_]", "", ids[0] if ids else str((flag.get("window") or {}).get("id", "picture")))[:40] or "picture"
    os.makedirs(folder, exist_ok=True)
    with _flag_lock:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        name, n = f"{stamp}_{label}", 1
        while os.path.exists(os.path.join(folder, name)):
            n += 1
            name = f"{stamp}-{n}_{label}"
        path = os.path.join(folder, name)
        os.makedirs(os.path.join(path, "raw"))
    files = []
    m = re.match(r"^data:image/(png|webp|jpeg);base64,(.+)$", image, re.S)
    if m:
        ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
        with open(os.path.join(path, f"shown.{ext}"), "wb") as fh:
            fh.write(base64.b64decode(m.group(2)))
        files.append(f"shown.{ext}")
    for i in ids:
        try:
            data = archive_png(i)
        except (FileNotFoundError, KeyError):
            continue
        with open(os.path.join(path, "raw", f"{i}.png"), "wb") as fh:
            fh.write(data)
        files.append(f"raw/{i}.png")
    flag["files"] = files
    with open(os.path.join(path, "flag.json"), "w") as fh:
        json.dump(flag, fh, indent=1)
    with _flag_lock:
        if not os.path.exists(os.path.join(folder, "README.txt")):
            with open(os.path.join(folder, "README.txt"), "w") as fh:
                fh.write(FLAGS_README)
        with open(os.path.join(folder, "index.jsonl"), "a") as fh:
            fh.write(json.dumps({"name": name, **flag}, separators=(",", ":")) + "\n")
        count = len(flag_entries(folder))
    print(f"flagged {name}: {flag.get('note') or ''}", flush=True)
    return name, count


def undo_flag(folder, name):
    """Takes a flag back: its folder moves to undone/ (nothing is deleted) and its line leaves index.jsonl."""
    with _flag_lock:
        if not os.path.isdir(os.path.join(folder, name)):
            return None
        os.makedirs(os.path.join(folder, "undone"), exist_ok=True)
        shutil.move(os.path.join(folder, name), os.path.join(folder, "undone", name))
        keep = [e for e in flag_entries(folder) if e.get("name") != name]
        part = os.path.join(folder, f"index.jsonl.{threading.get_ident()}.part")
        with open(part, "w") as fh:
            fh.writelines(json.dumps(e, separators=(",", ":")) + "\n" for e in keep)
        os.replace(part, os.path.join(folder, "index.jsonl"))
        return len(keep)


def flags_page(folder):
    """Every flag on one page, newest first: the picture as shown, when and what it was, the note."""
    esc = lambda v: html.escape(str(v if v is not None else ""))
    cards = []
    for e in reversed(flag_entries(folder)):
        name, shown = e.get("name", ""), next((f for f in e.get("files", []) if f.startswith("shown.")), None)
        win, what = e.get("window") or {}, e.get("shown") or {}
        frames = e.get("frames") or []
        detail = " · ".join(filter(None, [f.get("id", "") + (f" {f.get('filters')}" if f.get("filters") else "") for f in frames[:6]]))
        tags = "".join(f"<span class=tag>{esc(t)}</span>" for t in e.get("tags") or [])
        cards.append(f"""<figure>
  <a href="{esc(name)}/{esc(shown or 'flag.json')}">{f'<img loading=lazy src="{esc(name)}/{esc(shown)}" alt="">' if shown else '<div class=none>no picture</div>'}</a>
  <figcaption><b>{esc(e.get('mission_utc', ''))}</b> {esc(win.get('title', ''))}{' · ' + esc(what.get('what')) if what.get('what') else ''}
  <div class=ids>{esc(detail)}</div>{tags}{f'<p>{esc(e.get("note"))}</p>' if e.get('note') else ''}
  <div class=links><a href="{esc(e.get('link') or '#')}">open this moment</a> · <a href="{esc(name)}/flag.json">details</a>{''.join(f' · <a href="{esc(name)}/{esc(f)}">{esc(f.split("/")[-1])}</a>' for f in e.get('files', []) if f.startswith('raw/'))}
  <div class=when>flagged {esc(e.get('received', ''))}</div></div></figcaption>
</figure>""")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Flagged pictures</title><style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; padding: 16px; background: #0b0d11; color: #dfe4ea; font: 13px/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; }}
h1 {{ font-size: 15px; font-weight: 600; margin: 0 0 4px; }} .sub {{ color: #8a94a3; margin: 0 0 16px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }}
figure {{ margin: 0; background: #14171d; border: 1px solid #262b34; border-radius: 6px; overflow: hidden; }}
figure img, .none {{ display: block; width: 100%; aspect-ratio: 1; object-fit: contain; background: #000; }} .none {{ display: grid; place-items: center; color: #555; }}
figcaption {{ padding: 8px 10px 10px; }} figcaption p {{ margin: 6px 0 0; white-space: pre-wrap; }}
.ids, .when {{ font: 11px/1.4 ui-monospace, Menlo, monospace; color: #8a94a3; word-break: break-all; }}
.tag {{ display: inline-block; margin: 5px 4px 0 0; padding: 1px 7px; border-radius: 9px; background: rgba(138,182,255,.16); color: #b9d0ff; font-size: 11px; }}
.links {{ margin-top: 6px; font-size: 11.5px; }} a {{ color: #8ab6ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
</style></head><body><h1>Flagged pictures</h1><p class=sub>{len(cards)} flagged · saved in {esc(folder)} · <a href="index.json">index.json</a></p>
<main>{''.join(cards) or '<p>Nothing flagged yet. In Cassini OS, press the flag in a picture window&#39;s title bar, or R.</p>'}</main></body></html>"""


# site files sent gzipped to browsers that take it: a year of replay data is ~18 MB, its catalog JSON
# shrinks ~7x and the track and pointing files ~25%. Each file is compressed once and kept in memory
# (until it changes) up to GZIP_KEEP bytes of compressed data
GZIP_TYPES = (".json", ".bin", ".html", ".js", ".css", ".txt", ".svg", ".csv")
GZIP_KEEP = 256 * 1024 * 1024
_gzipped = {}
_gzip_lock = threading.Lock()


def gzipped(path, st):
    key = (path, st.st_mtime_ns, st.st_size)
    with _gzip_lock:
        data = _gzipped.get(key)
    if data is None:
        with open(path, "rb") as fh:
            data = gzip.compress(fh.read(), 6, mtime=0)
        with _gzip_lock:
            for old in [k for k in _gzipped if k[0] == path]:
                del _gzipped[old]
            while _gzipped and sum(map(len, _gzipped.values())) + len(data) > GZIP_KEEP:
                del _gzipped[next(iter(_gzipped))]
            _gzipped[key] = data
    return data


# picture requests being answered now (GET /frames/..., /reel/...), by when each came in: a stretch being made ahead
# gives way to the fresh ones (prebuild.Segments). One that has taken longer than LIVE_FRESH s (a pass's mosaic being
# built) no longer counts, so a slow mosaic never holds the stretch up.
_live = {}
_live_lock = threading.Lock()
LIVE_FRESH = 1.5


def live_requests():
    now = time.monotonic()
    with _live_lock:
        return sum(now - t < LIVE_FRESH for t in _live.values())


class Server(ThreadingHTTPServer):
    # the default backlog of 5 resets connections when several viewers open theirs at once
    # (a browser opens six per page); the OS caps it at its own limit anyway
    request_queue_size = 128
    daemon_threads = True


def make_handler(site, cache, flags=None):
    segments = []   # the stretches made ahead (prebuild.Segments), started on the first POST /prebuild

    def prebuilds():
        if not segments:
            # prebuild imports this module by name: the running server's own makers and caches, not a second copy
            sys.modules.setdefault("frame_server", sys.modules[__name__])
            import prebuild
            segments.append(prebuild.Segments(cache, live=live_requests))
        return segments[0]

    class Handler(SimpleHTTPRequestHandler):
        # keep-alive: a viewer loads frames one after another, and a new connection for each
        # costs a round trip (more through a tunnel); every reply says its Content-Length
        protocol_version = "HTTP/1.1"
        # headers and body go out as separate writes; without this the body waits ~40 ms for
        # the browser's delayed ACK on a kept-alive connection
        disable_nagle_algorithm = True

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site or os.devnull, **kwargs)

        revalidate = False

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "X-Composite, X-Reel, X-Movie, X-Center, X-Thumb")
            if self.revalidate:
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def do_OPTIONS(self):
            # Chrome asks before a public https page may load from a server on this machine
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

        def send_json(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def pictures(self):
            # the film's pictures come from the same makers (and cache) as the camera windows'
            return export.Pictures(cache, color=color_webp, processed=globals().get("processed_webp"), frame=webp, slots=_color_slots)

        def send_picture(self, data, fmt, query, name, headers=None, forever=True):
            """A picture route's answer: WebP or PNG, as a named attachment when download=1 asks for one. forever:
            the browser may keep it for good (the address's picture never changes); False for a stand-in (a
            mosaic of the tiles made so far), which must be asked for again."""
            headers = dict(headers or {})
            if query.get("download", ["0"])[0] == "1":
                headers["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
            if not forever:
                headers["Cache-Control"] = "no-store"
            return self.send_bytes(data, "image/png" if fmt == "png" else "image/webp", forever, headers)

        def send_file(self, path, mime, query, name, headers=None, forever=True):
            """A picture kept in a file, sent a megabyte at a time (a native mosaic can be hundreds of MB)."""
            size = os.path.getsize(path)
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            if query.get("download", ["0"])[0] == "1":
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if forever else "no-store")
            self.end_headers()
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        def centre_of(self, query, frame_id):
            """center=1 (Auto center in a camera window): the pass's view (obs_mosaic.centre_view: centred on the body,
            or north up where it is for a close-up), or None for the picture as it is. False for a ring, spoke or
            sky pass or a frame SPICE has no place for: the answer (404, X-Center says why) is sent, so the window
            shows the picture as it is for the whole pass."""
            if query.get("center", ["0"])[0] != "1" or reel._index is None:
                return None
            try:
                view = obs_mosaic.centre_view(frame_id)
            except Exception as e:
                view = {"centre": False, "why": f"{type(e).__name__}: {e}"[:200]}
            if view.get("centre") or view.get("north"):
                return view
            self.not_centred(view)
            return False

        def not_centred(self, view):
            body = json.dumps(view).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Center", json.dumps(view))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.started = time.monotonic()
            self.revalidate = False
            url = urlparse(self.path)
            if url.path == "/export":
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    return self.send_json(export.submit(export.options(parse_qs(url.query)), cache, self.pictures()))
                except (ValueError, LookupError) as e:
                    return self.send_json({"error": str(e)}, 400)
                except OverflowError as e:
                    return self.send_json({"error": str(e)}, 413)
            if url.path == "/prebuild" or re.match(r"^/prebuild/[0-9a-f]{16}/stop$", url.path):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if reel._index is None and url.path == "/prebuild":
                    return self.send_json({"error": "no index of the frames"}, 404)
                if url.path != "/prebuild":
                    job = prebuilds().stop(url.path.split("/")[2])
                    return self.send_json(job) if job else self.send_json({"error": "no such stretch"}, 404)
                import prebuild
                try:
                    return self.send_json(prebuilds().submit(prebuild.segment_options(parse_qs(url.query))))
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
            n = int(self.headers.get("Content-Length") or 0)
            if url.path == "/jumplog":
                if not 0 < n <= JUMPLOG_MAX:
                    self.close_connection = True
                    return self.send_error(413, "Too big")
                try:
                    report = json.loads(self.rfile.read(n))
                    assert isinstance(report, dict)
                except (ValueError, AssertionError):
                    return self.send_error(400, "Not a report")
                save_jumplog(cache, report, self.client_address[0])
                return self.send_json({"ok": True})
            if not flags or not (url.path == "/flags" or re.match(r"^/flags/[^/]+/undo$", url.path)):
                self.rfile.read(n) if 0 < n <= FLAG_MAX else None
                return self.send_error(404)
            if n > FLAG_MAX:
                self.close_connection = True
                return self.send_error(413, "Too big")
            body = self.rfile.read(n)
            if url.path == "/flags":
                try:
                    flag = json.loads(body)
                    assert isinstance(flag, dict)
                except (ValueError, AssertionError):
                    return self.send_error(400, "Not a flag")
                name, count = save_flag(flags, flag)
                return self.send_bytes(json.dumps({"name": name, "count": count}).encode(), "application/json", False)
            name = url.path.split("/")[2]
            count = undo_flag(flags, name) if FLAG_NAME.match(name) else None
            if count is None:
                return self.send_error(404, "No such flag")
            return self.send_bytes(json.dumps({"name": name, "count": count}).encode(), "application/json", False)

        def do_PUT(self):
            self.started = time.monotonic()
            self.revalidate = False
            m = re.match(r"^/export/([0-9a-f]{16})/sound\.wav$", urlparse(self.path).path)
            length = int(self.headers.get("Content-Length") or 0)
            if not m or not 0 < length <= 400 * 1024 * 1024:
                return self.send_error(400, "PUT /export/<job>/sound.wav with a WAV body")
            try:
                export.sound(cache, m.group(1), self.rfile.read(length))
                return self.send_json({"ok": True})
            except LookupError as e:
                return self.send_json({"error": str(e)}, 404)

        def send_film(self, path, job, download):
            """The film, whole or the byte range asked for (players ask for ranges to start before the end arrives)."""
            size = os.path.getsize(path)
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start, end = int(m.group(1)), min(size - 1, int(m.group(2) or size - 1))
                else:
                    start = max(0, size - int(m.group(2)))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            name = (job or {}).get("name", "cassini.mp4")
            self.send_header("Content-Disposition", f'{"attachment" if download else "inline"}; filename="{name}"')
            self.end_headers()
            with open(path, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def do_GET(self):
            # look=classic: pictures drawn from I/F the way they were before the balanced display model;
            # colors=raw: each filter drawn straight as a channel, without natural color (calibration.colors)
            query = parse_qs(urlparse(self.path).query)
            picture, me = self.path.startswith(("/frames/", "/reel/")), object()
            if picture:
                with _live_lock:
                    _live[me] = time.monotonic()
            try:
                with calibration.looking(query.get("look", [calibration.LOOKS[0]])[0]), \
                        calibration.coloring(query.get("colors", [calibration.COLORS[0]])[0]):
                    return self.get()
            finally:
                if picture:
                    with _live_lock:
                        _live.pop(me, None)

        def get(self):
            self.started = time.monotonic()
            url = urlparse(self.path)
            # a kept-alive connection reuses this handler, so the last request's choice must not stick
            self.revalidate = False
            if url.path == "/export/plan.json":
                try:
                    return self.send_json(export.public_plan(export.plan(export.options(parse_qs(url.query)))))
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
                except OverflowError as e:
                    return self.send_json({"error": str(e)}, 413)
            m = re.match(r"^/export/([0-9a-f]{16})\.(json|mp4)$", url.path)
            if m:
                job = export.status(cache, m.group(1))
                if m.group(2) == "json":
                    return self.send_json(job) if job else self.send_json({"error": "no such export"}, 404)
                path = export.film_path(cache, m.group(1))
                if not path:
                    return self.send_error(404, "That film is not made (yet)")
                return self.send_film(path, job, parse_qs(url.query).get("download", ["0"])[0] != "0")
            m = re.match(r"^/prebuild/([0-9a-f]{16})\.json$", url.path)
            if m:
                job = prebuilds().status(m.group(1)) if segments else None
                return self.send_json(job) if job else self.send_json({"error": "no such stretch"}, 404)
            if flags and (url.path == "/flags" or url.path.startswith("/flags/")):
                return self.send_flags(url.path)
            if url.path == "/jumplog":
                return self.send_json(jumplog(cache))
            if url.path == "/health":
                return self.send_bytes(f"ok {data_source.get_source()}\n".encode(), "text/plain", False)
            if url.path == "/frames/color.webp":
                query = parse_qs(url.query)
                ids = query.get("ids", [""])[0].split(",")
                if not 2 <= len(ids) <= 3 or not all(FRAME_ID.match(i) for i in ids) or len({i[0] for i in ids}) > 1:
                    return self.send_error(400, "ids= takes two or three frame ids from one camera")
                size, fmt = size_of(query, 512), picture_format(query)
                channel = query.get("channel", [""])[0]
                if channel and channel not in ("0", "1", "2"):
                    return self.send_error(400, "channel= takes 0, 1 or 2")
                channel = int(channel) if channel else None
                # a channel is named after its frame (a two-filter composite's green, made from both, after the set)
                if channel is None:
                    name = f"Cassini_{'_'.join(ids)}_color"
                elif len(ids) == 2 and channel == 1:
                    name = f"Cassini_{'_'.join(ids)}_green"
                else:
                    name = f"Cassini_{ids[channel if len(ids) == 3 else channel // 2]}_in_color"
                centre = self.centre_of(query, ids[-1])
                if centre is False:
                    return
                try:
                    data, report = color_webp(ids, size, cache, fmt, channel, centre)
                    return self.send_picture(data, fmt, query, name, {"X-Composite": json.dumps(report)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
                except LookupError as e:
                    return self.not_centred({"centre": False, "frame": True, "why": str(e)[:200]})
            if url.path == "/frames/thumb.webp":
                query = parse_qs(url.query)
                try:
                    hint = thumb_hint(query)
                except ValueError as e:
                    return self.send_error(400, str(e))
                if not hint:
                    return self.send_error(400, "mosaic=, color= or frame= is needed")
                size = size_of(query, THUMB_SIZE)
                if size == FULL:
                    return self.send_error(400, "a thumbnail is small: size= up to 1024")
                # the page asks without a version and a version bump changes the picture, so the browser keeps it a
                # day, not a year, and then checks (a 304 is a few bytes)
                tag = f'"{thumb_key(hint, size)}"'
                if self.headers.get("If-None-Match") == tag:
                    self.send_response(304)
                    self.send_header("ETag", tag)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                try:
                    data, what = thumb_webp(hint, size, cache)
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
                return self.send_bytes(data, "image/webp", False,
                                       {"ETag": tag, "Cache-Control": "public, max-age=86400", "X-Thumb": json.dumps(what)})
            m = re.match(r"^/frames/processed/([^/]+)\.webp$", url.path)
            if m:
                if not FRAME_ID.match(m.group(1)):
                    return self.send_error(400, "Not a frame id")
                query = parse_qs(url.query)
                size, fmt = size_of(query, 512), picture_format(query)
                centre = self.centre_of(query, m.group(1))
                if centre is False:
                    return
                try:
                    data, report = processed_webp(m.group(1), size, cache, fmt, centre)
                    return self.send_picture(data, fmt, query, f"Cassini_{m.group(1)}_processed", {"X-Composite": json.dumps(report)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
                except LookupError as e:
                    return self.not_centred({"centre": False, "frame": True, "why": str(e)[:200]})
            if url.path == "/reel/bodies.json":
                return self.send_bytes(json.dumps(reel.bodies()).encode(), "application/json", False)
            m = re.match(r"^/reel/([A-Z0-9_]+)\.json$", url.path)
            if m:
                shots = reel.shots(m.group(1))
                if not shots:
                    return self.send_error(404, "No pictures of that body")
                return self.send_bytes(json.dumps({"target": m.group(1), "shots": shots}).encode(), "application/json", False)
            m = re.match(r"^/frames/reel/([A-Z0-9_]+)/(\d+)\.webp$", url.path)
            if m:
                query = parse_qs(url.query)
                shots, n = reel.shots(m.group(1)), int(m.group(2))
                if n >= len(shots):
                    return self.send_error(404, "No such picture")
                size = min(SIZES, key=lambda s: abs(s - int(query.get("size", ["768"])[0])))
                try:
                    data, report = reel.shot_webp(m.group(1), n, size, cache, query.get("mosaic", ["1"])[0] != "0", _color_slots)
                    return self.send_bytes(data, "image/webp", headers={"X-Reel": json.dumps(report, default=str)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
            m = re.match(r"^/frames/mosaic/([^/]+)\.json$", url.path)
            if m:
                # where each frame sits in the mosaic shown for that frame (obs_mosaic.tile_map), for hover and
                # click-to-open in the camera windows; 404 when the frame is not in a mosaic pass
                if not FRAME_ID.match(m.group(1)):
                    return self.send_error(400, "Not a frame id")
                found = obs_mosaic.tile_map(m.group(1), cache) if reel._index is not None else None
                return self.send_json(found) if found else self.send_json({"error": "not a mosaic pass"}, 404)
            m = re.match(r"^/frames/mosaic/([^/]+)/frame\.webp$", url.path)
            if m:
                # one frame of that mosaic on its own at full resolution, with the mosaic's levels and colours
                # (obs_mosaic.pointing_picture): ids = its frames, one per filter as the tile map gives them
                # (&channel=0-2: one filter's channel of it)
                query = parse_qs(url.query)
                ids = [i for i in query.get("ids", [""])[0].split(",") if i]
                if not FRAME_ID.match(m.group(1)) or not ids or len(ids) > 3 or not all(FRAME_ID.match(i) for i in ids):
                    return self.send_error(400, "Not frame ids")
                size, fmt, ch = size_of(query, FULL), picture_format(query), query.get("channel", [None])[0]
                if ch is not None and ch not in ("0", "1", "2"):
                    return self.send_error(400, "channel is 0, 1 or 2")
                made = obs_mosaic.pointing_picture(m.group(1), ids, cache, size, fmt, _mosaic_slots, None if ch is None else int(ch)) \
                    if reel._index is not None else None
                if not made:
                    return self.send_error(404, "Not frames of that mosaic")
                return self.send_picture(made[0], fmt, query, f"Cassini_{'_'.join(ids)}_in_mosaic" + ("" if ch is None else f"_channel{ch}"), {"X-Reel": json.dumps(made[1])})
            m = re.match(r"^/frames/mosaic/([^/]+)/full\.(json|webp|jpg|png)$", url.path)
            if m:
                # the mosaic shown for that frame at native resolution (mosaic_native): .json its size, estimates and
                # whether it is made (make=jpg|png starts making it, for the save menu); .webp?crop=x0,y0,x1,y1 a part
                # of it (fractions of the picture) for the zoom lens; .jpg / .png all of it (download=1 to save).
                # force=, tune=, hide=, look= and colors= as the mosaic route's
                if not FRAME_ID.match(m.group(1)):
                    return self.send_error(400, "Not a frame id")
                if reel._index is None:
                    return self.send_error(404, "Not a mosaic pass")
                query = parse_qs(url.query)
                try:
                    tune = obs_mosaic.parse_tune(query.get("tune", [""])[0], query.get("hide", [""])[0])
                    crop = [float(v) for v in query["crop"][0].split(",")] if query.get("crop") else None
                except ValueError:
                    return self.send_error(400, "tune= is n:dx:dy,..., hide= is n,... and crop= is x0,y0,x1,y1")
                if crop is not None:
                    crop = [max(0.0, min(1.0, v)) for v in crop]
                    if len(crop) != 4 or crop[2] - crop[0] < 1e-4 or crop[3] - crop[1] < 1e-4:
                        return self.send_error(400, "crop= is x0,y0,x1,y1, fractions of the picture")
                force, kind = bool(query.get("force")), m.group(2)
                try:
                    if kind == "json":
                        made = mosaic_native.info(m.group(1), cache, force, tune)
                        if made and query.get("make", [""])[0] in ("jpg", "png"):
                            fmt = query["make"][0]
                            if not made["ready"][fmt] and fmt not in made["making"]:
                                in_background(mosaic_native.start(m.group(1), cache, fmt, force, tune, _mosaic_slots))
                                made["making"][fmt] = 0.0
                        return self.send_json(made) if made else self.send_json({"error": "not a mosaic pass"}, 404)
                    if kind == "webp" and crop is None:
                        return self.send_error(400, "a crop= of the native mosaic, or .jpg / .png for all of it")
                    made = mosaic_native.picture(m.group(1), cache, crop, kind, _mosaic_slots, force, tune)
                except FileNotFoundError:
                    made = None
                if not made:
                    return self.send_error(404, "No mosaic for this frame")
                path, report = made
                name = f"Cassini_{m.group(1)}_mosaic_full_resolution_{report['width']}x{report['height']}"
                return self.send_file(path, {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[kind],
                                      query, name + "." + kind, {"X-Native": json.dumps(report)}, forever=not report["behind"])
            m = re.match(r"^/frames/movie/([^/]+)\.(webp|json)$", url.path)
            if m:
                # a frame played as a movie of its pass (obs_mosaic.movie_webp): centred by SPICE, on the pass's one
                # display scale and one view; .json: the pass's frames, for the movie's filmstrip
                if not FRAME_ID.match(m.group(1)):
                    return self.send_error(400, "Not a frame id")
                if reel._index is None:
                    return self.send_error(404, "No index of the frames")
                if m.group(2) == "json":
                    info = obs_mosaic.pass_info(m.group(1), cache)
                    return self.send_json(info) if info else self.send_error(404, "Not in a pass")
                query = parse_qs(url.query)
                size, fmt = size_of(query, 512), picture_format(query)
                # full resolution: the pass's view at its longest side (obs_mosaic.OUT), as saved from the window
                size = max(SIZES) if size == FULL else size
                try:
                    trail = max(0, min(obs_mosaic.TRAIL, int(query.get("trail", ["0"])[0] or 0)))
                except ValueError:
                    return self.send_error(400, "trail= takes a number of frames")
                try:
                    if query.get("mode", [""])[0] == "rolling":
                        # a mosaic movie: every place's newest tile (laps= newest copies of each), never emptied
                        laps = max(1, min(obs_mosaic.TRAIL, int(query.get("laps", ["1"])[0] or 1)))
                        full = size_of(query, 512) == FULL
                        made = obs_mosaic.rolling_webp(m.group(1), FULL if full else size, cache, laps, _mosaic_slots, fmt,
                                                       out=min(obs_mosaic.CANVAS, FULL_MAX) if full else obs_mosaic.OUT)
                        if made and made[0] is not None:
                            return self.send_picture(made[0], fmt, query, f"Cassini_{m.group(1)}_mosaic_movie", {"X-Movie": json.dumps(made[1])},
                                                     forever=not made[1].get("partial"))
                    else:
                        with _movie_slots:
                            made = obs_mosaic.movie_webp(m.group(1), size, cache, trail, query.get("color", ["1"])[0] != "0",
                                                       centre=query.get("center", ["1"])[0] != "0")
                except (FileNotFoundError, ValueError):
                    made = None
                if not made:
                    return self.send_error(404, "Not in a pass")
                if made[0] is None:
                    # the pass is being worked out, or SPICE could not place the frame: the window shows the frame
                    return self.send_error(503 if made[1].get("why") == "working out the pass" else 404, made[1].get("why", ""))
                data = made[0] if fmt == "webp" else encode(Image.open(io.BytesIO(made[0])), FULL, "png")
                return self.send_picture(data, fmt, query, f"Cassini_{m.group(1)}_movie", {"X-Movie": json.dumps(made[1])})
            m = re.match(r"^/frames/mosaic/([^/]+)\.webp$", url.path)
            if m:
                # the camera windows ask this for each frame: the mosaic when the frame is a new tile of a
                # real mosaic (reel.mosaic_of, mosaic.panels), otherwise 404 at once and the window keeps its frame
                if not FRAME_ID.match(m.group(1)):
                    return self.send_error(400, "Not a frame id")
                query = parse_qs(url.query)
                size, fmt, name = size_of(query, 512), picture_format(query), f"Cassini_{m.group(1)}_mosaic"
                if query.get("warm"):
                    # the window will reach this frame soon: when it is in a mosaic pass, start working out the
                    # pass (its plan reads every frame of it, many seconds) and its first tiles now, and say so
                    # ({"mosaic": true}), so the window asks for that pass's mosaic in its pass lane from the start
                    # ({"movie": true}: the observation is a movie or a stare, so the window never asks for its frames)
                    kind = {"mosaic": False, "movie": False}
                    if reel._index is not None:
                        in_background(obs_mosaic.warm_frame, m.group(1), cache)
                        try:
                            kind = obs_mosaic.kind_of(m.group(1))
                        except Exception:
                            pass
                    return self.send_json(kind)
                # a whole-body mosaic (obs_mosaic): the observation's mosaic so far, every filter; at full
                # resolution, its canvas (obs_mosaic.CANVAS) up to FULL_MAX
                if reel._index is not None:
                    # tune= / hide=: the person's changes to the mosaic's tiles (Cassini Studio), laid over SPICE's
                    # placement (obs_mosaic.tuned_layout); the mosaic without them is the same address without them
                    try:
                        tune = obs_mosaic.parse_tune(query.get("tune", [""])[0], query.get("hide", [""])[0])
                    except ValueError:
                        return self.send_error(400, "tune= is n:dx:dy,... and hide= is n,...")
                    if tune[0] or tune[1]:
                        name += "_tuned"
                    try:
                        # force=1: the window's Mosaic switch, the pass's mosaic whatever obs_mosaic calls it
                        made = obs_mosaic.mosaic_webp(m.group(1), size, cache, _mosaic_slots, fmt=fmt,
                                                      out=min(obs_mosaic.CANVAS, FULL_MAX) if size == FULL else obs_mosaic.OUT,
                                                      force=bool(query.get("force")), tune=tune)
                    except FileNotFoundError:
                        made = None
                    if made:
                        # behind: the mosaic of the tiles made so far, not yet this frame's (asked for again later)
                        return self.send_picture(made[0], fmt, query, name, {"X-Reel": json.dumps(made[1])}, forever=not made[1].get("behind"))
                    # a movie plays as frames: no rolling mosaic either (its drift would paste frames together)
                    found = obs_mosaic.unit_of(m.group(1))
                    if query.get("force"):
                        return self.send_error(404, "No tile of this pass placed yet")
                    if found and found[0]["movie"]:
                        return self.send_error(404, "A movie, not a mosaic")
                    # a mosaic pass with no tile placed, or none with anything above black yet: the window
                    # keeps its frame (obs_mosaic.blank)
                    if found and found[0]["mosaic"] and found[1] >= 0:
                        return self.send_error(404, "Nothing in this pass's mosaic yet")
                found = reel.mosaic_of(m.group(1), wait=False)
                if not found:
                    return self.send_error(404, "Not a mosaic tile")
                try:
                    # a rolling mosaic is drawn at reel.OUT, its full resolution here
                    data, report = reel.shot_webp(*found, reel.OUT if size == FULL else size, cache, True, _mosaic_slots)
                    if fmt == "png":
                        data = encode(Image.open(io.BytesIO(data)), FULL, "png")
                    return self.send_picture(data, fmt, query, name, {"X-Reel": json.dumps(report, default=str)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
            m = re.match(r"^/frames/([^/]+)\.(webp|png)$", url.path)
            if m:
                frame_id, kind = m.groups()
                if not FRAME_ID.match(frame_id):
                    return self.send_error(400, "Not a frame id")
                try:
                    query = parse_qs(url.query)
                    if kind == "png":
                        return self.send_picture(archive_png(frame_id), "png", query, f"Cassini_{frame_id}_archive")
                    size, fmt = size_of(query, 512), picture_format(query)
                    if reel._index is not None and size != FULL:
                        # a frame of a mosaic pass (the window asks for frames a few ahead): start its tiles
                        in_background(obs_mosaic.warm_frame, frame_id, cache)
                    return self.send_picture(webp(frame_id, size, cache, fmt), fmt, query, f"Cassini_{frame_id}")
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
            if not site:
                return self.send_error(404)
            # pages and their JSON change with every rebuild, so browsers must check before reusing them;
            # frames, textures and track files keep the default heuristic caching
            self.revalidate = url.path.endswith(("/", ".html", ".json"))
            try:
                if self.send_gzipped(url.path):
                    return
                return super().do_GET()
            finally:
                # replay data is small and quick to send: one that took a while says the server was busy
                took = time.monotonic() - self.started
                if took > 1 and "/data/" in url.path:
                    print(f"slow data {took:.1f} s {url.path} ({threading.active_count()} threads)", flush=True)

        def send_flags(self, url_path):
            if url_path == "/flags":
                self.send_response(301)
                self.send_header("Location", "/flags/")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            rest = url_path[len("/flags/"):]
            if rest == "":
                return self.send_bytes(flags_page(flags).encode(), "text/html; charset=utf-8", False)
            if rest == "index.json":
                entries = flag_entries(flags)[::-1]
                return self.send_bytes(json.dumps({"count": len(entries), "flags": entries}).encode(), "application/json", False)
            name, _, file = rest.partition("/")
            if not FLAG_NAME.match(name) or not FLAG_FILE.match(file):
                return self.send_error(404)
            path = os.path.join(flags, name, file)
            if not os.path.isfile(path):
                return self.send_error(404)
            with open(path, "rb") as fh:
                data = fh.read()
            mime = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".json": "application/json"}[os.path.splitext(file)[1]]
            return self.send_bytes(data, mime, False)

        def send_gzipped(self, url_path):
            """A site file gzipped, if the browser takes gzip and it is worth it; False otherwise."""
            if "gzip" not in self.headers.get("Accept-Encoding", ""):
                return False
            path = self.translate_path(url_path)
            if os.path.isdir(path):
                path = os.path.join(path, "index.html")
            if not path.endswith(GZIP_TYPES) or not os.path.isfile(path):
                return False
            st = os.stat(path)
            modified = self.date_time_string(int(st.st_mtime))
            since = self.headers.get("If-Modified-Since")
            if since:
                try:
                    if email.utils.parsedate_to_datetime(since).timestamp() >= int(st.st_mtime):
                        self.send_response(304)
                        self.send_header("Last-Modified", modified)
                        self.end_headers()
                        return True
                except (TypeError, ValueError, OverflowError):
                    pass
            data = gzipped(path, st)
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Last-Modified", modified)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True

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
    ap.add_argument("--flags", default=os.environ.get("CASSINI_FLAGS", "~/Documents/flagged-pictures"),
                    help="where pictures flagged in Cassini OS are saved (POST /flags, page /flags/)")
    args = ap.parse_args()
    site = os.path.abspath(os.path.expanduser(args.site)) if args.site else None
    print(f"Frames from {data_source.get_source()}, kernels from {data_source.get_kernel_source()}, cache in {args.cache}")
    # every year's kernels stay extracted once used, so a reel going back and forth in time is not slowed
    data_source.KEEP_SPICE_CACHE = True
    data_source._zip_index() if data_source.using_zip() else None  # build or load the zip index up front
    # the camera windows' mosaic route needs the index; read it now rather than on the first request
    threading.Thread(target=reel.target_of, daemon=True).start()
    # the first composite would otherwise wait while stacking reads the whole image index (all ~443k rows)
    threading.Thread(target=color_image.stacking.load_index, daemon=True).start()
    if site:
        # the Highlights window's thumbnails, made now (and after any version bump) rather than when it opens
        threading.Thread(target=warm_thumbs, args=(site, args.cache), daemon=True).start()
    flags = os.path.abspath(os.path.expanduser(args.flags))
    print(f"Flagged pictures go to {flags}")
    server = Server((args.host, args.port), make_handler(site, args.cache, flags))
    print(f"Serving on http://{args.host}:{args.port}/" + (f" (site: {site})" if site else ""))
    server.serve_forever()


if __name__ == "__main__":
    main()
