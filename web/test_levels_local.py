"""The Movie Editor's exposure graph worked out in the page (web/cassini-os/src/levels-local.js,
window.cassiniPlanLocal.levels) is the frame server's (/export/levels.json: export.levels, measure, brightness,
stretches, exposures), run here in node against the Python:

1. Pillow as the server uses it: BILINEAR and LANCZOS resampling (RGB, and RGBA premultiplied), RGB to L, a picture
   pasted over black or the Background by its alpha (export.Pictures._on_black): byte for byte.
2. export.brightness on made-up pictures (lit disks, crescents, specks, noise, nearly black): the same log, but for
   numpy's float32 log, which is not correctly rounded and differs by platform (AVX2, AVX-512, NEON): the page's is,
   so a log can differ in its last float32 bit and, rounded to 5 places, by 1e-5 in a picture in a few hundred.
3. export.stretches and exposures (the level points' line, Even out over each stretch with obs_mosaic.evened_gains,
   whose page port is cassiniSteadyMath().evenedGains) on made-up plans and brightnesses: exactly.
4. The whole answer, export.levels against cassiniPlanLocal.levels, on the four stretches of web/test_plan_local.py
   (its data and pass rule), every frame's picture a made-up one (the same pixels on both sides, as the server's
   makers would give them): exactly, but for the log's last bit as in 2.

  python web/test_levels_local.py [--data <export dir>] [--synthetic]
"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [HERE]
import io, json, math, subprocess, zlib  # noqa: E401,E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import test_plan_local as T  # noqa: E402  (the data, the pass rule and the stretches)
import export  # noqa: E402
import obs_mosaic as om  # noqa: E402

PLAN_JS = T.PLAN_JS
LEVELS_JS = os.path.join(HERE, "cassini-os", "src", "levels-local.js")
STEADY_HTML = os.path.join(HERE, "cassini-os", "src", "steady-local.html")
tmp = T.tmp
rng = np.random.default_rng(17)

# node: plan-local.js, levels-local.js and cassiniSteadyMath in one context, then a command from a JSON file
NODE = r"""
const fs = require('fs'), vm = require('vm');
const [planJs, levelsJs, steadyHtml, jobFile] = process.argv.slice(1);
const ctx = vm.createContext({ console, globalThis: {} });
ctx.globalThis = ctx;
const page = fs.readFileSync(steadyHtml, 'utf8');
const steady = page.slice(page.indexOf('<script>') + 8, page.indexOf('</script>'));
const m = { exports: {} }; vm.runInContext(fs.readFileSync(planJs, 'utf8'), Object.assign(ctx, { module: m }));
ctx.cassiniPlanLocal = m.exports;
const l = { exports: {} }; ctx.module = l; vm.runInContext(fs.readFileSync(levelsJs, 'utf8'), ctx);
ctx.module = undefined; ctx.window = ctx; ctx.document = { addEventListener() {} };
try { vm.runInContext(steady, ctx); } catch (e) {}
const P = ctx.cassiniPlanLocal, L = l.exports._levels; P.levels = l.exports.levels;
const job = JSON.parse(fs.readFileSync(jobFile, 'utf8'));
const img = o => ({ data: Uint8ClampedArray.from(Buffer.from(o.b64, 'base64')), width: o.w, height: o.h, bands: o.bands || 4 });
const b64 = d => Buffer.from(d.buffer, d.byteOffset, d.byteLength).toString('base64');
(async () => {
  let out;
  if (job.cmd === 'pillow') out = job.cases.map(c => {
    const im = img(c.im);
    const r = c.op === 'rgba' ? L.resizeRGBA(im, c.w, c.h, c.filter) : c.op === 'black' ? L.onBlack(im, c.size, c.bg) : L.resize(im, c.w, c.h, c.filter);
    return { w: r.width, h: r.height, b64: b64(r.data) };
  });
  else if (job.cmd === 'brightness') out = job.cases.map(c => L.brightness(img(c)));
  else if (job.cmd === 'exposures') out = job.cases.map(c => L.exposures(c.opt, c.pics, c.logs, P._));
  else if (job.cmd === 'log2') out = job.gains.map(g => Math.log2(g));
  else if (job.cmd === 'levels') {
    P.source.allMonths = async () => job.parts.map(p => ({ start: p.start, end: p.end, key: p.file, catalog: () => JSON.parse(fs.readFileSync(p.file, 'utf8')) }));
    P.source.kind = async id => { if (!(id in job.kinds)) throw new Error('no kind table for ' + id); return job.kinds[id]; };
    const pics = {};
    for (const f of fs.readdirSync(job.pictures)) { const m = /^(.+)_(\d+)x(\d+)\.rgba$/.exec(f); pics[m[1]] = { file: job.pictures + '/' + f, w: +m[2], h: +m[3] }; }
    P.source.picture = async e => { const p = pics[e.id]; return p ? { data: Uint8ClampedArray.from(fs.readFileSync(p.file)), width: p.w, height: p.h } : null; };
    out = [];
    for (const r of job.runs) {
      const q = Object.assign({}, r.q, { cams: 'NW', list: '1' }); delete q.drop; delete q.targets; delete q.filters;
      const plan = r.pictures ? await P.plan(q) : null;
      out.push(await P.levels(r.q, plan && plan.pictures));
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


def node(job):
    path = os.path.join(tmp, "levels-job.json")
    json.dump(job, open(path, "w"))
    r = subprocess.run(["node", "-e", NODE, PLAN_JS, LEVELS_JS, STEADY_HTML, path], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr)
    return json.loads(r.stdout)


def packed(a):
    """An RGBA or RGB uint8 array as the page holds a picture (4 bytes a pixel)."""
    h, w = a.shape[:2]
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :a.shape[2]] = a
    if a.shape[2] == 3:
        rgba[..., 3] = 0
    import base64
    return {"b64": base64.b64encode(rgba.tobytes()).decode(), "w": w, "h": h, "bands": a.shape[2]}


def scene(w, h, seed, alpha=False, kind=None):
    """A made-up picture: a lit disk (or crescent, or speck) on a noisy dark sky, sometimes an RGBA picture whose
    edge is transparent (a centred body the frame caught at its edge), sometimes colored."""
    r = np.random.default_rng(seed)
    kind = kind or ["disk", "crescent", "speck", "dark", "field"][seed % 5]
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy, rad = w * r.uniform(0.3, 0.7), h * r.uniform(0.3, 0.7), min(w, h) * r.uniform(0.15, 0.45)
    d = np.hypot(x - cx, y - cy)
    g = np.zeros((h, w))
    if kind in ("disk", "crescent"):
        g = np.where(d < rad, r.uniform(80, 250) * (1 - 0.5 * (d / rad) ** 2), 0)
        if kind == "crescent":
            g = np.where(np.hypot(x - cx - rad * 0.5, y - cy) < rad, 0, g)
    elif kind == "speck":
        g = np.where(d < 2.5, 200, 0)
    elif kind == "field":
        g = 120 + 60 * np.sin(x / 7.3) * np.cos(y / 5.1)
    g = g + r.normal(0, r.uniform(0.5, 3), (h, w))
    tint = r.uniform(0.7, 1.0, 3) if seed % 3 == 0 else np.ones(3)
    rgb = np.clip(g[..., None] * tint, 0, 255).astype(np.uint8)
    if not alpha:
        return rgb
    a = np.full((h, w), 255, np.uint8)
    edge = int(w * r.uniform(0.1, 0.4))
    a[:, :edge] = 0
    a[:, edge:edge + 3] = [60, 128, 200]
    return np.dstack([rgb, a])


def pil(a):
    return Image.fromarray(a, "RGBA" if a.shape[2] == 4 else "RGB")


# 1. Pillow
cases, want = [], []
for n in range(36):
    w, h = int(rng.integers(40, 700)), int(rng.integers(40, 700))
    a = scene(w, h, n, alpha=n % 2 == 1)
    if n % 3 == 0 and a.shape[2] == 3:
        tw, th = max(1, int(rng.integers(8, 300))), max(1, int(rng.integers(8, 300)))
        cases.append({"op": "rgb", "im": packed(a), "w": tw, "h": th, "filter": "bilinear"})
        want.append(np.asarray(pil(a).resize((tw, th), Image.BILINEAR)))
    elif a.shape[2] == 4 and n % 4 == 1:
        tw, th = max(1, int(rng.integers(8, 900))), max(1, int(rng.integers(8, 900)))
        cases.append({"op": "rgba", "im": packed(a), "w": tw, "h": th, "filter": "lanczos"})
        want.append(np.asarray(pil(a).resize((tw, th), Image.LANCZOS)))
    else:
        bg = None if n % 5 else "335577"
        p = export.Pictures(None)
        if bg:
            p.movie = dict(p.movie, bg=bg)
        cases.append({"op": "black", "im": packed(a if a.shape[2] == 4 else np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])),
                      "size": 512, "bg": bg})
        want.append(np.asarray(p._on_black(pil(a), 512)))
got = node({"cmd": "pillow", "cases": cases})
import base64  # noqa: E402
for c, w, g in zip(cases, want, got):
    arr = np.frombuffer(base64.b64decode(g["b64"]), np.uint8).reshape(g["h"], g["w"], 4)
    bands = w.shape[2] if w.ndim == 3 else 1
    assert (g["h"], g["w"]) == w.shape[:2], (c["op"], (g["h"], g["w"]), w.shape)
    assert np.array_equal(arr[..., :bands], w.reshape(w.shape[0], w.shape[1], bands)), f"{c['op']} differs: {int((arr[..., :bands] != w.reshape(w.shape[0], w.shape[1], bands)).sum())} values"
print(f"Pillow: {len(cases)} pictures resized (BILINEAR, LANCZOS premultiplied) and put on black the same, byte for byte")

# 2. brightness
pics = []
for n in range(400):
    side = int(rng.choice([512, 384, 160, 100, 512]))
    w, h = (side, int(side * rng.uniform(0.4, 1))) if n % 2 else (int(side * rng.uniform(0.4, 1)), side)
    pics.append(scene(max(1, w), max(1, h), 1000 + n))
want = [export.brightness(pil(a)) for a in pics]
got = node({"cmd": "brightness", "cases": [packed(a) for a in pics]})
same = sum(1 for a, b in zip(want, got) if a == b or (a is not None and b is not None and math.isclose(a, b, rel_tol=0, abs_tol=0)))
nones = sum(1 for a in want if a is None)
assert all((a is None) == (b is None) for a, b in zip(want, got)), "too little lit: answers differ"
ulp = max((abs(a - b) / np.spacing(np.float32(abs(a))) for a, b in zip(want, got) if a is not None and a != b), default=0)
assert ulp <= 1, f"a log differs by {ulp} float32 steps"
r5 = sum(1 for a, b in zip(want, got) if a is not None and round(a, 5) != round(b, 5))
print(f"brightness: {len(pics)} pictures ({nones} too little lit), {same} logs the same to the bit, the rest one float32 step apart "
      f"(numpy's float32 log); rounded to 5 places as served, {len(pics) - r5} of {len(pics)} the same")

# 3. stretches and exposures
FIRSTS = ["movie", "mosaic", "color", "processed", "frame", "rolling"]
xcases, xwant = [], []
for n in range(60):
    k = int(rng.integers(1, 160))
    pl, first = [], FIRSTS[0]
    for i in range(k):
        if rng.random() < 0.08:
            first = FIRSTS[int(rng.integers(len(FIRSTS)))]
        e = {"id": f"N{1600000000 + i}_1", "cam": "NW"[int(rng.random() < 0.3)], "target": ["SATURN", "TITAN"][int(rng.random() < 0.1)], "first": first}
        if rng.random() < 0.2:
            e["set"] = "true"
        pl.append(e)
    logs = {e["id"]: (None if rng.random() < 0.05 else round(float(rng.normal(-1.5, 0.4) + (1 if rng.random() < 0.04 else 0)), 5)) for e in pl if rng.random() < 0.97}
    lv = {pl[int(i)]["id"]: round(float(rng.uniform(-2, 2)), 2) for i in rng.integers(0, k, int(rng.integers(0, 4)))}
    opt = {"levels": lv, "even": int(rng.choice([0, 1, 3, 8, 30]))}
    xcases.append({"opt": opt, "pics": pl, "logs": logs})
    xwant.append(list(export.exposures(opt, pl, logs)))
xgot = node({"cmd": "exposures", "cases": xcases})
for c, w, g in zip(xcases, xwant, xgot):
    assert w == g, f"exposures differ: even {c['opt']['even']}\n  server {w}\n  page   {g}"
gains = [g / 200 for g in range(50, 801)]
# (math.log2 is the C library's, which differs by platform and is not correctly rounded: a gain's log2 may differ in
# its last bit, never enough to move an answer rounded to 4 places)
l2 = node({"cmd": "log2", "gains": gains})
assert all(abs(a - math.log2(g)) <= np.spacing(abs(math.log2(g)) or 1.0) for a, g in zip(l2, gains)), "log2 differs"
l2_bits = sum(a != math.log2(g) for a, g in zip(l2, gains))
consts = {"flash": om.EXPOSURE_FLASH, "gain": om.EXPOSURE_GAIN, "roll": om.EXPOSURE_ROLL, "free": om.EXPOSURE_FREE}
js = subprocess.run(["node", "-e", "const fs=require('fs'),vm=require('vm');const m={exports:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{module:m,globalThis:{},console},{});process.stdout.write(JSON.stringify(m.exports._levels.EXPOSURE))", LEVELS_JS],
                    capture_output=True, text=True, check=True).stdout
assert json.loads(js) == consts, f"exposure constants differ: {js} vs {consts}"
assert (export.LEVELS_SIDE, export.LEVELS_LIT) == (160, 0.04), "LEVELS_SIDE / LEVELS_LIT changed: update levels-local.js"
print(f"exposures: {len(xcases)} made-up plans the same (line, Even out at 0 to 30, total); log2 of every gain the same "
      f"but {l2_bits} in its last bit; the constants the same")

# 4. the whole answer on the four stretches, every picture made up
frames_pics, ids = {}, set()
runs = []
for name, (a, b) in T.STRETCHES.items():
    base = {"from": T.iso(a), "until": T.iso(b), "cams": "NW", "fps": "auto", "size": "1024"}
    p = export.plan(export.options({k: [v] for k, v in {**base, "cams": "NW", "list": "1"}.items()}))
    ids |= {e["id"] for e in p["pictures"]}
    some = [e["id"] for e in p["pictures"]]
    lv = {some[len(some) // 3]: 0.75, some[2 * len(some) // 3]: -1.25} if len(some) > 3 else {}
    for q in ({}, {"even": "8"}, {"even": "30", "levels": ",".join(f"{k}:{v}" for k, v in lv.items())}, {"even": "3", "cams": "W", "pictures": "color"},
              {"even": "12", "drop": ",".join(some[:5]), "mos": "off"}):
        runs.append({"name": name, "q": {**base, **q}, "pictures": len(runs) % 2 == 0})


def made(fid):
    """The made-up picture of a frame (RGBA, a transparent edge sometimes), the same for every try: a few hundred px,
    so the server's _on_black and the page's both enlarge it to 512 (LANCZOS) before measuring."""
    h = zlib.crc32(fid.encode())
    w, hh = 120 + h % 140, 120 + (h // 140) % 140
    a = scene(w, hh, h % 100000, alpha=h % 4 == 0)
    return a if a.shape[2] == 4 else np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])


made_pics = {fid: made(fid) for fid in sorted(ids)}
pdir = os.path.join(tmp, "pictures")
os.makedirs(pdir, exist_ok=True)
for fid, a in made_pics.items():
    a.tofile(os.path.join(pdir, f"{fid}_{a.shape[1]}x{a.shape[0]}.rgba"))
pfile = pdir


class Made(export.Pictures):
    def picture(self, e, size, full=False, cap=None):
        return self._on_black(Image.fromarray(made_pics[e["id"]], "RGBA"), size), "made"


export.Pictures = Made
want = []
for r in runs:
    opt = export.options({k: [v] for k, v in r["q"].items()})
    while True:
        out = export.levels(opt, tmp, Made(tmp))
        if out["total"] is not None and out["done"] >= out["total"] and (not opt["even"] or "even" in out):
            break
        export.measure(opt, tmp, Made(tmp), wait=True)
    want.append(T.norm(out))
got = [T.norm(g) for g in node({"cmd": "levels", "runs": runs, "parts": T.parts, "kinds": T.kinds, "pictures": pfile})]
bad = 0
lvl_diff = even_diff = 0
for r, w, g in zip(runs, want, got):
    assert g.get("error") is None, f"{r['name']} {r['q']}: page error {g['error']}"
    assert set(w["level"]) == set(g["level"]) and (w["done"], w["total"]) == (g["done"], g["total"]), f"{r['name']}: other frames measured"
    d = [k for k in w["level"] if w["level"][k] != g["level"][k]]
    assert all(abs(w["level"][k] - g["level"][k]) <= 1.5e-4 for k in d), f"{r['name']}: levels differ by more than the log's last bit"
    lvl_diff += len(d)
    we, ge = w.get("even", {}), g.get("even", {})
    e = [k for k in set(we) | set(ge) if we.get(k) != ge.get(k)]
    even_diff += len(e)
    if d or e:
        bad += 1
n_lv = sum(len(w["level"]) for w in want)
n_ev = sum(len(w.get("even", {})) for w in want)
print(f"levels: {len(runs)} answers on {len(T.STRETCHES)} stretches, {n_lv:,} levels and {n_ev:,} Even out changes; "
      f"{len(runs) - bad} the same throughout, {lvl_diff} levels and {even_diff} Even out changes apart by the log's last bit")
assert even_diff <= max(2, n_ev // 200), "Even out differs beyond the log's last bit"
print("ok")
