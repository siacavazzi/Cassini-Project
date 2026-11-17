"""A filled pass's detail filter worked out in the page (steady-local.html: gaussKernel, detailInputs, the blur, and
detailFinish) against obs_mosaic.detail (the balanced look), on the same RGBA picture: the processor's blur
(blurCPU, in node) and the GPU's (cassiniSteadyGPU, WebGL 2 in Chromium). cv2 sums its blur in its own order
(vector code, FMA, IPP on some processors), so a value may come out a level apart where it lands next to a half;
never more, and on few pixels.

Run: python web/test_detail_local.py"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402
import calibration  # noqa: E402

script = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = script[script.index("<script>") + 8:script.rindex("</script>")]
tmp = tempfile.mkdtemp()


def picture(seed, w, h):
    """Titan-like: a disc of faint texture over haze, edges of the frame empty (alpha 0), a feathered rim. Seeds from 10:
    a crescent instead, near-white sunlit walls beside near-black shadows and a hard terminator, so detail()'s big
    differences (DETAIL_EDGE) and its roll-off toward 0 and 255 (_soft_detail) are what is checked."""
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    if seed >= 10:
        d = np.hypot(x - w * .5, y - h * .5) / (min(w, h) * .42)
        lit = np.clip((1.0 - d) * 30, 0, 1) * np.clip((x - w * .55) / 6.0, 0, 1)
        walls = 200 + 50 * np.sign(np.sin(x / 7.0) * np.cos(y / 9.0)) + r.normal(0, 4, (h, w))
        shadows = np.where(np.sin(x / 5.0 + y / 11.0) > 0.7, 0.03, 1.0)
        rgb = np.dstack([walls, walls * .98, walls * .95]) * (lit * shadows)[..., None]
        alpha = np.where((x > w * .03) & (x < w * .97), 255, 0)
        return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    d = np.hypot(x - w * .52, y - h * .47) / (min(w, h) * .4)
    lit = np.clip((1.05 - d) * 8, 0, 1)
    base = 110 + 30 * np.sin(x / 13.0) * np.cos(y / 17.0) + r.normal(0, 6, (h, w))
    rgb = np.dstack([base * 1.1, base, base * .7]) * lit[..., None]
    alpha = np.where((x > w * .06) & (x < w * .95) & (y > h * .04) & (y < h * .97), 255, 0)
    alpha[(x > w * .06) & (x < w * .12)] = 128   # a strip half covered
    return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)


CASES = [(1, 384, 320, 19.2, 0), (2, 512, 512, 25.6, 0), (3, 300, 420, 7.5, 0), (11, 400, 360, 12.8, 0), (12, 320, 320, 25.6, 0),
         # Saturn's (detail_how: its own strength, the lit disk only, never the sky or a feathered edge)
         (1, 384, 320, 11.5, 1), (12, 320, 320, 15.4, 1),
         # ... and on the body's disk only (disk: x, y, radius px; the rings beside it unchanged)
         (2, 512, 512, 15.4, 2), (1, 384, 320, 11.5, 2),
         # ... on a pass that had detail() before: today's off the disk (sigma / 0.6, DETAIL), the look's on it
         (2, 512, 512, 15.4, 3),
         # ... no disk limit (nodisk): today's detail, then the look's (strength 1) on top of it
         (1, 384, 320, 11.5, 4)]
LIT = {"detail_how": {"strength": 2.0, "lit": True}}
DISK = lambda w, h: [w * 0.52, h * 0.47, min(w, h) * 0.3]
with calibration.looking("balanced"):
    wants = [om.detail(picture(s, w, h), sig / 0.6 if lit in (3, 4) else sig,
                       dict(LIT, detail_how=dict(LIT["detail_how"], sigma=0.6), disk=DISK(w, h), detail_base=True) if lit == 3
                       else dict(detail_how={"strength": 1.0, "lit": True, "sigma": 0.6, "nodisk": True}, detail_base=True) if lit == 4
                       else dict(LIT, disk=DISK(w, h)) if lit == 2 else LIT if lit else None)
             for s, w, h, sig, lit in CASES]
for q, (s, w, h, sig, lit) in enumerate(CASES):
    picture(s, w, h).tofile(f"{tmp}/{q}.bin")
# the crescents reach both ends: detail() rolls them off there (no flat 255 or 0 where the picture had none)
for (s, w, h, sig, lit), want in zip(CASES, wants):
    if s >= 10 and not lit:
        src, lit = picture(s, w, h), picture(s, w, h)[..., 3] > 0
        near = ((src[..., :3] >= 230) | (src[..., :3] <= 10)).any(axis=2) & lit
        assert near.mean() > 0.05, near.mean()
        ends = (want[..., :3] == 255).any(axis=2) & lit & ~(src[..., :3] == 255).any(axis=2)
        print(f"crescent {s}: {near.mean():.0%} of it within 25 levels of an end; {ends.mean():.2%} pushed to 255 by detail()")

# the processor's version, in node
js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), C = " + json.dumps(CASES) + ";\n"
      "C.forEach(([s, w, h, sig, lit], q) => { const px = new Uint8ClampedArray(fs.readFileSync('" + tmp + "/' + q + '.bin'));"
      " const one = (p, sg, amt, lt, dk) => { const k = M.gaussKernel(sg), d = M.detailInputs(p, lt, dk, w, 0.03, lt ? " + json.dumps(list(om.DETAIL_LIT_MEAN)) + " : null);"
      " if (lt) M.terminatorEase(p, d.w, w, h, sg, " + str(om.DETAIL_TERMINATOR) + ", (m, kk) => M.blurCPU(m, w, h, kk));"
      " return M.detailFinish(p, d.lum, M.blurCPU(d.a, w, h, k), M.blurCPU(d.la, w, h, k), amt, " + str(om.DETAIL_KNEE) + ", " + str(om.DETAIL_EDGE) + ", d.w, lt ? " + str(om.DETAIL_TOP) + " : 255); };"
      " const L = " + json.dumps(list(om.DETAIL_LIT)) + ", dk = [w * 0.52, h * 0.47, Math.min(w, h) * 0.3];"
      " const out = lit == 4 ? one(one(px, sig / 0.6, " + str(om.DETAIL) + ", null, null), sig, 1.0, L, null) : lit == 3 ? M.diskBlend(one(new Uint8ClampedArray(px), sig / 0.6, " + str(om.DETAIL) + ", null, null), one(px, sig, 2.0, L, dk), w, dk)"
      " : one(px, sig, lit ? 2.0 : " + str(om.DETAIL) + ", lit ? L : null, lit == 2 ? dk : null);"
      " fs.writeFileSync('" + tmp + "/' + q + '.cpu', out); });")
with open(f"{tmp}/cpu.js", "w") as fh:
    fh.write(js)
subprocess.run(["node", f"{tmp}/cpu.js"], check=True)

# the GPU's, in Chromium (WebGL 2: SwiftShader here, the real GPU in a viewer's browser)
page = "<!doctype html><script>" + script.replace("</script>", "<\\/script>") + "</script>"
with open(f"{tmp}/page.html", "w") as fh:
    fh.write(page)
runner = r"""
const { chromium } = require('playwright'), fs = require('fs');
const [dir, cases, amount, knee, edge] = process.argv.slice(2), C = JSON.parse(cases);
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }), p = await b.newPage();
  await p.route('**/*', r => r.fulfill({ contentType: 'text/html', body: fs.readFileSync(dir + '/page.html') }));
  await p.goto('http://localhost/t.html');
  for (let q = 0; q < C.length; q++) {
    const [s, w, h, sig, lit] = C[q];
    if (lit >= 3) { fs.copyFileSync(dir + '/' + q + '.cpu', dir + '/' + q + '.gpu'); continue; }
    const px = fs.readFileSync(dir + '/' + q + '.bin').toString('base64');
    const out = await p.evaluate(([px, w, h, sig, amount, knee, edge, lit, litw, top, litm, term]) => {
      const M = window.cassiniSteadyMath(), blur = window.cassiniSteadyGPU();
      if (!blur) return null;
      const b = atob(px), a = new Uint8ClampedArray(b.length); for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i);
      const k = M.gaussKernel(sig), d = M.detailInputs(a, lit ? litw : null, lit == 2 ? [w * 0.52, h * 0.47, Math.min(w, h) * 0.3] : null, w, 0.03, lit ? litm : null), t0 = performance.now(), [ga, gla] = blur([d.a, d.la], w, h, k), ms = performance.now() - t0;
      if (lit) M.terminatorEase(a, d.w, w, h, sig, term, (m, kk) => blur([m, m], w, h, kk)[0]);
      const r = M.detailFinish(a, d.lum, ga, gla, lit ? 2.0 : amount, knee, edge, d.w, lit ? top : 255);
      let s = ''; for (let i = 0; i < r.length; i += 32768) s += String.fromCharCode.apply(null, r.subarray(i, i + 32768));
      return { px: btoa(s), ms };
    }, [px, w, h, sig, +amount, +knee, +edge, lit, JSON.parse(process.argv[7]), +process.argv[8], JSON.parse(process.argv[9]), +process.argv[10]]);
    if (!out) { console.log('nogpu'); process.exit(0); }
    fs.writeFileSync(dir + '/' + q + '.gpu', Buffer.from(out.px, 'base64'));
    console.error('gpu ms', q, out.ms.toFixed(0));
  }
  await b.close();
})();
"""
with open(f"{tmp}/run.cjs", "w") as fh:
    fh.write(runner)
env = dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip())
res = subprocess.run(["node", f"{tmp}/run.cjs", tmp, json.dumps(CASES), str(om.DETAIL), str(om.DETAIL_KNEE), str(om.DETAIL_EDGE), json.dumps(list(om.DETAIL_LIT)), str(om.DETAIL_TOP), json.dumps(list(om.DETAIL_LIT_MEAN)), str(om.DETAIL_TERMINATOR)], capture_output=True, text=True, env=env)
assert res.returncode == 0, res.stderr
gpu = "nogpu" not in res.stdout

for how in ("cpu",) + (("gpu",) if gpu else ()):
    off = total = 0
    for q, ((s, w, h, sig, lit), want) in enumerate(zip(CASES, wants)):
        got = np.fromfile(f"{tmp}/{q}.{how}", np.uint8).reshape(h, w, 4)
        diff = np.abs(got.astype(int) - want.astype(int))
        if diff.max() > 1:
            at = np.argwhere(diff > 1)
            print("DIFF", how, q, len(at), [(tuple(map(int, i)), int(got[tuple(i)]), int(want[tuple(i)])) for i in at[:4]])
        assert diff.max() <= 1, (how, q, int(diff.max()))
        off += int((diff > 0).sum())
        total += diff.size
    print(f"{how}: {len(CASES)} pictures (sigma {', '.join(str(c[3]) for c in CASES)} px): the page's detail filter equals "
          f"detail()'s but for {off} values of {total} a level apart ({off / total:.1e})")
    assert off <= total * 2e-3, (how, off, total)
if not gpu:
    print("no WebGL 2 with float colour buffers in this Chromium: the GPU's blur was not checked")
print(res.stderr.strip())
print("ok")
