// The exposure graph worked out in the page (levels-local.js) against the frame server's /export/levels.json, on
// real pictures, for a film with Auto center off (ctr=0) and on (ctr=1). The server measures the pictures the film
// draws (export.Pictures: centred color and processed pictures when the film's Auto center is on); the page must ask
// the frame server for the same pictures. Prints "match" or "differ" for each.
//
//   node web/check_levels_centre.mjs http://127.0.0.1:8765 [--from 2005-04-16T15:00:00 --until 2005-04-16T23:00:00]
//     [--pictures color] [--chrome]
//
// Needs playwright (or playwright-core with --chrome, which uses the installed Google Chrome) and a frame server
// running this commit's web/frames. The page code is taken from this checkout and put into the server's page.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

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
let bad = 0;
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
  bad += !ok;
  console.log(`ctr=${ctr}: ${ok ? "match" : "differ"} (${ids.size} pictures; ${differ} levels differ, the most by ` +
    `${most === Infinity ? "lit vs too little lit" : most.toFixed(4) + " EV"}; ${missing} measured on one side only)`);
  for (const id of shown.slice(0, 10)) {
    console.log(`  ${id}: server ${want.level[id]} EV, page ${got.level[id]} EV; the page fetched:`);
    for (const f of fetched.filter(f => f.includes(id))) console.log(`    ${f}`);
  }
}
if (errors.length) console.log("page errors:", errors.slice(0, 5).join(" | "));
await browser.close();
process.exit(bad ? 1 : 0);
