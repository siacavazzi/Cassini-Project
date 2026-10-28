#!/usr/bin/env python3
"""
A film made on this computer (export.html makeHere) against the frame server's (export.py render), on the same plan
and the same pictures: every picture is in the same pane at the same place for the same frames, the holds and the
film's length are the same, a mosaic holds behind its observation the same way, a missing picture falls back to the
next try, and the soundtrack is in the file. Both films are lossy (H.264), so the panes are compared as decoded
(PSNR); the captions are drawn by two font renderers, so they are only checked to be there.

The page's own script (src/export.html) runs in Chromium (Playwright) with a stand-in frame server and stand-ins
for the rest of Cassini OS; export.py's render runs with a stand-in Pictures that hands it the same pictures.

  python web/test_export_here.py
"""
import base64
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import export  # noqa: E402

SIZE = 512
T0 = 1104537600   # 2005-01-01T00:00:00
rng = np.random.default_rng(7)


def picture(seed, w, h):
    """A picture with structure the encoder has to keep: gradients, a disc, noise, alpha around a body."""
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    a = (x * (200 / w) + y * (40 / h) + r.integers(0, 30)).astype(np.float32)
    disc = (x - w * r.uniform(.3, .7)) ** 2 + (y - h * r.uniform(.3, .7)) ** 2 < (min(w, h) * r.uniform(.15, .35)) ** 2
    rgb = np.dstack([a + disc * 60, a * .8 + disc * 90, a * .6 + disc * 30]) + r.normal(0, 3, (h, w, 1))
    alpha = np.where((x > 4) & (y > 4) & (x < w - 4) & (y < h - 4), 255, 0)
    return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)


# a stretch of both cameras: movie frames, a mosaic pass with frames between its tiles, colour sets, frames alone,
# a picture the server does not have (its next try stands in) and one it is still making (503 first)
pics, files, missing, busy = [], {}, set(), set()
t = T0
for n in range(30):
    cam = "NW"[n % 3 == 2]
    t += [20, 45, 300, 5, 90][n % 5] + (5 * 3600 if n == 17 else 0)
    fid = f"{'N' if cam == 'N' else 'W'}{1104537600 + n}_1"
    kind = ["movie", "mosaic", "mosaic", "color", "processed", "frame"][n % 6] if n < 24 else "processed"
    obs = "ISS_TEST_MOS" if kind == "mosaic" or n in (9, 16) else f"ISS_TEST_{n}"
    tries = []
    if kind == "movie":
        tries.append(("movie", fid))
    elif kind == "mosaic":
        tries.append(("mosaic", fid))
    elif kind == "color":
        tries.append(("color", [fid, fid.replace("_1", "_2"), fid.replace("_1", "_3")]))
    tries += [("processed", fid), ("frame", fid)]
    e = {"id": fid, "cam": cam, "t": float(t), "target": ["SATURN", "TITAN", "ENCELADUS", ""][n % 4], "filters": "CL1/CL2",
         "obs": obs, "nm": 650, "try": tries}
    if kind == "color":
        e["set"] = ["true", "false", "two"][n % 3]
    srcs = [export.source(k, a) for k, a in tries]
    if n == 10:
        missing.add(srcs[0])     # its best picture is not there: processed stands in
    if n == 7:
        busy.add(srcs[0])        # the server is still making it
    for q, (k, src) in enumerate(zip([k for k, _ in tries], srcs)):
        w, h = (SIZE, SIZE) if k != "color" else (SIZE, 380)
        if n % 4 == 1:
            w, h = 300, 420          # smaller and taller than the pane: centred, enlarged as _on_black does
        files[src] = picture(n * 10 + q, w, h)
    pics.append(e)
export.timing(pics, "auto")
opt = {"cams": "NW", "size": SIZE, "caption": True, "fps": "auto", "movie": {}, "sound": True}
plan = {"pictures": pics, "count": len(pics), "seconds": round(sum(e["frames"] for e in pics) / export.FPS, 2),
        "frames": sum(e["frames"] for e in pics), "width": export.width(opt), "height": export.height(opt)}
public = export.public_plan(plan)
tmp = tempfile.mkdtemp()


class Stand(export.Pictures):
    """export.py's Pictures with the frame server's makers replaced by the same pictures the page gets."""

    def __init__(self):
        super().__init__(None)

    def make(self, kind, arg, size):
        src = export.source(kind, arg)
        if src in missing or src not in files:
            return None
        out = io.BytesIO()
        Image.fromarray(files[src], "RGBA").save(out, "PNG")
        return out.getvalue(), {"movie": "movie", "mosaic": "mosaic", "color": "colour", "processed": "processed", "frame": "frame"}[kind]


