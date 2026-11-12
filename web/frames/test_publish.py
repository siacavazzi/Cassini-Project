#!/usr/bin/env python3
"""
Checks the publisher (web/frames/publish.py, WP3).

  python web/frames/test_publish.py
      the parts that need no picture cache: how a report is kept (whole, trimmed, sidecar) and a marker, the mirror's
      shape and its metadata round trip, the R2 client against a local stand-in for R2's S3 API (signed requests, MD5,
      metadata as x-amz-meta-*), a second store writing nothing, refused and missing URLs, and the manifest's shape

  CASSINI_PUBLISH_CACHE=CACHE CASSINI_PUBLISH_MIRROR=MIRROR [CASSINI_PUBLISH_SERVER=http://HOST:PORT] \\
    python web/frames/test_publish.py
      on a mirror publish.py --to-dir wrote from CACHE (its state folder MIRROR.state beside it), with the pipeline's
      environment (CASSINI_DATA, ...) and resolve() filled in (WP1): every URL publish.py enumerates is published, a
      marker, or listed missing with a reason; the manifest validates and names every family; 1,000 sampled objects
      have the bytes and the report of the frame server's own answer (a normal frame server on CACHE at
      CASSINI_PUBLISH_SERVER; without it, of resolve()); and a second publish into the mirror writes nothing.
"""
import hashlib
import http.server
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish  # noqa: E402
from publish import keys  # noqa: E402

FAILED = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        FAILED.append(what)


class FakeAnswer:
    def __init__(self, kind, path=None, mime=None, headers=None, status=200, body=None):
        self.kind, self.path, self.mime, self.headers, self.status, self.body = kind, path, mime, headers or {}, status, body


# ---------- storage ----------
def test_storage():
    route = publish.ROUTE["color"]
    small = {"observation": "ISS_X", "ids": ["N1", "N2", "N3"], "kind": "color", "width": 1024, "height": 1024}
    a = FakeAnswer("file", "/x.webp", "image/webp", {"X-Composite": json.dumps(small)})
    objs = publish.objects_for(a, route, "composite/t1/frames/color.webp~ids=a", lambda _: b"PIC")
    check(len(objs) == 1 and objs[0][3] == {"x-composite": publish.compact(small)} and objs[0][4] == "whole",
          "a small report is kept whole, as compact JSON under the header's lower-case name")
    check(objs[0][2] == "image/webp" and objs[0][1] == b"PIC", "the picture keeps its bytes and content type")

    big = dict(small, notes=["x" * 100] * 40)   # a field the page does not read, past the budget
    objs = publish.objects_for(FakeAnswer("file", "/x", "image/webp", {"X-Composite": json.dumps(big)}), route, "k", lambda _: b"P")
    meta = objs[0][3]
    check(objs[0][4] == "trimmed" and meta.get("x-report-trimmed") == "1" and json.loads(meta["x-composite"]) == small,
          "a report over the budget is trimmed to the fields the page reads (headers.json page_reads)")
    check(publish.meta_size(meta) <= publish.BUDGET, "trimmed metadata fits the budget")

    huge = dict(small, why="y" * 3000)   # a field the page reads, past the budget even trimmed
    objs = publish.objects_for(FakeAnswer("file", "/x", "image/webp", {"X-Composite": json.dumps(huge)}), route, "k", lambda _: b"P")
    check(len(objs) == 2 and objs[0][3] == {"x-report-sidecar": "1"} and objs[1][0] == "k.h.json"
          and json.loads(objs[1][1]) == huge and objs[1][2] == "application/json",
          "a report too big even trimmed goes whole into a sidecar object <key>.h.json")

    view = {"centre": False, "why": "a sky pass"}
    neg = FakeAnswer("negative", status=404, headers={"X-Center": json.dumps(view)}, body=json.dumps(view).encode())
    objs = publish.objects_for(neg, route, "k", None)
    check(objs == [("k", b"", "application/json", {"x-status": "404", "x-center": publish.compact(view),
                                                    "x-body": json.dumps(view)}, "marker")],
          "Auto center's 404 is an empty marker object with x-status, x-center and x-body (headers.json markers)")

    frame = publish.objects_for(FakeAnswer("file", "/x", "image/webp"), publish.ROUTE["frame"], "k", lambda _: b"F")
    check(frame[0][3] == {}, "a route with no report keeps no metadata")


