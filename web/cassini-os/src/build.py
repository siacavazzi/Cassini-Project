#!/usr/bin/env python3
"""
Builds the Cassini OS pages from the replay viewer (web/replay/index.html): each page is one of the
heads in this folder (styles, window manager, menus, camera feed) followed by the viewer's script,
patched so colours and fonts come from CSS, the HUD draws into its own canvas, and Cassini is
NASA's 3D model (data/models/cassini.glb.b64.txt).

  python web/cassini-os/src/build.py            # writes web/cassini-os/index.html
  python web/cassini-os/src/build.py --public --out DIR [--frames URL]
                                                 # the public site (docs/public-site, WP6): a folder for Pages
  python web/cassini-os/src/build.py SRC HEAD OUT

The page reads web/replay/data (the data/ link), so build that first with web/replay/build_data.py (and
web/replay/build_coverage.py, which the public build needs).

The public switch (site.json "public" and "frames"; --public and --frames win): the page reads them as
window.cassiniPublic and window.cassiniFrames (settings.html), hides and forces what web/public/policy.json
page_settings lists, asks the frames host (the Worker; the page's own origin when there is no --frames) for every
picture, version.json, slices.json and the usage counts, and loads three.js and its fonts from the build's own
vendor/ folder rather than from jsDelivr and Google Fonts. --out gets the whole static site (public_tree below).
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- the public site's static folder (docs/public-site, WP6; WP8 deploys it to Pages) ----------
# The Worker shares the site's hostname on these prefixes, so no static file may sit under one of them.
WORKER_PREFIXES = ("frames", "reel", "export", "prebuild", "flags", "stats", "jumplog", "usage", "health", "version.json", "debug")
# three.js, the film muxer and the two fonts, served from the build's vendor/ folder instead of jsDelivr and Google Fonts: pinned
# files, checked by their SHA-256 so a changed upstream file fails the build instead of reaching visitors
VENDOR = {
    "vendor/three/three.min.js": ("https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js",
                                         "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2"),
    "vendor/three/OrbitControls.js": ("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js",
                                         "02bb4ade710f3e607329e37a21f098bc3ac70eb6e33daf8a65e79f4db785e7b2"),
    "vendor/three/GLTFLoader.js": ("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js",
                                         "5c15967ba830918a9caea6338712c994c354bccd4edc4569bde411c3ec06a3e6"),
    # the film muxer (export.html's MUXER, an ES module imported only while a film is made)
    "vendor/mp4-muxer/mp4-muxer.mjs": ("https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.5/build/mp4-muxer.mjs",
                                         "69f25ab5dd735289936fedbf72a0430182f6c053a0cc6b555beefb810d3d2ca9"),
    "vendor/fonts/share-tech-mono-latin.woff2": ("https://fonts.gstatic.com/s/sharetechmono/v16/J7aHnp1uDWRBEqV98dVQztYldFcLowEFA87Heg.woff2",
                                         "73b87eb7b02dfec4cb1ddfabad6e625d9c77b3c81015064420de88d8dd04816c"),
    "vendor/fonts/silkscreen-latin-ext.woff2": ("https://fonts.gstatic.com/s/silkscreen/v6/m8JXjfVPf62XiF7kO-i9YL1la0GA1dOkDw.woff2",
                                         "5ae60a8bb15c2065126fdf5af9912cd548be48fd43f19d543b69b95ee0314240"),
    "vendor/fonts/silkscreen-latin.woff2": ("https://fonts.gstatic.com/s/silkscreen/v6/m8JXjfVPf62XiF7kO-i9YLNla0GA1dM.woff2",
                                         "17bb6d80eeea10c69887aa64a1b48e70a3f540de50480da9ec933fac1996bf97"),
}
# Google Fonts' own stylesheet for the two fonts (css2?family=Silkscreen&family=Share+Tech+Mono, as a current browser
# gets it), pointed at vendor/fonts/
FONT_FACES = """
@font-face { font-family: 'Share Tech Mono'; font-style: normal; font-weight: 400; font-display: swap; src: url(vendor/fonts/share-tech-mono-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: 'Silkscreen'; font-style: normal; font-weight: 400; font-display: swap; src: url(vendor/fonts/silkscreen-latin-ext.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'Silkscreen'; font-style: normal; font-weight: 400; font-display: swap; src: url(vendor/fonts/silkscreen-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
"""


def vendor_file(path, out):
    """one pinned file into out/path, from ~/.cache/cassini-vendor/<host>/<path> when it has been fetched before (a
    machine that cannot reach jsDelivr can be given the files there: they are the npm packages' own, three@0.128.0 and mp4-muxer@5.1.5)"""
    import hashlib, shutil, urllib.request
    url, sha = VENDOR[path]
    cache = os.path.join(os.path.expanduser("~"), ".cache", "cassini-vendor", url.split("://", 1)[1])
    if not os.path.exists(cache):
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (cassini-os build)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        open(cache + ".part", "wb").write(body)
        os.replace(cache + ".part", cache)
    got = hashlib.sha256(open(cache, "rb").read()).hexdigest()
    assert sha is None or got == sha, f"{url}: SHA-256 {got}, expected {sha} (delete {cache} to fetch it again)"
    os.makedirs(os.path.dirname(os.path.join(out, path)), exist_ok=True)
    shutil.copyfile(cache, os.path.join(out, path))


def public_tree(root, out):
    """Everything Pages serves next to index.html (already written to out): the About and How pages, the icons, the
    models, the replay data with its coverage, the vendored three.js and fonts, the share card, robots.txt and the
    sitemap. Nothing from src/, bench/ or replay/, and nothing under a prefix the Worker answers."""
    import shutil
    data = os.path.realpath(os.path.join(root, "data"))
    for need in ("mission.json", "coverage"):
        assert os.path.exists(os.path.join(data, need)), (
            f"{os.path.join(data, need)} is missing: build the replay data first (web/replay/build_data.py, then web/replay/build_coverage.py)")
    skip = shutil.ignore_patterns("*.py", "*.cjs", "make_*.html", "__pycache__", ".DS_Store")
    for d in ("about", "how", "icons", "models"):
        if os.path.exists(os.path.join(out, d)):
            shutil.rmtree(os.path.join(out, d))
        shutil.copytree(os.path.join(root, d), os.path.join(out, d), ignore=skip)
    if os.path.exists(os.path.join(out, "data")):
        shutil.rmtree(os.path.join(out, "data"))
    shutil.copytree(data, os.path.join(out, "data"), symlinks=False, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"))
    for f in ("favicon.svg", "favicon-48.png", "apple-touch-icon.png", "share.jpg", "robots.txt", "sitemap.xml"):
        if os.path.exists(os.path.join(root, f)):
            shutil.copyfile(os.path.join(root, f), os.path.join(out, f))
    for path in VENDOR:
        vendor_file(path, out)
    files, size, biggest = 0, 0, (0, "")
    for dirpath, _, names in os.walk(out):
        for n in names:
            rel = os.path.relpath(os.path.join(dirpath, n), out).replace(os.sep, "/")
            assert not rel.startswith(WORKER_PREFIXES), f"{rel}: the Worker answers this path on the site's hostname"
            b = os.path.getsize(os.path.join(dirpath, n))
            files += 1; size += b; biggest = max(biggest, (b, rel))
    print(f"public site in {out}: {files} files, {size / 2**20:.1f} MiB, largest {biggest[1]} ({biggest[0] / 2**20:.1f} MiB)")


FLAGS = ("--public", "--frames", "--out")
if len(sys.argv) == 1 or sys.argv[1] in FLAGS:
    import argparse
    ap = argparse.ArgumentParser(description="Build the Cassini OS page")
    ap.add_argument("--public", action="store_true", help="the public site (window.cassiniPublic)")
    ap.add_argument("--frames", default=None, help="the frames host (the Worker), when it is not the page's own origin")
    ap.add_argument("--out", default=None, help="the folder the public site is written to")
    a = ap.parse_args()
    root = os.path.dirname(HERE)
    sys.path.insert(0, HERE)
    import seo
    site = seo.load()
    public = a.public or site.get("public") is True
    frames = a.frames if a.frames is not None else site.get("frames") or ""
    if public and not a.out:
        sys.exit("build.py: the public site is written to a folder of its own: --out DIR (index.html here is the Mini's page)")
    if a.out and not public:
        sys.exit("build.py: --out is for the public site (--public)")
    out_index = os.path.join(a.out, "index.html") if public else os.path.join(root, "index.html")
    if public:
        os.makedirs(a.out, exist_ok=True)
    env = dict(os.environ, CASSINI_PUBLIC="1" if public else "", CASSINI_FRAMES_HOST=frames)
    for head in ["head-quiet.html"]:
        subprocess.run([sys.executable, __file__, os.path.join(root, "..", "replay", "index.html"),
                        os.path.join(HERE, head), out_index], check=True, env=env)
    seo.write_files(site)      # about/, robots.txt, sitemap.xml (site.json)
    if public:
        public_tree(root, a.out)
    sys.exit(0)
import sys, re, json, hashlib
src = open(sys.argv[1]).read()           # prototype source
study = open(sys.argv[2]).read()          # study: everything up to (not incl.) the three.js script tags
out = sys.argv[3]
# what search engines and link previews read (seo.py, site.json): title, description, share card, structured data,
# and a few lines for browsers without JavaScript
sys.path.insert(0, HERE)
import seo
site = seo.load()
for old, new in [("<title>Cassini OS Quiet</title>", seo.head(site)), ("<body>\n<div id=\"app\">", "<body>\n" + seo.noscript(site) + "\n<div id=\"app\">")]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
script = src[src.index('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js">'):]

# movie mode (movie.html): its style joins the head's, a Movie button joins the transport, and its script runs after
# the chrome script (it wraps the clock's studyAdvance hook)
# flagging pictures (flag.html): its style joins the head's, its panel and toast go into #app, and its script runs right
# after the chrome script, ahead of movie mode's and the body reels' (its key handler must see keys typed into a note first)
flag = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "flag.html")).read()
fpart = lambda tag: flag[flag.index(f"<{tag}"):flag.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", fpart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + fpart("section") + "\n" + flag[flag.index('<div id="flagtoast"'):flag.index("</div>", flag.index('<div id="flagtoast"')) + 6] + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += fpart("script") + "\n"

movie = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "movie.html")).read()
part = lambda tag: movie[movie.index(f"<{tag}"):movie.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('<button class="btn round skip" id="next" aria-label="Next moment">▶▶</button>',
     '<button class="btn round skip" id="next" aria-label="Next moment">▶▶</button>\n'
     '          <button class="btn round skip" id="movie" aria-pressed="false" aria-label="Movie mode" title="Movie mode: skip the time between pictures and play them at a set frame rate (M)">'
     '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M5 3v10M11 3v10M2 6.3h3M2 9.7h3M11 6.3h3M11 9.7h3"/></svg></button>'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# settings (settings.html): its style joins the head's, its window goes into #app, and its script runs before the
# chrome script, so the chrome, movie mode and the viewer can all read window.cassiniSettings
settings = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "settings.html")).read()
spart = lambda tag: settings[settings.index(f"<{tag}"):settings.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", spart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + spart("section") + "\n\n" + '  <div id="loading">'),
    ("<script>\n// ---------- Cassini OS chrome", spart("script") + "\n<script>\n// ---------- Cassini OS chrome"),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)

# pause in the background (away.html): its style joins the head's, its note goes into #app, and its script runs right
# after the settings script (it adds two Playback settings), ahead of every script that draws or fetches: it holds the
# page's animation frames while the tab is hidden or the window has lost focus
away = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "away.html")).read()
apart = lambda tag: away[away.index(f"<{tag}"):away.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", apart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + away[away.index('<div id="awaynote"'):away.index("</div>", away.index('<div id="awaynote"')) + 6] + "\n\n" + '  <div id="loading">'),
    ("<script>\n// ---------- Cassini OS chrome", apart("script") + "\n<script>\n// ---------- Cassini OS chrome"),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)

# phone layout (phone.html): its style joins the head's and its script runs before the chrome script (after the
# settings script), so the window manager already knows whether it is laying out a phone
phone = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "phone.html")).read()
ppart = lambda tag: phone[phone.index(f"<{tag}"):phone.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", ppart("style")[len("<style>"):] + "\n</head>"),
    ("<script>\n// ---------- Cassini OS chrome", ppart("script") + "\n<script>\n// ---------- Cassini OS chrome"),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)

