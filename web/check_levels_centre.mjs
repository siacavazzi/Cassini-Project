// The exposure graph worked out in the page (levels-local.js) against the frame server's /export/levels.json, on
// real pictures, for a film with Auto center off (ctr=0) and on (ctr=1). The server measures the pictures the film
// draws (export.Pictures: centred color and processed pictures when the film's Auto center is on); the page must ask
// the frame server for the same pictures. Prints "match" or "differ" for each.
//
//   node web/check_levels_centre.mjs http://127.0.0.1:8765 [--from 2005-04-16T15:00:00 --until 2005-04-16T23:00:00]
//     [--pictures color] [--chrome] [--python ~/venv/bin/python] [--cold]
//
// Before measuring, every mosaic the film shows is made to the end (--cold: not), since the frame server answers a
// mosaic still being made with the tiles so far (X-Reel "behind"), and its /export/levels.json stores what it saw.
//
// For a picture that differs, the picture the page used is measured again by the server's own Python
// (export.brightness on export.Pictures._on_black of the served WebP; --python PATH or PYTHON, default python3: the
// frame server's interpreter, with numpy and Pillow): "the page measured the served picture right" means the server's /export/levels.json measured some
// other picture (a server-side defect, cold-levels-finding.md), not the page port.
//
// The page's plan is compared with the server's /export/plan.json try by try, and each picture the page measured is
// named by the exact address picture() ended on (levels-local.js _levels.used).
// Exit 0: the same plans and the same levels; 2: the same plans, and the only differences are SERVER-SIDE ones; 1:
// the plans differ, or the page port does.
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
let bad = 0, serverSide = 0;   // films that differ otherwise; films whose every difference is SERVER-SIDE
for (const ctr of ["0", "1"]) {
  // the film's query, with the page's look and movie style as the Movie Editor sends them to the server
  const extra = await page.evaluate(c => window.cassiniLook() + window.cassiniMovieStyle({ center: c === "1" }), ctr);
  const query = `from=${from}&until=${until}&cams=NW&pictures=${pictures}&ctr=${ctr}${extra}`;
  const q = Object.fromEntries(new URLSearchParams(query));
  // the server's plan for the same film ([kind, address] tries, best first); its mosaics made to the end first, so
  // neither side measures a mosaic still behind its frame (the server answers those 200 with X-Reel "behind")
  const splan = await (await fetch(`${server}/export/plan.json?${query}&list=1`)).json();
  if (splan.error) throw new Error(`server plan: ${splan.error}`);
  const stries = Object.fromEntries((splan.pictures || []).map(e => [e.id, e.tries]));
  if (!argv.includes("--cold")) {
    const mosaics = (splan.pictures || []).filter(e => e.tries[0][0] === "mosaic").map(e => `${server}${e.tries[0][1]}?size=512`);
    const tm = Date.now();
    for (const url of mosaics) {
      for (;;) {
        const r = await fetch(url, { cache: "no-store" });
        let b = 0;
        try { b = JSON.parse(r.headers.get("X-Reel") || "{}").behind || 0; } catch (e) { b = 0; }
        if ((r.ok && !b) || r.status === 404 || Date.now() - tm > 3600e3) break;
        await new Promise(res => setTimeout(res, 3000));
      }
    }
    if (mosaics.length) console.log(`ctr=${ctr}: ${mosaics.length} mosaics made to the end before measuring (${((Date.now() - tm) / 1000).toFixed(0)} s)`);
  }
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
    const plan = await P.plan(Object.assign({}, q, { list: "1" }));
    if (plan.error) return { error: plan.error };
    P._levels.used.clear();
    const out = await P.levels(q, plan.pictures);
    out.tries = Object.fromEntries(plan.pictures.map(e => [e.id, e.tries]));
    out.used = Object.fromEntries(P._levels.used);
    return out;
  }, q);
  if (got.error) throw new Error(`page: ${got.error}`);
  // the server's plan, try by try, against the page's
  const planIds = new Set([...Object.keys(stries), ...Object.keys(got.tries)]);
  const planDiff = [...planIds].filter(id => JSON.stringify(stries[id]) !== JSON.stringify(got.tries[id]));
  console.log(`ctr=${ctr}: plans ${planDiff.length ? "DIFFER" : "the same"} (${planIds.size} pictures; ${planDiff.length} with other tries)`);
  for (const id of planDiff.slice(0, 10))
    console.log(`  ${id}: server's plan ${JSON.stringify(stries[id] ?? null)}\n  ${" ".repeat(id.length)}  page's plan   ${JSON.stringify(got.tries[id] ?? null)}`);

  const ids = new Set([...Object.keys(want.level), ...Object.keys(got.level)]);
  let differ = 0, most = 0, missing = 0;
  const shown = [];
  for (const id of ids) {
    const a = want.level[id], b = got.level[id];
    if (!(id in want.level) || !(id in got.level)) { missing++; shown.push(id); continue; }
    if (a === b) continue;
    const d = a === null || b === null ? Infinity : Math.abs(a - b);
    most = Math.max(most, d);
    if (d > ev) { differ++; shown.push(id); }
  }
  const ok = !differ && !missing;
  let explained = 0;
  console.log(`ctr=${ctr}: levels ${ok ? "match" : "differ"} (${ids.size} pictures; ${differ} levels differ, the most by ` +
    `${most === Infinity ? "lit vs too little lit" : most.toFixed(4) + " EV"}; ${missing} measured on one side only)`);
  for (const id of shown) {
    const u = got.used[id], samePlan = !planDiff.includes(id);
    console.log(`  ${id}: server ${want.level[id]} EV, page ${got.level[id]} EV; ${samePlan ? "the same tries in both plans" : "OTHER TRIES in the two plans"}; ` +
      `the page's picture: ${u ? `try ${u.n + 1} (${u.kind}) ${u.url}` : "none"}`);
    for (const f of fetched.filter(f => f.includes(id))) console.log(`    fetched ${f}`);
    if (!u || !(id in got.level)) continue;
    const py = `import sys, io, math, urllib.request; sys.path[:0] = [sys.argv[1] + "/frames", sys.argv[1] + "/replay"]
import export; from PIL import Image
im = Image.open(io.BytesIO(urllib.request.urlopen(sys.argv[2]).read())); lv = export.brightness(export.Pictures(None)._on_black(im, 512))
print("null" if lv is None else round(round(lv, 5) / math.log(2), 4))`;
    try {
      const v = execFileSync(arg("--python", process.env.PYTHON || "python3"), ["-c", py, HERE, new URL(u.url, server + "/").href], { encoding: "utf8" }).trim();
      const served = v === "null" ? null : +v;
      // the server's levels measured another picture than the one both plans put first, which the page measured right
      const right = served === got.level[id] && samePlan && u.n === 0;
      explained += right;
      console.log(`    the server's Python on the page's picture: ${served} EV: ` + (right
        ? "SERVER-SIDE: both plans put this try first, the page used it and measured it right; the server's levels measured another picture"
        : served === got.level[id] ? (u.n ? `the page measured try ${u.n + 1} right, but its earlier tries failed` : "the page measured it right, but the plans differ")
          : "the page differs from it"));
    } catch (e) { console.log(`    (the server's Python could not measure it: ${String(e.message).split("\n")[0]})`); }
  }
  if (planDiff.length || (!ok && explained !== shown.length)) bad++;
  else if (!ok) serverSide++;
}
console.log("the page read pixels through:", await page.evaluate(() => window.cassiniPlanLocal._levels && window.cassiniPlanLocal._levels.pixelsHow ? window.cassiniPlanLocal._levels.pixelsHow() || "nothing" : "unknown"));
if (errors.length) console.log("page errors:", errors.slice(0, 5).join(" | "));
await browser.close();
// exit 0: the same plans and every level the same; 2: the same plans, and each level that differs is SERVER-SIDE (the
// page used the first try both plans give and measured it as the server's Python does); 1: anything else
if (serverSide && !bad) console.log(`SERVER-SIDE ONLY: ${serverSide} film(s) differ only where the server's levels measured a picture it does not serve`);
process.exit(bad ? 1 : serverSide ? 2 : 0);
