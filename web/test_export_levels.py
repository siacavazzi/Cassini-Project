#!/usr/bin/env python3
"""The film made on this computer (export.html makeHere) takes the Movie Editor's exposure levels, Even out and
frames edited on their own as the frame server's film does (export.py options, exposures, render's own): each
picture's EV from the page against export.exposures on the same plan, with the frame server's Even out changes
(/export/levels.json "even") handed to both, and the frame looks it picks. Before 2026-10-31 the film made here took
none of them. The page's script runs in Chromium (Playwright) with a stand-in frame server.

  python web/test_export_levels.py
"""
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import export  # noqa: E402

T0 = 1104537600
pics = [{"id": f"N{T0 + n}_1", "cam": "N", "t": float(T0 + 60 * n), "target": "SATURN", "filters": "CL1/CL2", "obs": "X",
         "nm": 650, "try": [("processed", f"N{T0 + n}_1")]} for n in range(20)]
export.timing(pics, "auto")
cut = {"levels": f"{pics[3]['id']}:0.5,{pics[9]['id']}:-1.25,{pics[15]['id']}:3", "even": "8",
       "fedit": f"{pics[5]['id']}~ct:20|{pics[6]['id']}~ex:0.3,sa:-10", "edit": "wa:15"}
key = urlencode(dict({"from": "2005-01-01T00:00:00", "until": "2005-01-01T01:00:00", "cams": "N"}, **cut))
even = {pics[n]["id"]: round(0.1 * (n % 5) - 0.2, 4) for n in range(20) if n % 5 != 2}
opt = export.options(parse_qs(key))
# the server's line, plus the Even out changes as levels.json hands them to the page
_, line, _ = export.exposures(opt, pics)
want = [round(max(-2 * export.LEVEL_EV, min(2 * export.LEVEL_EV, a + even.get(e["id"], 0))), 4) for a, e in zip(line, pics)]

src = open(os.path.join(HERE, "cassini-os", "src", "export.html")).read()
window = src[src.index('<section class="win" id="excard"'):src.index("</section>") + 10]
script = src[src.index("<script>"):src.rindex("</script>") + 9]
stubs = """<script>
const store = {};
window.cassiniSettings = { define(d) { if (!(d.key in store)) store[d.key] = d.value; }, get: k => store[k], set(k, v) { store[k] = v; }, on() {} };
window.cassiniLook = () => ""; window.cassiniMovieStyle = () => "";
const etToMs = et => et * 1000, utcToEt = s => Date.parse(s + "Z") / 1000, etToX = () => 0, xToEt = () => 0, drawTimeline = () => {};
const fmtDur = s => `${Math.round(s)} s`;
let catalog = { id: [] };
const state = { et: 0, focus: "CASSINI", follow: true };
</script>"""
tmp = tempfile.mkdtemp()
open(os.path.join(tmp, "page.html"), "w").write(f"<!doctype html><meta charset=utf-8><body><canvas id=tl></canvas><ul id=gomenu></ul>{window}{stubs}{script}")
open(os.path.join(tmp, "data.json"), "w").write(json.dumps({"plan": {"pictures": pics}, "key": key, "even": even}))
runner = r"""
const { chromium } = require('playwright'), fs = require('fs');
const [page_, data_] = process.argv.slice(2), D = JSON.parse(fs.readFileSync(data_));
(async () => {
  const b = await chromium.launch(), p = await b.newPage();
  let asked = 0;
  await p.route('**/*', r => {
    const u = new URL(r.request().url());
    if (u.pathname === '/page.html') return r.fulfill({ contentType: 'text/html', body: fs.readFileSync(page_) });
    // still measuring on the first ask, done on the next
    if (u.pathname === '/export/levels.json') { asked++; return r.fulfill({ contentType: 'application/json', body: JSON.stringify(asked < 2 ? { done: 3, total: 20, even_ready: true } : { done: 20, total: 20, even_ready: true, even: D.even }) }); }
    return r.fulfill({ status: 404, body: '' });
  });
  await p.goto('http://localhost/page.html?frames=http://localhost');
  const r = await p.evaluate(async ([plan, key]) => { const x = await window.cassiniExport.exposures(plan, key); return { ev: x.ev, own: [...x.own] }; }, [D.plan, D.key]);
  console.log(JSON.stringify(Object.assign(r, { asked })));
  await b.close();
})();
"""
open(os.path.join(tmp, "run.cjs"), "w").write(runner)
env = dict(os.environ, NODE_PATH=os.environ.get("NODE_PATH", "/opt/node22/lib/node_modules"))
out = json.loads(subprocess.run(["node", os.path.join(tmp, "run.cjs"), os.path.join(tmp, "page.html"), os.path.join(tmp, "data.json")],
                                capture_output=True, text=True, env=env, check=True).stdout.strip().splitlines()[-1])
got = [round(v, 4) for v in out["ev"]]
assert max(abs(a - b) for a, b in zip(got, want)) < 1e-3, (got, want)
assert any(line) and any(even.values()) and out["asked"] >= 2
assert sorted(dict(out["own"])) == sorted(opt["fedit"])
print("ok")