# shareable links (link.html): its style joins the head's, its toast goes into #app, and its script runs before the chrome
# script (after the settings script), so a link's view is applied after the settings have set the viewer up
link = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "link.html")).read()
lpart = lambda tag: link[link.index(f"<{tag}"):link.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", lpart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + lpart("div") + "\n\n" + '  <div id="loading">'),
    ("<script>\n// ---------- Cassini OS chrome", lpart("script") + "\n<script>\n// ---------- Cassini OS chrome"),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)

# performance (perf.html): its style joins the head's and its script runs before the chrome script (after the settings
# script), so the viewer can ask window.cassiniPerf for its pixel ratio when it makes its renderers
perf = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "perf.html")).read()
fpart = lambda tag: perf[perf.index(f"<{tag}"):perf.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", fpart("style")[len("<style>"):] + "\n</head>"),
    ("<script>\n// ---------- Cassini OS chrome", fpart("script") + "\n<script>\n// ---------- Cassini OS chrome"),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)

# image stabilization on this computer (steady-local.html): its script runs before the chrome script, whose camera
# feed asks window.cassiniSteadyLocal for a movie frame's smoothing
steadylocal = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "steady-local.html")).read()
assert study.count("<script>\n// ---------- Cassini OS chrome") == 1
study = study.replace("<script>\n// ---------- Cassini OS chrome", steadylocal[steadylocal.index("<script>"):steadylocal.index("</script>") + 9]
                      + "\n<script>\n// ---------- Cassini OS chrome")

# the Movie Editor's film plan and exposure levels worked out in the page (WP7a: plan-local.js, levels-local.js,
# window.cassiniPlanLocal): their scripts run before the chrome script, so the export and the Movie Editor find them;
# each is inlined once it exists in this folder, and left out until then
for js in ("plan-local.js", "levels-local.js"):
    jpath = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), js)
    if os.path.exists(jpath):
        body = open(jpath).read()
        assert "</script" not in body.lower(), f"{js}: no </script> inside an inlined script"
        study = study.replace("<script>\n// ---------- Cassini OS chrome", f"<script>\n// ---------- {js} (inlined by build.py)\n{body}\n</script>"
                              + "\n<script>\n// ---------- Cassini OS chrome")

# color smoothing on this computer (colour-smooth.html): its script runs before the chrome script, whose camera feed
# and film export ask window.cassiniColourSmooth to move a color picture toward its neighbours' palette
smooth = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "colour-smooth.html")).read()
study = study.replace("<script>\n// ---------- Cassini OS chrome", smooth[smooth.index("<script>"):smooth.index("</script>") + 9]
                      + "\n<script>\n// ---------- Cassini OS chrome")

# additional stabilization of a film on this computer (film-steady.html): its script runs before the chrome script, so
# the Movie Editor and the film export find window.cassiniFilmSteady
filmsteady = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "film-steady.html")).read()
study = study.replace("<script>\n// ---------- Cassini OS chrome", filmsteady[filmsteady.index("<script>"):filmsteady.index("</script>") + 9]
                      + "\n<script>\n// ---------- Cassini OS chrome")

