#!/usr/bin/env python3
"""
The public site's publisher (WP3, docs/public-site/briefs/WP3.md): copies every picture the public page can ask for
from a finished picture cache into R2 under its canonical key, and nothing else; or the same into a local folder, the
mirror, which every test uses before real R2. Nothing here makes or changes a picture: each file is the one the frame
server would send, found by resolve() (web/frames/resolve.py, WP1), and its key comes from keys.canonical()
(web/public/keys.py) with the family tags of the versions the cache was built under.

  python web/frames/publish.py --cache CACHE --to-dir MIRROR            the mirror (no network)
  python web/frames/publish.py --cache CACHE --to-r2                    R2; credentials from the environment only:
                                                                        R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
                                                                        R2_SECRET_ACCESS_KEY, R2_BUCKET
  ... --years 2004 (2004-2006, 2004,2008; or --from 2004-06-01 --until 2004-08-01)   one stretch; default: what the
                                                                        cache's slices.json records, else the mission
  ... --site web/cassini-os                                             the page's data (highlights.json) for the
                                                                        highlight thumbnails, and version.json
  ... --tables DIR                                                      WP2's tables output (default <cache>/public-tables)
  ... --jobs N                                                          processes (default: every core)
  ... --dry-run                                                         enumerate, resolve and count; write nothing

What it publishes, family by family (keys.json families; policy.json routes and the values each allows):
  frame       /frames/<ID>.webp at 128, 512 and 1024 for every frame of the stretch (prebuild phase frames)
  archive     /frames/<ID>.png, the archive's own PNG (decision D6)
  composite   /frames/color.webp for every filter set the page makes (prebuild page_sets) at 512, 1024 and full, with
              Auto center (center=1, decision D4); where Auto center answers 404 with X-Center (a pass it leaves as it
              is) that answer becomes a marker and the set is published as it is (no center), which the page asks next
  processed   /frames/processed/<ID>.webp at 256, 512 and 1024, center=1, markers as for composites
  pass        a pass's pictures as prebuild makes them (make_pass, make_planes, make_evened): a mosaic movie's rolling
              picture (mode=rolling) at 512 and 1024; a mosaic's mosaic so far at 512 and 1024, its last frame at full
              (D3, WP2's fullview phase); a movie's frames at 128, 512 and 1024, its planes (color=0 at 1024, and
              detail=0 for a filled pass), its evened frames (exposure=8) where the page cannot even it; a toss-up's
              other kind (a mosaic's movie frames, a movie's force=1 mosaics)
  thumb       /frames/thumb.webp at 256 for each highlight (<site>/data/highlights.json) in the stretch
  table       WP2's tables and alias shards as they are, under table/<tag>/ (keys.json tables)
Every URL goes through keys.canonical(); one the policy refuses is never published. Each object carries its
Content-Type and its X-* report as metadata the way headers.json storage says (whole, trimmed to the fields the page
reads, or a sidecar object <key>.h.json); a negative answer (Auto center's 404) is a marker object. The manifest
(manifest.schema.json) goes up last and its key is printed: WP8 points the Worker's MANIFEST_KEY at it.

It goes year by year, in parallel; an object whose bytes (md5, R2's ETag) and metadata are already there is skipped,
so a run stopped part way picks up where it was and a second run uploads nothing. The state folder (--state) keeps a
ledger of what each target holds and published.json: objects and bytes per family and year, and every URL that was
enumerated but not published, with the reason. The mirror holds each object at its key, its metadata beside it as
<key>.meta.json in the shape of R2's put() options ({"httpMetadata": {"contentType"}, "customMetadata": {...}}), which
web/worker/tools/mirror.mjs (WP4) loads into a local R2.
"""
import argparse
import base64
import collections
import concurrent.futures
import datetime
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PUBLIC = os.path.join(REPO, "web", "public")
sys.path.insert(0, HERE)
sys.path.insert(0, PUBLIC)
import keys  # noqa: E402  (light: the contracts only)

with open(os.path.join(PUBLIC, "headers.json")) as _fh:
    HEADERS = json.load(_fh)