server = os.path.join(tmp, "server.mp4")
made = export.render(opt, plan, Stand(), server, workers=2)

# the page: export.html's window and script, with stand-ins for the chrome it lives in
src = open(os.path.join(HERE, "cassini-os", "src", "export.html")).read()
style = src[src.index("<style>"):src.index("</style>") + 8]
window = src[src.index('<section class="win" id="excard"'):src.index("</section>") + 10]
script = src[src.index("<script>"):src.rindex("</script>") + 9]
stubs = """<script>
const store = { "export.sound": true };   // sound is off by default (#174); the test checks the soundtrack too
window.cassiniSettings = { define(d) { if (!(d.key in store)) store[d.key] = d.value; }, get: k => store[k], set(k, v) { store[k] = v; }, on() {} };
window.cassiniLook = () => ""; window.cassiniMovieStyle = () => "&trail=0&laps=1";
const etToMs = et => et * 1000, utcToEt = s => Date.parse(s + "Z") / 1000, etToX = () => 0, xToEt = () => 0, drawTimeline = () => {};
const fmtDur = s => `${Math.round(s)} s`;
let catalog = { id: %s };
const state = { et: 0, focus: "CASSINI", follow: true };
// the live sound's synth stand-in: a tone per picture, rendered offline as sound.html's render does
window.cassiniSound = { async render(events, seconds, rate) {
  const ctx = new OfflineAudioContext(2, Math.ceil(seconds * rate), rate);
  for (const ev of events) { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = 300 + (ev.k %% 7) * 60; g.gain.value = 0.2; o.connect(g).connect(ctx.destination); o.start(ev.t); o.stop(ev.t + 0.08); }
  return ctx.startRendering();
} };
</script>""" % json.dumps([e["id"] for e in pics])
page = f"<!doctype html><meta charset=utf-8>{style}<body><canvas id=tl></canvas><ul id=gomenu></ul>{window}{stubs}{script}"
with open(os.path.join(tmp, "page.html"), "w") as fh:
    fh.write(page)
pngs = {}
for k, a in files.items():
    out = io.BytesIO()
    Image.fromarray(a, "RGBA").save(out, "PNG")
    pngs[k] = base64.b64encode(out.getvalue()).decode()
with open(os.path.join(tmp, "frames.json"), "w") as fh:
    json.dump({"plan": public, "pngs": pngs, "missing": sorted(missing), "busy": sorted(busy)}, fh)
muxer = os.path.join(tmp, "node_modules", "mp4-muxer", "build", "mp4-muxer.mjs")   # the page loads it from jsdelivr
runner = r"""
const { chromium } = require('playwright'), fs = require('fs');
const [page_, data_, out_, muxer_] = process.argv.slice(2), D = JSON.parse(fs.readFileSync(data_)), asked = {};
(async () => {
  const b = await chromium.launch(), p = await b.newPage();
  p.on('console', m => { if (m.type() === 'warning' || m.type() === 'error') console.error('page:', m.text()); });
  await p.route('**/*', async r => {
    const u = new URL(r.request().url());
    if (u.hostname === 'cdn.jsdelivr.net') return r.fulfill({ contentType: 'text/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: fs.readFileSync(muxer_) });
    if (u.pathname === '/page.html') return r.fulfill({ contentType: 'text/html', body: fs.readFileSync(page_) });
    if (u.pathname === '/export/plan.json') return r.fulfill({ contentType: 'application/json', body: JSON.stringify(D.plan) });
    // the picture's address as the plan gives it, without the size and style the page adds
    const q = new URLSearchParams(u.search), ids = q.get('ids'), key = u.pathname + (ids ? `?ids=${ids}` : '');
    asked[key] = (asked[key] || 0) + 1;
    if (D.busy.includes(key) && asked[key] < 3) return r.fulfill({ status: 503, body: 'making' });
    if (D.missing.includes(key) || !D.pngs[key]) return r.fulfill({ status: 404, body: 'none' });
    return r.fulfill({ contentType: 'image/png', body: Buffer.from(D.pngs[key], 'base64') });
  });
  await p.goto('http://localhost/page.html?frames=http://localhost');
  const r = await p.evaluate(async ([a, b]) => {
    const E = window.cassiniExport;
    E.open(); E.mark(a, b);
    for (let i = 0; i < 100 && document.getElementById('exgo').disabled; i++) await new Promise(r => setTimeout(r, 100));
    document.getElementById('exgo').click();
    for (let i = 0; i < 1200 && !E.state.made && !/Failed/.test(document.getElementById('exstate').textContent); i++) await new Promise(r => setTimeout(r, 100));
    if (!E.state.made) return { error: document.getElementById('exstate').textContent };
    const blob = await (await fetch(document.getElementById('exvid').src)).blob(), buf = new Uint8Array(await blob.arrayBuffer());
    let s = ''; for (let i = 0; i < buf.length; i += 32768) s += String.fromCharCode.apply(null, buf.subarray(i, i + 32768));
    return { made: E.state.made, state: document.getElementById('exstate').textContent, mp4: btoa(s) };
  }, [D.plan.pictures[0].t - 1, D.plan.pictures[D.plan.pictures.length - 1].t + 1]);
  if (r.error) { console.error(r.error); process.exit(1); }
  fs.writeFileSync(out_, Buffer.from(r.mp4, 'base64'));
  console.log(JSON.stringify({ made: r.made, state: r.state, asked }));
  await b.close();
})();
"""
with open(os.path.join(tmp, "run.cjs"), "w") as fh:
    fh.write(runner)