# ---------- targets ----------
def test_mirror(tmp):
    m = publish.Mirror(os.path.join(tmp, "mirror"))
    key = "composite/tabc/frames/color.webp~center=1&ids=N1500000000_1,N1500000001_1&size=1024"
    custom = {"x-composite": '{"a":1}'}
    led = publish.Ledger(os.path.join(tmp, "state", "ledger.sqlite"))
    first = publish.store(m, led, [(key, b"PIC", "image/webp", custom, "whole")])
    check(first[0][3] is True, "the mirror writes a new object")
    with open(os.path.join(m.root, key + ".meta.json")) as fh:
        meta = json.load(fh)
    check(meta == {"httpMetadata": {"contentType": "image/webp"}, "customMetadata": custom},
          "metadata sits beside the object as <key>.meta.json in the shape of R2's put() options (WP4's loader)")
    check(m.held(key) == (hashlib.md5(b"PIC").hexdigest(), "image/webp", custom), "the mirror reads its object back")
    again = publish.store(m, led, [(key, b"PIC", "image/webp", custom, "whole")])
    check(again[0][3] is False, "the same object again is not written")
    fresh = publish.store(m, None, [(key, b"PIC", "image/webp", custom, "whole")])
    check(fresh[0][3] is False, "without the ledger the target's own md5 and metadata say it is there")
    changed = publish.store(m, led, [(key, b"PIC", "image/webp", {"x-composite": '{"a":2}'}, "whole")])
    check(changed[0][3] is True, "changed metadata is written again")
    try:
        m._path("../outside")
        check(False, "a key cannot leave the mirror")
    except ValueError:
        check(True, "a key cannot leave the mirror")


class FakeS3(http.server.BaseHTTPRequestHandler):
    objects, seen = {}, []

    def log_message(self, *a):
        pass

    def _checks(self, body):
        auth = self.headers.get("Authorization", "")
        FakeS3.seen.append((self.command, self.path, dict(self.headers)))
        ok = auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDTEST/") and "/auto/s3/aws4_request" in auth \
            and "Signature=" in auth and self.headers.get("x-amz-content-sha256") == hashlib.sha256(body).hexdigest()
        if not ok:
            self.send_response(403)
            self.end_headers()
        return ok

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not self._checks(body):
            return
        import base64
        if self.headers.get("Content-MD5") != base64.b64encode(hashlib.md5(body).digest()).decode():
            self.send_response(400)
            self.end_headers()
            return
        meta = {k.lower(): v for k, v in self.headers.items() if k.lower().startswith("x-amz-meta-")}
        FakeS3.objects[urllib.parse.unquote(self.path)] = (body, self.headers.get("Content-Type"), meta)
        self.send_response(200)
        self.send_header("ETag", '"' + hashlib.md5(body).hexdigest() + '"')
        self.end_headers()

    def _get(self, head):
        if not self._checks(b""):
            return
        got = FakeS3.objects.get(urllib.parse.unquote(self.path))
        if got is None:
            self.send_response(404)
            self.end_headers()
            return
        body, ctype, meta = got
        self.send_response(200)
        self.send_header("ETag", '"' + hashlib.md5(body).hexdigest() + '"')
        self.send_header("Content-Type", ctype)
        for k, v in meta.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        self._get(True)

    def do_GET(self):
        self._get(False)


