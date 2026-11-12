// The Worker's code in node with an in-memory bucket: what it counts in Analytics Engine, and D1 read from the source.
// (fixtures.test.mjs runs the bundled Worker in workerd; this file checks what workerd cannot show.)
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handle, forgetManifest, forgetShards, forgetSampling } from "../src/index.mjs";
import { MANIFEST, FAMILIES } from "./fixture_mirror.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));

// R2's get() as far as the Worker uses it
function bucket(objects) {
  return {
    async get(key) {
      const o = objects[key];
      if (!o) return null;
      const bytes = new TextEncoder().encode(o.body);
      return {
        size: bytes.length, httpEtag: `"${key.length}"`, httpMetadata: o.httpMetadata || {}, customMetadata: o.customMetadata || {},
        body: new Blob([bytes]).stream(), text: async () => o.body, json: async () => JSON.parse(o.body),
      };
    },
  };
}

function env(objects, extra = {}) {
  const points = [], gets = [];
  const b = bucket(objects), BUCKET = { get: key => { gets.push(key); return b.get(key); } };
  return { points, gets, BUCKET, MANIFEST_KEY: "manifest/m.json", SITE_ENV: "local", USAGE: { writeDataPoint: p => points.push(p) }, ...extra };
}

const FRAME_KEY = `frame/${FAMILIES.frame}/frames/N1500060789_2.webp`;
const COLOR_KEY = `composite/${FAMILIES.composite}/frames/color.webp~ids=N1500060789_2,N1500060800_2`;
const OBJECTS = {
  "manifest/m.json": { body: JSON.stringify(MANIFEST) },
  [FRAME_KEY]: { body: "frame bytes", httpMetadata: { contentType: "image/webp" } },
  [COLOR_KEY]: { body: "colour bytes", httpMetadata: { contentType: "image/webp" }, customMetadata: { "x-report-sidecar": "1" } },
  [COLOR_KEY + ".h.json"]: { body: '{\n "observation": "X", "ids": ["N1500060789_2", "N1500060800_2"]\n}' },
};
const get = (e, url, init) => handle(new Request("https://frames.test" + url, init), e, { waitUntil() {} });

test("one data point per answer: route, store, status, outcome, bytes and R2 reads", async () => {
  forgetManifest();
  const e = env(OBJECTS);
  await (await get(e, "/frames/N1500060789_2.webp")).arrayBuffer();
  await (await get(e, "/frames/color.webp?ids=N1500060789_2,N1500060800_2")).arrayBuffer();
  await get(e, "/frames/N1500060800_1.webp");
  await get(e, "/flags/");
  await get(e, "/frames/N1500060789_2.webp", { method: "POST" });
  await get(e, "/usage", { method: "POST", body: "visit" });
  await get(e, "/usage", { method: "POST", body: "something else" });
  const p = e.points.map(x => ({ route: x.indexes[0], store: x.blobs[0], status: x.blobs[1], outcome: x.blobs[4], bytes: x.doubles[0], reads: x.doubles[1] }));
  assert.deepEqual(p, [
    { route: "frame", store: "r2", status: "200", outcome: "ok", bytes: 11, reads: 2 },        // the manifest, then the picture
    { route: "color", store: "r2", status: "200", outcome: "ok", bytes: 12, reads: 2 },        // the picture and its sidecar
    { route: "frame", store: "r2", status: "404", outcome: "miss", bytes: 37, reads: 1 },
    { route: "flags", store: "refused", status: "404", outcome: "refused", bytes: p[3].bytes, reads: 0 },
    { route: "none", store: "refused", status: "405", outcome: "refused", bytes: p[4].bytes, reads: 0 },
    { route: "usage", store: "usage", status: "visit", outcome: "ok", bytes: 0, reads: 0 },
    { route: "usage", store: "worker", status: "204", outcome: "ok", bytes: 0, reads: 0 },
  ]);
});

test("the sidecar's report comes back compact under the route's header", async () => {
  forgetManifest();
  const r = await get(env(OBJECTS), "/frames/color.webp?ids=N1500060789_2,N1500060800_2");
  assert.equal(r.headers.get("x-composite"), '{"observation":"X","ids":["N1500060789_2","N1500060800_2"]}');
});

test("a POST to a picture's address is 405 with Allow", async () => {
  const r = await get(env(OBJECTS), "/frames/N1500060789_2.webp", { method: "POST" });
  assert.equal(r.status, 405);
  assert.equal(r.headers.get("allow"), "GET, HEAD");
});

