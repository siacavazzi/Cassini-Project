// Gate G3's harness pass (public site, WP10a): runs one harness session (S1, default play) on each of the ten stretches
// in stretches.json through the rig, then prints G2's counts per stretch and the cost model on all of them.
//
//   node web/public/load/g3_stretches.mjs --site http://HOST:8916 [--frames http://HOST:8915] --out DIR
//        [--minutes 3] [--only 1,4,9] [--spares] [--parallel N] [--channel chrome] [--three DIR]
//
// Each stretch's logs go to DIR/NN-<label>/ (zero_origin.mjs --out), so the load runner can replay them:
//   node web/public/load/load_runner.mjs --frames http://HOST:8915 --viewers 100 DIR/*/
// --parallel  stretches run at once (default: one per four cores; each is a browser playing for --minutes)
// Exit status 0 when every stretch ran with origin, refused and miss all 0.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseArgs, readSessions, checkTarget, checkWorker } from "./replay.mjs";
import { countSession, model, printModel } from "./cost_model.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const { flags } = parseArgs(process.argv.slice(2), ["spares", "headed"]);
const fail = m => { console.error(m); process.exit(2); };
if (!flags.site || !flags.out) fail("--site URL and --out DIR are needed");
const site = await checkTarget(flags.site).catch(e => fail(e.message));
const frames = await checkWorker(flags.frames ? await checkTarget(flags.frames).catch(e => fail(e.message)) : site).catch(e => fail(e.message));
const S = JSON.parse(fs.readFileSync(path.join(here, "stretches.json"), "utf8"));
let list = S.stretches.map((s, i) => ({ ...s, n: i + 1 }));
if (flags.spares) list = list.concat(S.spares.map((s, i) => ({ ...s, n: S.stretches.length + i + 1 })));
if (flags.only) { const keep = new Set(flags.only.split(",").map(Number)); list = list.filter(s => keep.has(s.n)); }
const minutes = flags.minutes || String(S.minutes);

// every stretch must be inside what the rig publishes
const slices = await fetch(`${frames}/frames/slices.json`).then(r => r.ok ? r.json() : null).catch(() => null);
const spans = slices && slices.spans;
const outside = spans ? list.filter(s => !spans.some(([a, b]) => s.t >= a && s.t < b)) : [];
if (outside.length) console.log(`not in the rig's slices (they will play an empty sky): ${outside.map(s => `${s.n} ${s.label} ${s.t}`).join("; ")}`);

const slug = s => `${String(s.n).padStart(2, "0")}-${s.label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
function run(s) {
  const dir = path.join(flags.out, slug(s));
  const argv = [path.join(here, "..", "harness", "zero_origin.mjs"), "--site", site, "--mode", "public", "--sessions", S.session,
    "--moment", s.t, "--speed", String(s.speed), "--label", s.label, "--minutes", minutes, "--out", dir];
  if (frames !== site) argv.push("--frames", frames);
  for (const k of ["channel", "three"]) if (flags[k]) argv.push(`--${k}`, flags[k]);
  if (flags.headed) argv.push("--headed");
  return new Promise(res => {
    const p = spawn(process.execPath, argv, { stdio: ["ignore", "pipe", "inherit"] });
    let text = "";
    p.stdout.on("data", d => { text += d; });
    p.on("exit", code => { console.log(`${slug(s).padEnd(40)} ${text.trim().split("\n").pop()}`); res({ s, dir, code }); });
  });
}

const parallel = Math.max(1, +(flags.parallel || Math.floor(os.cpus().length / 4)));
const queue = [...list], done = [];
await Promise.all(Array.from({ length: Math.min(parallel, queue.length) }, async () => { while (queue.length) done.push(await run(queue.shift())); }));
done.sort((a, b) => a.s.n - b.s.n);

const rows = [];
for (const d of done) {
  const f = path.join(d.dir, `${S.session}.json`);
  const log = fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : null;
  const c = log ? log.counts : null;
  rows.push({ n: d.s.n, label: d.s.label, t: d.s.t, speed: d.s.speed, ran: d.code === 0, error: log ? log.error : "no log", counts: c, outside: outside.includes(d.s) });
}
console.log(`\n n  stretch                              requests  frames  origin  refused  miss  marker  probe   MB`);
for (const r of rows) {
  const c = r.counts || {};
  console.log(`${String(r.n).padStart(2)}  ${r.label.padEnd(36)} ${String(c.requests ?? "-").padStart(8)} ${String(c.frames ?? "-").padStart(7)} ${String(c.origin ?? "-").padStart(7)} ${String(c.refused ?? "-").padStart(8)} ${String(c.miss ?? "-").padStart(5)} ${String(c.marker ?? "-").padStart(7)} ${String(c.probe ?? "-").padStart(6)} ${c.bytes !== undefined ? (c.bytes / 1e6).toFixed(1).padStart(5) : "    -"}${r.error ? "  ERROR " + String(r.error).split("\n")[0] : ""}`);
}
const ok = rows.every(r => r.ran && r.counts && !r.error && r.counts.origin === 0 && r.counts.refused === 0 && r.counts.miss === 0);
console.log(`G2 on the ten stretches: ${ok ? "PASS" : "FAIL"}\n`);

const sessions = (await readSessions(done.map(d => d.dir).filter(d => fs.existsSync(d)))).filter(s => s.requests);
let M = null;
if (sessions.length) { M = model(await Promise.all(sessions.map(countSession)), { storageGb: 250 }); printModel(M); }
fs.writeFileSync(path.join(flags.out, "g3-stretches.json"), JSON.stringify({ when: new Date().toISOString(), site, frames, minutes: +minutes, pass: ok, stretches: rows, cost: M }, null, 1));
process.exit(ok ? 0 : 1);
