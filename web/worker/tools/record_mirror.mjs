// A stand-in for WP3's mirror until publish.py exists: the frames-host requests of harness logs, asked again of a frame
// server and written as a mirror (tools/mirror.mjs layout) under the canonical keys, so wrangler dev can serve a real
// session's pictures. A test tool only: it runs on a Mac next to a frame server and is never part of the Worker.
//
//   node tools/record_mirror.mjs --server http://127.0.0.1:8955 --out DIR LOG.json [LOG.json ...]
//
// LOG.json is a harness session log (zero_origin.mjs --out). Each r2 answer is written at its key with its X-* report
// as metadata (an X-Center 404 becomes a marker); each table answer becomes a one-frame pass (pass id R-<frame>) and
// an alias entry, so the Worker answers it from tables as it will from WP2's; version.json and slices.json go into a
// manifest. Tags are fixed local ones (t000000000001...), not the publish's. Running it again adds to the mirror.
import fs from "node:fs";
import path from "node:path";
import { loadKeys } from "../../public/keys.mjs";

const argv = process.argv.slice(2);
const opt = name => { const i = argv.indexOf(`--${name}`); return i < 0 ? null : argv.splice(i, 2)[1]; };
const server = (opt("server") || "").replace(/\/$/, "");
const out = opt("out");
if (!server || !out || !argv.length) { console.error("--server URL --out DIR LOG.json ..."); process.exit(2); }

const K = await loadKeys();
const KEYS = JSON.parse(fs.readFileSync(new URL("../../public/keys.json", import.meta.url), "utf8"));
const FAMILIES = Object.fromEntries(Object.keys(KEYS.families.list).map((f, i) => [f, "t" + String(i + 1).padStart(12, "0")]));
const REPORTS = ["x-composite", "x-movie", "x-reel", "x-thumb"];

const write = (key, body, meta) => {
  const f = path.join(out, key);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, body);
  if (meta) fs.writeFileSync(f + ".meta.json", JSON.stringify(meta));
};
const readJson = (key, dflt) => { try { return JSON.parse(fs.readFileSync(path.join(out, key), "utf8")); } catch (e) { return dflt; } };

const urls = new Map();
for (const log of argv) {
  const j = JSON.parse(fs.readFileSync(log, "utf8"));
  for (const r of j.requests || []) {
    const u = new URL(r.url);
    const a = K.canonical(r.method, u.pathname + u.search, FAMILIES);
    if (a.store === "refused" || a.store === "worker") continue;
    urls.set(a.store === "r2" ? a.key : `${r.method} ${u.pathname}${u.search}`, { method: r.method, path: u.pathname + u.search, a });
  }
}

const n = { r2: 0, marker: 0, table: 0, manifest: 0, absent: 0, failed: 0, bytes: 0 };
const manifestOut = { families: FAMILIES };
const tasks = [...urls.values()];
async function one({ path: p, a }) {
  try {
    if (a.store === "manifest") {
      const r = await fetch(server + p);
      if (r.ok) { manifestOut[a.field] = await r.json(); n.manifest++; }
      return;
    }
    if (a.store === "r2") {
      if (fs.existsSync(path.join(out, a.key))) return;
      const r = await fetch(server + p);
      const body = Buffer.from(await r.arrayBuffer());
      if (r.status === 404 && r.headers.get("x-center")) {
        write(a.key, "", { httpMetadata: { contentType: "application/json" }, customMetadata: { "x-status": "404", "x-center": r.headers.get("x-center"), "x-body": body.toString().slice(0, 512) } });
        n.marker++; return;
      }
      if (!r.ok) { n.absent++; return; }
      const custom = {};
      for (const h of REPORTS) if (r.headers.get(h)) custom[h] = JSON.stringify(JSON.parse(r.headers.get(h)));
      write(a.key, body, { httpMetadata: { contentType: r.headers.get("content-type") || "image/webp" }, customMetadata: custom });
      n.r2++; n.bytes += body.length; return;
    }
    if (a.store === "table") {
      if (a.answer !== undefined) return;
      const r = await fetch(server + p);
      if (!r.ok) { n.absent++; return; }
      const value = await r.json();
      if (a.no_alias_answer !== undefined && JSON.stringify(value) === JSON.stringify(a.no_alias_answer)) return;   // in no pass
      const pass = "R-" + a.frame, m = "R-" + a.frame;
      const shard = readJson(a.alias_key, { shard: a.alias_key.split("/").pop().replace(".json", ""), frames: {} });
      const entry = shard.frames[a.frame] || { p: pass, n: -1, m };
      if (a.route === "pass_info") { entry.n = value.n; delete value.n; }
      shard.frames[a.frame] = entry;
      write(a.alias_key, JSON.stringify(shard), { httpMetadata: { contentType: "application/json" } });
      write(a.part_key.replace("{pass}", pass).replace("{m}", m), JSON.stringify(value), { httpMetadata: { contentType: "application/json" } });
      n.table++;
    }
  } catch (e) { n.failed++; }
}
// table answers write the same shard: one at a time for them, pictures in parallel
const tables = tasks.filter(t => t.a.store === "table"), rest = tasks.filter(t => t.a.store !== "table");
for (const t of tables) await one(t);
for (let i = 0; i < rest.length; i += 16) await Promise.all(rest.slice(i, i + 16).map(one));

const id = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "") + "-0000000";
const old = fs.existsSync(path.join(out, "manifest")) ? fs.readdirSync(path.join(out, "manifest")).sort().pop() : null;
const prev = old ? readJson(`manifest/${old}`, {}) : {};
const manifest = {
  publish_id: id, published: new Date().toISOString(), commit: "0000000", versions: { recorded_from: server },
  families: FAMILIES, slices: manifestOut.slices || prev.slices || { spans: null, phases: {} },
  version: manifestOut.version || prev.version || {},
};
write(`manifest/${id}.json`, JSON.stringify(manifest), { httpMetadata: { contentType: "application/json" } });
console.log(`${tasks.length} distinct URLs: ${JSON.stringify(n)}; manifest manifest/${id}.json`);