test("D1: the Worker's source makes no outbound request", () => {
  const files = fs.readdirSync(path.join(here, "..", "src")).map(f => path.join(here, "..", "src", f));
  files.push(path.join(here, "..", "..", "public", "keys.mjs"));
  const bad = [];
  for (const f of files) {
    const src = fs.readFileSync(f, "utf8").replace(/\/\/.*$/gm, "");
    // a call of fetch (global, globalThis.fetch, a service binding's .fetch), connect() sockets, WebSocket, XHR
    for (const m of src.matchAll(/\bfetch\s*\(|\bconnect\s*\(|new\s+WebSocket\b|XMLHttpRequest|\bsendBeacon\b/g)) bad.push(`${path.basename(f)}: ${m[0]}`);
  }
  assert.deepEqual(bad, []);
  assert.match(fs.readFileSync(files[0], "utf8"), /export default \{ fetch: handle \}/);   // the handler itself, not a call
});

// ---- the two costs WP10a found (PR #438): table answers read R2 every time; one data point per request ----

// the Cache API as far as the Worker uses it: one colo's cache, by request URL
function colo() {
  const kept = new Map();
  return { kept, default: {
    async match(req) { const r = kept.get(req.url); return r ? r.clone() : undefined; },
    async put(req, res) { kept.set(req.url, res.clone()); },
  } };
}
const TABLE = `table/${FAMILIES.table}`;
const TABLES = {
  "manifest/m.json": { body: JSON.stringify(MANIFEST) },
  [`${TABLE}/alias/N15000.json`]: { body: JSON.stringify({ shard: "N15000", frames: {
    N1500060789_2: { p: "PASS1", n: 3 }, N1500060800_2: { p: "PASS1", n: 4 }, N1500060812_2: { p: "PASS1", n: 5 } } }) },
  [`${TABLE}/pass/PASS1/steady/c1k0.json`]: { body: '{"steady": [1, 2, 3]}' },
  [`${TABLE}/pass/PASS1/info.json`]: { body: '{"pass": "PASS1"}' },
};
const tableGet = async (e, url) => { const waits = []; const r = await handle(new Request("https://frames.test" + url), e, { waitUntil: p => waits.push(p) }); await Promise.all(waits); return r; };

test("table answers: the alias shard and the pass part are read from R2 once, then from the Cache API and the isolate", async () => {
  forgetManifest(); forgetShards();
  const c = colo(); globalThis.caches = c;
  try {
    const e = env(TABLES);
    const asks = ["N1500060789_2", "N1500060800_2", "N1500060812_2"].map(id => `/frames/movie/${id}.steady.json?center=1&color=0`);
    const bodies = [];
    for (const u of asks) { const r = await tableGet(e, u); assert.equal(r.status, 200); bodies.push(await r.text()); }
    assert.deepEqual(bodies, Array(3).fill('{"steady": [1, 2, 3]}'));
    const reads = e.points.map(p => p.doubles[1]);
    assert.deepEqual(reads, [3, 0, 0]);                      // the manifest, the shard, the part; then nothing from R2
    assert.deepEqual(e.points.map(p => p.blobs[2]), ["miss", "hit", "hit"]);
    // a fresh isolate in the same colo: the shard and the part come from the Cache API
    forgetShards();
    const info = await tableGet(e, "/frames/movie/N1500060812_2.json");
    assert.deepEqual(await info.json(), { pass: "PASS1", n: 5 });
    assert.deepEqual(e.points.map(p => p.doubles[1]), [3, 0, 0, 1]);   // only info.json, which no one had asked
    forgetShards();
    await tableGet(e, "/frames/movie/N1500060789_2.steady.json?center=1&color=0");
    assert.equal(e.points.at(-1).doubles[1], 0);
    assert.equal(e.gets.filter(k => k.startsWith(TABLE + "/alias/")).length, 1);
    // a frame in no pass and a pass with no table published are not kept, and answer as before
    const none = await tableGet(e, "/frames/movie/N1500099999_2.steady.json?center=1&color=0");
    assert.equal(none.status, 404);
  } finally { delete globalThis.caches; forgetShards(); }
});

test("data points: ordinary answers sampled 1 in USAGE_SAMPLE, weighing that many; every refusal and miss written", async () => {
  forgetManifest(); forgetShards(); forgetSampling();
  const e = env(OBJECTS, { USAGE_SAMPLE: "4" });
  for (let i = 0; i < 12; i++) await (await get(e, "/frames/N1500060789_2.webp")).arrayBuffer();
  await get(e, "/frames/N1500060800_1.webp");                       // a miss
  await get(e, "/flags/");                                           // refused
  await get(e, "/usage", { method: "POST", body: "visit" });         // a counted word
  const p = e.points.map(x => ({ outcome: x.blobs[4], status: x.blobs[1], weight: x.doubles[2] }));
  assert.deepEqual(p.filter(x => x.outcome === "ok" && x.status === "200"), Array(3).fill({ outcome: "ok", status: "200", weight: 4 }));
  assert.deepEqual(p.filter(x => x.status !== "200").map(x => [x.outcome, x.status, x.weight]), [["miss", "404", 1], ["refused", "404", 1], ["ok", "visit", 1]]);
  assert.equal(p.reduce((t, x) => t + x.weight, 0), 15);           // the points stand for every answer
  assert.equal(e.points.length, 6);                                 // 6 points for 15 answers
  // without USAGE_SAMPLE (local), one point per answer, weighing 1
  forgetSampling();
  const all = env(OBJECTS);
  for (let i = 0; i < 3; i++) await get(all, "/frames/N1500060789_2.webp");
  assert.deepEqual(all.points.map(x => x.doubles[2]), [1, 1, 1]);
});
