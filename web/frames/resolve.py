"""
The cache-only resolver (public site, WP1): which file in the picture cache answers a request, without making
anything. WP0 wrote its signature (the contracts, web/public/); the publisher (WP3) and the frame server's --public mode
call it.

resolve() takes each route's decisions from the route's own code: frame_server's handler and the makers' naming helpers
(frame_server.frame_path, color_base, processed_base, thumb_base, centre_decision, rolling_out; obs_mosaic.mosaic_pass,
tiles_made_through, layout, _mosaic_path, movie_ready, movie_path, rolling_layout, rolling_path; reel.shot_path), which
the makers themselves call for their file names, so it can never name a different file than the maker writes. It never
makes a picture, never starts background work (warm_frame, tiles_ahead, warm_movie, rolling_ahead, _map_later or a
startup warmer) and never waits for a slot: while it runs (cache_only) any file written, folder made, file moved or
removed, or thread started in its context stops it (NotMade), and it answers "none".

  answer = resolve("/frames/color.webp", {"ids": ["N1,N2,N3"], "size": ["1024"], "center": ["1"]}, cache)
  answer.kind     "file": answer.path is the cached file the server would send, answer.headers its X-* headers
                  "negative": a deliberate negative answer (Auto center's 404 with X-Center): answer.status,
                  answer.headers and answer.body are what the server sends
                  "none": the cache has no answer (not made yet, made only in part, or not a picture this route makes)
                  "busy" (resolve.BUSY, status 503): not known yet. The route's layout works something out again on
                  every request because the cache keeps none of it (ring fits a pass never keeps), and that took longer
                  than BUDGET seconds. Ask again: it is not "not there". The publisher retries it (with a larger
                  CASSINI_RESOLVE_BUDGET if it keeps coming back busy); --public answers 503 with Retry-After

  read(answer)    the bytes of a "file" answer. The archive route (/frames/<ID>.png) answers the archive's own PNG,
                  which is no file of the cache: its path is the file when the archive is a folder, else
                  "<archive.zip>!/<member>", which read() reads; every other path is a plain file.

  table(path, query, cache)   the --public mode's answer to a table route (tile map, pass info, steady and fade tables,
                  warm=1's pass kind) from what the cache keeps, as the same obs_mosaic functions work it out, None
                  (a miss: never {"working": true}), or resolve.BUSY (as above: ask again).

What it answers is what the server sends for the same request on the same cache, with two differences on purpose: a
picture the server sends as a stand-in it asks for again (a mosaic behind its frame, a mosaic movie drawn without some
of its tiles, a movie whose pass is being worked out) is "none", since the public site keeps only finished pictures;
and an Auto center 404 the server decides only while making the picture (a frame SPICE cannot place, LookupError) is
not in the cache, so it is "none" too (the publisher writes no marker for it).
"""
import contextlib
import contextvars
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

KINDS = ("file", "negative", "none", "busy")


@dataclass(frozen=True)
class Answer:
    kind: str                                   # one of KINDS
    status: int = 200                           # the HTTP status the server sends (200 for a file)
    path: Optional[str] = None                  # kind "file": the cached file, absolute
    mime: Optional[str] = None                  # kind "file": image/webp, image/png or application/json
    headers: Dict[str, str] = field(default_factory=dict)   # X-Composite, X-Movie, X-Reel, X-Thumb, X-Center
    body: Optional[bytes] = None                # kind "negative": the body the server sends (JSON)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"kind is one of {KINDS}")
        if self.kind == "file" and not self.path:
            raise ValueError("a file answer names its path")


NONE = Answer("none", 404)
# the budget (BUDGET) ran out on work the layout does on every request because the cache keeps none of it (ring fits a
# pass never keeps): the answer is not known yet, not "not there". Ask again (a publisher retries it, given more time
# with a larger CASSINI_RESOLVE_BUDGET, or on a quieter machine; --public answers 503 with Retry-After)
BUSY = Answer("busy", 503)
ZIP_MEMBER = "!/"   # an archive frame inside the archive zip: "<zip>!/<member>"


class NotMade(BaseException):
    """Raised inside resolve() where the route's code would make something: the cache has no answer. A BaseException,
    so the makers' own `except Exception` (a thumbnail or warmer carrying on past one failure) cannot swallow it."""