# per-body camera windows (bodywin.html, a setting): its style joins the head's and its script runs after the chrome
# script, whose camera feed and window manager it reuses
bodywin = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "bodywin.html")).read()
bpart = lambda tag: bodywin[bodywin.index(f"<{tag}"):bodywin.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", bpart("style")[len("<style>"):] + "\n</head>")
study += bpart("script") + "\n"

# body reels (reel.html): its style joins the head's, its window goes into #app next to the others, and its
# script runs after the chrome script (it adds "Play a Body…" to the Go menu)
reel = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "reel.html")).read()
part = lambda tag: reel[reel.index(f"<{tag}"):reel.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# highlight reel (highlights.html): its style joins the head's, its window goes into #app, a Highlights menu joins the
# menu bar before Window (so the chrome script wires it with the other menus), and its script runs after the chrome script
hl = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "highlights.html")).read()
part = lambda tag: hl[hl.index(f"<{tag}"):hl.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
    ('    <div class="menu"><button aria-haspopup="true">Window</button>',
     '    <div class="menu"><button aria-haspopup="true">Highlights</button>\n      <ul id="hlmenu"></ul></div>\n'
     '    <div class="menu"><button aria-haspopup="true">Window</button>'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# sound (sound.html, off until switched on): its style joins the head's and its script runs after the chrome script,
# whose camera windows call window.cassiniPicture for each picture they put up
snd = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "sound.html")).read()
part = lambda tag: snd[snd.index(f"<{tag}"):snd.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>")
study += part("script") + "\n"

# movie export (export.html): its style joins the head's, its window goes into #app, and its script runs after the
# chrome script (it draws the marked stretch through window.studyTimeline and adds "Export Movie…" to the Go menu)
ex = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "export.html")).read()
part = lambda tag: ex[ex.index(f"<{tag}"):ex.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# pre-processing a stretch (segment.html): its style joins the head's, its bar and note go into #app, and its script runs
# after the export script, whose marks it follows ("cassini:marks") and whose timeline drawing it wraps
sg = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "segment.html")).read()
part = lambda tag: sg[sg.index(f"<{tag}"):sg.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("aside") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# the gallery (gallery.html): its style joins the head's, its window, share menu and toast go into #app, and its script
# runs after the chrome script and movie export's (it adds Add to Gallery to the picture windows and asks the export for
# a film's sound) and before the dock's, which opens it
gal = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "gallery.html")).read()
part = lambda tag: gal[gal.index(f"<{tag}"):gal.index(f"</{tag}>") + len(tag) + 3]
gextra = gal[gal.index('<ul id="galshare"'):gal.index("</div>", gal.index('<div id="galtoast"')) + 6]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n" + gextra + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# the zoom lens (loupe.html): its style joins the head's, the lens goes into #app, and its script runs after the chrome
# script; it finds the pictures under the pointer itself (every window's .well .shot, any img[data-loupe])
lp = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "loupe.html")).read()
part = lambda tag: lp[lp.index(f"<{tag}"):lp.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + lp[lp.index('<div id="loupe"'):lp.index("</div>", lp.index('<div id="loupe"')) + 6] + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# Cassini Studio (studio.html): its style joins the head's, its window goes into #app, and its script runs after the
# gallery's (it saves and shares through window.cassiniGallery) and before the dock's, which opens it
stu = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "studio.html")).read()
part = lambda tag: stu[stu.index(f"<{tag}"):stu.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# the Movie Editor (movieedit.html): its style joins the head's, its window goes into #app, and its script runs after
# Cassini Studio's (it draws with the studio's renderer and edits the look there) and the export's and pre-processing's,
# whose stretch it edits
me = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "movieedit.html")).read()
part = lambda tag: me[me.index(f"<{tag}"):me.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# the body view (bodymode.html): its style joins the head's, its window goes into #app, and its script runs after the
# chrome script (it reads the camera feeds and the window manager) and before the dock's, which opens it
bm = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "bodymode.html")).read()
part = lambda tag: bm[bm.index(f"<{tag}"):bm.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# the Moments window built out (moments.html): its style joins the head's and its script runs after the body view's,
# whose filter it follows ("cassini:bodymode"); it wraps the chrome's studyMoments and draws the list itself
mo = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "moments.html")).read()
part = lambda tag: mo[mo.index(f"<{tag}"):mo.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>")
study += part("script") + "\n"

# the orbit diagram (orbit.html): its style joins the head's and its script runs after the chrome script (the camera
# windows draw it when they show one, and the export draws it onto a saved picture)
od = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "orbit.html")).read()
part = lambda tag: od[od.index(f"<{tag}"):od.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>")
study += part("script") + "\n"

# the dock (dock.html): its style joins the head's, the dock goes into #app, and its script runs after the chrome
# script (the window manager minimizes into it through window.cassiniDock) and after the body windows' and the
# highlight reel's, whose windows it opens
dk = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "dock.html")).read()
part = lambda tag: dk[dk.index(f"<{tag}"):dk.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("nav") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
study += part("script") + "\n"

# About (about.html): its style joins the head's, its window goes into #app, and its script runs after the chrome script;
# the Credits tab lists credits.json, the one list of every credit, and every surface map, ring and shape file under
# web/replay/data/textures has to have an entry there
ab = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "about.html")).read()
part = lambda tag: ab[ab.index(f"<{tag}"):ab.index(f"</{tag}>") + len(tag) + 3]
credits = json.load(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "credits.json")))
ids = [e["id"] for g in credits["groups"] for e in g["entries"]]
assert len(ids) == len(set(ids)), "credits.json: an id is used twice"
assert all(e.get("title") and e.get("credit") and e.get("license") for g in credits["groups"] for e in g["entries"]), "credits.json: every entry needs a title, credit and license"
covered = {f for g in credits["groups"] for e in g["entries"] for f in e.get("files", [])}
texdir = os.path.join(HERE, "..", "..", "replay", "data", "textures")
for dirpath, _, names in os.walk(texdir):
    for n in names:
        rel = os.path.relpath(os.path.join(dirpath, n), texdir).replace(os.sep, "/")
        rel = re.sub(r"^[0-9]+k/", "", rel)
        assert n.endswith(".md") or rel in covered, f"{rel} has no credit: add it to the files of an entry in web/cassini-os/src/credits.json"