def test_r2(tmp):
    try:
        publish.R2(env={})
        check(False, "R2 needs its credentials from the environment")
    except SystemExit as e:
        check("R2_ACCOUNT_ID" in str(e) and "R2_BUCKET" in str(e), "R2 needs its credentials from the environment")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeS3)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKIDTEST", "R2_SECRET_ACCESS_KEY": "s3cr3t-never-sent",
           "R2_BUCKET": "cassini-os", "R2_ENDPOINT": f"http://127.0.0.1:{srv.server_port}"}
    r2 = publish.R2(env=env)
    key = "pass/tabc/frames/movie/N1500000000_1.webp~color=0&size=1024"
    custom = {"x-movie": '{"frame":3,"of":9}', "x-report-trimmed": "1"}
    led = publish.Ledger(os.path.join(tmp, "r2state", "ledger.sqlite"))
    first = publish.store(r2, led, [(key, b"MOVIE", "image/webp", custom, "trimmed")])
    stored = FakeS3.objects.get("/cassini-os/" + key)
    check(first[0][3] and stored == (b"MOVIE", "image/webp", {f"x-amz-meta-{k}": v for k, v in custom.items()}),
          "R2 gets the object with its content type and metadata as x-amz-meta-* (R2's customMetadata), signed, MD5 checked")
    check(r2.held(key) == (hashlib.md5(b"MOVIE").hexdigest(), "image/webp", custom), "a HEAD reads the ETag and metadata back")
    n = len(FakeS3.seen)
    again = publish.store(r2, led, [(key, b"MOVIE", "image/webp", custom, "trimmed")])
    check(not again[0][3] and len(FakeS3.seen) == n, "a second store asks nothing of R2 (the ledger holds it)")
    verify = publish.store(r2, led, [(key, b"MOVIE", "image/webp", custom, "trimmed")], verify=True)
    check(not verify[0][3] and [s[0] for s in FakeS3.seen[n:]] == ["HEAD"], "--verify asks with one HEAD and writes nothing")
    check(all("s3cr3t-never-sent" not in json.dumps(s) for s in FakeS3.seen), "the secret key is never sent")
    r2.SINGLE_PUT_MAX = 4
    try:
        r2.put("big", b"12345", "image/webp", {})
        check(False, "an object past one PUT's limit is refused, never sent as multipart (its ETag would not be its md5)")
    except RuntimeError:
        check("/cassini-os/big" not in FakeS3.objects,
              "an object past one PUT's limit is refused, never sent as multipart (its ETag would not be its md5)")
    check(r2._url_path("a/b~c=1&d=2,3") == "/cassini-os/a/b~c%3D1%26d%3D2%2C3", "keys are escaped in the S3 path")
    srv.shutdown()


def test_one():
    tags = {f: "t000000000000" for f in publish.FAMILIES}
    refused = publish.one({"family": "pass", "year": 2004, "urls": ["/frames/movie/N1500000000_1.webp?trail=3"]},
                          tags=tags, cache="/nowhere", resolve_fn=lambda *a: 1 / 0, target=None, ledger=None)
    check(refused[0]["outcome"] == "refused" and "trail" in refused[0]["reason"],
          "a URL the policy refuses is never resolved or published")
    from resolve import NONE
    missing = publish.one({"family": "frame", "year": 2004, "urls": ["/frames/N1500000000_1.webp?size=1024"]},
                          tags=tags, cache="/nowhere", resolve_fn=lambda *a: NONE, target=None, ledger=None)
    check(missing[0]["outcome"] == "missing" and missing[0]["key"] == "frame/t000000000000/frames/N1500000000_1.webp~size=1024"
          and missing[0]["reason"], "a URL the cache cannot answer is listed missing, with its key and a reason")
    view = {"centre": False, "why": "sky"}
    asked = []

    def fake(path, q, cache):
        asked.append((path, q))
        if q.get("center") == ["1"]:
            return FakeAnswer("negative", status=404, headers={"X-Center": json.dumps(view)}, body=json.dumps(view).encode())
        return FakeAnswer("file", "/p", "image/webp", {"X-Composite": "{}"})
    recs = publish.one({"family": "processed", "year": 2004,
                        "urls": ["/frames/processed/N1500000000_1.webp?size=512&center=1"],
                        "as_is": ["/frames/processed/N1500000000_1.webp?size=512"]},
                       tags=tags, cache="/c", resolve_fn=fake, target=None, ledger=None, dry=True,
                       read_fn=lambda a: b"P")
    check([r["outcome"] for r in recs] == ["marker", "published"] and recs[1]["key"].endswith("N1500000000_1.webp"),
          "Auto center's 404 is published as a marker and the picture as it is follows it")
    recs = publish.one({"family": "processed", "year": 2004,
                        "urls": ["/frames/processed/N1500000000_1.webp?size=512&center=1"],
                        "as_is": ["/frames/processed/N1500000000_1.webp?size=512"]},
                       tags=tags, cache="/c", resolve_fn=lambda *a: FakeAnswer("file", "/p", "image/webp", {}),
                       target=None, ledger=None, dry=True, read_fn=lambda a: b"P")
    check(len(recs) == 1, "a centred picture is published without its as-is copy")

    calls, slow = [], publish.SLOW
    publish.SLOW = -1   # every resolve counts as slow

    def nothing(path, q, cache):
        calls.append(path)
        return NONE
    gave_up = {}
    for n in (1, 2, 3):
        recs = publish.one({"family": "pass", "year": 2009, "pass": "P",
                            "urls": [f"/frames/mosaic/N150000000{n}_1.webp?size=1024"]},
                           tags=tags, cache="/c", resolve_fn=nothing, target=None, ledger=None, dry=True, gave_up=gave_up)
    publish.SLOW = slow
    busy = publish.one({"family": "pass", "year": 2009, "pass": "Q", "urls": ["/frames/mosaic/N1500000001_1.webp?size=512"]},
                       tags=tags, cache="/c", resolve_fn=lambda *a: FakeAnswer("busy", status=503), target=None,
                       ledger=None, dry=True, gave_up={})
    s = publish.summary(busy)
    check(busy[0]["outcome"] == "busy" and len(s["busy"]) == 1 and not s["missing"],
          "a busy answer (resolve()'s work budget ran out) is never counted missing: it is kept to be asked again, "
          "and listed busy if it stays so")
    check(len(calls) == 1 and recs[0]["outcome"] == "missing" and "earlier frame" in recs[0]["reason"],
          "a route resolve() gives up on slowly is not asked again for the rest of the pass, and is listed missing")


