#!/usr/bin/env python3
"""A film made in the page (export.html) waits for a finished mosaic, as the server's film does
(export.Pictures.finished_mosaic): the frame server answers a mosaic still being made with the tiles so far (200,
X-Reel "behind" > 0), and export.html's fetchPicture asks again until "behind" is 0, then decodes that one; past
MOSAIC_WAIT it gives up (null: the next try stands in). A picture without X-Reel and a 404 are as before; a 503 that
never ends and a request that keeps failing give up at the same limit, as the server's film does on its TimeoutError.
The wait rule is one function, levels-local.js's fetchFinished (cassiniPlanLocal.fetchFinished), which the exposure
graph measures with too.

fetchPicture is taken from src/export.html and fetchFinished from src/levels-local.js as they are, and run in node with
a stand-in fetch, clock and decoder.

  python web/test_export_mosaic_wait.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "cassini-os", "src", "export.html"), encoding="utf8").read()
# (fetchBlob, which waits by fetchFinished, and fetchPicture, which decodes its file)
a = src.index("  async function fetchBlob")
code = src[a:src.index("\n  }\n", src.index("  async function fetchPicture", a)) + 4]
lev = open(os.path.join(HERE, "cassini-os", "src", "levels-local.js"), encoding="utf8").read()
a = lev.index("  const WAIT_MOST = ")
wait = lev[a:lev.index("\n  }\n", lev.index("async function fetchFinished")) + 4]
assert "WAIT_MOST = 900e3" in wait, "WAIT_MOST is not the server's 900 s (export.MOSAIC_WAIT)"

JS = r"""
let now = 0;
const realNow = Date.now; Date.now = () => now;
const setTimeout = (f, ms) => { now += ms; f(); };
let answers, asked;
const fetch = async (url, init) => { asked.push([url, init && init.cache || ""]); const a = answers.length > 1 ? answers.shift() : answers[0];
  if (a === 'fail') throw new TypeError('Failed to fetch'); return a; };
const createImageBitmap = async blob => ({ picture: blob });
const reply = (status, reel) => ({ status, ok: status >= 200 && status < 300, headers: { get: k => (k === 'X-Reel' && reel ? JSON.stringify(reel) : null) },
  blob: async () => (reel ? 'behind ' + reel.behind : 'plain') });
""" + wait + r"""
const window = { cassiniPlanLocal: { fetchFinished } };
""" + code + r"""
(async () => {
  const out = {};
  const run = async (name, list) => { answers = list; asked = []; now = 0; const got = await fetchPicture('/frames/mosaic/X.webp?size=512', { done: false });
    out[name] = { got: got && got.picture, asked: asked.length, nostore: asked.slice(1).every(a => a[1] === 'no-store'), waited: now }; };
  await run('finished at once', [reply(200, { behind: 0 })]);
  await run('behind twice, then finished', [reply(200, { behind: 5 }), reply(503), reply(200, { behind: 2 }), reply(200, { behind: 0 })]);
  await run('no X-Reel', [reply(200, null)]);
  await run('404', [reply(404, null)]);
  await run('never finished', [reply(200, { behind: 3 })]);
  await run('503 for ever', [reply(503)]);
  await run('fails, then comes', ['fail', 'fail', reply(200, null)]);
  await run('fails for ever', ['fail']);
  process.stdout.write(JSON.stringify(out));
})();
"""
r = subprocess.run(["node", "-e", JS], capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stderr)
got = json.loads(r.stdout)
assert got["finished at once"]["got"] == "behind 0" and got["finished at once"]["asked"] == 1, got["finished at once"]
w = got["behind twice, then finished"]
assert w["got"] == "behind 0" and w["asked"] == 4 and w["nostore"], w
assert got["no X-Reel"]["got"] == "plain" and got["no X-Reel"]["asked"] == 1, got["no X-Reel"]
assert got["404"]["got"] is None and got["404"]["asked"] == 1, got["404"]
n = got["never finished"]
assert n["got"] is None and 900e3 <= n["waited"] < 905e3, n
for k in ("503 for ever", "fails for ever"):
    assert got[k]["got"] is None and 900e3 <= got[k]["waited"] < 905e3, (k, got[k])
f = got["fails, then comes"]
assert f["got"] == "plain" and f["asked"] == 3 and f["nostore"], f
print(f"a finished mosaic at once: 1 ask; behind twice (and a 503) then finished: {w['asked']} asks, the finished one, "
      f"asked again past the browser's cache; no X-Reel and a 404 as before; never finished: given up after "
      f"{n['waited'] / 1000:.0f} s ({n['asked']} asks), the next try stands in; a 503 or a failing request for ever: "
      f"given up at the same limit; two failed requests then a picture: the picture")
print("ok")