for old, new in [
    ("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
ascript = part("script")
assert ascript.count('/*CREDITS*/{"groups":[]}') == 1
study += ascript.replace('/*CREDITS*/{"groups":[]}', json.dumps({"groups": credits["groups"]}, ensure_ascii=False, separators=(",", ":"))) + "\n"

# the tour (tutorial.html): its style joins the head's and its script runs after every other part's (its hints point at
# their controls; the hint itself is made by the script)
tu = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "tutorial.html")).read()
part = lambda tag: tu[tu.index(f"<{tag}"):tu.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", part("style")[len("<style>"):] + "\n</head>")
study += part("script") + "\n"

def rep(old, new, count=1):
    global script
    assert script.count(old) == count, (old, script.count(old))
    script = script.replace(old, new)

rep('"use strict";\n', '''"use strict";
// ---------- study theme: colours and fonts for the canvas/3D parts come from CSS custom properties ----------
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const rgb3 = n => cssVar(n).split(",").map(Number);
const THEME = {
  clear: cssVar("--gl-clear"), fov: cssVar("--gl-fov"), fovW: cssVar("--gl-fov-w"), trail: rgb3("--gl-trail"),
  mkCassini: rgb3("--gl-mk-cassini"), mkTitan: rgb3("--gl-mk-titan"), mk: rgb3("--gl-mk"),
  orbit: cssVar("--gl-orbit"), orbitTitan: cssVar("--gl-orbit-titan"),
  grid: cssVar("--tl-grid"), text: cssVar("--tl-text"), font: cssVar("--tl-font"), efont: cssVar("--tl-efont"),
  barN: cssVar("--tl-n"), barW: cssVar("--tl-w"), axis: cssVar("--tl-axis"), ms: cssVar("--tl-ms"),
  sat: cssVar("--tl-sat"), titan: cssVar("--tl-titan"), other: cssVar("--tl-other"), now: cssVar("--tl-now"),
  nowGlow: cssVar("--tl-now-glow").replace(/"/g, ""), barStyle: cssVar("--tl-bar-style") || "solid"
};
''')
# Cassini OS opens at the Settings window's start time (playback.start). By default a visit with no ?t= lands on
# one of a few famous moments at random (settings.html, window.cassiniLandings), written into the address as a
# link; a pinned time from the older list is read here. The fallback is "In Saturn's Shadow", 2006-09-15, the WAC
# mosaic of Saturn backlit by the Sun, the benchmark in web/frames/mosaic_benchmark.py; a ?t= link wins
rep('get("t") || "2005-01-14T09:30:00"',
    'get("t") || (window.cassiniSettings && /^\\d{4}-/.test(cassiniSettings.get("playback.start")) && cassiniSettings.get("playback.start")) || "2006-09-15T14:28:00"')

# a landing moment (settings.html) outside the years the picture cache holds: another landing inside them, if any
rep('if (!inside(startEt)) startEt = (encounters.find(',
    'if (!inside(startEt)) startEt = (window.cassiniLandingIn && cassiniLandingIn(inside)) || (encounters.find(')

# surface map size: a ?tex= link wins, then the Settings window's choice
rep('const TEX_TIER = (new URLSearchParams(location.search).get("tex") || (location.hash.match(/^#tex-(\\w+)$/) || [])[1] || "2k").toLowerCase();',
    'const TEX_TIER = (new URLSearchParams(location.search).get("tex") || (location.hash.match(/^#tex-(\\w+)$/) || [])[1] || (window.cassiniSettings && cassiniSettings.get("view.textures")) || "2k").toLowerCase();')
# star sky size: a ?sky= link wins, then the Settings window's choice
rep('const SKY_TIER = (new URLSearchParams(location.search).get("sky") || "auto").toLowerCase();',
    'const SKY_TIER = (new URLSearchParams(location.search).get("sky") || (window.cassiniSettings && cassiniSettings.get("view.sky")) || "auto").toLowerCase();')
rep('renderer.setClearColor(0x04060b, 1);', 'renderer.setClearColor(new THREE.Color(THEME.clear), 1);')
rep('const c = n === "CASSINI" ? [0.56, 0.79, 1] : n === "HUYGENS" ? [1, 0.82, 0.55] : n === "TITAN" ? [0.88, 0.6, 0.29] : [0.62, 0.66, 0.72];',
    'const c = n === "CASSINI" ? THEME.mkCassini : n === "HUYGENS" ? [1, 0.82, 0.55] : n === "TITAN" ? THEME.mkTitan : THEME.mk;')
rep('probeTrail.userData.N = N; probeTrail.frustumCulled = false; scene.add(probeTrail);',
    'probeTrail.userData.N = N; probeTrail.frustumCulled = false; hudScene.add(probeTrail);')
rep('color: name === "TITAN" ? 0x6a4d32 : 0x343c4a', 'color: new THREE.Color(name === "TITAN" ? THEME.orbitTitan : THEME.orbit)')
rep('new THREE.LineBasicMaterial({ color: 0x8ec9ff,', 'new THREE.LineBasicMaterial({ color: new THREE.Color(THEME.fov),')
rep('new THREE.MeshBasicMaterial({ color: 0x8ec9ff,', 'new THREE.MeshBasicMaterial({ color: new THREE.Color(THEME.fov),')
rep('const col = catalog.cam[k] === "N" ? 0x8ec9ff : 0x9fb6d6;\n  fov.children[0].material.color.setHex(col); fov.children[1].material.color.setHex(col);',
    'const col = catalog.cam[k] === "N" ? THEME.fov : THEME.fovW;\n  fov.children[0].material.color.set(col); fov.children[1].material.color.set(col);')
rep('c[3 * i] = 0.56 * br; c[3 * i + 1] = 0.79 * br; c[3 * i + 2] = 1.0 * br;',
    'c[3 * i] = THEME.trail[0] * br; c[3 * i + 1] = THEME.trail[1] * br; c[3 * i + 2] = THEME.trail[2] * br;')

rep('const scene = new THREE.Scene();\n', """const scene = new THREE.Scene();
// HUD layer: orbits, trail and camera cone render into their own canvas when the page provides one,
// so the page can give them a neon glow without blurring the planets.
const hudCanvas = document.getElementById("hud");
const hudScene = hudCanvas ? new THREE.Scene() : scene;
const hudRenderer = hudCanvas ? new THREE.WebGLRenderer({ canvas: hudCanvas, antialias: true, logarithmicDepthBuffer: true, preserveDrawingBuffer: true }) : null;
if (hudRenderer) { hudRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); hudRenderer.setClearColor(0x000000, 1); }
""")
rep('fov.visible = false; scene.add(fov);', 'fov.visible = false; hudScene.add(fov);')
# the camera cones belong to Cassini: with the view on a body they flick on and off with every frame, so they are
# drawn only while the view is on Cassini (free or follow camera) unless View > "Camera cones on every view" is on
rep('function updateFov() {\n  fov.visible = false;\n',
    'function updateFov() {\n  fov.visible = false;\n'
    '  if (state.focus !== "CASSINI" && !(window.cassiniSettings && cassiniSettings.get("view.conesEverywhere"))) return;\n')
rep('trailLine.userData.N = N; trailLine.frustumCulled = false; scene.add(trailLine);', 'trailLine.userData.N = N; trailLine.frustumCulled = false; hudScene.add(trailLine);')
rep('ln.frustumCulled = false; ln.userData.last = -1e99; scene.add(ln);', 'ln.frustumCulled = false; ln.userData.last = -1e99; hudScene.add(ln);')
rep('renderer.setSize(w, h, false); camera.aspect = w / h;', 'renderer.setSize(w, h, false); if (hudRenderer) hudRenderer.setSize(w, h, false); camera.aspect = w / h;')
rep('  } else renderer.render(scene, camera);\n', """  } else renderer.render(scene, camera);
  if (hudRenderer) { if (window.studyBeforeHud) window.studyBeforeHud(); hudRenderer.render(hudScene, camera); if (window.studyAfterRender) window.studyAfterRender(); }
""")
rep('    el.style.transform = `translate(${x}px, ${y}px) translateY(-50%)`;\n', """    el.style.transform = `translate(${x}px, ${y}px) translateY(-50%)`;
    if (window.studyLabel) window.studyLabel(name, el, (vA.x + 1) / 2 * w, y, pr);
""")

# performance (perf.html): the canvases are not kept between frames (keeping them costs a copy per frame), the pixel
# ratio follows Settings > Performance, a frame in which nothing moved is not drawn, and the frame rate is measured
rep('const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true, preserveDrawingBuffer: true });\nrenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));',
    'const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true, powerPreference: "high-performance" });\nrenderer.setPixelRatio(window.cassiniPerf ? cassiniPerf.pixelRatio() : Math.min(window.devicePixelRatio, 2));')
rep('new THREE.WebGLRenderer({ canvas: hudCanvas, antialias: true, logarithmicDepthBuffer: true, preserveDrawingBuffer: true }) : null;\nif (hudRenderer) { hudRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));',
    'new THREE.WebGLRenderer({ canvas: hudCanvas, antialias: true, logarithmicDepthBuffer: true }) : null;\nif (hudRenderer) { hudRenderer.setPixelRatio(window.cassiniPerf ? cassiniPerf.hudPixelRatio() : Math.min(window.devicePixelRatio, 2));')
rep("""  renderer.clear();
  const cd = camera.position.distanceTo(cassini.position);
  if (cd < 0.01) {""", """  // bring the camera's world matrix up to date with where the frame left it: a render does this, but a frame that is
  // not drawn kept the one Object3D.lookAt left half-way (the orbit controls' aim, before the follow view turned it),
  // and the rest test and the labels both read it, so while paused the labels jumped between two places
  camera.updateMatrixWorld();
  const draw = !window.cassiniPerf || cassiniPerf.draw(now);
  if (draw) renderer.clear();
  const cd = camera.position.distanceTo(cassini.position);
  if (!draw) {}
  else if (cd < 0.01) {""")
rep("""  if (hudRenderer) { if (window.studyBeforeHud) window.studyBeforeHud(); hudRenderer.render(hudScene, camera); if (window.studyAfterRender) window.studyAfterRender(); }
""", """  if (hudRenderer && draw && !document.body.classList.contains("nohud")) {
    if (window.studyBeforeHud) window.studyBeforeHud();
    hudRenderer.render(hudScene, window.studyHudCam || camera);
    if (window.studyAfterRender) window.studyAfterRender();
  }
  if (window.cassiniPerf) cassiniPerf.frame(now, draw);
""")
# the moons' painted look (noise, craters) is only worked out when there is no surface map to show instead
rep("""        float m = 0.0, craters = 0.0;
        if (kind < 3.5) { m = fbm(nb * 5.0) - 0.5; craters = smoothstep(0.62, 0.7, vnoise(nb * 22.0)) * 0.12; }
        vec3 alb = color * (1.0 + 0.32 * m - craters);""", """        float m = 0.0, craters = 0.0;
        if (hasMap < 0.5 && kind < 3.5) { m = fbm(nb * 5.0) - 0.5; craters = smoothstep(0.62, 0.7, vnoise(nb * 22.0)) * 0.12; }
        vec3 alb = color * (1.0 + 0.32 * m - craters);""")
rep('t.anisotropy = renderer.capabilities.getMaxAnisotropy();', 't.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());')
# the Moments list greys out the moments already past: only touch the list when that count changes
rep('  document.querySelectorAll("#mlist li").forEach(li => li.classList.toggle("past", +li.dataset.et < state.et - 3600));\n',
    """  const past = momentsBefore(state.et - 3600);
  if (past !== lastPast) { lastPast = past; document.querySelectorAll("#mlist li").forEach(li => li.classList.toggle("past", +li.dataset.et < state.et - 3600)); }
""")
rep('let lastT = performance.now(), lastTrailEt = -1e99, lastTrailFocus = "", lastReady = true;\n',
    """let lastT = performance.now(), lastTrailEt = -1e99, lastTrailFocus = "", lastReady = true, lastPast = -1, momentEts = null;
// how many moments in the list come before et (their times are read from the list once, and again if it changes)
function momentsBefore(et) {
  const list = $("mlist");
  if (!momentEts || momentEts.n !== list.childElementCount) momentEts = { n: list.childElementCount, ets: [...list.querySelectorAll("li[data-et]")].map(li => +li.dataset.et) };
  let c = 0; for (const t of momentEts.ets) if (t < et) c++;
  return c;
}
""")

# after a pause in the background (away.html) the clock carries on from where it stopped: the first frame back
# counts from the moment the page came back, not from the last frame before it went
rep('  const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;\n',
    '  const dt = Math.max(0, Math.min(0.1, (now - lastT) / 1000)); lastT = now;\n')
rep('function frame(now) {\n', 'document.addEventListener("cassini:away", e => { if (!e.detail.away) lastT = performance.now(); });\nfunction frame(now) {\n')

# surface maps are decoded off the main thread (createImageBitmap) where the browser can, so a 2k or 4k map arriving
# does not freeze the view while it decodes; a browser that cannot falls back to the plain loader
rep('const texLoader = new THREE.TextureLoader();\n', """const texLoader = new THREE.TextureLoader();
const bitmapLoader = typeof createImageBitmap === "function" && THREE.ImageBitmapLoader ? new THREE.ImageBitmapLoader().setOptions({ imageOrientation: "flipY", premultiplyAlpha: "none" }) : null;
function loadTexture(url, onLoad, onError) {
  const plain = () => texLoader.load(url, onLoad, undefined, onError);
  if (!bitmapLoader) return plain();
  bitmapLoader.load(url, bmp => { const t = new THREE.CanvasTexture(bmp); t.flipY = false; onLoad(t); }, undefined, plain);
}
""")
rep('  texLoader.load(dir + f + ".webp", t => {', '  loadTexture(dir + f + ".webp", t => {')
rep('  }, undefined, () => console.warn("texture missing for " + name));', '  }, () => console.warn("texture missing for " + name));')

# HUD hook: studies can add their own read-outs (and the speed reads from the shared scale, any speed the slider sets)
rep('''  $("mday").textContent = `Mission day ${fmtInt(Math.floor((ms - LAUNCH_MS) / 86400000))} · ${SPEEDS.find(s => s[0] === state.speed)[1]}${state.playing ? "" : " · paused"}`;''',
    '''  $("mday").textContent = `Mission day ${fmtInt(Math.floor((ms - LAUNCH_MS) / 86400000))} · ${cassiniSpeed.label(state.speed)}${state.playing ? "" : " · paused"}`;
  if (window.studyHud) window.studyHud(ms);''')
rep('''<span class="sc" title="Photo score">''', '''<span class="sc" title="Photo score" style="--s:${Math.round(e.photo_score)}">''')
rep('''    list.appendChild(li);
  }
}''', '''    list.appendChild(li);
  }
  if (window.studyMoments) window.studyMoments(picks);
}''')
# playback hook: the page can slow the clock (Cassini OS caps the pictures per second during imaging bursts)
rep('    setTime(state.et + dt * state.speed);\n',
    '    setTime(window.studyAdvance ? window.studyAdvance(state.et, dt, state.speed) : state.et + dt * state.speed);\n')
rep('''function setPlaying(p) { state.playing = p; $("play").textContent = p ? "❚❚" : "▶"; }''',
    '''function setPlaying(p) { state.playing = p; $("play").textContent = p ? "❚❚" : "▶"; $("play").classList.toggle("playing", p); }''')
# timeline colours/fonts
tl = script[script.index('function drawTimeline() {'):script.index('function setView(')]
t2 = tl
for a, b in [
  ('g.font = "400 10px \'IBM Plex Mono\', monospace";', 'g.font = THEME.font;'),
  ('g.fillStyle = "rgba(150,172,205,0.18)"; g.fillRect(Math.round(x), 0, 1, h);', 'g.fillStyle = THEME.grid; g.fillRect(Math.round(x), 0, 1, h);'),
  ('g.fillStyle = "#8794a8"; g.fillText(lab, x + 4, 5);', 'g.fillStyle = THEME.text; g.fillText(lab, x + 4, 5);'),
  ('g.fillStyle = "rgba(142,201,255,0.75)";', 'g.fillStyle = THEME.barN;'),
  ('g.fillStyle = "rgba(111,143,179,0.65)";', 'g.fillStyle = THEME.barW;'),
  ('g.fillStyle = "rgba(150,172,205,0.25)"; g.fillRect(0, base, w, 1);', 'g.fillStyle = THEME.axis; g.fillRect(0, base, w, 1);'),
  ('g.font = "600 10px \'Barlow Condensed\', sans-serif";', 'g.font = THEME.efont;'),
  ('g.fillStyle = ms ? "#e6bb68" : e.body === "SATURN" ? "rgba(230,187,104,0.45)" : e.body === "TITAN" ? "#e0994a" : "#c7d0dc";',
   'g.fillStyle = ms ? THEME.ms : e.body === "SATURN" ? THEME.sat : e.body === "TITAN" ? THEME.titan : THEME.other;'),
  ('g.fillStyle = "#e6bb68"; g.fillRect(Math.round(xn) - 1, 0, 2, h);',
   'if (THEME.nowGlow) { g.fillStyle = THEME.nowGlow; g.fillRect(Math.round(xn) - 4, 0, 8, h); }\n  g.fillStyle = THEME.now; g.fillRect(Math.round(xn) - 1, 0, 2, h);\n  if (window.studyTimeline) window.studyTimeline(g, w, h, xn);'),
  ]:
    assert t2.count(a) == 1, a
    t2 = t2.replace(a, b)
# bar style: "dots" draws each slice as a column of small squares (LCD look)
t2 = t2.replace('if (nN) { const hh = sc(nN) * (base - 22); g.fillRect(x, base - hh, bw - 0.5, hh); }',
                'if (nN) { const hh = sc(nN) * (base - 22); barRect(g, x, base - hh, bw - 0.5, hh); }')
t2 = t2.replace('if (nW) { const hh = sc(nW) * (h - base - 6); g.fillRect(x, base + 1, bw - 0.5, hh); }',
                'if (nW) { const hh = sc(nW) * (h - base - 6); barRect(g, x, base + 1, bw - 0.5, hh); }')
t2 = t2.replace('  // camera frames per pixel slice, narrow-angle up, wide-angle down\n', '  if (window.studyBars) window.studyBars(g, w, h); else {\n  // camera frames per pixel slice, narrow-angle up, wide-angle down\n')
t2 = t2.replace('g.fillStyle = THEME.axis; g.fillRect(0, base, w, 1);\n', 'g.fillStyle = THEME.axis; g.fillRect(0, base, w, 1);\n  }\n')
# the months not loaded: Cassini OS draws them in its own lanes (studyBars, head-quiet.html)
assert t2.count('  drawUnloadedBars(g, w, h);\n') == 1
t2 = t2.replace('  drawUnloadedBars(g, w, h);\n', '  if (!window.studyBars) drawUnloadedBars(g, w, h);\n')
script = script.replace(tl, '''function barRect(g, x, y, w, h) {
  if (THEME.barStyle !== "dots") { g.fillRect(x, y, w, h); return; }
  for (let yy = Math.round(y + h); yy > y; yy -= 3) g.fillRect(x, yy - 2, w, 2);
}
''' + t2)
# real Cassini: NASA's Cassini-Huygens model (NASA 3D Resources), Draco-decoded, shipped as base64 text
rep('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>\n',
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>\n')
# smooth lines (smoothlines.html): its script runs right after three.js loads, ahead of the viewer, so every line the
# viewer adds to a scene is drawn anti-aliased
sl = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "smoothlines.html")).read()
rep('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>\n',
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>\n' + sl[sl.index("<script>"):sl.index("</script>") + 9] + "\n")
rep('function makeCassini() {\n  // Rough', 'function makeCassiniPrimitive() {\n  // Rough')
rep('// ---------- state ----------\n', """// NASA's Cassini-Huygens model replaces the primitive one once it has loaded.
const HUYGENS_RELEASE_ET = 157212064.18; // 2004-12-25 02:00 UTC, Huygens separates (same as the release milestone)
let cassiniProbe = [];
function makeCassini() {
  const g = new THREE.Group(), prim = makeCassiniPrimitive();
  g.add(prim);
  if (THREE.GLTFLoader) fetch("data/models/cassini.glb.b64.txt").then(r => { if (!r.ok) throw new Error(r.status); return r.text(); }).then(t => {
    const s = atob(t.trim()), u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    new THREE.GLTFLoader().parse(u.buffer, "", gltf => {
      const m = gltf.scene;
      // model axes -> the cassini group (+Z high-gain dish = body -Z, +Y camera side = body -Y, X = body X):
      // its +Y (dish) goes to +Z, its +X (Huygens side, body -X) to -X, its +Z (remote sensing pallet) to +Y
      m.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(-1, 0, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 1, 0)));
      m.updateMatrixWorld(true);
      // scale so the high-gain dish is its real 4 m across
      const dish = m.getObjectByName("dish"), box = new THREE.Box3().setFromObject(dish), sz = box.getSize(new THREE.Vector3());
      m.scale.setScalar(4 / Math.max(sz.x, sz.y, sz.z));
      // the camera cones start at the front of the two camera tubes on the remote sensing pallet (model metres,
      // measured on the model: the wide 28 cm tube is the NAC, the slim 11 cm one beside it the WAC; 1 cm out
      // so the cone's tip is not hidden inside the tube)
      m.updateMatrix();
      CAM_MOUNT.N.set(0.589, 0.401, 1.827).applyMatrix4(m.matrix);
      CAM_MOUNT.W.set(0.981, 0.615, 1.593).applyMatrix4(m.matrix);
      m.traverse(o => {
        o.layers.set(1);
        if (/_h$/.test(o.name)) cassiniProbe.push(o);
        // the viewer renders without sRGB output, so read the textures as-is or the foil comes out too dark
        // the white parts clip to pure white in full sun; pull them down so the dish keeps its shading
        if (o.isMesh && /dish|plastic_white/.test(o.material.name)) o.material.color.multiplyScalar(0.55);
        if (o.isMesh && o.material.map) { o.material.map.encoding = THREE.LinearEncoding; o.material.color.multiplyScalar(0.85); o.material.needsUpdate = true; }
      });
      cassiniProbe.forEach(o => { o.visible = state.et < HUYGENS_RELEASE_ET; });
      g.remove(prim); g.add(m);
      window.cassiniModel = m;
    }, e => console.warn("Cassini model:", e));
  }).catch(e => console.warn("Cassini model:", e));
  return g;
}

// ---------- state ----------
""")
rep('  cassini.scale.setScalar(Math.max(1e-6, dist * 0.002));\n',
    '  cassini.scale.setScalar(Math.max(1e-6, dist * 0.002));\n  for (const o of cassiniProbe) o.visible = state.et < HUYGENS_RELEASE_ET;\n')
# close-up pass: blow Cassini and the close camera up a million times so the log depth buffer has the precision
# to separate the real model's thin parts (at true scale they z-fight into speckle)
rep("""    closeCam.position.copy(camera.position); closeCam.quaternion.copy(camera.quaternion);
    closeCam.fov = camera.fov; closeCam.aspect = camera.aspect; closeCam.near = cd * 0.02; closeCam.far = cd * 60;
    closeCam.updateProjectionMatrix();
    renderer.clearDepth();
    renderer.render(scene, closeCam);""", """    const K = 1e6, cs = cassini.scale.x;
    closeCam.position.copy(camera.position).sub(cassini.position).multiplyScalar(K).add(cassini.position); closeCam.quaternion.copy(camera.quaternion);
    closeCam.fov = camera.fov; closeCam.aspect = camera.aspect; closeCam.near = cd * 0.02 * K; closeCam.far = cd * 60 * K;
    closeCam.updateProjectionMatrix();
    cassini.scale.setScalar(cs * K);
    renderer.clearDepth();
    renderer.render(scene, closeCam);
    cassini.scale.setScalar(cs);""")
rep('  const card = $("imgcard");\n', '  const card = $("camsink");\n')   # the page has a window per camera (see the head)
# finale hooks (finale.html): its own clock before the bodies are placed, Cassini carried on past the end of the data,
# its attitude, and the camera after the orbit controls
rep('  updateBodies();\n  if (ready && state.focus', '  if (window.studyFrame) window.studyFrame(dt);\n  updateBodies();\n  if (ready && state.focus')
rep('  for (const name in tracks) positionAt(tracks[name], state.et, pos[name]);\n',
    '  for (const name in tracks) positionAt(tracks[name], state.et, pos[name]);\n  if (window.studyPositions) window.studyPositions();\n')
rep('  } else { relScene("EARTH", vA); cassini.lookAt(vA); }\n', '  } else { relScene("EARTH", vA); cassini.lookAt(vA); }\n  if (window.studyAttitude) window.studyAttitude();\n')
rep('  aimFollow();\n', '  aimFollow();\n  if (window.studyCamera) window.studyCamera();\n')
# Huygens after the release (huygens-release.html): window.studyCoast places the probe for its first hour from ESA's
# separation numbers and gives it a model of its own until it reaches Titan's air; it works without the probe's own
# track (data/huygens.json) too, for the days before Cassini's getaway burn. Not a cutscene hook: it runs whenever the
# probe is on its own
# From the landing on, window.studyLanded (huygens-landing.html) keeps the probe on its landing point for good, marked
# while the camera is near Titan, and draws it there up close
rep('function probeActive() { return !!probe && state.et >= probe.track.start && state.et <= probe.track.end; }',
    'function probeActive() { return !!probe && state.et >= probe.track.start && state.et <= probe.track.end || !probe && !!window.studyCoast && studyCoast.active(state.et) || !!window.studyLanded && studyLanded.active(state.et); }')
rep('  if (name === "HUYGENS") return probeActive();\n', '  if (name === "HUYGENS") return probeActive() && (!window.studyLanded || studyLanded.marked(state.et));\n')
rep('  if (probe) {\n    pos.HUYGENS = v3(); probeObj = new THREE.Object3D(); names.push("HUYGENS");',
    '  if (probe || window.studyCoast) {\n    pos.HUYGENS = v3(); probeObj = new THREE.Object3D(); names.push("HUYGENS");')
rep('  if (probe) { positionAt(probe.track, state.et, pos.HUYGENS); relScene("HUYGENS", probeObj.position); }',
    '  if (pos.HUYGENS) {\n    if (probe) positionAt(probe.track, state.et, pos.HUYGENS);\n    if (window.studyCoast) studyCoast.place(state.et, pos.HUYGENS);\n    if (window.studyLanded) studyLanded.place(state.et, pos.HUYGENS);\n    relScene("HUYGENS", probeObj.position);\n    if (window.studyCoast) studyCoast.draw();\n    if (window.studyLanded) studyLanded.draw();\n  }')
rep('  probeTrail.visible = probeActive() && state.et < probe.events.landing + 6 * 3600;',
    '  probeTrail.visible = !!probe && probeActive() && state.et < probe.events.landing + 6 * 3600;')
rep('  pe.hidden = !probeActive();', '  pe.hidden = !probe || !shown("HUYGENS");')
rep('  const near = probe && state.et > probe.track.start - 30 * 86400 && state.et < probe.track.end + 30 * 86400;',
    '  const near = shown("HUYGENS") || probe && state.et >= (probe.events.separation || probe.track.start) && state.et < probe.track.end + 30 * 86400;')
# while it coasts, the probe is a spacecraft to look at up close, not a point above Titan; landed, it is 10 m off
rep('name === "HUYGENS" ? 4 :', 'name === "HUYGENS" ? (window.studyCoast && studyCoast.modelShown(state.et) ? 1.6e-5 : window.studyLanded && studyLanded.active(state.et) ? 1e-5 : 4) :')
rep('  if (name === "HUYGENS") {\n    // from the side', '  if (name === "HUYGENS" && !(window.studyCoast && studyCoast.modelShown(state.et)) && !(window.studyLanded && studyLanded.active(state.et))) {\n    // from the side')
# surface sites (surface-sites.html, window.studySites): places on a body's surface with nothing of their own to draw,
# such as Dragonfly's future landing site on Titan, marked with the viewer's own marker dot and label. Each is one
# more name in the marker list; its style joins the head's and its script runs after the chrome script
ss = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "surface-sites.html")).read()
spart = lambda tag: ss[ss.index(f"<{tag}"):ss.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", spart("style")[len("<style>"):] + "\n</head>")
study += spart("script") + "\n"
rep('  const mg = new THREE.BufferGeometry();\n  mg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(names.length * 3), 3));',
    '  if (window.studySites) for (const s of studySites.list) names.push(s.key);\n  const mg = new THREE.BufferGeometry();\n  mg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(names.length * 3), 3));')
rep('n === "HUYGENS" ? [1, 0.82, 0.55] : n === "TITAN" ? THEME.mkTitan',
    'n === "HUYGENS" ? [1, 0.82, 0.55] : window.studySites && studySites.is(n) ? studySites.color(n) : n === "TITAN" ? THEME.mkTitan')
rep('    el.className = "lbl" + (name === "CASSINI" ? " cassini" : name === "HUYGENS" ? " probe" : LABEL_PRIORITY(name) < 5 ? " major" : "");\n'
    '    el.textContent = titleCase(name);\n'
    '    el.addEventListener("click", () => setFocus(name));',
    '    const site = window.studySites && studySites.is(name);\n'
    '    el.className = "lbl" + (site ? " site" : name === "CASSINI" ? " cassini" : name === "HUYGENS" ? " probe" : LABEL_PRIORITY(name) < 5 ? " major" : "");\n'
    '    el.textContent = site ? studySites.label(name) : titleCase(name);\n'
    '    el.addEventListener("click", () => site ? studySites.click(name) : setFocus(name));')
rep('function objPos(n) { return n === "CASSINI" ? cassini.position : ',
    'function objPos(n) { return n === "CASSINI" ? cassini.position : window.studySites && studySites.is(n) ? studySites.obj(n).position : ')
rep('function shown(name) {\n', 'function shown(name) {\n  if (window.studySites && studySites.is(name)) return studySites.marked(name);\n')
rep('function bodyRadius(name) { return name === "CASSINI" ? 0.0035 : ',
    'function bodyRadius(name) { return name === "CASSINI" ? 0.0035 : window.studySites && studySites.is(name) ? studySites.radius(name) : ')
rep('  state.target = imagingTarget();\n', '  if (window.studySites) studySites.place();\n  state.target = imagingTarget();\n')
# sites are placed last among the labels, so they never push a body's label out, and a label's box is as wide as its
# first line (its name; the HUD adds a second line under it), so a site's is as wide as its own name
rep('const LABEL_PRIORITY = n => n === state.focus ? 0 :', 'const LABEL_PRIORITY = n => window.studySites && studySites.is(n) ? 6 : n === state.focus ? 0 :')
rep('    const box = [x, y - 8, x + name.length * 8 + 10, y + 8];', '    const box = [x, y - 8, x + (el.firstChild ? el.firstChild.textContent : name).length * 8 + 10, y + 8];')
# the close-up pass takes in every small craft near the camera (Cassini, and Huygens on its own): the nearest sets the
# range, and all of them are blown up about it together
rep("""  const cd = camera.position.distanceTo(cassini.position);
  if (!draw) {}""", """  const closeObjs = [cassini].concat(window.studyCloseObjects ? studyCloseObjects() : []);
  let cRef = cassini, cd = camera.position.distanceTo(cassini.position);
  for (const o of closeObjs) { const d = camera.position.distanceTo(o.position); if (o.visible && d < cd) { cd = d; cRef = o; } }
  if (!draw) {}""")
rep("""    const K = 1e6, cs = cassini.scale.x;
    closeCam.position.copy(camera.position).sub(cassini.position).multiplyScalar(K).add(cassini.position); closeCam.quaternion.copy(camera.quaternion);
    closeCam.fov = camera.fov; closeCam.aspect = camera.aspect; closeCam.near = cd * 0.02 * K; closeCam.far = cd * 60 * K;
    closeCam.updateProjectionMatrix();
    cassini.scale.setScalar(cs * K);
    renderer.clearDepth();
    renderer.render(scene, closeCam);
    cassini.scale.setScalar(cs);""", """    const K = 1e6, O = cRef.position.clone(), keep = closeObjs.map(o => [o.position.clone(), o.scale.clone()]);
    let far = cd * 60;
    for (const o of closeObjs) if (o.visible) far = Math.max(far, Math.min(camera.position.distanceTo(o.position) * 1.5, 0.02));
    closeCam.position.copy(camera.position).sub(O).multiplyScalar(K).add(O); closeCam.quaternion.copy(camera.quaternion);
    closeCam.fov = camera.fov; closeCam.aspect = camera.aspect; closeCam.near = cd * 0.02 * K; closeCam.far = far * K;
    closeCam.updateProjectionMatrix();
    for (const o of closeObjs) { o.position.sub(O).multiplyScalar(K).add(O); o.scale.multiplyScalar(K); }
    renderer.clearDepth();
    renderer.render(scene, closeCam);
    closeObjs.forEach((o, i) => { o.position.copy(keep[i][0]); o.scale.copy(keep[i][1]); });""")
# effective wavelength of every filter pair, for placing colour channels: "N:CL1/RED" -> nm
nm = {}
for line in open(os.path.join(HERE, "..", "..", "..", "filter_calibration.csv")).read().splitlines()[1:]:
    camera, filters, wavelength = line.split(",")[:3]
    nm[camera] = nm.get(camera, []) + [(filters, float(wavelength))]
pairs = {}
WHEELS = {"ISSNA": ("CL1", "RED", "BL1", "UV2", "UV1", "IRP0", "P120", "P60", "P0", "HAL", "IR4", "IR2"),
          "ISSWA": ("CL1", "IR3", "IR4", "IR5", "CB3", "MT3", "CB2", "MT2", "IR2")}
for camera, rows in nm.items():
    for filters, wavelength in rows:
        # the table joins the two wheels' names; split at the first wheel's name it starts with
        first = max((f for f in WHEELS[camera] if filters.startswith(f)), key=len)
        pairs[f"{camera[3]}:{first}/{filters[len(first):]}"] = wavelength
assert study.count("/*FILTER_NM*/{}") == 1
study = study.replace("/*FILTER_NM*/{}", json.dumps(pairs, separators=(",", ":"), sort_keys=True))
# loading screen (loading.html): its style joins the head's, its overlay goes into #app, and its script runs after the
# viewer's (it reads yearReady and the viewer's three.js); the facts come from loading-facts.json
loading = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "loading.html")).read()
lpart = lambda tag: loading[loading.index(f"<{tag}"):loading.index(f"</{tag}>") + len(tag) + 3]
facts = json.load(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "loading-facts.json")))
assert facts and all(f["text"] and f["source"].startswith("https://") for f in facts)
for old, new in [
    ("</style>\n</head>", lpart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + lpart("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
lscript = lpart("script")
assert lscript.count("/*FACTS*/[]") == 1
script += lscript.replace("/*FACTS*/[]", json.dumps(facts, ensure_ascii=False)) + "\n"
# what every cutscene shares (cutscene.html): its style joins the head's and its script runs before any cutscene's (it
# fills the viewer's cutscene hooks patched in below and wraps the clock's studyAdvance hook for their triggers)
cs = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "cutscene.html")).read()
cpart = lambda tag: cs[cs.index(f"<{tag}"):cs.index(f"</{tag}>") + len(tag) + 3]
assert study.count("</style>\n</head>") == 1
study = study.replace("</style>\n</head>", cpart("style")[len("<style>"):] + "\n</head>")
script += cpart("script") + "\n"
# atmospheric entry effects for the cutscenes (entry-fx.html, adds to cutscene.html's fx): script only
efx = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "entry-fx.html")).read()
script += efx[efx.index("<script"):efx.index("</script>") + len("</script>")] + "\n"
# Huygens' own models (huygens-models.html, window.huygensModels), for the release and landing cutscenes: script only
hmod = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "huygens-models.html")).read()
script += hmod[hmod.index("<script"):hmod.index("</script>") + len("</script>")] + "\n"
# the Grand Finale (finale.html): its style joins the head's, its overlay goes into #app, and its script runs last (it
# registers its hooks and its trigger with cutscene.html)
fin = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "finale.html")).read()
npart = lambda tag: fin[fin.index(f"<{tag}"):fin.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", npart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + npart("section") + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
# the real readings from the final plunge (finale-data.json, from NASA's Planetary Data System), when there are some
fd = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "finale-data.json")
fscript = npart("script")
assert fscript.count("/*FINALE_DATA*/null") == 1
if os.path.exists(fd):
    fscript = fscript.replace("/*FINALE_DATA*/null", json.dumps(json.load(open(fd)), separators=(",", ":")))
