// The exposure graph worked out in the page (levels-local.js) against the frame server's /export/levels.json, on
// real pictures, for a film with Auto center off (ctr=0) and on (ctr=1). The server measures the pictures the film
// draws (export.Pictures: centred color and processed pictures when the film's Auto center is on); the page must ask
// the frame server for the same pictures. Prints "match" or "differ" for each.
//
//   node web/check_levels_centre.mjs http://127.0.0.1:8765 [--from 2005-04-16T15:00:00 --until 2005-04-16T23:00:00]
//     [--pictures color] [--chrome] [--python ~/venv/bin/python]
//
// For a picture that differs, the picture the page used is measured again by the server's own Python
// (export.brightness on export.Pictures._on_black of the served WebP; --python PATH or PYTHON, default python3: the
// frame server's interpreter, with numpy and Pillow): "the page measured the served picture right" means the server's /export/levels.json measured some
// other picture (a server-side defect, cold-levels-finding.md), not the page port.
//
// Exit 0: both films the same; 2: the only differences are SERVER-SIDE ones; 1: the page port differs.
//
// Needs playwright (or playwright-core with --chrome, which uses the installed Google Chrome) and a frame server
// running this commit's web/frames. The page code is taken from this checkout and put into the server's page.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const server = (argv.find(a => /^https?:/.test(a)) || "http://127.0.0.1:8765").replace(/\/$/, "");
const from = arg("--from", "2005-04-16T15:00:00"), until = arg("--until", "2005-04-16T23:00:00");
const pictures = arg("--pictures", "color");
let pw;
try { pw = require("playwright"); } catch (e) { pw = require("playwright-core"); }
const browser = await pw.chromium.launch(argv.includes("--chrome") ? { channel: "chrome" } : {});
const page = await browser.newPage();
const errors = [];
page.on("pageerror", e => errors.push(String(e)));
// every picture the page asks for, with the answer's status (for a picture that differs)
let fetched = [];
page.on("response", r => { if (/\/frames\//.test(r.url())) fetched.push(`${r.status()} ${r.url().replace(server, "")}`); });
page.on("requestfailed", r => { if (/\/frames\//.test(r.url())) fetched.push(`failed ${r.url().replace(server, "")}`); });
await page.goto(`${server}/?t=${from}&view=titan&play=0`, { waitUntil: "load" });
await page.waitForFunction(() => window.cassiniSteadyMath && window.cassiniLook, null, { timeout: 120000 });
const src = f => fs.readFileSync(path.join(HERE, "cassini-os", "src", f), "utf8");
// this checkout's page code, over whatever the server's page has
await page.addScriptTag({ content: src("plan-local.js") });
await page.addScriptTag({ content: src("levels-local.js") });

const ev = 1.5e-4;   // one step of the float32 log, after rounding to 4 places
let bad = 0, serverSide = 0;   // films with a page differ; films whose every differ is the server's
for (const ctr of ["0", "1"]) {
  // the film's query, with the page's look and movie style as the Movie Editor sends them to the server
  const extra = await page.evaluate(c => window.cassiniLook() + window.cassiniMovieStyle({ center: c === "1" }), ctr);
  const query = `from=${from}&until=${until}&cams=NW&pictures=${pictures}&ctr=${ctr}${extra}`;
  const q = Object.fromEntries(new URLSearchParams(query));
  const t0 = Date.now();
  let want;
  for (;;) {   // the server measures on a thread of its own: ask until every picture is measured
    want = await (await fetch(`${server}/export/levels.json?${query}`)).json();
    if (want.error) throw new Error(`server: ${want.error}`);
    if (want.total !== null && want.done >= want.total) break;
    if (Date.now() - t0 > 3600e3) throw new Error(`server: ${want.done} of ${want.total} after an hour`);
    await new Promise(r => setTimeout(r, 3000));
  }
  fetched = [];
  const got = await page.evaluate(async q => {
    const P = window.cassiniPlanLocal;
    P.levels = P.levels || window.cassiniPlanLocal.levels;
    const plan = await P.plan(Object.assign({}, q, { list: "1" }));
    if (plan.error) return { error: plan.error };
    return P.levels(q, plan.pictures);
  }, q);
  if (got.error) throw new Error(`page: ${got.error}`);
  const ids = new Set([...Object.keys(want.level), ...Object.keys(got.level)]);
  let differ = 0, most = 0, missing = 0;
  const shown = [];
  for (const id of ids) {
    const a = want.level[id], b = got.level[id];
    if (!(id in want.level) || !(id in got.level)) { missing++; continue; }
    if (a === b) continue;
    const d = a === null || b === null ? Infinity : Math.abs(a - b);
    most = Math.max(most, d);
    if (d > ev) { differ++; shown.push(id); }
  }
  for (const id of ids) if (!(id in want.level) || !(id in got.level)) shown.push(id);
  const ok = !differ && !missing;
  let explained = 0;
  console.log(`ctr=${ctr}: ${ok ? "match" : "differ"} (${ids.size} pictures; ${differ} levels differ, the most by ` +
    `${most === Infinity ? "lit vs too little lit" : most.toFixed(4) + " EV"}; ${missing} measured on one side only)`);
  for (const id of shown) {
    console.log(`  ${id}: server ${want.level[id]} EV, page ${got.level[id]} EV; the page fetched:`);
    const mine = fetched.filter(f => f.includes(id));
    for (const f of mine) console.log(`    ${f}`);
    const used = mine.find(f => f.startsWith("200 "));
    if (used && id in got.level) {
      const py = `import sys, io, math, urllib.request; sys.path[:0] = [sys.argv[1] + "/frames", sys.argv[1] + "/replay"]
import export; from PIL import Image
im = Image.open(io.BytesIO(urllib.request.urlopen(sys.argv[2]).read())); lv = export.brightness(export.Pictures(None)._on_black(im, 512))
print("null" if lv is None else round(round(lv, 5) / math.log(2), 4))`;
      try {
        const v = execFileSync(arg("--python", process.env.PYTHON || "python3"), ["-c", py, HERE, server + used.slice(4).replace(/&amp;/g, "&")], { encoding: "utf8" }).trim();
        const served = v === "null" ? null : +v;
        const right = served === got.level[id];
        explained += right;
        console.log(`    the server's Python on that picture: ${served} EV: ` + (right ? "SERVER-SIDE: the page measured the served picture right; the server's levels measured another picture" : "the page differs from it"));
      } catch (e) { console.log(`    (the server's Python could not measure it: ${String(e.message).split("\n")[0]})`); }
    }
  }
  if (!ok && explained === shown.length) serverSide++;
  else if (!ok) bad++;
}
console.log("the page read pixels through:", await page.evaluate(() => window.cassiniPlanLocal._levels && window.cassiniPlanLocal._levels.pixelsHow ? window.cassiniPlanLocal._levels.pixelsHow() || "nothing" : "unknown"));
if (errors.length) console.log("page errors:", errors.slice(0, 5).join(" | "));
await browser.close();
// exit 0: every level the same; 2: the page matched every picture it was served, and each differ is the server's
// /export/levels.json measuring another picture (measured, labelled SERVER-SIDE above); 1: the page differs
if (serverSide && !bad) console.log(`SERVER-SIDE ONLY: ${serverSide} film(s) differ only where the server's levels measured a picture it does not serve`);
process.exit(bad ? 1 : serverSide ? 2 : 0);