BUDGET = HEADERS["storage"]["metadata_budget_bytes"]
MARKER_BODY_MAX = 512
FAMILIES = tuple(keys.KEYS["families"]["list"])
ROUTE = {r["id"]: r for r in keys.POLICY["routes"]}

# what prebuild makes, at the sizes policy.json builds (a size here that a route does not build would be snapped by
# keys.canonical to one it does, and published once)
FRAME_SIZES = (128, 512, 1024)
COLOR_SIZES = ("512", "1024", "full")
PROCESSED_SIZES = (256, 512, 1024)
PASS_SIZES = (512, 1024)
STRIP_SIZE = 128
PLANE_SIZE = 1024
EVENED = 8   # obs_mosaic.EXPOSURE_SMOOTH, read from the module at enumeration


def compact(obj):
    return json.dumps(obj, separators=(",", ":"))


def md5_hex(data):
    return hashlib.md5(data).hexdigest()


def meta_size(custom):
    return sum(len(k.encode()) + len(v.encode()) for k, v in custom.items())


# ---------- storage: an answer as objects (headers.json storage and markers) ----------
def objects_for(answer, route, key, read):
    """[(key, bytes, content type, customMetadata, role)] for one resolved answer: the picture (with its report kept
    whole, trimmed or in a sidecar) or a marker. read(answer) gives a file answer's bytes."""
    if answer.kind == "negative":
        view = answer.headers.get("X-Center")
        custom = {"x-status": str(answer.status)}
        if view is not None:
            custom["x-center"] = compact(json.loads(view))
        body = answer.body or b""
        if len(body) <= MARKER_BODY_MAX:
            custom["x-body"] = body.decode("utf-8", "replace")
        return [(key, b"", HEADERS["markers"]["content_type"], custom, "marker")]
    data = read(answer)
    header = route.get("header")
    custom, out, role = {}, [], "whole"
    if header and answer.headers.get(header) is not None:
        report = json.loads(answer.headers[header])
        name = header.lower()
        custom = {name: compact(report)}
        if meta_size(custom) > BUDGET:
            keep = HEADERS["page_reads"].get(header, [])
            trimmed = {name: compact({k: v for k, v in report.items() if k in keep}) if isinstance(report, dict)
                       else compact(report), "x-report-trimmed": "1"}
            if meta_size(trimmed) <= BUDGET:
                custom, role = trimmed, "trimmed"
            else:
                custom, role = {"x-report-sidecar": "1"}, "sidecar"
                out.append((key + ".h.json", compact(report).encode(), "application/json", {}, "sidecar-object"))
    out.insert(0, (key, data, answer.mime or "application/octet-stream", custom, role))
    return out


# ---------- targets ----------
class Mirror:
    """A folder in R2's shape: each object at its key, its metadata at <key>.meta.json."""
    name = "mirror"

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.id = "dir:" + self.root

    def _path(self, key):
        path = os.path.normpath(os.path.join(self.root, key))
        if not path.startswith(self.root + os.sep):
            raise ValueError(f"key outside the mirror: {key}")
        return path

    def held(self, key):
        """(md5, content type, customMetadata) of the object at key, or None."""
        path = self._path(key)
        try:
            with open(path, "rb") as fh:
                digest = md5_hex(fh.read())
            with open(path + ".meta.json") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            return None
        return digest, meta.get("httpMetadata", {}).get("contentType"), meta.get("customMetadata", {})

    def put(self, key, data, content_type, custom):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        meta = compact({"httpMetadata": {"contentType": content_type}, "customMetadata": custom}).encode()
        for target, blob in ((path, data), (path + ".meta.json", meta)):
            fd, part = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".part-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
            os.replace(part, target)

    def read(self, key):
        with open(self._path(key), "rb") as fh:
            return fh.read()


