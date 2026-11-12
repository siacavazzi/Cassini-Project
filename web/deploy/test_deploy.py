#!/usr/bin/env python3
"""
Tests for web/deploy/ (WP8), no network and no Cloudflare account needed:

  python web/deploy/test_deploy.py

- the Worker's routes cover every policy route and every fixture URL, and no file of the public site hides under one
- the rendered wrangler.toml parses, has no placeholder left, is off workers.dev, and binds what WP4 reads
- the site build keeps only page files (allowlist) and the Pages measurement flags files over 25 MiB
- a manifest from the test mirror passes manifest-check and a broken one does not
- the switch history finds the step to roll back to
- no secret is in web/deploy, and the stand-in Worker never fetches an origin (D1)
- the cost sheet's arithmetic
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cf  # noqa: E402
import cost  # noqa: E402

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None


class Routes(unittest.TestCase):
    def test_every_fixture_url_reaches_the_worker(self):
        paths = cf.worker_paths()
        cases = json.load(open(os.path.join(cf.ROOT, "web", "public", "key_fixtures.json")))["cases"]
        self.assertGreater(len(cases), 200)
        for c in cases:
            url = c["url"]
            p = urlsplit(url).path
            if not any(cf.path_matches(r, p) for r in paths):
                # only a URL no policy route matches may go to Pages instead (page files)
                self.assertIsNone(c["expect"].get("route"), f"{url}: a policy route the Worker's routes miss")

    def test_every_policy_route_has_a_worker_route(self):
        paths = cf.worker_paths()
        for r in json.load(open(cf.POLICY))["routes"]:
            lit, _ = cf._literal(r["pattern"])
            self.assertTrue(any(cf.path_matches(x, lit) or (x.endswith("*") and lit.startswith(x[:-1])) for x in paths),
                            r["pattern"])

    def test_page_files_are_not_hidden(self):
        paths = cf.worker_paths()
        for name in cf.SITE_TOP + ["data/mission.json", "data/catalog.json", "data/coverage/index.json",
                                   "vendor/three.min.js", "how/index.html"]:
            self.assertFalse(any(cf.path_matches(r, "/" + name) for r in paths), name)

    def test_route_syntax(self):
        for r in cf.routes("staging.example.com"):
            self.assertNotIn("*", r[:-1], r)          # Cloudflare routes take '*' only at the end of the path
            self.assertTrue(r.startswith("staging.example.com/"))


class Render(unittest.TestCase):
    def test_render(self):
        d = tempfile.mkdtemp()
        try:
            for env in ("local", "staging", "production"):
                p = cf.render(env, "manifest/20261111T210000Z-0000000.json", os.path.join(cf.ROOT, "web/worker/src/index.mjs"), d)
                text = open(p).read()
                self.assertNotRegex(text, r"@[A-Z_]+@")
                if tomllib:
                    t = tomllib.loads(text)
                    for e in (t, t["env"]["staging"], t["env"]["production"]):
                        self.assertIs(e["workers_dev"], False)
                        self.assertIs(e["preview_urls"], False)
                        self.assertEqual(e["vars"]["MANIFEST_KEY"], "manifest/20261111T210000Z-0000000.json")
                        self.assertEqual(e["r2_buckets"][0]["binding"], "BUCKET")
                        self.assertEqual(e["analytics_engine_datasets"][0]["binding"], "USAGE")
                    self.assertTrue(all(r["pattern"].startswith(cf.site_env()["STAGING_HOST"] + "/") for r in t["env"]["staging"]["routes"]))
                    self.assertNotIn("routes", t)        # the local Worker has no routes
            with self.assertRaises(SystemExit):
                cf.render("staging", "manifest/latest.json", "x.mjs", d)
        finally:
            shutil.rmtree(d)


class Build(unittest.TestCase):
    def test_copy_skips_tools_and_evidence(self):
        src, dst = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            for f in ["index.json", "a/b.webp", "make_icons.cjs", "make_images.py", "README.md", "evidence/x.png",
                      "src/head.html", ".DS_Store", "cache-123/x", "how/page.js"]:
                os.makedirs(os.path.dirname(os.path.join(src, f)) or src, exist_ok=True)
                open(os.path.join(src, f), "w").write("x")
            skipped = []
            cf._copy_tree(src, dst, skipped)
            self.assertEqual(sorted(cf._all_files(dst)), ["a/b.webp", "how/page.js", "index.json"])
        finally:
            shutil.rmtree(src); shutil.rmtree(dst)

    def test_measure(self):
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "small.json"), "w").write("{}")
            with open(os.path.join(d, "big.bin"), "wb") as f:
                f.truncate(cf.PAGES_MAX_FILE_BYTES + 1)
            m = cf.measure(d)
            self.assertEqual(m["files"], 2)
            self.assertFalse(m["fits"])
            self.assertEqual(m["over_size"][0]["path"], "big.bin")
            os.remove(os.path.join(d, "big.bin"))
            self.assertTrue(cf.measure(d)["fits"])
        finally:
            shutil.rmtree(d)


class DataCheck(unittest.TestCase):
    def test_both_replay_layouts_pass_the_input_check(self):
        for layout in (["mission.json", "catalog.json", "coverage/index.json"],
                       ["mission.json", "catalog/2004.json", "months/2004-07.json", "coverage/index.json"]):
            d, out = tempfile.mkdtemp(), tempfile.mkdtemp()
            try:
                for f in layout:
                    os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
                    open(os.path.join(d, f), "w").write("{}")
                os.rmdir(out)
                with redirect_stdout(io.StringIO()):
                    info = cf.build(d, out, "local")
                self.assertTrue(os.path.exists(os.path.join(out, "data", layout[1])), layout)
                self.assertEqual(info["env"], "local")
                self.assertTrue(os.path.exists(out + ".build.json"))
                self.assertFalse([f for f in cf._all_files(out) if f.startswith(".")])   # nothing hidden goes to Pages
            finally:
                shutil.rmtree(d); shutil.rmtree(out, ignore_errors=True)
                if os.path.exists(out + ".build.json"):
                    os.remove(out + ".build.json")
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "mission.json"), "w").write("{}")
            with self.assertRaises(SystemExit):
                cf.build(d, os.path.join(d, "out"), "local")
        finally:
            shutil.rmtree(d)


FAKE_PUBLIC_BUILD = r'''
import os, shutil, sys
# a stand-in for WP6's build.py: --public needs --out, and the replay data must be at web/cassini-os/data first
HERE = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(HERE)
a = sys.argv[1:]
assert "--public" in a
if "--out" not in a:
    sys.exit("build.py: the public site is written to a folder of its own: --out DIR")
out = a[a.index("--out") + 1]
data = os.path.realpath(os.path.join(root, "data"))
for need in ("mission.json", "coverage"):
    assert os.path.exists(os.path.join(data, need)), need
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w").write("public")
shutil.copytree(data, os.path.join(out, "data"))
'''


class PublicBuild(unittest.TestCase):
    def test_build_with_a_public_switch(self):
        repo, data, out = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
        old = cf.ROOT
        try:
            os.makedirs(os.path.join(repo, "web", "cassini-os", "src"))
            os.makedirs(os.path.join(repo, "web", "replay", "data", "textures"))
            open(os.path.join(repo, "web", "replay", "data", "textures", "t.webp"), "w").write("t")
            open(os.path.join(repo, "web", "cassini-os", "src", "build.py"), "w").write("# --public\n" + FAKE_PUBLIC_BUILD)
            os.symlink("../replay/data", os.path.join(repo, "web", "cassini-os", "data"))
            g = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
            g("init", "-q"); g("add", "-A")
            g("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "fake")
            for f in ("mission.json", "catalog/2004.json", "coverage/index.json"):
                os.makedirs(os.path.dirname(os.path.join(data, f)), exist_ok=True)
                open(os.path.join(data, f), "w").write("{}")
            os.rmdir(out)
            cf.ROOT = repo
            with redirect_stdout(io.StringIO()):
                info = cf.build(data, out, "staging")
            self.assertTrue(info["public_switch"])
            self.assertEqual(open(os.path.join(out, "index.html")).read(), "public")
            for f in ("data/mission.json", "data/catalog/2004.json", "data/coverage/index.json", "data/textures/t.webp"):
                self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            self.assertIn("Disallow: /", open(os.path.join(out, "robots.txt")).read())
        finally:
            cf.ROOT = old
            for d in (repo, data, out):
                shutil.rmtree(d, ignore_errors=True)
            if os.path.exists(out + ".build.json"):
                os.remove(out + ".build.json")


class Manifest(unittest.TestCase):
    def test_mirror_manifest(self):
        d = tempfile.mkdtemp()
        try:
            out = subprocess.run([sys.executable, os.path.join(HERE, "make_test_mirror.py"), d], capture_output=True, text=True, check=True)
            a, b = out.stdout.split()
            ma = cf.manifest_check(os.path.join(d, a))
            mb = cf.manifest_check(os.path.join(d, b))
            self.assertNotEqual(ma["families"]["frame"], mb["families"]["frame"])
            bad = dict(ma); del bad["families"]
            p = os.path.join(d, "bad.json"); json.dump(bad, open(p, "w"))
            with self.assertRaises(BaseException):
                cf.manifest_check(p)
        finally:
            shutil.rmtree(d)


class History(unittest.TestCase):
    def test_previous(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "h.json")
        prev = lambda: cf.history(p, "previous", []).get("manifest")
        try:
            self.assertIsNone(prev())
            cf.history(p, "add", ["manifest=A", "worker_version=1"])
            self.assertIsNone(prev())
            cf.history(p, "add", ["manifest=B", "worker_version=2"])
            cf.history(p, "add", ["manifest=B", "worker_version=2"])          # a re-deploy is not a step back
            self.assertEqual(prev(), "A")
            cf.history(p, "add", ["manifest=A", "worker_version=1", "rollback=1"])
            self.assertEqual(cf.history(p, "last", [])["manifest"], "A")
            self.assertIsNone(prev())                                       # a second rollback never goes forward to B
            cf.history(p, "add", ["manifest=C", "worker_version=3"])
            cf.history(p, "add", ["manifest=D", "worker_version=4"])
            self.assertEqual(prev(), "C")
            cf.history(p, "add", ["manifest=C", "worker_version=3", "rollback=1"])
            self.assertEqual(prev(), "A")                                   # back two steps: D, then C, to A
        finally:
            shutil.rmtree(d)


class Secrets(unittest.TestCase):
    def test_no_secret_in_the_folder(self):
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "."], cwd=HERE,
                                capture_output=True, text=True, check=True).stdout.split()
        self.assertIn("deploy.sh", listed)
        for f in listed:
                text = open(os.path.join(HERE, f), errors="ignore").read()
                self.assertNotRegex(text, r"(?<![A-Za-z0-9_])[A-Za-z0-9_-]{40}(?![A-Za-z0-9_-])(?<!-)", f"{f}: a token-shaped string")
                self.assertNotRegex(text, r"[0-9a-f]{32}(?![0-9a-f])", f"{f}: an account-ID-shaped string")
                self.assertNotRegex(text, r"[A-Za-z0-9._%+-]+@(gmail|icloud|me|outlook)\.com", f"{f}: an email")
        for line in open(os.path.join(HERE, "cloudflare.env.example")):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                self.assertIn(v, ("", "cassini-os"), k)

    def test_stub_worker_never_fetches(self):
        self.assertNotRegex(open(os.path.join(HERE, "stub", "worker.mjs")).read(), r"(?<!async )(?<![\w.])fetch\s*\(")


class Cost(unittest.TestCase):
    def test_sheet(self):
        rows = [{"session": "S1", "seconds": 120, "frames_requests": 120, "frames_bytes": 12e6, "static_requests": 10, "static_bytes": 30e6}]
        pm = cost.per_minute(rows)
        self.assertAlmostEqual(pm["frames_requests_per_min"], 60)
        c = cost.month_cost(20e6, 10, 0.5, 2)
        self.assertAlmostEqual(c["workers"], 5 + 10 * 0.30)
        self.assertAlmostEqual(c["r2_reads"], 0)                   # 10 M misses, all inside the free 10 M
        self.assertAlmostEqual(c["storage"], 0)
        self.assertIn("Cost sheet", cost.sheet(pm, 200, 0.5, 2, "test"))
        # Analytics Engine: one point per 10 answers (the Worker's USAGE_SAMPLE on staging and production)
        self.assertAlmostEqual(cost.month_cost(200e6, 0, 0.5, 2)["analytics"], (20e6 - 10e6) / 1e6 * 0.25)
        self.assertAlmostEqual(cost.month_cost(200e6, 0, 0.5, 2, ae_sample=1)["analytics"], (200e6 - 10e6) / 1e6 * 0.25)
        self.assertIn("double3", cost.AE_SQL)


if __name__ == "__main__":
    unittest.main(verbosity=1)