# the people who made the mission happen (mission-team.json, from NASA's and ESA's team pages): the credits roll after
# the finale, and window.cassiniTeam for the About window
team = json.load(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "mission-team.json")))
assert all(s.get("title") and (s.get("people") or s.get("names") or s.get("text") or s.get("groups")) for s in team["sections"]), "mission-team.json: every section needs a title and people, names, text or groups"
assert fscript.count("/*MISSION_TEAM*/null") == 1
fscript = fscript.replace("/*MISSION_TEAM*/null", json.dumps({k: team[k] for k in ("intro", "sections", "closing", "sources")}, ensure_ascii=False, separators=(",", ":")))
script += fscript + "\n"
# more cutscenes, each its own file spliced like the finale (style into the head, section into #app, script after the
# finale's; each chains the study* hooks): skipped while a file is not there yet
CUTSCENES = ["soi.html", "launch.html", "huygens-release.html", "huygens-landing.html"]
for name in CUTSCENES:
    cpath = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), name)
    if not os.path.exists(cpath):
        continue
    cut = open(cpath).read()
    cpart = lambda tag: cut[cut.index(f"<{tag}"):cut.index(f"</{tag}>") + len(tag) + 3]
    for old, new in [
        ("</style>\n</head>", cpart("style")[len("<style>"):] + "\n</head>"),
        ('  <div id="loading">', "  " + cpart("section") + "\n\n" + '  <div id="loading">'),
    ]:
        assert study.count(old) == 1, old
        study = study.replace(old, new)
    cscript = cpart("script")
    # a cutscene's published numbers (<name>-data.json), written in where its script asks for them
    cdata = cpath[:-len(".html")] + "-data.json"
    marker = "/*" + name[:-len(".html")].upper().replace("-", "_") + "_DATA*/null"
    if marker in cscript:
        assert os.path.exists(cdata), cdata
        cscript = cscript.replace(marker, json.dumps(json.load(open(cdata)), ensure_ascii=False, separators=(",", ":")))
    script += cscript + "\n"
