#!/usr/bin/env python3
"""
The public site's contracts (web/public/, docs/public-site/README.md) hold together and match the code they describe:

  - keys.py reproduces every answer in key_fixtures.json (keys.mjs is held to the same file by test_keys.mjs)
  - every route the frame server answers today has a policy route, and a new server route fails this test until
    policy.json says what the public site does with it
  - the sizes, limits and defaults policy.json allows are the code's (frame_server, obs_mosaic, calibration, prebuild),
    read from the source so the test needs no data or kernels
  - the JSON files parse, the schemas are valid JSON Schema, and the files agree with each other (families, headers)
  - no contract file names a picture version: versions bump every day and live only in the publish manifest
  - resolve.py's Answer type behaves

Run: python web/public/test_contracts.py   (needs only the standard library; jsonschema when installed)
"""
import ast
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import keys  # noqa: E402

bad = 0


def check(name, ok, got=None):
    global bad
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if got is None or ok else f": {got}"))


def load(name):
    with open(os.path.join(HERE, name)) as fh:
        return json.load(fh)


def source(rel):
    with open(os.path.join(REPO, rel)) as fh:
        return fh.read()


def constant(rel, name):
    """A module-level constant's value, read from the source (ast.literal_eval of its assignment)."""
    for node in ast.parse(source(rel)).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{rel}: {name}")


policy, kj, headers, fx = load("policy.json"), load("keys.json"), load("headers.json"), load("key_fixtures.json")
routes = {r["id"]: r for r in policy["routes"]}

# ---- the fixtures ----
cases = fx["cases"]
check("at least 200 fixtures", len(cases) >= 200, len(cases))
wrong = [c["url"] for c in cases if keys.canonical(c.get("method", "GET"), c["url"]) != c["expect"]]
check("keys.py reproduces every fixture", not wrong, wrong[:5])
covered = {c["expect"]["route"] for c in cases}
check("every policy route has a fixture", set(routes) <= covered, sorted(set(routes) - covered))
for k in kj["global"]["drop"]:
    check(f"a fixture drops global parameter {k}", any(f"{k}=" in c["url"] and c["expect"]["key"] and f"{k}=" not in c["expect"]["key"] for c in cases))
for rid in ("movie",):
    for p in ("laps", "fade", "persist"):
        check(f"a fixture drops {p} on plain movie frames", any(c["expect"]["route"] == rid and f"{p}=" in c["url"] and c["expect"]["key"] and f"{p}=" not in c["expect"]["key"] for c in cases))
check("a fixture drops x=1 on a pointing's tile map route", any(c["expect"]["route"] == "tile_map" and "x=1" in c["url"] and not c["expect"]["refused"] for c in cases))
check("tags fill the key", keys.canonical("GET", "/frames/N1500060789_2.webp?size=1024", {"frame": "tabc"})["key"] == "frame/tabc/frames/N1500060789_2.webp~size=1024")
check("family tags are stable and versions-only", keys.family_tag("frame", {"frame_server.FRAME_VERSION": "frames-q95", "obs_mosaic.VERSION": "x"}) ==
      keys.family_tag("frame", {"frame_server.FRAME_VERSION": "frames-q95", "obs_mosaic.VERSION": "y"}))
check("a version bump changes a dependent family's tag", keys.family_tag("pass", {"obs_mosaic.VERSION": "a"}) != keys.family_tag("pass", {"obs_mosaic.VERSION": "b"}))

# ---- every server route has a policy route ----
srv = source("web/frames/frame_server.py")
found = set(re.findall(r're\.match\(r"(\^/[^"]+)"', srv)) | {f"=={p}" for p in re.findall(r'url(?:\.|_)path == "(/[^"]*)"', srv)}
for tup in re.findall(r'url\.path in \(([^)]*)\)', srv):
    found |= {f"=={p}" for p in re.findall(r'"(/[^"]*)"', tup)}