# ---------- cache only: nothing written, nothing started ----------
# seconds a resolve may spend working out again what a layout works out on every request because nothing of it is kept
# (obs_mosaic.kept_only): a ring pass whose fits find too little to keep takes about a second, and is answered; one
# whose fits the cache lacks would take minutes, and is answered "none" when this is spent
BUDGET = float(os.environ.get("CASSINI_RESOLVE_BUDGET", "5"))
_cache_only = contextvars.ContextVar("cache_only", default=None)   # the picture cache being read (its real path)
_WRITE_EVENTS = {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.link", "os.symlink", "os.truncate",
                 "os.chmod", "os.utime", "shutil.copyfile", "shutil.move", "shutil.rmtree", "shutil.make_archive"}
# a child process could write anywhere, the cache included: none is started under cache_only
_CHILD_EVENTS = {"subprocess.Popen", "os.posix_spawn", "os.spawn", "os.system", "os.exec", "os.fork", "os.forkpty",
                 "pty.spawn", "os.startfile"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_installed = []
_install_lock = threading.Lock()


def _inside(path, cache):
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, str):
        return False   # (an open file descriptor: nothing new is opened for writing by name)
    real = os.path.realpath(path)
    return real == cache or real.startswith(cache + os.sep)


def _audit(event, args):
    cache = _cache_only.get()
    if cache is None:
        return
    if event == "open":
        mode, flags = args[1], args[2]
        if ((isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & _WRITE_FLAGS)) \
                and _inside(args[0], cache):
            raise NotMade(f"would write {args[0]}")
    elif event in _WRITE_EVENTS and args and _inside(args[0], cache):
        raise NotMade(f"would {event} {args[0]}")
    elif event in _CHILD_EVENTS:
        raise NotMade(f"would start a child process ({event})")
    elif event == "sqlite3.connect" and args:
        # a database in the cache is opened read-only (a URI with mode=ro) or not at all: sqlite writes through its own
        # file calls, which the open hook never sees
        db = args[0]
        db = os.fsdecode(db) if isinstance(db, bytes) else str(db)
        if db.startswith("file:"):
            name, _, opts = db[5:].partition("?")
            if "mode=ro" in opts.split("&") or not _inside(name, cache):
                return
            raise NotMade(f"would open {name} for writing")
        if db != ":memory:" and _inside(db, cache):
            raise NotMade(f"would open {db} for writing")


def _install():
    """The guards cache_only relies on, installed once per process: an audit hook that stops any file of the picture cache
    written (or folder made, moved, removed in it, or a database in it opened other than read-only), and any child
    process started, and a check in Thread.start that stops any thread started, while cache_only is on in the calling
    context. obs_mosaic.kept_only(BUDGET) goes with it: the mosaic code never makes a plan or a tile, and stops working
    out fits and registrations the cache does not keep once BUDGET is spent, checked tile by tile, rather than at the
    write after minutes of it. Both do nothing anywhere else (the server's own requests, its warmers).
    Files outside the cache are not pictures: SPICE's kernels extracted to its own cache, for one, stay allowed."""
    if _installed:
        return
    with _install_lock:
        if _installed:
            return
        sys.addaudithook(_audit)
        start = threading.Thread.start

        def guarded_start(self, *args, **kwargs):
            if _cache_only.get() is not None:
                raise NotMade("would start background work")
            return start(self, *args, **kwargs)
        threading.Thread.start = guarded_start
        _installed.append(True)


@contextlib.contextmanager
def cache_only(cache):
    """Code run inside this writes nothing into the picture cache, starts nothing and works out nothing the cache does
    not keep (NotMade, or obs_mosaic.NotKept, where it would)."""
    _install()
    om = _fs().obs_mosaic   # (imported before the guard is on: importing frame_server starts a process, bootleg_autonav)
    token = _cache_only.set(os.path.realpath(cache))
    try:
        with om.kept_only(BUDGET):
            yield
    finally:
        _cache_only.reset(token)


# ---------- the server's modules, as the running server has them ----------
def _fs():
    """frame_server: the running server's own module when this runs inside it (it registers itself under its name
    before --public starts), else imported."""
    fs = sys.modules.get("frame_server")
    if fs is None:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import frame_server as fs
    return fs


_prepared = []


def prepare():
    """What the server works out as it starts and resolve() reads (the index of the frames, its observations and rows),
    loaded now, outside cache_only. Once per process; --public calls it before it listens."""
    if _prepared:
        return
    with _install_lock:
        if _prepared:
            return
        fs = _fs()
        fs.data_source.KEEP_SPICE_CACHE = True   # (as the server: kernels stay extracted, never cleared under a request)
        fs.reel.target_of()
        fs.obs_mosaic._observations()
        fs.obs_mosaic._row_of()
        _prepared.append(True)


