#!/usr/bin/env python3
"""
The deploy helpers behind deploy.sh (WP8, docs/public-site/briefs/WP8.md). Standard library only, so it runs on both
Macs and in the cloud without installing anything.

  python web/deploy/cf.py routes --host staging.cassinios.com       the Worker's routes, from policy.json
  python web/deploy/cf.py render --env staging --manifest KEY --main PATH --out DIR
                                                                    writes DIR/wrangler.toml from the template
  python web/deploy/cf.py build --data DIR --out DIR [--env staging] [--commit REV]
                                                                    the public site, from a clean worktree, for Pages
  python web/deploy/cf.py measure DIR [--json FILE]                 the upload against Pages' limits
  python web/deploy/cf.py manifest-check FILE                       a publish manifest against manifest.schema.json
  python web/deploy/cf.py history FILE add|last|previous ...        the switch history deploy.sh keeps
  python web/deploy/cf.py access --env staging [--apply]            the Cloudflare Access app that locks staging
  python web/deploy/cf.py pages-domain --env staging [--apply]      the Pages custom domain and its DNS record
  python web/deploy/cf.py pages-deployments --env staging           the Pages project's deployments, newest first
  python web/deploy/cf.py pages-rollback --env staging --to ID [--apply]
  python web/deploy/cf.py check-lock URL...                         every URL must answer with the Access sign-in

Every call that changes something on Cloudflare prints what it would do and does it only with --apply. Credentials
come from the environment only (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CASSINI_STAGING_EMAILS); nothing here
prints them.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
POLICY = os.path.join(ROOT, "web", "public", "policy.json")
SCHEMA = os.path.join(ROOT, "web", "public", "manifest.schema.json")
API = "https://api.cloudflare.com/client/v4"

# Pages' limits (developers.cloudflare.com/pages/platform/limits): files per deployment and bytes per file. 20,000
# is the Free plan's file count and the brief's gate; a paid account may allow more, but the gate stays at 20,000.
PAGES_MAX_FILES = 20000
PAGES_MAX_FILE_BYTES = 25 * 1024 * 1024


def site_env():
    """site.env as a dict (names only, nothing secret)."""
    out = {}
    with open(os.path.join(HERE, "site.env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def host_of(env, conf=None):
    conf = conf or site_env()
    return {"staging": conf["STAGING_HOST"], "production": conf["PRODUCTION_HOST"]}[env]


def project_of(env, conf=None):
    conf = conf or site_env()
    return {"staging": conf["PAGES_PROJECT_STAGING"], "production": conf["PAGES_PROJECT_PRODUCTION"]}[env]


# ---------- the Worker's routes ----------

def _literal(pattern):
    """The literal path a policy pattern starts with, and whether the pattern is nothing but that literal."""
    p = pattern[1:] if pattern.startswith("^") else pattern
    out, i = "", 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p) and not p[i + 1].isalnum():
            out += p[i + 1]; i += 2; continue
        if c in ".^$*+?()[]{}|\\":
            break
        out += c; i += 1
    rest = p[i:]
    return out, rest == "$"


def worker_paths():
    """Path patterns (Cloudflare route syntax, '*' only at the end) that cover every route in policy.json: an exact
    path where the pattern is one fixed path, else '/<first segment>*'. Every policy route, refused ones included,
    goes to the Worker, so a refused request is answered 404 and counted rather than falling through to Pages."""
    routes = json.load(open(POLICY))["routes"]
    exact, prefixes = set(), set()
    for r in routes:
        lit, whole = _literal(r["pattern"])
        if not lit.startswith("/"):
            raise SystemExit(f"policy route {r.get('id')} does not start with a fixed '/': {r['pattern']}")
        seg = lit.split("/")[1]
        if whole and "/" not in lit[1:]:
            exact.add(lit)
        else:
            prefixes.add("/" + seg)
    exact = {e for e in exact if not any(e.startswith(p) for p in prefixes)}
    return sorted(p + "*" for p in prefixes) + sorted(exact)


def routes(host):
    return [host + p for p in worker_paths()]


def path_matches(route_path, path):
    return path.startswith(route_path[:-1]) if route_path.endswith("*") else path == route_path


# ---------- wrangler.toml ----------

def render(env, manifest, main, out_dir, conf=None):
    conf = conf or site_env()
    t = open(os.path.join(HERE, "wrangler.template.toml")).read()
    fill = {
        "WORKER_NAME": conf["WORKER_NAME"], "WORKER_MAIN": os.path.abspath(main), "MANIFEST_KEY": manifest,
        "R2_BUCKET_NAME": conf["R2_BUCKET_NAME"],
        "USAGE_DATASET_STAGING": conf["USAGE_DATASET_STAGING"], "USAGE_DATASET_PRODUCTION": conf["USAGE_DATASET_PRODUCTION"],
        "STAGING_ROUTES": ",\n".join(f'  {{ pattern = "{r}", zone_name = "{conf["CASSINI_DOMAIN"]}" }}' for r in routes(conf["STAGING_HOST"])),
        "PRODUCTION_ROUTES": ",\n".join(f'  {{ pattern = "{r}", zone_name = "{conf["CASSINI_DOMAIN"]}" }}' for r in routes(conf["PRODUCTION_HOST"])),
    }
    if not re.fullmatch(r"manifest/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,40}\.json", manifest):
        raise SystemExit(f"not a manifest key (keys.json manifest.key_format): {manifest!r}")
    for k, v in fill.items():
        t = t.replace(f"@{k}@", v)
    left = re.findall(r"@[A-Z_]+@", t)
    if left:
        raise SystemExit(f"template names left unfilled: {left}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "wrangler.toml")
    open(path, "w").write(t)
    return path


# ---------- the site for Pages ----------

# what of web/cassini-os goes to Pages: the page, its sub-pages and assets. Not the sources (src/), the page bench,
# the old replay page (never linked: CLAUDE.md), READMEs, tools or anything a run left in the folder
SITE_TOP = ["index.html", "about", "how", "icons", "models", "vendor", "favicon.svg", "favicon-48.png", "apple-touch-icon.png",
            "share.jpg", "robots.txt", "sitemap.xml"]
SKIP_NAME = re.compile(r"(^\.|^__pycache__$|^README|\.md$|\.py$|\.pyc$|\.cjs$|\.sh$|^make_|\.bak$|~$|\.tmp$|\.log$)")
SKIP_DIR = {"src", "bench", "replay", "evidence", "flags", "prebuild", "cache", "out", "output", "node_modules"}
# built replay data: mission.json, and the catalog either whole (the old one-year layout's catalog.json) or by year
# (the whole-mission layout's catalog/<year>.json, build_data.py --years 1997-2017)
DATA_NEEDS = ["mission.json", ("catalog.json", "catalog")]


def _copy_tree(src, dst, skipped):
    for base, dirs, files in os.walk(src, followlinks=True):
        rel = os.path.relpath(base, src)
        keep = []
        for d in dirs:
            if d in SKIP_DIR or SKIP_NAME.search(d) or d.startswith("cache-"):
                skipped.append(os.path.normpath(os.path.join(rel, d)) + "/")
            else:
                keep.append(d)
        dirs[:] = keep
        for f in files:
            if SKIP_NAME.search(f):
                skipped.append(os.path.normpath(os.path.join(rel, f)))
                continue
            os.makedirs(os.path.join(dst, rel), exist_ok=True)
            shutil.copy2(os.path.join(base, f), os.path.join(dst, rel, f))


def public_switch_supported(build_py):
    return "--public" in open(build_py).read()


def build(data, out, env="local", commit="HEAD", allow_unswitched=False):
    """The public site in out/, built from a clean worktree at commit (nothing from this checkout's working tree),
    with the replay data from data/ (web/replay/build_data.py and build_coverage.py output)."""
    data = os.path.abspath(os.path.expanduser(data))
    out = os.path.abspath(out)
    need = [f if isinstance(f, tuple) else (f,) for f in DATA_NEEDS]
    missing = [" or ".join(alt) for alt in need if not any(os.path.exists(os.path.join(data, f)) for f in alt)]
    if missing:
        raise SystemExit(f"{data} is not built replay data (missing {', '.join(missing)}): run web/replay/build_data.py "
                         "and build_coverage.py at this commit first")
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"{out} is not empty: the build writes only into a new folder")
    os.makedirs(out, exist_ok=True)
    rev = subprocess.run(["git", "-C", ROOT, "rev-parse", commit], capture_output=True, text=True, check=True).stdout.strip()
    wt = tempfile.mkdtemp(prefix="cassini-pages-")
    skipped = []
    try:
        subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", "--quiet", wt, rev], check=True)
        build_py = os.path.join(wt, "web", "cassini-os", "src", "build.py")
        cmd = [sys.executable, build_py]
        if public_switch_supported(build_py):
            cmd.append("--public")
            switched = True
        elif env == "local" or allow_unswitched:
            print("note: build.py has no --public yet (WP6); building the private page", file=sys.stderr)
            switched = False
        else:
            raise SystemExit("build.py has no --public switch at this commit (WP6): refusing to deploy the private "
                             "page to " + env)
        subprocess.run(cmd, cwd=wt, check=True, stdout=subprocess.DEVNULL)
        site = os.path.join(wt, "web", "cassini-os")
        for name in SITE_TOP:
            p = os.path.join(site, name)
            if os.path.isdir(p):
                _copy_tree(p, os.path.join(out, name), skipped)
            elif os.path.exists(p):
                shutil.copy2(p, os.path.join(out, name))
        # replay data: the tracked models and textures first, then the built data over them
        _copy_tree(os.path.join(wt, "web", "replay", "data"), os.path.join(out, "data"), skipped)
        _copy_tree(data, os.path.join(out, "data"), skipped)
    finally:
        subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", wt], capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
    if env != "production":
        # staging and local copies are never indexed, even if the lock were lifted
        open(os.path.join(out, "robots.txt"), "w").write("User-agent: *\nDisallow: /\n")
        open(os.path.join(out, "_headers"), "w").write("/*\n  X-Robots-Tag: noindex\n")
    clash = [p for p in _all_files(out) if any(path_matches(r, "/" + p) for r in worker_paths())]
    if clash:
        raise SystemExit(f"files the Worker's routes would hide: {clash[:10]}")
    info = {"commit": rev, "env": env, "public_switch": switched, "data": data, "skipped": sorted(set(skipped))}
    json.dump(info, open(os.path.join(out, ".build.json"), "w"), indent=1)
    return info


def _all_files(d):
    for base, _, files in os.walk(d):
        for f in files:
            yield os.path.relpath(os.path.join(base, f), d).replace(os.sep, "/")


def measure(d):
    files = [(p, os.path.getsize(os.path.join(d, p))) for p in _all_files(d) if not p.startswith(".build")]
    files.sort(key=lambda x: -x[1])
    by_top = {}
    for p, n in files:
        top = p.split("/")[0] if "/" in p else "(top)"
        if top == "data" and p.count("/") >= 2:
            top = "data/" + p.split("/")[1]
        c = by_top.setdefault(top, [0, 0])
        c[0] += 1; c[1] += n
    over = [{"path": p, "bytes": n} for p, n in files if n > PAGES_MAX_FILE_BYTES]
    return {
        "files": len(files), "bytes": sum(n for _, n in files),
        "largest": [{"path": p, "bytes": n} for p, n in files[:10]],
        "by_folder": {k: {"files": v[0], "bytes": v[1]} for k, v in sorted(by_top.items(), key=lambda kv: -kv[1][1])},
        "limits": {"max_files": PAGES_MAX_FILES, "max_file_bytes": PAGES_MAX_FILE_BYTES},
        "over_size": over, "fits": len(files) <= PAGES_MAX_FILES and not over,
    }


def measure_text(m):
    mb = lambda n: f"{n / 1048576:,.1f} MiB"
    lines = [f"{m['files']:,} files, {mb(m['bytes'])} in all; largest {m['largest'][0]['path']} {mb(m['largest'][0]['bytes'])}"
             if m["largest"] else "no files",
             f"limits: {m['limits']['max_files']:,} files, {mb(m['limits']['max_file_bytes'])} a file -> "
             + ("FITS" if m["fits"] else "DOES NOT FIT"), "", "| folder | files | size |", "|---|---|---|"]
    lines += [f"| {k} | {v['files']:,} | {mb(v['bytes'])} |" for k, v in m["by_folder"].items()]
    lines += ["", "| largest files | size |", "|---|---|"] + [f"| {x['path']} | {mb(x['bytes'])} |" for x in m["largest"]]
    if m["over_size"]:
        lines += ["", "Over 25 MiB: " + ", ".join(x["path"] for x in m["over_size"])]
    return "\n".join(lines)


# ---------- the publish manifest ----------

def manifest_check(path):
    """The checks of manifest.schema.json that matter before switching: required fields, the publish id's form,
    every family's tag. (jsonschema is used when installed, for the whole schema.)"""
    m = json.load(open(path))
    schema = json.load(open(SCHEMA))
    try:
        import jsonschema
        jsonschema.validate(m, schema)
    except ImportError:
        props = schema["properties"]
        for k in schema["required"]:
            if k not in m:
                raise SystemExit(f"manifest: no {k}")
        if set(m) - set(props):
            raise SystemExit(f"manifest: unknown fields {sorted(set(m) - set(props))}")
        if not re.fullmatch(props["publish_id"]["pattern"], m["publish_id"]):
            raise SystemExit("manifest: publish_id")
        fams = props["families"]["propertyNames"]["enum"]
        tag = props["families"]["additionalProperties"]["pattern"]
        if sorted(m["families"]) != sorted(fams) or not all(re.fullmatch(tag, v) for v in m["families"].values()):
            raise SystemExit("manifest: families")
        if "spans" not in m["slices"]:
            raise SystemExit("manifest: slices.spans")
    if os.path.basename(path) not in (m["publish_id"] + ".json",) and not path.endswith("manifest.json"):
        print(f"note: file name {os.path.basename(path)} is not {m['publish_id']}.json", file=sys.stderr)
    return m


# ---------- switch history ----------
# A JSON list, oldest first, of {"when", "env", "manifest", "worker_version", "pages_deployment", "commit", "by"}.
# deploy.sh keeps it in R2 at deploy/<env>/history.json (local: a file), so either Mac can roll back.

def history(path, op, fields):
    h = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else []
    if op == "add":
        h.append(dict(f.split("=", 1) for f in fields))
        json.dump(h, open(path, "w"), indent=1)
        return h[-1]
    if op == "last":
        return h[-1] if h else {}
    if op == "previous":
        # the switch before the last one that differs from it (a re-deploy of the same manifest is not a step back)
        if not h:
            return {}
        last = h[-1]
        for e in reversed(h[:-1]):
            if (e.get("manifest"), e.get("worker_version")) != (last.get("manifest"), last.get("worker_version")):
                return e
        return {}
    raise SystemExit(f"history: unknown op {op}")


# ---------- Cloudflare API (Access, Pages domains, Pages rollback) ----------

def _api(method, path, body=None):
    tok, acct = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not tok or not acct:
        raise SystemExit("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are not set (source ~/.cassini-cloudflare.env)")
    req = urllib.request.Request(API + path.replace("{acct}", acct), method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            out = json.load(e)
        except Exception:
            raise SystemExit(f"{method} {path}: HTTP {e.code}")
    if not out.get("success"):
        raise SystemExit(f"{method} {path}: {json.dumps(out.get('errors'))}")
    return out["result"]


def _zone_id(conf):
    z = _api("GET", f"/zones?name={conf['CASSINI_DOMAIN']}")
    if not z:
        raise SystemExit(f"zone {conf['CASSINI_DOMAIN']} is not on this account")
    return z[0]["id"]


def access(env, apply):
    """One self-hosted Access application over every name staging is reachable at: its host (Pages and the Worker's
    routes) and the Pages project's pages.dev names (the project's own and every preview). Allowed: the emails in
    CASSINI_STAGING_EMAILS, by one-time PIN. Made before the host's DNS record exists, so staging is never open."""
    if env != "staging":
        raise SystemExit("only staging is locked; production opens only on Sam's go (G4)")
    conf = site_env()
    proj = project_of(env, conf)
    emails = [e.strip() for e in os.environ.get("CASSINI_STAGING_EMAILS", "").split(",") if e.strip()]
    if not emails:
        raise SystemExit("CASSINI_STAGING_EMAILS is empty: nobody could open staging")
    domains = [conf["STAGING_HOST"], f"{proj}.pages.dev", f"*.{proj}.pages.dev"]
    want = {
        "name": f"Cassini OS staging ({proj})", "type": "self_hosted", "domain": domains[0],
        "self_hosted_domains": domains, "session_duration": "24h", "app_launcher_visible": False,
        "policies": [{"name": "staging viewers", "decision": "allow", "precedence": 1,
                      "include": [{"email": {"email": e}} for e in emails]}],
    }
    print(f"Access app over {', '.join(domains)}; {len(emails)} allowed email(s)")
    if not apply:
        print("(dry run: nothing changed; --apply to make it)")
        return want
    apps = _api("GET", "/accounts/{acct}/access/apps")
    have = [a for a in apps if set(a.get("self_hosted_domains") or [a.get("domain")]) & set(domains)]
    if have:
        res = _api("PUT", f"/accounts/{{acct}}/access/apps/{have[0]['id']}", want)
        print(f"updated Access app {res['id']}")
    else:
        res = _api("POST", "/accounts/{acct}/access/apps", want)
        print(f"made Access app {res['id']}")
    return res


def pages_domain(env, apply):
    """The Pages project's custom domain (its host) and the proxied CNAME to <project>.pages.dev that carries it and
    the Worker's routes. Staging only after its Access app exists."""
    conf = site_env()
    host, proj = host_of(env, conf), project_of(env, conf)
    print(f"custom domain {host} on Pages project {proj}; DNS CNAME {host} -> {proj}.pages.dev (proxied)")
    if not apply:
        print("(dry run: nothing changed; --apply to make it)")
        return
    if env == "staging":
        apps = _api("GET", "/accounts/{acct}/access/apps")
        if not any(host in (a.get("self_hosted_domains") or [a.get("domain")]) for a in apps):
            raise SystemExit(f"no Access app covers {host}: run `cf.py access --env staging --apply` first")
    doms = _api("GET", f"/accounts/{{acct}}/pages/projects/{proj}/domains")
    if not any(d["name"] == host for d in doms):
        _api("POST", f"/accounts/{{acct}}/pages/projects/{proj}/domains", {"name": host})
        print(f"added {host} to {proj}")
    zone = _zone_id(conf)
    recs = _api("GET", f"/zones/{zone}/dns_records?name={host}")
    rec = {"type": "CNAME", "name": host, "content": f"{proj}.pages.dev", "proxied": True, "ttl": 1,
           "comment": "Cassini OS " + env + " (web/deploy)"}
    if recs:
        _api("PUT", f"/zones/{zone}/dns_records/{recs[0]['id']}", rec)
    else:
        _api("POST", f"/zones/{zone}/dns_records", rec)
    print(f"DNS {host} -> {proj}.pages.dev")


def pages_deployments(env):
    proj = project_of(env)
    out = _api("GET", f"/accounts/{{acct}}/pages/projects/{proj}/deployments?env=production")
    return [{"id": d["id"], "created_on": d["created_on"], "commit": (d.get("deployment_trigger") or {}).get("metadata", {}).get("commit_hash"),
             "url": d.get("url")} for d in out]


def pages_rollback(env, to, apply):
    proj = project_of(env)
    print(f"Pages {proj}: production back to deployment {to}")
    if not apply:
        print("(dry run: nothing changed; --apply to do it)")
        return
    _api("POST", f"/accounts/{{acct}}/pages/projects/{proj}/deployments/{to}/rollback")
    print("rolled back")


def check_lock(urls):
    """Each URL, asked with no cookie, must answer with Cloudflare Access (a redirect to <team>.cloudflareaccess.com,
    or 401/403 from Access). Anything else, a 200 above all, means staging is open: deploy.sh stops there."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    bad = []
    for u in urls:
        try:
            r = opener.open(urllib.request.Request(u, method="GET"), timeout=30)
            status, loc = r.status, r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            status, loc = e.code, e.headers.get("Location", "")
        except Exception as e:
            status, loc = 0, str(e)
        locked = (status in (301, 302, 303, 307) and "cloudflareaccess.com" in loc) or status in (401, 403)
        print(f"{'locked' if locked else 'OPEN  '} {status} {u}")
        if not locked:
            bad.append(u)
    if bad:
        raise SystemExit(f"{len(bad)} URL(s) answer without Access: {bad}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("routes"); s.add_argument("--host", default="")
    s = sub.add_parser("render"); s.add_argument("--env", default="local"); s.add_argument("--manifest", required=True)
    s.add_argument("--main", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("build"); s.add_argument("--data", required=True); s.add_argument("--out", required=True)
    s.add_argument("--env", default="local"); s.add_argument("--commit", default="HEAD"); s.add_argument("--allow-unswitched", action="store_true")
    s = sub.add_parser("measure"); s.add_argument("dir"); s.add_argument("--json")
    s = sub.add_parser("manifest-check"); s.add_argument("file")
    s = sub.add_parser("history"); s.add_argument("file"); s.add_argument("op"); s.add_argument("fields", nargs="*")
    for name in ("access", "pages-domain"):
        s = sub.add_parser(name); s.add_argument("--env", default="staging"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("pages-deployments"); s.add_argument("--env", default="staging")
    s = sub.add_parser("pages-rollback"); s.add_argument("--env", default="staging"); s.add_argument("--to", required=True)
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("check-lock"); s.add_argument("urls", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "routes":
        print("\n".join(routes(a.host)))
    elif a.cmd == "render":
        print(render(a.env, a.manifest, a.main, a.out))
    elif a.cmd == "build":
        info = build(a.data, a.out, a.env, a.commit, a.allow_unswitched)
        print(json.dumps({k: v for k, v in info.items() if k != "skipped"}, indent=1))
        print(measure_text(measure(a.out)))
    elif a.cmd == "measure":
        m = measure(a.dir)
        if a.json:
            json.dump(m, open(a.json, "w"), indent=1)
        print(measure_text(m))
        return 0 if m["fits"] else 1
    elif a.cmd == "manifest-check":
        m = manifest_check(a.file)
        print(f"ok {m['publish_id']}")
    elif a.cmd == "history":
        print(json.dumps(history(a.file, a.op, a.fields)))
    elif a.cmd == "access":
        access(a.env, a.apply)
    elif a.cmd == "pages-domain":
        pages_domain(a.env, a.apply)
    elif a.cmd == "pages-deployments":
        print(json.dumps(pages_deployments(a.env), indent=1))
    elif a.cmd == "pages-rollback":
        pages_rollback(a.env, a.to, a.apply)
    elif a.cmd == "check-lock":
        check_lock(a.urls)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
