// The Worker's code in node with an in-memory bucket: what it counts in Analytics Engine, and D1 read from the source.
// (fixtures.test.mjs runs the bundled Worker in workerd; this file checks what workerd cannot show.)
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handle, forgetManifest } from "../src/index.mjs";
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

function env(objects) {
  const points = [];
  return { points, BUCKET: bucket(objects), MANIFEST_KEY: "manifest/m.json", SITE_ENV: "local", USAGE: { writeDataPoint: p => points.push(p) } };
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