def _first(query, name, default):
    return query.get(name, [default])[0]


def _file(path, fmt, header=None, report=None):
    if not os.path.isfile(path):
        return NONE
    headers = {header: json.dumps(report)} if header else {}
    return Answer("file", 200, path, "image/png" if fmt == "png" else "image/webp", headers)


def _negative(view):
    status, headers, body = _fs().not_centred_answer(view)
    return Answer("negative", status, headers={k: v for k, v in headers.items() if k.startswith("X-")}, body=body)


def resolve(path: str, query: Dict[str, List[str]], cache: str) -> Answer:
    """The cache's answer to GET path?query (query as urllib.parse.parse_qs gives it, as the server reads it), using the
    route's own decisions, without making a picture or starting background work."""
    fs = _fs()
    prepare()
    try:
        with cache_only(cache), fs.calibration.looking(_first(query, "look", fs.calibration.LOOKS[0])), \
                fs.calibration.coloring(_first(query, "colors", fs.calibration.COLORS[0])), \
                fs.calibration.stepping(_first(query, "off", "")):
            return _route(fs, path, query, cache) or NONE
    except fs.obs_mosaic.NotKept as e:
        return BUSY if e.budget else NONE
    except (NotMade, FileNotFoundError, LookupError, ValueError):
        return NONE


def _route(fs, path, query, cache):
    if path == "/frames/color.webp":
        return _color(fs, query, cache)
    if path == "/frames/thumb.webp":
        return _thumb(fs, query, cache)
    m = re.match(r"^/frames/processed/([^/]+)\.webp$", path)
    if m:
        return _processed(fs, m.group(1), query, cache)
    m = re.match(r"^/frames/movie/([^/]+)\.webp$", path)
    if m and fs.FRAME_ID.match(m.group(1)):
        if _first(query, "mode", "") == "rolling":
            return _rolling(fs, m.group(1), query, cache)
        return _movie(fs, m.group(1), query, cache)
    m = re.match(r"^/frames/mosaic/([^/]+)\.webp$", path)
    if m and fs.FRAME_ID.match(m.group(1)) and not query.get("warm"):
        return _mosaic(fs, m.group(1), query, cache)
    m = re.match(r"^/frames/([^/]+)\.(webp|png)$", path)
    if m and fs.FRAME_ID.match(m.group(1)):
        if m.group(2) == "png":
            return _archive(fs, m.group(1))
        size, fmt = fs.size_of(query, 512), fs.picture_format(query)
        return _file(fs.frame_path(m.group(1), size, cache, fmt), fmt)
    return NONE


def _centre(fs, query, frame_id):
    """(the view to centre on or None, a negative Answer or None), as the handler's centre_of decides."""
    view = fs.centre_decision(query, frame_id)
    if view is None or fs.obs_mosaic.view_shown(view):
        return view, None
    return None, _negative(view)


def _color(fs, query, cache):
    ids = _first(query, "ids", "").split(",")
    if not 2 <= len(ids) <= 3 or not all(fs.FRAME_ID.match(i) for i in ids) or len({i[0] for i in ids}) > 1:
        return NONE
    size, fmt = fs.size_of(query, 512), fs.picture_format(query)
    channel = _first(query, "channel", "")
    if channel and channel not in ("0", "1", "2"):
        return NONE
    channel = int(channel) if channel else None
    centre, negative = _centre(fs, query, ids[-1])
    if negative:
        return negative
    base = fs.color_base(ids, size, cache, fmt, channel, centre)
    if not os.path.isfile(f"{base}.{fmt}"):
        return NONE
    return _file(f"{base}.{fmt}", fmt, "X-Composite", fs.reel.report_of(base + ".json", {}))


def _processed(fs, frame_id, query, cache):
    if not fs.FRAME_ID.match(frame_id):
        return NONE
    size, fmt = fs.size_of(query, 512), fs.picture_format(query)
    centre, negative = _centre(fs, query, frame_id)
    if negative:
        return negative
    base = fs.processed_base(frame_id, size, cache, fmt, centre)
    if not os.path.isfile(f"{base}.{fmt}"):
        return NONE
    return _file(f"{base}.{fmt}", fmt, "X-Composite", fs.reel.report_of(base + ".json", {}))