class R2:
    """R2 through its S3 API (Signature Version 4), standard library only. Credentials from the environment: R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (R2_ENDPOINT overrides the account's endpoint, for a test
    server). The bucket's access is not touched: it stays as Sam made it, private."""
    name = "r2"
    REGION = "auto"

    def __init__(self, env=None):
        env = os.environ if env is None else env
        missing = [k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET") if not env.get(k)]
        if missing:
            raise SystemExit("R2 credentials come from the environment only; missing: " + ", ".join(missing))
        self.bucket = env["R2_BUCKET"]
        self.endpoint = (env.get("R2_ENDPOINT") or f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com").rstrip("/")
        self.access, self.secret = env["R2_ACCESS_KEY_ID"], env["R2_SECRET_ACCESS_KEY"]
        self.id = f"r2:{self.endpoint}/{self.bucket}"
        self.host = urllib.parse.urlsplit(self.endpoint).netloc

    def _url_path(self, key):
        return "/" + urllib.parse.quote(self.bucket, safe="") + "/" + urllib.parse.quote(key, safe="/-_.~")

    def _sign(self, method, path, headers, payload_hash):
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        headers = dict(headers, host=self.host, **{"x-amz-date": amz_date, "x-amz-content-sha256": payload_hash})
        names = sorted(k.lower() for k in headers)
        lower = {k.lower(): str(v).strip() for k, v in headers.items()}
        canonical = "\n".join([method, path, "", "".join(f"{n}:{lower[n]}\n" for n in names), ";".join(names), payload_hash])
        scope = f"{day}/{self.REGION}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        k = ("AWS4" + self.secret).encode()
        for part in (day, self.REGION, "s3", "aws4_request"):
            k = hmac.new(k, part.encode(), hashlib.sha256).digest()
        sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.access}/{scope}, SignedHeaders={';'.join(names)}, "
                                    f"Signature={sig}")
        return headers

    def _request(self, method, key, data=b"", headers=None, tries=5):
        path = self._url_path(key)
        for attempt in range(tries):
            h = self._sign(method, path, headers or {}, hashlib.sha256(data).hexdigest())
            req = urllib.request.Request(self.endpoint + path, data=data if method == "PUT" else None, method=method,
                                         headers=h)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, dict(r.headers.items()), r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404 and method == "HEAD":
                    return 404, {}, b""
                if e.code < 500 and e.code != 429:
                    raise RuntimeError(f"R2 {method} {key}: {e.code} {e.read()[:300]!r}")
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(min(30, 2 ** attempt))
        raise RuntimeError(f"R2 {method} {key}: gave up after {tries} tries")

    def held(self, key):
        status, h, _ = self._request("HEAD", key)
        if status != 200:
            return None
        h = {k.lower(): v for k, v in h.items()}
        custom = {k[len("x-amz-meta-"):]: v for k, v in h.items() if k.startswith("x-amz-meta-")}
        return h.get("etag", "").strip('"'), h.get("content-type"), custom

    def put(self, key, data, content_type, custom):
        headers = {"Content-Type": content_type, "Content-MD5": base64.b64encode(hashlib.md5(data).digest()).decode()}
        headers.update({f"x-amz-meta-{k}": v for k, v in custom.items()})
        status, h, _ = self._request("PUT", key, data, headers)
        etag = {k.lower(): v for k, v in h.items()}.get("etag", "").strip('"')
        if etag and etag != md5_hex(data):
            raise RuntimeError(f"R2 PUT {key}: ETag {etag} is not the object's md5")

    def read(self, key):
        return self._request("GET", key)[2]


