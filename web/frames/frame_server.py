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
                               made on first request and cached on disk; every body's sharpest frame
                               (data/targets.json "best", the All bodies folder's picture) is made at 256 as
                               the server starts
  ...?size=full                any picture route below at full resolution, for a picture looked at on its own
                               (full view): a frame or composite at its native size, losslessly for frames;
                               a pass's mosaic at its canvas size; never more than CASSINI_FULL_MAX px
                               (default 2048) on the longest side. Live feeds, bursts, reels and movies keep
                               the capped sizes. &format=png sends PNG instead, &download=1 as a named
                               attachment (Cassini_<ID>.png), so the picture can be saved and shared
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
  /frames/processed/<ID>.webp?size=512
                               the frame alone made like a composite's channel (color_image.load_aligned with
                               one frame: repeat exposures stacked, lost pixels transparent, calibrated to I/F
                               and put on the pipeline's display scale), for movie mode; cached like the
                               composites, X-Composite as theirs
  /reel/bodies.json            every body with frames, most photographed first
  /reel/<TARGET>.json          the body's reel: its pictures in time order (web/frames/reel.py)
  /frames/reel/<TARGET>/<n>.webp?size=768&mosaic=1
                               picture n of the reel, made by the pipeline (color_image.processed_frame:
                               stacked, calibrated, aligned, centred on the body with north up by SPICE)
                               and drawn into the rolling mosaic with the pictures before it; made on
                               first request and cached. X-Reel says how it was made
  /frames/mosaic/<ID>.webp?size=512   (&warm=1: only start making the pass ahead of time, empty answer)
                               the mosaic frame <ID> is a new tile of, made like a reel picture: 404 when
                               the frame is not a mosaic tile (mosaic.panels: same camera, observation and
                               filter, the pointing stepped across the body, panels overlap)
                               When the frame is in a mosaic pass (obs_mosaic: one camera and observation,
                               three or more pointings), instead the pass's mosaic so far, every tile and
                               filter, in false colour when it cycles three or more; asking for a frame of the
                               pass starts making its tiles
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
  /health                      "ok" plus where the frames come from
  POST /flags                  a picture flagged in Cassini OS (the ⚑ button or R in a picture window): JSON with
                               the picture as shown (a data: URL), what the window showed and an optional note.
                               Saved under --flags (default ~/Documents/flagged-pictures) as <name>/shown.png,
                               <name>/raw/<ID>.png (each frame's archive PNG) and <name>/flag.json, with one line
                               per flag in index.jsonl; answers {"name", "count"}
  POST /flags/<name>/undo      takes a flag back: its folder moves to undone/ and its index line goes
  /flags/                      every flag on one page, newest first, each with a link to its moment
  /flags/index.json            the flags as a list, newest first ({"count", "flags"}); both take ?version=<commit>
                               to list only the flags made on that version
  /flags/<name>/<file>         a flag's files
  /version.json                which version this is: the commit the site is checked out at (its date, the PR it
                               merged), the commit the server itself runs, the page build in --site and every
                               picture-maker version (obs-v*, color-v*, reel-v*...); each flag keeps a copy
  POST /usage                  one word from the page ("visit", "visit-link", "copy-link"), added to today's usage
                               counts; every answer above is counted there too (usage.py: daily totals only, no
                               cookies, nothing per person), kept in --usage (default ~/Documents/cassini-usage)
  /stats/                      the usage counts on one page; /stats/usage.json?days=30 the same as JSON. Only for this
                               machine, its network and Tailscale (not through the Cloudflare tunnel), or ?key=$CASSINI_STATS_KEY
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
import subprocess
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402
import obs_mosaic  # noqa: E402
import export  # noqa: E402
import usage  # noqa: E402
counts = None   # the usage counts (usage.Usage), set by main(); None counts nothing

FRAME_ID = re.compile(r"^([NW])\d{10}_\d+$")
SIZES = (128, 256, 384, 512, 768, 1024)
# size=full: the picture at full resolution, capped so a whole-pass mosaic cannot run away with the bandwidth
FULL = "full"
FULL_MAX = int(os.environ.get("CASSINI_FULL_MAX", "2048"))
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


def webp(frame_id, size, cache, fmt="webp"):
    def make():
        im = Image.open(io.BytesIO(archive_png(frame_id)))
        im = im.convert("L") if im.mode in ("L", "I", "I;16", "P", "1") else im.convert("RGB")
        return encode(im, size, fmt)
    return cached(os.path.join(cache, size_dir(size, fmt), f"{frame_id}.{fmt}"), make)


def composite(ids):
    """RGBA composite of the frames ids (R,G,B, or longer and shorter wavelength), 1024 px, made by the
    pipeline's color path (color_image.load_aligned: repeat exposures stacked, calibrated, aligned),
    and a report of how each channel was made. One id makes the frame alone, black and white (LA)."""
    imgs, valid, _, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
    chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    report["ids"] = list(ids)
    if len(chans) == 1:
        return Image.fromarray(np.dstack([chans[0], alpha]), "LA"), report
    if len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    return Image.fromarray(np.dstack(chans + [alpha]), "RGBA"), report


# bumped whenever the way composites are made changes, so older ones are not served again
COLOR_VERSION = "color-v4"


def color_webp(ids, size, cache, fmt="webp"):
    """The composite as WebP (or PNG), and its report (also kept in the cache, next to the image)."""
    base = os.path.join(cache, COLOR_VERSION, size_dir(size, fmt), "_".join(ids))
    report = {}
    def make():
        with _color_slots:
            im, made = composite(ids)
        report.update(made)
        cached(base + ".json", lambda: json.dumps(made).encode())
        print("composite", json.dumps(made))
        return encode(im, size, fmt)
    data = cached(f"{base}.{fmt}", make)
    if not report and os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            report = json.load(fh)
    return data, report


def processed_webp(frame_id, size, cache):
    """One frame made like a composite's channel (composite with one id: repeat exposures stacked, lost pixels
    filled, calibrated to I/F and put on the pipeline's display scale), for movie mode; and its report. Cached
    like the composites."""
    base = os.path.join(cache, "proc-v1", str(size), frame_id)
    report = {}
    def make():
        with _movie_slots:
            im, made = composite([frame_id])
        report.update(made)
        cached(base + ".json", lambda: json.dumps(made).encode())
        return encode(im, size)
    data = cached(base + ".webp", make)
    if not report and os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            report = json.load(fh)
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
    return [obs_mosaic.VERSION, reel.VERSION, COLOR_VERSION]


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
    the Highlights window finds them made; after a maker's version bump this is where they are made again."""
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


# the picture each body shows in the dock's All bodies folder and its body window when it has no surface map: its
# sharpest frame (data/targets.json "best"), at this size
ICON_SIZE = 256


def warm_icons(site, cache):
    """Makes every body's folder picture that is not in the cache yet, one at a time, so the All bodies folder opens
    with its pictures in place instead of filling in one by one from the archive."""
    try:
        with open(os.path.join(site, "data", "targets.json")) as fh:
            ids = [b["best"] for b in json.load(fh)["bodies"].values() if b.get("best")]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return
    started, made, failed = time.monotonic(), 0, 0
    for frame_id in ids:
        if not FRAME_ID.match(frame_id) or os.path.exists(os.path.join(cache, size_dir(ICON_SIZE, "webp"), f"{frame_id}.webp")):
            continue
        try:
            webp(frame_id, ICON_SIZE, cache)
            made += 1
        except Exception as e:   # one picture that cannot be made must not stop the others
            failed += 1
            print(f"body picture {frame_id}: {e}", flush=True)
    print(f"body pictures: {len(ids)} ({made} made, {failed} failed) in {time.monotonic() - started:.0f} s", flush=True)


def warm_site(site, cache):
    warm_thumbs(site, cache)
    warm_icons(site, cache)


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


# ---------- the version: which commit the site and the server are, so each flag says which build made its picture ----------
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE_BUILD = re.compile(rb'/\*BUILD\*/"([0-9a-f]+)"')   # build.py writes the page's build id into index.html
_version_lock = threading.Lock()
_site_version = {}


def git_version(folder):
    """The commit checked out where folder is: short and full hash, commit date, subject, the PR it merged (from
    "Merge pull request #N" or a squash's "(#N)"), the branch, and whether tracked files differ; None without git."""
    def git(*args):
        return subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=10, check=True).stdout
    try:
        full, short, date, subject = git("log", "-1", "--format=%H%n%h%n%cI%n%s").split("\n")[:4]
        branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
        changed = bool(git("status", "--porcelain", "--untracked-files=no").strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    pr = re.search(r"^Merge pull request #(\d+)|\(#(\d+)\)$", subject)
    date = datetime.datetime.fromisoformat(date).astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {"commit": short, "full": full, "date": date, "subject": subject, "pr": int(pr.group(1) or pr.group(2)) if pr else None,
            "branch": branch, "changed": changed}


def version_label(v):
    """A version as people say it: 2026-10-27 · #137 · a1b2c3d (+ local changes)."""
    if not v:
        return "unknown"
    return " · ".join(filter(None, [v["date"][:10], f"#{v['pr']}" if v.get("pr") else None, v["commit"]])) + (" + local changes" if v.get("changed") else "")


def pipeline_versions():
    """Every picture maker's version string, as named in the code (obs_mosaic.VERSION, frame_server.COLOR_VERSION...):
    the same strings that name the cache folders, so a flag says which pipeline made its picture."""
    out = {}
    for name, mod in sorted(sys.modules.items()):
        if not os.path.abspath(getattr(mod, "__file__", None) or "/").startswith(REPO + os.sep):
            continue
        if name == "__mp_main__":   # the server run as a script, loaded again under this name: the same constants
            continue
        name = "frame_server" if name == "__main__" else name
        for key, value in vars(mod).items():
            if not re.match(r"^[A-Z0-9_]*(VERSION|VERSIONS|SUFFIX)$", key):
                continue
            if isinstance(value, str) or (isinstance(value, dict) and all(isinstance(x, str) for x in value.values())):
                out[f"{name}.{key}"] = value
    return out


SERVER_VERSION = git_version(REPO)   # the code this server runs: read once, as it starts


def site_version(site):
    """The version as it is now: the site is a checkout that git pull moves on without a restart, so its commit is read
    again every 30 seconds; the page build is read from index.html when that file changes."""
    folder = site or REPO
    index = os.path.join(site, "index.html") if site else None
    try:
        mtime = os.stat(index).st_mtime_ns if index else None
    except OSError:
        mtime = None
    with _version_lock:
        got = _site_version.get(folder)
        if got and time.monotonic() - got[0] < 30 and got[1] == mtime:
            return got[2]
    page = None
    if mtime is not None:
        with open(index, "rb") as fh:
            m = PAGE_BUILD.search(fh.read())
        page = m.group(1).decode() if m else None
    site_v = git_version(folder)
    v = {"version": version_label(site_v), "site": site_v, "page": page,
         "server": SERVER_VERSION, "server_version": version_label(SERVER_VERSION),
         "server_current": bool(site_v and SERVER_VERSION and site_v["full"] == SERVER_VERSION["full"]),
         "pipeline": pipeline_versions()}
    with _version_lock:
        _site_version[folder] = (time.monotonic(), mtime, v)
    return v


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
                       report), each frame's camera, filters, target and observation, the note and tags, the
                       viewer's settings, and "version": the site's commit (date, PR, hash; "version" is its
                       label, e.g. 2026-10-27 · #137 · a1b2c3d), the server's own commit, the page build the
                       viewer was running (page_current false: an older page, not reloaded since) and every
                       picture maker's version (obs-v*, color-v*, reel-v*...). /flags/?version=<commit> lists only
                       the flags made on that version.
undone/       flags taken back with Undo (moved here, not deleted)

Made by web/frames/frame_server.py; the page /flags/ on the frame server shows them all.
"""


def flag_entries(folder):
    try:
        with open(os.path.join(folder, "index.jsonl")) as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def save_flag(folder, flag, version=None):
    """Writes a flag (the JSON the page sent) into folder: its own folder with the picture as shown, the archive
    PNG of each frame and flag.json, and a line in index.jsonl; version (site_version) says which build it was made
    on. Returns the flag's name and how many there are."""
    image = flag.pop("image", None) or ""
    if version is not None:
        page = (flag.get("build") or {}).get("page") if isinstance(flag.get("build"), dict) else None
        flag["version"] = {**version, "page_shown": page, "page_current": bool(page and page == version.get("page"))}
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


def flag_version(e):
    """A flag's site commit and its label; flags made before versions were kept have neither."""
    v = e.get("version") or {}
    return (v.get("site") or {}).get("commit"), v.get("version")


def flags_of_version(entries, version):
    """The flags made on version (a commit, short or full, or a label's start such as 2026-10-27); all with none."""
    if not version:
        return entries
    keep = []
    for e in entries:
        site = (e.get("version") or {}).get("site") or {}
        if version in (site.get("commit"), site.get("full")) or (site.get("full") or "").startswith(version) \
                or ((e.get("version") or {}).get("version") or "").startswith(version):
            keep.append(e)
    return keep


def flags_page(folder, version="", now=None):
    """Every flag on one page, newest first: the picture as shown, when and what it was, the note, and the version it
    was made on; version= shows only that version's flags, and every version that has flags gets a link."""
    esc = lambda v: html.escape(str(v if v is not None else ""))
    every = flag_entries(folder)
    versions = {}
    for e in every:
        commit, label = flag_version(e)
        versions.setdefault(commit, [label or "before versions were kept", 0])[1] += 1
    cards = []
    for e in reversed(flags_of_version(every, version)):
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
  <div class=when>flagged {esc(e.get('received', ''))}</div>
  <div class="when ver">{f'version <a href="?version={esc(flag_version(e)[0])}">{esc(flag_version(e)[1])}</a>' if flag_version(e)[0] else 'version not kept (flagged before versions)'}{'' if (e.get('version') or {}).get('page_current', True) else ' · flagged from an older page, not reloaded since'}</div></div></figcaption>
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
.ids, .when {{ font: 11px/1.4 ui-monospace, Menlo, monospace; color: #8a94a3; word-break: break-all; }} .when.ver {{ word-break: normal; overflow-wrap: anywhere; }}
.tag {{ display: inline-block; margin: 5px 4px 0 0; padding: 1px 7px; border-radius: 9px; background: rgba(138,182,255,.16); color: #b9d0ff; font-size: 11px; }}
.links {{ margin-top: 6px; font-size: 11.5px; }} a {{ color: #8ab6ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
</style></head><body><h1>Flagged pictures</h1><p class=sub>{len(cards)} flagged{' on version ' + esc(version) + ' · <a href=".">every version</a>' if version else ''} · saved in {esc(folder)} · <a href="index.json{'?version=' + esc(version) if version else ''}">index.json</a>
{'<br>running version ' + esc(now['version']) if now else ''}{''.join(f' · <a href="?version={esc(c)}">{esc(lab)}</a> ({n})' for c, (lab, n) in versions.items() if c) if len(versions) > 1 or version else ''}</p>
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


class Server(ThreadingHTTPServer):
    # the default backlog of 5 resets connections when several viewers open theirs at once
    # (a browser opens six per page); the OS caps it at its own limit anyway
    request_queue_size = 128
    daemon_threads = True


def make_handler(site, cache, flags=None):
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
            self.send_header("Access-Control-Expose-Headers", "X-Composite, X-Reel, X-Thumb")
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

        def send_picture(self, data, fmt, query, name, headers=None):
            """A picture route's answer: WebP or PNG, as a named attachment when download=1 asks for one."""
            headers = dict(headers or {})
            if query.get("download", ["0"])[0] == "1":
                headers["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
            return self.send_bytes(data, "image/png" if fmt == "png" else "image/webp", headers=headers)

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
            n = int(self.headers.get("Content-Length") or 0)
            if url.path == "/usage":
                # the page's one word (usage.BEACONS); nothing else is read or kept
                body = self.rfile.read(n) if 0 < n <= 64 else b""
                if counts and body:
                    counts.beacon(self, body)
                self.send_response(204)
                self.send_header("Content-Length", "0")
                return self.end_headers()
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
                name, count = save_flag(flags, flag, site_version(site))
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
            if flags and (url.path == "/flags" or url.path.startswith("/flags/")):
                return self.send_flags(url.path, parse_qs(url.query).get("version", [""])[0])
            if url.path == "/version.json":
                return self.send_json(site_version(site))
            if url.path == "/jumplog":
                return self.send_json(jumplog(cache))
            if url.path in ("/stats", "/stats/", "/stats/usage.json"):
                return self.send_stats(url)
            if url.path == "/health":
                return self.send_bytes(f"ok {data_source.get_source()}\n".encode(), "text/plain", False)
            if url.path == "/frames/color.webp":
                query = parse_qs(url.query)
                ids = query.get("ids", [""])[0].split(",")
                if not 2 <= len(ids) <= 3 or not all(FRAME_ID.match(i) for i in ids) or len({i[0] for i in ids}) > 1:
                    return self.send_error(400, "ids= takes two or three frame ids from one camera")
                size, fmt = size_of(query, 512), picture_format(query)
                try:
                    data, report = color_webp(ids, size, cache, fmt)
                    return self.send_picture(data, fmt, query, f"Cassini_{'_'.join(ids)}_color", {"X-Composite": json.dumps(report)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
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
                size = min(SIZES, key=lambda s: abs(s - int(parse_qs(url.query).get("size", ["512"])[0])))
                try:
                    data, report = processed_webp(m.group(1), size, cache)
                    return self.send_bytes(data, "image/webp", headers={"X-Composite": json.dumps(report)})
                except FileNotFoundError:
                    return self.send_error(404, "Frame not in the archive")
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
                    found = None
                    if reel._index is not None:
                        threading.Thread(target=obs_mosaic.warm_frame, args=(m.group(1), cache), daemon=True).start()
                        try:
                            found = obs_mosaic.unit_of(m.group(1))
                        except Exception:
                            found = None
                    return self.send_json({"mosaic": bool(found and found[0]["mosaic"])})
                # a whole-body mosaic (obs_mosaic): the observation's mosaic so far, every filter; at full
                # resolution, its canvas (obs_mosaic.CANVAS) up to FULL_MAX
                if reel._index is not None:
                    try:
                        made = obs_mosaic.mosaic_webp(m.group(1), size, cache, _mosaic_slots, fmt=fmt,
                                                      out=min(obs_mosaic.CANVAS, FULL_MAX) if size == FULL else obs_mosaic.OUT)
                    except FileNotFoundError:
                        made = None
                    if made:
                        return self.send_picture(made[0], fmt, query, name, {"X-Reel": json.dumps(made[1])})
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
                    if kind == "png":
                        return self.send_bytes(archive_png(frame_id), "image/png")
                    query = parse_qs(url.query)
                    size, fmt = size_of(query, 512), picture_format(query)
                    if reel._index is not None and size != FULL and size >= 512:
                        # a frame of a mosaic pass (the window asks for frames a few ahead): start its tiles; not
                        # for a small picture (a body's folder picture), which no camera window asks for
                        threading.Thread(target=obs_mosaic.warm_frame, args=(frame_id, cache), daemon=True).start()
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

        def send_stats(self, url):
            """The usage counts (usage.py): the page and its JSON, for this machine's own network only."""
            if not counts:
                return self.send_error(404, "Usage counting is off (--usage off)")
            if not usage.may_see(self):
                return self.send_error(403, "The stats are private")
            if url.path == "/stats":
                self.send_response(301)
                self.send_header("Location", "/stats/" + (f"?{url.query}" if url.query else ""))
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if url.path == "/stats/":
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.html"), "rb") as fh:
                    return self.send_bytes(fh.read(), "text/html; charset=utf-8", False, {"Cache-Control": "no-store"})
            days = max(1, min(366, int(parse_qs(url.query).get("days", ["30"])[0] or 30)))
            return self.send_json(usage.summary(counts.days(days)))

        def log_request(self, code="-", size="-"):
            # every answer passes here once: the usage counts add it to today's totals (usage.Usage.request)
            if counts:
                try:
                    counts.request(self, int(code))
                except (TypeError, ValueError):
                    pass
            super().log_request(code, size)

        def send_flags(self, url_path, version=""):
            if url_path == "/flags":
                self.send_response(301)
                self.send_header("Location", "/flags/")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            rest = url_path[len("/flags/"):]
            if rest == "":
                return self.send_bytes(flags_page(flags, version, site_version(site)).encode(), "text/html; charset=utf-8", False)
            if rest == "index.json":
                entries = flags_of_version(flag_entries(flags), version)[::-1]
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
    ap.add_argument("--usage", default=os.environ.get("CASSINI_USAGE", "~/Documents/cassini-usage"),
                    help="where the daily usage counts are kept (usage.py, page /stats/); off to count nothing")
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
        # the Highlights window's thumbnails and the All bodies folder's pictures, made now (and after any version
        # bump) rather than when they open
        threading.Thread(target=warm_site, args=(site, args.cache), daemon=True).start()
    flags = os.path.abspath(os.path.expanduser(args.flags))
    print(f"Flagged pictures go to {flags}")
    global counts
    counts = None if args.usage == "off" else usage.Usage(os.path.abspath(os.path.expanduser(args.usage)))
    print(f"Usage counts in {counts.folder}" if counts else "Usage counting off")
    server = Server((args.host, args.port), make_handler(site, args.cache, flags))
    print(f"Serving on http://{args.host}:{args.port}/" + (f" (site: {site})" if site else ""))
    server.serve_forever()


if __name__ == "__main__":
    main()