def _thumb(fs, query, cache):
    hint = fs.thumb_hint(query)
    if not hint:
        return NONE
    size = fs.size_of(query, fs.THUMB_SIZE)
    if size == fs.FULL:
        return NONE
    base = fs.thumb_base(hint, size, cache)
    if not os.path.isfile(base + ".webp"):
        return NONE
    what = {}
    if os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            what = json.load(fh)
    return _file(base + ".webp", "webp", "X-Thumb", what)


def _movie(fs, frame_id, query, cache):
    om = fs.obs_mosaic
    if fs.reel._index is None:
        return NONE
    size, fmt = fs.size_of(query, 512), fs.picture_format(query)
    if fmt != "webp":
        return NONE   # (the server re-encodes a movie frame as PNG: no file of the cache)
    size = max(fs.SIZES) if size == fs.FULL else size
    trail = max(0, min(om.TRAIL, int(_first(query, "trail", "0") or 0)))
    steady = max(0, min(om.STEADY_MOST, int(_first(query, "steady", "0") or 0)))
    exposure = om.exposure_of(_first(query, "exposure", "0"))
    colour = _first(query, "color", "1") != "0"
    centre = _first(query, "center", "1") != "0"
    sharpen = _first(query, "detail", "1") != "0"
    found = om.unit_of(frame_id)
    if not found or found[1] < 0:
        return NONE
    u, n = found
    steady, exposure = om.steady_of(u, steady), om.exposure_of(exposure)
    if not om.movie_ready(u, cache, om._record(u, cache), colour, centre, steady, exposure):
        return NONE   # (the server answers 503 "working out the pass")
    path = om.movie_path(u, n, size, cache, trail, colour, centre, steady, exposure, sharpen)
    if not os.path.isfile(path):
        return NONE
    return _file(path, "webp", "X-Movie", fs.reel.report_of(path[:-4] + "json"))


def _rolling(fs, frame_id, query, cache):
    om = fs.obs_mosaic
    if fs.reel._index is None:
        return NONE
    size, fmt = fs.size_of(query, 512), fs.picture_format(query)
    laps = max(1, min(om.TRAIL, int(_first(query, "laps", "1") or 1)))
    fade = om.fade_style(int(_first(query, "fade", "0") or 0), int(_first(query, "persist", str(om.FADE_PERSIST)) or 0))
    full = size == fs.FULL
    out = fs.rolling_out(frame_id, cache, full)
    found = om.unit_of(frame_id)
    if not found or found[1] < 0:
        return NONE
    u, n = found
    if not os.path.exists(os.path.join(om.folder(u, cache), om.PLAN_FILE)):
        return NONE   # (the server answers 503 "working out the pass")
    skipped = []
    made = om.rolling_layout(u, n, cache, laps, made_only=True, skipped=skipped, fade=fade)
    if not made or skipped:
        return NONE   # (no tile placed yet, or drawn without tiles not made yet: a stand-in the server asks again for)
    path = om.rolling_path(u, made, size, cache, fmt, out)
    if path in om._blank or not os.path.isfile(path):
        return NONE
    report = fs.reel.report_of(path[:-len(fmt)] + "json")
    report.update({"rolling": True, "keep": laps, "n": n, "fade": list(fade)})
    return _file(path, fmt, "X-Movie", report)


def _mosaic(fs, frame_id, query, cache):
    om = fs.obs_mosaic
    size, fmt = fs.size_of(query, 512), fs.picture_format(query)
    if fs.reel._index is not None:
        tune = om.parse_tune(_first(query, "tune", ""), _first(query, "hide", ""))
        if tune[0] or tune[1]:
            return NONE   # (Studio's tuned mosaics are made on demand, never kept for the public site)
        found = om.mosaic_pass(frame_id, bool(query.get("force")))
        if found:
            u, n = found
            if not os.path.exists(os.path.join(om.folder(u, cache), om.PLAN_FILE)):
                return NONE
            if om.tiles_made_through(u, n, cache) < n:
                return NONE   # (the server sends the mosaic of the tiles made so far, "behind": a stand-in)
            laid = om.layout(u, n, cache)
            if size == "full":
                path = laid and om._mosaic_path(u, laid, size, cache, fmt, min(om.CANVAS, fs.FULL_MAX))
            else:
                path = laid and om._mosaic_path(u, laid, size, cache)   # (kept as WebP whatever was asked: mosaic_webp)
            if path and path not in om._blank and os.path.isfile(path):
                report = {**fs.reel.report_of(path[:path.rindex(".")] + ".json"), "behind": 0}
                return Answer("file", 200, path, "image/png" if fmt == "png" else "image/webp", {"X-Reel": json.dumps(report)})
    return _no_mosaic(fs, frame_id, query, cache)