class Ledger:
    """What a target holds, as this publisher put it there: key -> (md5, content type, metadata digest). A key whose
    entry matches is not asked of the target again (R2: no HEAD per object); --verify asks anyway."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS held (key TEXT PRIMARY KEY, md5 TEXT, ctype TEXT, meta TEXT)")
        self.lock = threading.Lock()

    @staticmethod
    def digest(custom):
        return hashlib.sha256(compact(dict(sorted(custom.items()))).encode()).hexdigest()[:16]

    def matches(self, key, md5, ctype, custom):
        with self.lock:
            row = self.db.execute("SELECT md5, ctype, meta FROM held WHERE key=?", (key,)).fetchone()
        return row == (md5, ctype, self.digest(custom))

    def note(self, key, md5, ctype, custom):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO held VALUES (?,?,?,?)", (key, md5, ctype, self.digest(custom)))
            self.db.commit()


def store(target, ledger, objects, verify=False):
    """Puts each object unless the target holds it already (same md5, content type and metadata). Returns
    [(key, bytes, role, written)]."""
    out = []
    for key, data, ctype, custom, role in objects:
        digest = md5_hex(data)
        same = ledger.matches(key, digest, ctype, custom) if ledger and not verify else False
        if not same:
            held = target.held(key)
            same = held is not None and held[0] == digest and held[1] == ctype and held[2] == custom
            if not same:
                target.put(key, data, ctype, custom)
            if ledger:
                ledger.note(key, digest, ctype, custom)
        out.append((key, len(data), role, not same))
    return out


# ---------- what to publish ----------
def url(path, **q):
    q = {k: v for k, v in q.items() if v is not None}
    return path + ("?" + urllib.parse.urlencode(q, safe=",") if q else "")


def units(cache, spans, site=None, families=FAMILIES, log=print):
    """Every unit of work, as {"family", "year", "urls": [...], "as_is": [...]}: urls are published as they resolve;
    as_is (composites and processed frames) only when the first url's answer is Auto center's 404, which the page
    follows by asking the picture as it is. In time order. Needs the pipeline (prebuild, frame_server, obs_mosaic)."""
    import prebuild
    import frame_server  # noqa: F401
    import obs_mosaic
    import reel
    global EVENED
    EVENED = obs_mosaic.EXPOSURE_SMOOTH
    idx, _ = reel.load_index()
    time_of = dict(zip(idx["id"].tolist(), idx["seconds_1970"].astype(float).tolist()))

    def year(frame_id):
        t = time_of.get(frame_id)
        return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).year if t is not None else 0

    def cut(phase, todo):
        return prebuild.within(phase, todo, spans) if spans else todo

    out = []
    if {"frame", "archive", "processed"} & set(families):
        ids = [t[0] for t in cut("frames", [(i, None) for i in prebuild.frame_ids()])]
        log(f"frames in the stretch: {len(ids)}")
        for i in ids:
            y = year(i)
            if "frame" in families:
                out.append({"family": "frame", "year": y,
                            "urls": [url(f"/frames/{i}.webp", size=s) for s in FRAME_SIZES]})
            if "archive" in families:
                out.append({"family": "archive", "year": y, "urls": [f"/frames/{i}.png"]})
            if "processed" in families:
                out.append({"family": "processed", "year": y,
                            "urls": [url(f"/frames/processed/{i}.webp", size=s, center=1) for s in PROCESSED_SIZES],
                            "as_is": [url(f"/frames/processed/{i}.webp", size=s) for s in PROCESSED_SIZES]})
    if "composite" in families:
        sets = cut("composites", [("_".join(s), s) for s in prebuild.page_sets()])
        log(f"filter sets in the stretch: {len(sets)}")
        for _, s in sets:
            ids = ",".join(s)
            out.append({"family": "composite", "year": year(s[-1]),
                        "urls": [url("/frames/color.webp", ids=ids, size=z, center=1) for z in COLOR_SIZES],
                        "as_is": [url("/frames/color.webp", ids=ids, size=z) for z in COLOR_SIZES]})
    if "pass" in families:
        movie_keys = {tuple(u["key"]) for u in prebuild.movie_passes()}
        mosaic_keys = {tuple(u["key"]) for u in prebuild.mosaic_passes()}
        passes = cut("movies", [("_".join(map(str, u["key"])), u) for u in prebuild.all_passes()
                                if tuple(u["key"]) in mosaic_keys | movie_keys])
        log(f"passes in the stretch: {len(passes)}")
        for _, u in passes:
            for unit in pass_units(u, cache, tuple(u["key"]) in movie_keys, obs_mosaic):
                unit["year"] = year(unit.pop("frame"))
                out.append(unit)
    if "thumb" in families:
        hints = highlight_hints(site)
        if hints is None:
            out.append({"family": "thumb", "year": 0, "urls": [], "missing": "no --site with data/highlights.json"})
        else:
            cuts = [(prebuild.slices.seconds(a) if a else -float("inf"), prebuild.slices.seconds(b) if b else float("inf"))
                    for a, b in spans or [(None, None)]]
            for hint in hints:
                ids = [hint.get("mosaic"), hint.get("frame")] + list(hint.get("color") or [])
                ts = [time_of[i] for i in ids if i in time_of]
                if not ts or not any(a <= t < b for t in ts for a, b in cuts):
                    continue
                q = {k: (",".join(v) if isinstance(v, list) else v) for k, v in hint.items()}
                out.append({"family": "thumb", "year": year(next(i for i in ids if i in time_of)),
                            "urls": [url("/frames/thumb.webp", **dict(sorted(q.items())))]})
    out.sort(key=lambda x: x["year"])
    return out


def pass_units(u, cache, movie_pass, om):
    """A pass's pictures as prebuild makes them (make_pass for the mosaics and movies phases and, for a movie pass,
    the strips phase; make_planes; make_evened), each frame its own unit. Whether a pass is filled (planes before
    detail) and whether the page evens it are read from the cache as resolve() reads it (cache only); where that is
    not known the pictures are listed, and resolve() says whether they are there."""
    import resolve
    kind, frames = u.get("kind"), u["frames"]
    filled = evens = None
    try:
        with resolve.cache_only():
            p = om.plan(u, cache)
            filled = om.sharpens(p["display_scale"])
            if movie_pass:
                evens = om.page_evens(u, cache, True, True)
    except BaseException as e:   # noqa: BLE001  (NotMade: a chain not kept; any other: the pass's plan not kept)
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
    last = len(frames) - 1
    for j, f in enumerate(frames):
        fid, urls = f[1], []
        sizes = PASS_SIZES + ((STRIP_SIZE,) if movie_pass else ())
        for size in sizes:
            if kind == "mosaic_movie":
                if size != STRIP_SIZE:
                    urls.append(url(f"/frames/movie/{fid}.webp", mode="rolling", size=size))
            elif u["mosaic"]:
                if size != STRIP_SIZE:
                    urls.append(url(f"/frames/mosaic/{fid}.webp", size=size))
            else:
                urls.append(url(f"/frames/movie/{fid}.webp", size=size))
            if size != STRIP_SIZE and u.get("tossup") and kind == "mosaic":
                urls.append(url(f"/frames/movie/{fid}.webp", size=size))
            elif size != STRIP_SIZE and u.get("tossup") and kind == "movie":
                urls.append(url(f"/frames/mosaic/{fid}.webp", size=size, force=1))
        if u["mosaic"] and kind != "mosaic_movie" and j == last:
            urls.append(url(f"/frames/mosaic/{fid}.webp", size="full"))
        if movie_pass:
            urls.append(url(f"/frames/movie/{fid}.webp", size=PLANE_SIZE, color=0))
            if filled is not False:
                urls.append(url(f"/frames/movie/{fid}.webp", size=PLANE_SIZE, color=0, detail=0))
            if evens is not True:
                urls += [url(f"/frames/movie/{fid}.webp", size=s, exposure=EVENED) for s in PASS_SIZES]
        yield {"family": "pass", "frame": fid, "urls": urls,
               "unsure": {"detail=0": filled is None, "exposure": evens is None}}


def highlight_hints(site):
    """The thumbnail hints of the Highlights window (<site>/data/highlights.json), as frame_server.warm_thumbs reads
    them; None without the file."""
    if not site:
        return None
    try:
        with open(os.path.join(site, "data", "highlights.json")) as fh:
            entries = json.load(fh)
    except (OSError, ValueError):
        return None
    out = []
    for e in entries:
        if e.get("kind") == "milestone" or not e.get("thumb"):
            continue
        out.append({k: e["thumb"][k] for k in ("mosaic", "color", "frame") if e["thumb"].get(k)})
    return out


def table_files(folder):
    """(relative path, absolute path) of each file WP2's tables phase wrote under <folder>/table/, sorted."""
    root = os.path.join(folder, "table")
    out = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            if n.endswith(".json") and not n.startswith("."):
                full = os.path.join(dirpath, n)
                out.append((os.path.relpath(full, root).replace(os.sep, "/"), full))
    return sorted(out)