# what Cassini is doing (activity.html) and what it had seen of each moon (coverage.html): each one's style joins the
# head's and its script runs after the viewer's and the cutscenes' (they read the viewer's pointing, tracks and moons,
# and wrap the attitude, read-out and timeline hooks)
for part in ("activity.html", "coverage.html"):
    act = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), part)).read()
    apart = lambda tag: act[act.index(f"<{tag}"):act.index(f"</{tag}>") + len(tag) + 3]
    assert study.count("</style>\n</head>") == 1
    study = study.replace("</style>\n</head>", apart("style")[len("<style>"):] + "\n</head>")
    script += apart("script") + "\n"
# ambient mode (ambient.html): its style joins the head's, its overlay goes into #app, and its script runs last (it
# chains the cutscenes' studyFrame hook and restyles the camera windows as its picture panels)
amb = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "ambient.html")).read()
mpart = lambda tag: amb[amb.index(f"<{tag}"):amb.index(f"</{tag}>") + len(tag) + 3]
for old, new in [
    ("</style>\n</head>", mpart("style")[len("<style>"):] + "\n</head>"),
    ('  <div id="loading">', "  " + amb[amb.index('<div id="ambient"'):amb.index("</div>\n\n<script>") + 6] + "\n\n" + '  <div id="loading">'),
]:
    assert study.count(old) == 1, old
    study = study.replace(old, new)