def _no_mosaic(fs, frame_id, query, cache):
    """The mosaic route past obs_mosaic's mosaic: 404 for a pass that is one (or a movie), else the body reel's
    rolling mosaic (reel.mosaic_of, shot_webp)."""
    if fs.reel._index is not None:
        found = fs.obs_mosaic.unit_of(frame_id)
        if query.get("force") or (found and found[0]["movie"]) or (found and found[0]["mosaic"] and found[1] >= 0):
            return NONE
    if fs.picture_format(query) != "webp":
        return NONE   # (the server re-encodes it as PNG)
    target = fs.reel.target_of().get(frame_id)
    if not isinstance(target, str) or target not in fs.reel._shots:
        return NONE   # (the server answers 404 while the body's reel is worked out, in the background)
    found = fs.reel.mosaic_of(frame_id, wait=False)
    if not found:
        return NONE
    size = fs.size_of(query, 512)
    path, report_path, drawn = fs.reel.shot_path(*found, fs.reel.OUT if size == fs.FULL else size, cache, True)
    if not os.path.isfile(path) or not os.path.isfile(report_path):
        return NONE
    with open(report_path) as fh:
        report = json.load(fh)
    report["mosaic"] = drawn
    return Answer("file", 200, path, "image/webp", {"X-Reel": json.dumps(report, default=str)})


def _archive(fs, frame_id):
    member = f"{fs.FOLDERS[frame_id[0]]}/{frame_id}.png"
    ds = fs.data_source
    if not ds.exists(member):
        return NONE
    if ds.using_zip():
        return Answer("file", 200, ds.get_source() + ZIP_MEMBER + member, "image/png")
    return Answer("file", 200, ds._folder_path(member), "image/png")


def read(answer: Answer) -> bytes:
    """The bytes of a "file" answer (an archive frame from the archive zip)."""
    if answer.kind != "file":
        raise ValueError("only a file answer has bytes")
    if ZIP_MEMBER in answer.path and not os.path.isfile(answer.path):
        return _fs().data_source.read_bytes(answer.path.split(ZIP_MEMBER, 1)[1])
    with open(answer.path, "rb") as fh:
        return fh.read()


# ---------- tables ----------
def table(path: str, query: Dict[str, List[str]], cache: str):
    """The answer (a JSON-able object) to a table route from what the cache keeps, as the server's own functions work
    it out (obs_mosaic.tile_map, pass_info, steady_table, fade_table, kind_of), None: a miss (never
    {"working": true}, which the server answers while it works the table out), or BUSY: the budget ran out, ask again."""
    fs = _fs()
    prepare()
    om = fs.obs_mosaic
    if fs.reel._index is None:
        return None
    try:
        with cache_only(cache):
            m = re.match(r"^/frames/mosaic/([^/]+)\.json$", path)
            if m and fs.FRAME_ID.match(m.group(1)):
                return om.tile_map(m.group(1), cache)
            m = re.match(r"^/frames/mosaic/([^/]+)\.webp$", path)
            if m and fs.FRAME_ID.match(m.group(1)) and query.get("warm"):
                return om.kind_of(m.group(1), cache)
            m = re.match(r"^/frames/movie/([^/]+)\.fade\.json$", path)
            if m and fs.FRAME_ID.match(m.group(1)):
                laps = max(1, min(12, int(_first(query, "laps", "1"))))
                w, h = int(_first(query, "w", "0")), int(_first(query, "h", "0"))
                return _kept(om.fade_table(m.group(1), cache, laps, min(w, 4096), min(h, 4096)))
            m = re.match(r"^/frames/movie/([^/]+)\.steady\.json$", path)
            if m and fs.FRAME_ID.match(m.group(1)):
                return _kept(om.steady_table(m.group(1), cache, _first(query, "center", "1") != "0",
                                             _first(query, "color", "0") != "0"))
            m = re.match(r"^/frames/movie/([^/]+)\.json$", path)
            if m and fs.FRAME_ID.match(m.group(1)):
                return _kept(om.pass_info(m.group(1), cache))
    except om.NotKept as e:
        return BUSY if e.budget else None
    except (NotMade, FileNotFoundError, LookupError, ValueError, KeyError):
        return None
    return None


def _kept(answer):
    return None if not answer or answer.get("working") else answer