# ---------- the work ----------
_W = {}


def _init(cache, target_spec, state, tags, verify, dry):
    import resolve
    _W.update(cache=cache, tags=tags, verify=verify, dry=dry, resolve=resolve)
    resolve.prepare()
    _W["target"] = make_target(target_spec)
    _W["ledger"] = Ledger(os.path.join(state, "ledger.sqlite")) if not dry else None


def make_target(spec):
    kind, _, arg = spec.partition(":")
    return Mirror(arg) if kind == "dir" else R2() if kind == "r2" else None


def read_answer(answer):
    import resolve
    reader = getattr(resolve, "read", None)
    if reader is not None:
        return reader(answer)
    with open(answer.path, "rb") as fh:
        return fh.read()


def one(u, tags=None, cache=None, resolve_fn=None, target=None, ledger=None, verify=False, dry=False, read_fn=None):
    """Publishes one unit; returns its records: {url, key, family, year, outcome, bytes, objects, role, reason}.
    outcome: published (written now), held (already there), marker, missing, refused."""
    tags = tags if tags is not None else _W["tags"]
    cache = cache or _W.get("cache")
    resolve_fn = resolve_fn or _W["resolve"].resolve
    target = target if target is not None else _W.get("target")
    ledger = ledger if ledger is not None else _W.get("ledger")
    verify = verify or _W.get("verify", False)
    dry = dry or _W.get("dry", False)
    recs = []
    if u.get("missing"):
        return [{"url": None, "key": None, "family": u["family"], "year": u["year"], "outcome": "missing",
                 "bytes": 0, "reason": u["missing"]}]
    todo, as_is = list(u["urls"]), list(u.get("as_is") or [])
    while todo:
        link = todo.pop(0)
        rec = {"url": link, "family": u["family"], "year": u["year"], "bytes": 0}
        ans = keys.canonical("GET", link, tags)
        rec["key"] = ans.get("key")
        if ans["store"] == "refused":
            rec.update(outcome="refused", reason=ans["refused"])
            recs.append(rec)
            continue
        route = ROUTE[ans["route"]]
        rec["route"] = ans["route"]
        parts = urllib.parse.urlsplit(link)
        answer = resolve_fn(parts.path, urllib.parse.parse_qs(parts.query), cache)
        if answer.kind == "none":
            rec.update(outcome="missing", reason="not in the cache (resolve: none)")
            recs.append(rec)
            continue
        if answer.kind == "negative" and not route.get("markers"):
            rec.update(outcome="missing", reason=f"a {answer.status} the policy keeps no marker for")
            recs.append(rec)
            continue
        if answer.kind == "negative" and as_is:
            todo += as_is   # the page asks the picture as it is next
            as_is = []
        objs = objects_for(answer, route, ans["key"], read_fn or read_answer)
        if dry:
            written = [(k, len(d), role, True) for k, d, _, _, role in objs]   # (what would be written)
        else:
            written = store(target, ledger, objs, verify)
        rec["bytes"] = sum(n for _, n, _, _ in written)
        rec["objects"] = len(written)
        rec["role"] = written[0][2]
        rec["meta"] = meta_size(objs[0][3])
        rec["outcome"] = "marker" if answer.kind == "negative" else (
            "published" if any(w for *_, w in written) else "held")
        recs.append(rec)
    return recs


