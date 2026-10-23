#!/usr/bin/env python3
"""
Builds the Cassini OS pages from the replay viewer (web/replay/index.html): each page is one of the
heads in this folder (styles, window manager, menus, camera feed) followed by the viewer's script,
patched so colours and fonts come from CSS, the HUD draws into its own canvas, and Cassini is
NASA's 3D model (data/models/cassini.glb.b64.txt).

  python web/cassini-os/src/build.py            # writes web/cassini-os/index.html
  python web/cassini-os/src/build.py SRC HEAD OUT

The page reads web/replay/data (the data/ link), so build that first with web/replay/build_data.py.
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) == 1:
    root = os.path.dirname(HERE)
    for head, out in [("head-quiet.html", "index.html")]:
        subprocess.run([sys.executable, __file__, os.path.join(root, "..", "replay", "index.html"),
                        os.path.join(HERE, head), os.path.join(root, out)], check=True)
    sys.exit(0)
import sys, re, json
src = open(sys.argv[1]).read()           # prototype source
study = open(sys.argv[2]).read()          # study: everything up to (not incl.) the three.js script tags
out = sys.argv[3]
script = src[src.index('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js">'):]

# movie mode (movie.html): its style joins the head's, its window goes into #app next to the others, a Movie
# button joins the transport, and its script runs after the chrome script
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
    ('  <div id="loading">', "  " + part("section") + "\n\n" + '  <div id="loading">'),
    ('<button class="btn round skip" id="next" aria-label="Next moment">▶▶</button>',
     '<button class="btn round skip" id="next" aria-label="Next moment">▶▶</button>\n'
     '          <button class="btn round skip" id="movie" aria-pressed="false" aria-label="Movie mode" title="Movie mode: play one body\'s frames as a film (M)">'
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
# Cassini OS opens at the Settings window's start time (playback.start; by default "In Saturn's Shadow",
# 2006-09-15, the WAC mosaic of Saturn backlit by the Sun, the benchmark in web/frames/mosaic_benchmark.py);
# a ?t= link wins
rep('get("t") || "2005-01-14T09:30:00"',
    'get("t") || (window.cassiniSettings && cassiniSettings.get("playback.start")) || "2006-09-15T14:28:00"')

# surface map size: a ?tex= link wins, then the Settings window's choice
rep('const TEX_TIER = (new URLSearchParams(location.search).get("tex") || (location.hash.match(/^#tex-(\\w+)$/) || [])[1] || "2k").toLowerCase();',
    'const TEX_TIER = (new URLSearchParams(location.search).get("tex") || (location.hash.match(/^#tex-(\\w+)$/) || [])[1] || (window.cassiniSettings && cassiniSettings.get("view.textures")) || "2k").toLowerCase();')
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
  if (cd < 0.01) {""", """  const draw = !window.cassiniPerf || cassiniPerf.draw(now);
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
rep("""        float m = fbm(nb * 5.0) - 0.5;
        float craters = smoothstep(0.62, 0.7, vnoise(nb * 22.0)) * 0.12;
        vec3 alb = color * (1.0 + 0.32 * m - craters);""", """        float m = 0.0, craters = 0.0;
        if (hasMap < 0.5) { m = fbm(nb * 5.0) - 0.5; craters = smoothstep(0.62, 0.7, vnoise(nb * 22.0)) * 0.12; }
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

# HUD hook: studies can add their own read-outs
rep('''  $("mday").textContent = `Mission day ${fmtInt(Math.floor((ms - LAUNCH_MS) / 86400000))} · ${SPEEDS.find(s => s[0] === state.speed)[1]}${state.playing ? "" : " · paused"}`;''',
    '''  $("mday").textContent = `Mission day ${fmtInt(Math.floor((ms - LAUNCH_MS) / 86400000))} · ${SPEEDS.find(s => s[0] === state.speed)[1]}${state.playing ? "" : " · paused"}`;
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
script = script.replace(tl, '''function barRect(g, x, y, w, h) {
  if (THEME.barStyle !== "dots") { g.fillRect(x, y, w, h); return; }
  for (let yy = Math.round(y + h); yy > y; yy -= 3) g.fillRect(x, yy - 2, w, 2);
}
''' + t2)
# real Cassini: NASA's Cassini-Huygens model (NASA 3D Resources), Draco-decoded, shipped as base64 text
rep('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>\n',
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>\n')
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
rep('  state.pointed = !!qb;\n', '  state.pointed = !!qb;\n  window.cassiniPointing = qb ? "CK" : "EARTH";\n')
rep('  const card = $("imgcard");\n', '  const card = $("camsink");\n')   # the page has a window per camera (see the head)
# finale hooks (finale.html): its own clock before the bodies are placed, Cassini carried on past the end of the data,
# its attitude, and the camera after the orbit controls
rep('  updateBodies();\n  if (ready && state.focus', '  if (window.studyFrame) window.studyFrame(dt);\n  updateBodies();\n  if (ready && state.focus')
rep('  for (const name in tracks) positionAt(tracks[name], state.et, pos[name]);\n',
    '  for (const name in tracks) positionAt(tracks[name], state.et, pos[name]);\n  if (window.studyPositions) window.studyPositions();\n')
rep('  } else { relScene("EARTH", vA); cassini.lookAt(vA); }\n', '  } else { relScene("EARTH", vA); cassini.lookAt(vA); }\n  if (window.studyAttitude) window.studyAttitude();\n')
rep('  aimFollow();\n', '  aimFollow();\n  if (window.studyCamera) window.studyCamera();\n')
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
# the Grand Finale (finale.html): its style joins the head's, its overlay goes into #app, and its script runs last (it
# wraps the clock's studyAdvance hook and fills the finale hooks patched into the viewer below)
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
script += fscript + "\n"
open(out, 'w').write(study + script)
print("ok", out, len(study + script))