FAKE_RESOLVER = """
import os
from resolve import Answer, NONE
BUDGET = float(os.environ.get("CASSINI_RESOLVE_BUDGET", "5"))
def prepare():
    pass
def resolve(path, query, cache):
    if "N1500000001" in path:          # slow: answers only with a work budget of 30 s or more
        return Answer("file", 200, os.path.join(cache, "slow.webp"), "image/webp") if BUDGET >= 30 else Answer("busy", 503)
    if "N1500000003" in path:          # busy, then none once the budget lets it finish (a fit that ends at a refused write)
        return NONE if BUDGET >= 30 else Answer("busy", 503)
    if "N1500000002" in path:          # never within any budget
        return Answer("busy", 503)
    return Answer("file", 200, os.path.join(cache, "fast.webp"), "image/webp")
def read(answer):
    with open(answer.path, "rb") as fh:
        return fh.read()
"""


def test_busy_retry(tmp):
    """run_units then the busy rounds, as main() runs them, with a stand-in resolver in the worker processes."""
    import argparse
    import resolve
    if "busy" not in resolve.KINDS:
        check(True, "busy retry: skipped (this resolve.py has no busy answer yet)")
        return
    fake = os.path.join(tmp, "fakeres")
    os.makedirs(fake)
    with open(os.path.join(fake, "fake_resolver.py"), "w") as fh:
        fh.write(FAKE_RESOLVER)
    cache = os.path.join(tmp, "fcache")
    os.makedirs(cache)
    for name in ("fast", "slow"):
        with open(os.path.join(cache, name + ".webp"), "wb") as fh:
            fh.write(name.encode())
    old = {k: os.environ.get(k) for k in ("CASSINI_PUBLISH_RESOLVER", "PYTHONPATH", "CASSINI_RESOLVE_BUDGET")}
    os.environ["CASSINI_PUBLISH_RESOLVER"] = "fake_resolver"
    os.environ["PYTHONPATH"] = os.pathsep.join([fake, HERE] + ([old["PYTHONPATH"]] if old["PYTHONPATH"] else []))
    os.environ.pop("CASSINI_RESOLVE_BUDGET", None)
    sys.path.insert(0, fake)   # (spawned workers start with the parent's sys.path)
    try:
        tags = {f: "t000000000000" for f in publish.FAMILIES}
        work = [{"family": "frame", "year": 2009, "urls": [f"/frames/N150000000{n}_1.webp?size=1024"]} for n in (0, 1, 2, 3)]
        args = argparse.Namespace(jobs=2, verify=False, dry_run=False)
        spec = "dir:" + os.path.join(tmp, "busy-mirror")
        state = os.path.join(tmp, "busy-state")
        os.makedirs(state)
        recs = publish.run_units(work, args, cache, spec, state, tags, "p")
        first = sorted(r["outcome"] for r in recs)
        for budget in publish.BUSY_BUDGETS:
            busy = {r["url"] for r in recs if r["outcome"] == "busy"}
            again = [dict(u, urls=[x for x in u["urls"] if x in busy]) for u in work if set(u["urls"]) & busy]
            recs = [r for r in recs if r["outcome"] != "busy"] + publish.run_units(again, args, cache, spec, state, tags,
                                                                                  "p", budget, recs)
        out = {r["url"].split("/")[2][:11]: r["outcome"] for r in recs}
        check(first == ["busy", "busy", "busy", "published"]
              and out == {"N1500000000": "published", "N1500000001": "published", "N1500000002": "busy",
                          "N1500000003": "missing"},
              "a URL answered busy is asked again with a larger work budget: published when it resolves, counted none "
              "(missing) when it then answers none, and reported busy when it stays busy")
        mirror = publish.Mirror(spec[4:])
        keys_held = [r["key"] for r in recs if mirror.held(r["key"])]
        check(sorted(k.split("/")[-1][:11] for k in keys_held) == ["N1500000000", "N1500000001"],
              "nothing is uploaded for a URL that ends busy or none (no fallback in its place)")
    finally:
        sys.path.remove(fake)
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_manifest():
    tags = keys.family_tags({"frame_server.FRAME_VERSION": "frames-q95"})
    m = publish.manifest("20261111T120000Z-abcdef1", "abcdef1", {"frame_server.FRAME_VERSION": "frames-q95"}, tags,
                         {"spans": None, "phases": {}}, {"version": "x"}, {"total": {"objects": 0, "bytes": 0}})
    with open(os.path.join(publish.PUBLIC, "manifest.schema.json")) as fh:
        schema = json.load(fh)
    check(set(schema["required"]) <= set(m) and set(m) <= set(schema["properties"]), "the manifest has the schema's fields")
    try:
        import jsonschema
        jsonschema.validate(m, schema)
        check(True, "the manifest validates against manifest.schema.json")
    except ImportError:
        import re
        check(re.match(schema["properties"]["publish_id"]["pattern"], m["publish_id"]) is not None
              and all(re.match(r"^t[0-9a-f]{12}$", t) for t in m["families"].values()) and len(m["families"]) == 7,
              "the manifest's id and family tags have the schema's shapes (jsonschema not installed)")
    check(keys.KEYS["manifest"]["key_format"].format(publish_id=m["publish_id"]) == "manifest/20261111T120000Z-abcdef1.json",
          "the manifest's key is manifest/<publish_id>.json")