found |= {f"startswith{p}" for p in re.findall(r'url\.path\.startswith\("(/[^"]*)"\)', srv)}
# one sample request for each way the server matches a path; a new one fails here until it is added with its policy
SAMPLES = {
    "^/prebuild/[0-9a-f]{16}/stop$": ("POST", "/prebuild/0123456789abcdef/stop"),
    "^/flags/[^/]+/undo$": ("POST", "/flags/a/undo"),
    "^/export/([0-9a-f]{16})/sound\\.wav$": ("PUT", "/export/0123456789abcdef/sound.wav"),
    "^/export/plan-progress/([A-Za-z0-9_-]{1,40})\\.json$": ("GET", "/export/plan-progress/k.json"),
    "^/export/([0-9a-f]{16})\\.(json|mp4)$": ("GET", "/export/0123456789abcdef.mp4"),
    "^/prebuild/([0-9a-f]{16})\\.json$": ("GET", "/prebuild/0123456789abcdef.json"),
    "^/frames/processed/([^/]+)\\.webp$": ("GET", "/frames/processed/N1500060789_2.webp"),
    "^/reel/([A-Z0-9_]+)\\.json$": ("GET", "/reel/TITAN.json"),
    "^/frames/reel/([A-Z0-9_]+)/(\\d+)\\.webp$": ("GET", "/frames/reel/TITAN/3.webp"),
    "^/frames/mosaic/([^/]+)\\.json$": ("GET", "/frames/mosaic/N1500060789_2.json"),
    "^/frames/mosaic/([^/]+)/(?:p/(\\d+)|frame)\\.webp$": ("GET", "/frames/mosaic/N1500060789_2/p/1.webp"),
    "^/frames/mosaic/([^/]+)/full\\.(json|webp|jpg|png)$": ("GET", "/frames/mosaic/N1500060789_2/full.json"),
    "^/frames/movie/([^/]+)\\.fade\\.json$": ("GET", "/frames/movie/N1500060789_2.fade.json"),
    "^/frames/movie/([^/]+)\\.steady\\.json$": ("GET", "/frames/movie/N1500060789_2.steady.json"),
    "^/frames/movie/([^/]+)\\.(webp|json)$": ("GET", "/frames/movie/N1500060789_2.webp"),
    "^/frames/mosaic/([^/]+)\\.webp$": ("GET", "/frames/mosaic/N1500060789_2.webp"),
    "^/frames/([^/]+)\\.(webp|png|tif|lbl)$": ("GET", "/frames/N1500060789_2.tif"),
    "==/export": ("POST", "/export"), "==/prebuild": ("POST", "/prebuild"), "==/usage": ("POST", "/usage"),
    "==/jumplog": ("GET", "/jumplog"), "==/flags": ("GET", "/flags"), "==/debug/samples": ("GET", "/debug/samples"),
    "==/export/plan.json": ("GET", "/export/plan.json"), "==/export/levels.json": ("GET", "/export/levels.json"),
    "==/version.json": ("GET", "/version.json"), "==/stats": ("GET", "/stats"), "==/stats/": ("GET", "/stats/"),
    "==/stats/usage.json": ("GET", "/stats/usage.json"), "==/health": ("GET", "/health"),
    "==/frames/slices.json": ("GET", "/frames/slices.json"), "==/frames/color.webp": ("GET", "/frames/color.webp"),
    "==/frames/thumb.webp": ("GET", "/frames/thumb.webp"), "==/reel/bodies.json": ("GET", "/reel/bodies.json"),
    "startswith/flags/": ("GET", "/flags/index.json"),
}
new = sorted(found - set(SAMPLES))
check("every way the server matches a path is known to this test (else add it here and to policy.json)", not new, new)
gone = sorted(set(SAMPLES) - found)
check("no sample left for a path the server no longer matches", not gone, gone)
unrouted = [s for s in SAMPLES.values() if keys.route_of(s[0], s[1], {}) is None]
check("every sample request fits a policy route", not unrouted, unrouted)
check("POST and PUT routes are all refused or the Worker's", all(r["store"] in ("refused", "worker") for r in policy["routes"] if r["method"] != "GET"))

# ---- the code's numbers ----
sizes = constant("web/frames/frame_server.py", "SIZES")
check("keys.json all_sizes are frame_server.SIZES", tuple(kj["sizes"]["all_sizes"]) == tuple(sizes), sizes)
for r in policy["routes"]:
    for name, spec in r.get("params", {}).items():
        if spec.get("type") == "size":
            check(f"{r['id']}: built sizes are frame_server sizes", set(spec["built"]) <= set(sizes), spec["built"])
            check(f"{r['id']}: default size is built", spec["default"] in spec["built"], spec["default"])
pb = source("web/frames/prebuild.py")


def prebuilt(pattern):
    m = re.search(pattern, pb, re.S)
    return sorted(int(x) for x in re.findall(r"\d+", m.group(1))) if m else None


