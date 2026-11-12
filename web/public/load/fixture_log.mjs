// A harness-shaped session log of every key fixture (web/public/key_fixtures.json), with the status the Worker's fixture
// mirror must answer for each (web/worker/test/fixture_mirror.mjs), so the load runner can be run in the cloud against
// `node web/worker/tools/dev.mjs --fixtures` before the rehearsal rig's logs exist.
//
//   node web/public/load/fixture_log.mjs --out DIR [--seconds 60] [--host http://127.0.0.1:8911]
//
// Writes DIR/FIX.json: the 232 cases spread evenly over --seconds, in the shape zero_origin.mjs --out writes.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "./replay.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));

export async function fixtureLog({ seconds = 60, host = "http://127.0.0.1:8911" } = {}) {
  const { makeFixtureMirror } = await import(path.join(here, "..", "..", "worker", "test", "fixture_mirror.mjs"));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "g3-fixture-mirror-"));
  try {
    const m = await makeFixtureMirror(tmp);
    const t0 = Date.UTC(2026, 10, 12);
    const step = (seconds * 1000) / m.cases.length;
    const requests = m.cases.map((c, i) => ({
      url: host + (/^https?:/.test(c.url) ? new URL(c.url).pathname + new URL(c.url).search : c.url), method: c.method || "GET", type: "fetch", t: Math.round(t0 + i * step),
      status: m.expect[i].status, headers: {}, bytes: (m.expect[i].body || "").length,
    }));
    return { session: "FIX", title: "every key fixture once", mode: "public", site: host, frames: host, seconds, error: null, steps: [], requests };
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  const { flags } = parseArgs(process.argv.slice(2));
  if (!flags.out) { console.error("--out DIR is needed"); process.exit(2); }
  const log = await fixtureLog({ seconds: +(flags.seconds || 60), host: flags.host });
  fs.mkdirSync(flags.out, { recursive: true });
  fs.writeFileSync(path.join(flags.out, "FIX.json"), JSON.stringify(log, null, 1));
  console.log(`${log.requests.length} requests over ${log.seconds} s in ${path.join(flags.out, "FIX.json")}`);
}
