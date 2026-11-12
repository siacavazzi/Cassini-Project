#!/usr/bin/env python3
"""A film made in the page (export.html) waits for a finished mosaic, as the server's film does
(export.Pictures.finished_mosaic): the frame server answers a mosaic still being made with the tiles so far (200,
X-Reel "behind" > 0), and export.html's fetchPicture asks again until "behind" is 0, then decodes that one; past
MOSAIC_WAIT it gives up (null: the next try stands in). A picture without X-Reel, a 503 and a 404 are as before.

fetchPicture is taken from src/export.html as it is and run in node with a stand-in fetch, clock and decoder.

  python web/test_export_mosaic_wait.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "cassini-os", "src", "export.html"), encoding="utf8").read()
a = src.index("  // a mosaic still behind its frame (X-Reel")
b = src.index("\n  }\n", src.index("async function fetchPicture")) + 4
code = src[a:b]
assert "MOSAIC_WAIT = 900e3" in code, "MOSAIC_WAIT is not the server's 900 s (export.MOSAIC_WAIT)"

JS = r"""
let now = 0;
const realNow = Date.now; Date.now = () => now;
const sleep = ms => { now += ms; return Promise.resolve(); };
let answers, asked;
const fetch = async (url, init) => { asked.push([url, init && init.cache || ""]); return answers.length > 1 ? answers.shift() : answers[0]; };
const createImageBitmap = async blob => ({ picture: blob });
const reply = (status, reel) => ({ status, ok: status >= 200 && status < 300, headers: { get: k => (k === 'X-Reel' && reel ? JSON.stringify(reel) : null) },
  blob: async () => (reel ? 'behind ' + reel.behind : 'plain') });
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
print(f"a finished mosaic at once: 1 ask; behind twice (and a 503) then finished: {w['asked']} asks, the finished one, "
      f"asked again past the browser's cache; no X-Reel and a 404 as before; never finished: given up after "
      f"{n['waited'] / 1000:.0f} s ({n['asked']} asks), the next try stands in")
print("ok")