check("frame sizes are what prebuild's frames phase makes", prebuilt(r"frame_server\.webp\(i, s, c\) for s in \(([^)]*)\)") == sorted(routes["frame"]["params"]["size"]["built"]))
check("composite sizes are what prebuild's composites phase makes", prebuilt(r"color_webp\(s, z, c, centre=centred\(s\[-1\]\)\) for z in \(([^)]*)\)") == sorted(routes["color"]["params"]["size"]["built"]))
check("processed sizes are what prebuild's processed phase makes", prebuilt(r"processed_webp\(i, z, c, centre=centred\(i\)\) for z in \(([^)]*)\)") == sorted(routes["processed"]["params"]["size"]["built"]))
check("pass pictures are made at 1024 and 512 (make_pass), strips at 128", prebuilt(r"def make_pass\(u, cache, sizes=\(([^)]*)\)") == [512, 1024] and "make_pass(u, c, (128,))" in pb)
check("thumb size is frame_server.THUMB_SIZE", routes["thumb"]["params"]["size"]["built"] == [constant("web/frames/frame_server.py", "THUMB_SIZE")])
om = "web/frames/obs_mosaic.py"
check("movie exposure allows obs_mosaic.EXPOSURE_SMOOTH", constant(om, "EXPOSURE_SMOOTH") in routes["movie"]["params"]["exposure"]["allowed"])
check("movie trail limit is obs_mosaic.TRAIL", routes["movie"]["params"]["trail"]["max"] == constant(om, "TRAIL"))
check("movie steady limit is obs_mosaic.STEADY_MOST", routes["movie"]["params"]["steady"]["max"] == constant(om, "STEADY_MOST"))
check("movie exposure limit is obs_mosaic.EXPOSURE_MOST", routes["movie"]["params"]["exposure"]["max"] == constant(om, "EXPOSURE_MOST"))
check("mosaic movie fade limit is obs_mosaic.FADE_MAX", routes["mosaic_movie"]["params"]["fade"]["max"] == constant(om, "FADE_MAX"))
check("mosaic movie laps limit is obs_mosaic.TRAIL (the server clamps laps to it)", routes["mosaic_movie"]["params"]["laps"]["max"] == constant(om, "TRAIL"))
check("the default look is calibration.LOOKS[0]", kj["global"]["default_only"]["look"] == constant("calibration.py", "LOOKS")[0])
check("the default colors are calibration.COLORS[0]", kj["global"]["default_only"]["colors"] == constant("calibration.py", "COLORS")[0])

# ---- the files agree ----
fams = set(kj["families"]["list"])
check("every r2 route names a family keys.json has", all(r.get("family") in fams for r in policy["routes"] if r["store"] == "r2"))
check("manifest families are keys.json's", set(load("manifest.schema.json")["properties"]["families"]["propertyNames"]["enum"]) == fams)
r2 = {r["id"] for r in policy["routes"] if r["store"] == "r2"}
check("headers.json names a header (or none) for every r2 route", r2 <= set(headers["per_route"]), sorted(r2 - set(headers["per_route"])))
check("headers.json routes are policy routes", set(headers["per_route"]) <= set(routes))
check("every header a route sends lists the fields the page reads", all(h in headers["page_reads"] for h in headers["per_route"].values() if h))
check("table parts named by routes exist", all(r["part"] in kj["tables"]["parts"] for r in policy["routes"] if r["store"] == "table"))
check("every route id is unique", len(routes) == len(policy["routes"]))

# ---- schemas ----
try:
    import jsonschema
    for name in ("tables.schema.json", "manifest.schema.json"):
        jsonschema.Draft202012Validator.check_schema(load(name))
        check(f"{name} is valid JSON Schema", True)
    tables = load("tables.schema.json")
    part = lambda name: jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": tables["$defs"]})
    v = part("alias_shard")
    check("an alias shard validates", v.is_valid({"shard": "N15000", "frames": {"N1500060789_2": {"p": "SATURN_ISS_029RI_X_N_0", "n": 3, "m": None}}}))
    check("an alias shard with a bad id fails", not v.is_valid({"shard": "N15000", "frames": {"x": {"p": "a", "n": 1}}}))
    st = part("steady")
    check("a working steady table is not a table", not st.is_valid({"working": True, "local": False}))
except ImportError:
    print("skip schema checks (pip install jsonschema)")

# ---- no versions in the contracts ----
VERSIONED = re.compile(r"\b(obs|reel|export|levels|native|thumb|color|colour|frames|avif|hdr)-v\d+\b")
hits = []
for root, _, files in os.walk(HERE):
    for f in files:
        if f.endswith((".json", ".mjs", ".py", ".md")) and f != os.path.basename(__file__):
            with open(os.path.join(root, f)) as fh:
                hits += [f"{f}: {m.group(0)}" for m in VERSIONED.finditer(fh.read())]
check("no contract file names a picture version", not hits, hits[:5])

# ---- resolve.py ----
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
import resolve  # noqa: E402
check("resolve.Answer takes a file", resolve.Answer("file", path="/x.webp").kind == "file")
try:
    resolve.Answer("maybe")
    check("resolve.Answer refuses an unknown kind", False)
except ValueError:
    check("resolve.Answer refuses an unknown kind", True)
check("resolve() answers none on an empty cache", resolve.resolve("/frames/N1500060789_2.webp", {}, tempfile.mkdtemp()).kind == "none")

print(f"{'all ok' if not bad else f'{bad} failed'}")
sys.exit(1 if bad else 0)