def _batch(us):
    return [r for u in us for r in one(u)]


def tables_units(folder, tags):
    """Each WP2 table file as an object under table/<tag>/ (keys.json tables)."""
    tag = tags["table"]
    return [(f"table/{tag}/{rel}", full) for rel, full in table_files(folder)]


def publish_tables(folder, tags, target, ledger, verify, dry):
    recs = []
    files = tables_units(folder, tags) if os.path.isdir(os.path.join(folder, "table")) else None
    if files is None:
        return [{"url": None, "key": None, "family": "table", "year": 0, "outcome": "missing", "bytes": 0,
                 "reason": f"no tables at {folder}/table (WP2's tables phase)"}]
    for key, full in files:
        with open(full, "rb") as fh:
            data = fh.read()
        objs = [(key, data, "application/json", {}, "whole")]
        written = [(key, len(data), "whole", True)] if dry else store(target, ledger, objs, verify)
        recs.append({"url": None, "key": key, "family": "table", "year": 0, "bytes": len(data), "objects": 1,
                     "outcome": "published" if written[0][3] else "held"})
    return recs


def git_commit():
    try:
        return subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def summary(recs):
    counts = collections.defaultdict(lambda: collections.defaultdict(lambda: {"objects": 0, "bytes": 0}))
    outcomes = collections.Counter()
    roles = collections.Counter()
    missing, refused = [], []
    meta = collections.defaultdict(list)
    for r in recs:
        outcomes[r["outcome"]] += 1
        if r["outcome"] in ("published", "held", "marker"):
            c = counts[r["family"]][str(r["year"])]
            c["objects"] += r.get("objects", 1)
            c["bytes"] += r["bytes"]
            roles[r.get("role", "whole")] += 1
            if r.get("route"):
                meta[(r["route"], r.get("role", "whole"))].append(r.get("meta", 0))
        elif r["outcome"] == "missing":
            missing.append({k: r.get(k) for k in ("url", "key", "family", "year", "reason")})
        elif r["outcome"] == "refused":
            refused.append({k: r.get(k) for k in ("url", "family", "year", "reason")})
    total = {"objects": sum(c["objects"] for f in counts.values() for c in f.values()),
             "bytes": sum(c["bytes"] for f in counts.values() for c in f.values())}
    per_family = {f: {"objects": sum(c["objects"] for c in ys.values()), "bytes": sum(c["bytes"] for c in ys.values())}
                  for f, ys in counts.items()}
    return {"total": total, "families": per_family, "by_year": {f: dict(sorted(ys.items())) for f, ys in sorted(counts.items())},
            "outcomes": dict(outcomes), "storage": dict(roles), "metadata": metadata_sizes(meta),
            "missing": missing, "refused": refused}