# ---------- on a real cache and mirror ----------
def test_mirror_of_cache(cache, mirror, server):
    state = mirror.rstrip("/") + ".state"
    with open(os.path.join(state, "published.json")) as fh:
        pub = json.load(fh)
    check(not pub.get("partial") and not pub.get("dry_run"), "the publish finished (published.json is not partial)")
    target = publish.Mirror(mirror)
    import frame_server
    versions = frame_server.picture_versions()
    tags = keys.family_tags(versions)
    man_path = os.path.join(mirror, pub["manifest_key"])
    with open(man_path) as fh:
        man = json.load(fh)
    check(man["families"] == tags and man["versions"] == json.loads(json.dumps(versions)),
          "the manifest's tags are keys.family_tags(picture_versions()) of the code that resolves the cache")
    with open(os.path.join(publish.PUBLIC, "manifest.schema.json")) as fh:
        schema = json.load(fh)
    try:
        import jsonschema
        jsonschema.validate(man, schema)
        check(True, "the published manifest validates")
    except ImportError:
        check(set(schema["required"]) <= set(man), "the published manifest has the schema's required fields")

    # every enumerated URL is published, a marker, or listed missing
    missing = {m["url"] for m in pub["missing"] if m.get("url")}
    work = publish.units(cache, [tuple(s) for s in pub["spans"]] if pub.get("spans") else None,
                         None, [f for f in publish.FAMILIES if f not in ("thumb", "table")], log=lambda m: None)
    unaccounted, markers, total = [], 0, 0
    for u in work:
        urls = list(u["urls"])
        while urls:
            link = urls.pop(0)
            total += 1
            ans = keys.canonical("GET", link, tags)
            if ans["store"] == "refused":
                unaccounted.append((link, "refused"))
                continue
            held = target.held(ans["key"])
            if held is not None:
                if (held[2] or {}).get("x-status"):
                    markers += 1
                    urls += u.get("as_is") or []
                    u["as_is"] = []
            elif link not in missing:
                unaccounted.append((link, ans["key"]))
    check(not unaccounted, f"every enumerated URL ({total}, {markers} markers) is in the mirror or listed missing"
          + (f": {unaccounted[:3]}" if unaccounted else ""))
    check(all(m.get("reason") for m in pub["missing"]), f"each of the {len(pub['missing'])} missing URLs has a reason")

    # 1,000 sampled objects: the server's bytes and report
    import resolve
    published = []
    for u in work:
        for link in u["urls"]:
            ans = keys.canonical("GET", link, tags)
            if ans.get("key") and link not in missing:
                published.append((link, ans["key"]))
    random.Random(7).shuffle(published)
    sample, bad, how = published[:1000], [], "frame server at " + server if server else "resolve() + read()"
    for link, key in sample:
        held = target.held(key)
        if held is None or held[2].get("x-status"):
            continue
        with open(os.path.join(mirror, key), "rb") as fh:
            data = fh.read()
        if server:
            try:
                with urllib.request.urlopen(server.rstrip("/") + link, timeout=120) as r:
                    want, hdrs = r.read(), {k: v for k, v in r.headers.items() if k.lower().startswith("x-")}
            except urllib.error.HTTPError as e:
                bad.append((link, f"server {e.code}"))
                continue
        else:
            p = urllib.parse.urlsplit(link)
            a = resolve.resolve(p.path, urllib.parse.parse_qs(p.query), cache)
            want, hdrs = resolve.read(a), a.headers
        if data != want:
            bad.append((link, "bytes differ"))
            continue
        route = publish.ROUTE[keys.canonical("GET", link)["route"]]
        header = route.get("header")
        got = {k.lower(): v for k, v in hdrs.items()}
        if header and header.lower() in got:
            report = json.loads(got[header.lower()])
            custom = held[2]
            if custom.get("x-report-sidecar") == "1":
                with open(os.path.join(mirror, key + ".h.json")) as fh:
                    kept = json.load(fh)
            else:
                kept = json.loads(custom[header.lower()])
                if custom.get("x-report-trimmed") == "1":
                    keep = publish.HEADERS["page_reads"][header]
                    report = {k: v for k, v in report.items() if k in keep}
            if kept != report:
                bad.append((link, "report differs"))
    check(len(sample) >= min(1000, len(published)) and not bad,
          f"{len(sample)} sampled objects have the bytes and report of the {how}" + (f": {bad[:3]}" if bad else ""))

    # a second run writes nothing
    env = dict(os.environ)
    args = [sys.executable, os.path.join(HERE, "publish.py"), "--cache", cache, "--to-dir", mirror,
            "--families", ",".join(f for f in publish.FAMILIES if f != "table"), "--jobs", str(os.cpu_count() or 4)]
    if pub.get("spans") is not None and os.environ.get("CASSINI_PUBLISH_YEARS"):
        args += ["--years", os.environ["CASSINI_PUBLISH_YEARS"]]
    if os.environ.get("CASSINI_PUBLISH_SITE"):
        args += ["--site", os.environ["CASSINI_PUBLISH_SITE"]]
    second_state = tempfile.mkdtemp(prefix="publish-second-")
    shutil.copy(os.path.join(state, "ledger.sqlite"), second_state)
    out = subprocess.run(args + ["--state", second_state], env=env, capture_output=True, text=True)
    with open(os.path.join(second_state, "published.json")) as fh:
        again = json.load(fh)
    pictures = again["outcomes"].get("published", 0)
    check(out.returncode == 0 and pictures == 0, f"a second publish writes no picture (outcomes {again['outcomes']})")
    shutil.rmtree(second_state, ignore_errors=True)


def main():
    tmp = tempfile.mkdtemp(prefix="test-publish-")
    try:
        test_storage()
        test_mirror(tmp)
        test_r2(tmp)
        test_one()
        test_busy_retry(tmp)
        test_manifest()
        cache, mirror = os.environ.get("CASSINI_PUBLISH_CACHE"), os.environ.get("CASSINI_PUBLISH_MIRROR")
        if cache and mirror:
            test_mirror_of_cache(os.path.abspath(cache), os.path.abspath(mirror), os.environ.get("CASSINI_PUBLISH_SERVER"))
        else:
            print("skip the cache checks: set CASSINI_PUBLISH_CACHE and CASSINI_PUBLISH_MIRROR (see the docstring)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILED)} failed" if FAILED else "\nall passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