script += mpart("script") + "\n"
# the page's build id (about.html's /*BUILD*/""): a hash of everything else in it, so the same sources always build the
# same page, and the frame server's /version.json (which reads it back from index.html) and each flag can tell an
# older page, open since before the last merge, from the one being served
page = study + script
# the public switch (settings.html; docs/public-site, WP6): CASSINI_PUBLIC and CASSINI_FRAMES_HOST come from the
# top of this file (--public, --frames, site.json)
PUBLIC, FRAMES_HOST = os.environ.get("CASSINI_PUBLIC") == "1", os.environ.get("CASSINI_FRAMES_HOST", "")
assert page.count("/*PUBLIC*/false") == 1 and page.count('/*FRAMES_HOST*/""') == 1
page = page.replace("/*PUBLIC*/false", "/*PUBLIC*/" + ("true" if PUBLIC else "false"))
page = page.replace('/*FRAMES_HOST*/""', "/*FRAMES_HOST*/" + json.dumps(FRAMES_HOST.rstrip("/")))
if PUBLIC:
    # every part that picks its frame server itself (the camera windows, the export, the gallery, the viewer...) takes
    # the frames host settings.html chose, after ?frames= as before
    pick = 'const q = new URLSearchParams(location.search).get("frames");\n'
    n = 0
    for m in list(re.finditer(re.escape(pick) + r'( *)if \(q\) return q\.replace\(/\\/\$/, ""\);\n', page))[::-1]:
        page = page[:m.end()] + m.group(1) + "if (window.cassiniFrames) return window.cassiniFrames;\n" + page[m.end():]
        n += 1
    assert n == page.count(pick), "a part picks its frame server another way: point it at window.cassiniFrames"
    # three.js and the fonts from vendor/ (the top of this file copies them there)
    for url, path in [(u, p) for p, (u, _) in VENDOR.items() if u.endswith(".js")]:
        assert page.count(f'<script src="{url}"></script>') == 1, url
        page = page.replace(f'<script src="{url}"></script>', f'<script src="{path}"></script>')
    # the film muxer, imported by its URL: "./vendor/..." (import() takes a path only with ./, and resolves it against the page)
    mux = [p for p in VENDOR if p.endswith(".mjs")][0]
    assert page.count(f'"{VENDOR[mux][0]}"') == 1, VENDOR[mux][0]
    page = page.replace(f'"{VENDOR[mux][0]}"', f'"./{mux}"')
    fonts = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Silkscreen&family=Share+Tech+Mono&display=swap">'
    assert page.count(fonts) == 1
    page = page.replace(fonts, "<style>" + FONT_FACES + "</style>")
    page = re.sub(r'<link rel="preconnect" href="https://fonts\.(googleapis|gstatic)\.com"( crossorigin)?>\n', "", page)
    assert "fonts.googleapis.com/css" not in page and "cdn.jsdelivr.net" not in page
assert page.count('/*BUILD*/""') == 1
page = page.replace('/*BUILD*/""', '/*BUILD*/"%s"' % hashlib.sha256(page.encode()).hexdigest()[:12])
open(out, 'w').write(page)
print("ok", out, len(page))