def metadata_sizes(meta):
    """Per route and storage (whole, trimmed, sidecar, marker): objects and their metadata bytes, p50, p95 and max,
    against headers.json's budget."""
    out = []
    for (route, role), xs in sorted(meta.items()):
        xs = sorted(xs)
        out.append({"route": route, "storage": role, "objects": len(xs), "p50": xs[len(xs) // 2],
                    "p95": xs[min(len(xs) - 1, int(0.95 * (len(xs) - 1) + 0.5))], "max": xs[-1], "budget": BUDGET})
    return out


def manifest(publish_id, commit, versions, tags, slices_answer, version, counts):
    return {"publish_id": publish_id, "published": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": commit, "versions": versions, "families": tags, "slices": slices_answer, "version": version,
            "counts": counts}


def published_slices(cache, versions, spans):
    """/frames/slices.json for what was published: what the cache covers (slices.covered) cut to the stretch asked."""
    import slices
    got = slices.covered(cache, versions)
    if spans:
        have = [tuple(s) for s in got["spans"]] if got["spans"] is not None else [(None, None)]
        cut = slices.intersect(slices.merge(have), slices.merge(spans))
        got["spans"] = [list(s) for s in cut]
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    to = ap.add_mutually_exclusive_group(required=True)
    to.add_argument("--to-dir", help="write the mirror here")
    to.add_argument("--to-r2", action="store_true", help="upload to R2 (credentials from the environment)")
    ap.add_argument("--state", help="ledger and published.json (default <to-dir>.state, or ~/.cassini-publish/<bucket>)")
    ap.add_argument("--site", help="the page folder (data/highlights.json, version.json)")
    ap.add_argument("--tables", help="WP2's tables output (default <cache>/public-tables)")
    ap.add_argument("--years")
    ap.add_argument("--from", dest="since")
    ap.add_argument("--until")
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--verify", action="store_true", help="ask the target for every object, past the ledger")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="at most this many units per family (a quick look)")
    args = ap.parse_args(argv)

    import prebuild
    import frame_server
    cache = os.path.abspath(args.cache)
    families = [f for f in args.families.split(",") if f]
    unknown = set(families) - set(FAMILIES)
    if unknown:
        ap.error(f"no such family: {', '.join(sorted(unknown))}")
    versions = frame_server.picture_versions()
    tags = keys.family_tags(versions)
    spans = prebuild.spans_of(args)
    if spans is None:
        import slices
        covered = slices.covered(cache, versions)["spans"]
        spans = [tuple(s) for s in covered] if covered else None
    if args.to_r2:
        target_spec = "r2:"
        state = args.state or os.path.expanduser(f"~/.cassini-publish/{os.environ.get('R2_BUCKET', 'r2')}")
        make_target(target_spec)   # credentials checked before any work
    else:
        target_spec = "dir:" + os.path.abspath(args.to_dir)
        state = args.state or os.path.abspath(args.to_dir).rstrip("/") + ".state"
    os.makedirs(state, exist_ok=True)
    commit = git_commit()
    publish_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + commit[:12]
    print(f"publish {publish_id}: cache {cache}, stretch {spans or 'the whole mission'}, to {target_spec}", flush=True)
    print("family tags: " + ", ".join(f"{f} {t}" for f, t in tags.items()), flush=True)

    started = time.monotonic()
    work = units(cache, spans, args.site, families, log=lambda m: print(m, flush=True))
    if args.limit:
        seen = collections.Counter()
        kept = []
        for u in work:
            seen[u["family"]] += 1
            if seen[u["family"]] <= args.limit:
                kept.append(u)
        work = kept
    print(f"{len(work)} units, {sum(len(u['urls']) for u in work)} URLs (before Auto center's as-is pictures) "
          f"in {time.monotonic() - started:.0f} s", flush=True)

    recs = []
    by_year = collections.defaultdict(list)
    for u in work:
        by_year[u["year"]].append(u)
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.jobs), initializer=_init,
                                                initargs=(cache, target_spec, state, tags, args.verify, args.dry_run)) as pool:
        for y in sorted(by_year):
            us = by_year[y]
            size = max(1, min(200, len(us) // (args.jobs * 4) or 1))
            batches = [us[k:k + size] for k in range(0, len(us), size)]
            t0 = time.monotonic()
            for got in pool.map(_batch, batches):
                recs += got
            s = summary([r for r in recs if r["year"] == y])
            print(f"{y}: {s['total']['objects']} objects, {s['total']['bytes'] / 1e6:.1f} MB, "
                  f"outcomes {s['outcomes']} in {time.monotonic() - t0:.0f} s", flush=True)
            write_json(os.path.join(state, "published.json"), dict(summary(recs), publish_id=publish_id, partial=True))

    target = make_target(target_spec) if not args.dry_run else None
    ledger = Ledger(os.path.join(state, "ledger.sqlite")) if not args.dry_run else None
    if "table" in families:
        recs += publish_tables(args.tables or os.path.join(cache, "public-tables"), tags, target, ledger,
                               args.verify, args.dry_run)

    s = summary(recs)
    site = os.path.abspath(args.site) if args.site else None
    man = manifest(publish_id, commit, versions, tags, published_slices(cache, versions, spans),
                   json.loads(json.dumps(frame_server.site_version(site), default=str)),
                   {"total": s["total"], "families": s["families"], "by_year": s["by_year"]})
    man_key = keys.KEYS["manifest"]["key_format"].format(publish_id=publish_id)
    report = dict(s, publish_id=publish_id, manifest_key=man_key, target=target_spec, cache=cache,
                  spans=spans, commit=commit, seconds=round(time.monotonic() - started), partial=False,
                  dry_run=args.dry_run, urls=sum(1 for r in recs if r.get("url")))
    if not args.dry_run:
        store(target, None, [(man_key, json.dumps(man, indent=1).encode(), "application/json", {}, "manifest")])
    write_json(os.path.join(state, "published.json"), report)
    print(f"done in {time.monotonic() - started:.0f} s: {s['total']['objects']} objects, {s['total']['bytes'] / 1e9:.2f} GB; "
          f"outcomes {s['outcomes']}; storage {s['storage']}; {len(s['missing'])} missing, {len(s['refused'])} refused",
          flush=True)
    print(f"published.json: {os.path.join(state, 'published.json')}")
    print(("(dry run, nothing written) " if args.dry_run else "") + f"manifest: {man_key}")
    return 0


def write_json(path, obj):
    part = path + ".part"
    with open(part, "w") as fh:
        json.dump(obj, fh, indent=1, default=str)
    os.replace(part, path)


if __name__ == "__main__":
    sys.exit(main())
