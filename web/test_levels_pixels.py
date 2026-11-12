"""levels-local.js reads a served picture's pixels as the server's Pillow does (export.Pictures opens the WebP with
Pillow): in Chromium, on lossy WebPs with and without a partly transparent alpha. A 2D canvas keeps premultiplied
pixels and rounds a partly transparent pixel's colour twice (the 0.065 EV a centred Titan close-up measured apart);
the page reads them through a WebGL texture. Needs node with playwright.

  python web/test_levels_pixels.py [--chrome]   (--chrome: the installed Google Chrome, through playwright-core)
"""
import json, os, subprocess, sys, tempfile  # noqa: E401
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS_JS = os.path.join(HERE, "cassini-os", "src", "levels-local.js")
tmp = tempfile.mkdtemp(prefix="levels-pixels-")
names = []
for n, (h, w) in enumerate([(300, 400), (512, 337), (97, 512)]):
    y, x = np.mgrid[0:h, 0:w]
    rgb = np.clip(np.dstack([128 + 100 * np.sin(x / (7 + n)), 128 + 90 * np.cos(y / 13), (x + y * n) % 256]), 0, 255).astype(np.uint8)
    edge = np.clip((x - w // 4) * (3 + n), 0, 255).astype(np.uint8)
    for alpha in (True, False):
        name = f"p{n}{'a' if alpha else 'o'}.webp"
        Image.fromarray(np.dstack([rgb, edge]) if alpha else rgb, "RGBA" if alpha else "RGB").save(os.path.join(tmp, name), quality=80)
        np.asarray(Image.open(os.path.join(tmp, name)).convert("RGBA")).tofile(os.path.join(tmp, name + ".rgba"))
        names.append(name)
JS = r"""
let pw; try { pw = require('playwright'); } catch (e) { pw = require('playwright-core'); }
const fs = require('fs'), http = require('http'), path = require('path');
const [js, dir, names, chrome] = [process.argv[1], process.argv[2], JSON.parse(process.argv[3]), process.argv[4] === '1'];
const srv = http.createServer((q, r) => { if (q.url === '/') { r.writeHead(200, { 'content-type': 'text/html' }); return r.end('<html></html>'); }
  const f = path.join(dir, path.basename(q.url.split('?')[0]));
  if (!names.includes(path.basename(f)) || !fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  r.writeHead(200, { 'content-type': 'image/webp' }); r.end(fs.readFileSync(f)); }).listen(0, async () => {
  const b = await pw.chromium.launch(chrome ? { channel: 'chrome' } : {}), p = await b.newPage();
  await p.goto(`http://127.0.0.1:${srv.address().port}/`);
  await p.evaluate(s => { window.cassiniPlanLocal = { _: {} }; (0, eval)(s); }, fs.readFileSync(js, 'utf8'));
  const out = {};
  for (const f of names) {
    const d = await p.evaluate(async f => { const bmp = await createImageBitmap(await (await fetch('/' + f)).blob(), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
      return Array.from(window.cassiniPlanLocal._levels.pixels(bmp)); }, f);
    if (!out.how) out.how = await p.evaluate(() => window.cassiniPlanLocal._levels.pixelsHow());
    const want = fs.readFileSync(path.join(dir, f + '.rgba')); let n = 0; for (let i = 0; i < want.length; i++) if (d[i] !== want[i]) n++;
    out[f] = n;
  }
  console.log(JSON.stringify(out)); await b.close(); srv.close();
});
"""
r = subprocess.run(["node", "-e", JS, LEVELS_JS, tmp, json.dumps(names), "1" if "--chrome" in sys.argv else "0"], capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stderr)
got = json.loads(r.stdout)
how = got.pop("how")
bad = {k: v for k, v in got.items() if v}
assert not bad, f"pixels differ from Pillow's: {bad}"
print(f"pixels ({how}): {len(names)} WebPs ({len(names) // 2} with a partly transparent edge) read in Chromium the same as Pillow, byte for byte")
print("ok")