if not os.path.exists(muxer):
    subprocess.run(["npm", "install", "--no-save", "--prefix", tmp, "mp4-muxer@5.1.5"], check=True, capture_output=True)
here = os.path.join(tmp, "here.mp4")
env = dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip())
res = subprocess.run(["node", os.path.join(tmp, "run.cjs"), os.path.join(tmp, "page.html"), os.path.join(tmp, "frames.json"), here, muxer],
                     capture_output=True, text=True, env=env)
if res.returncode:
    print(res.stdout, res.stderr)
    raise SystemExit("the page did not make the film")
got = json.loads(res.stdout.strip().splitlines()[-1])


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def frames_at(path, ns, w, h):
    """The film's frames ns (at its 30 a second: a held picture is the same frame again), as decoded."""
    pick = "+".join(f"eq(n\\,{n})" for n in ns)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={export.FPS},select='{pick}'", "-vsync", "0",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def psnr(a, b):
    m = np.mean((a.astype(float) - b.astype(float)) ** 2)
    return 99.0 if m == 0 else 10 * np.log10(255 ** 2 / m)


ps, pt = probe(server), probe(here)
W, H, ch = plan["width"], plan["height"], export.caption_h(opt)
vs = [s for s in pt["streams"] if s["codec_type"] == "video"][0]
assert (vs["width"], vs["height"]) == (W, H), vs
assert any(s["codec_type"] == "audio" for s in pt["streams"]), "no soundtrack in the page's film"
d_server, d_here = float(ps["format"]["duration"]), float(pt["format"]["duration"])
assert abs(d_server - d_here) < 0.1, (d_server, d_here)
kinds_server = {k: v for k, v in made.items()}
kinds_here = got["made"]["kinds"]
assert kinds_server == kinds_here, (kinds_server, kinds_here)
assert got["asked"].get(sorted(busy)[0], 0) >= 3, "the page did not wait for a picture the server was making"
mid = [int(round(e["at"] * export.FPS)) + e["frames"] // 2 for e in pics]
A, B = frames_at(server, mid, W, H), frames_at(here, mid, W, H)
assert len(A) == len(B) == len(pics), (len(A), len(B))
panes = [psnr(a[:SIZE], b[:SIZE]) for a, b in zip(A, B)]
caps = [psnr(a[SIZE:], b[SIZE:]) for a, b in zip(A, B)]
print(f"film: {len(pics)} pictures, {d_here:.2f} s here and {d_server:.2f} s on the server, {W}x{H}, "
      f"{got['made']['codec']} + {got['made']['audio']}, {got['made']['bytes'] / 1e6:.2f} MB here, made as {kinds_here}")
print(f"panes at each picture's middle: {min(panes):.1f} dB worst, {np.median(panes):.1f} dB median (both H.264); "
      f"captions {min(caps):.1f} dB worst (two font renderers)")
assert min(panes) > 34, panes
assert kinds_here.get("held behind mosaic"), kinds_here
if os.environ.get("EVIDENCE"):
    # one picture's moment from each film, the server's above the page's
    k = max(range(len(pics)), key=lambda i: bool(pics[i].get("skipped")))
    Image.fromarray(np.vstack([A[k], np.full((8, W, 3), 255, np.uint8), B[k]])).save(os.environ["EVIDENCE"])
print("ok")
