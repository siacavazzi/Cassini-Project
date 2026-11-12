// The Worker in workerd (Miniflare), on a hand-made mirror that answers every case of web/public/key_fixtures.json
// (test/fixture_mirror.mjs): every fixture is answered per its store, the X-* reports come back whole, trimmed or from
// the sidecar, markers answer their status, fallbacks are used, downloads are named, and no request ever leaves the
// Worker (an outbound request fails the test). Run: npm test (bundles first with wrangler).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { makeFixtureMirror, MANIFEST } from "./fixture_mirror.mjs";
import { loadMirror } from "../tools/mirror.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(here, "..", "dist", "index.js");
const ORIGIN = "https://frames.test";
let mf, mirror, outbound = [];

async function start(vars = {}) {
  const m = new Miniflare({
    modules: true, scriptPath: SCRIPT, compatibilityDate: "2026-08-01", compatibilityFlags: ["nodejs_compat"],
    r2Buckets: ["BUCKET"],
    bindings: { MANIFEST_KEY: mirror.manifestKey, SITE_ENV: "local", ...vars },
    // D1: nothing may reach an origin; any outbound request is recorded and fails
    outboundService: req => { outbound.push(req.url); return new Response("outbound blocked", { status: 599 }); },
  });
  await loadMirror(mirror.dir, await m.getR2Bucket("BUCKET"));
  return m;
}

before(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wp4-mirror-"));
  mirror = { ...(await makeFixtureMirror(dir)), dir };
  mf = await start();
});
after(async () => { await mf.dispose(); fs.rmSync(mirror.dir, { recursive: true, force: true }); });

const ask = (method, url, init = {}) => mf.dispatchFetch(/^https?:/.test(url) ? url : ORIGIN + url, { method, redirect: "manual", ...init });

test("every key fixture is answered per its store", async () => {
  const bad = [];
  const seen = { r2: 0, table: 0, manifest: 0, worker: 0, refused: 0, marker: 0, fallback: 0 };
  for (let i = 0; i < mirror.cases.length; i++) {
    const c = mirror.cases[i], want = mirror.expect[i], method = c.method || "GET";
    const res = await ask(method, c.url, method === "POST" && c.url === "/usage" ? { body: "visit" } : {});
    const body = await res.text();
    const fail = why => bad.push(`${method} ${c.url}: ${why}`);
    seen[c.expect.store]++;
    if (want.fallback) seen.fallback++;
    if (res.headers.get("x-center")) seen.marker++;
    if (res.status !== want.status) { fail(`status ${res.status}, want ${want.status} (${body.slice(0, 120)})`); continue; }
    if (want.body !== undefined && body !== want.body) fail(`body ${JSON.stringify(body.slice(0, 120))}, want ${JSON.stringify(want.body.slice(0, 120))}`);
    if (want.bodyStarts && !body.startsWith(want.bodyStarts)) fail(`body ${JSON.stringify(body.slice(0, 160))}`);
    if (want.json !== undefined) { try { assert.deepEqual(JSON.parse(body), want.json); } catch (e) { fail(`json ${body.slice(0, 160)}`); } }
    for (const [h, v] of Object.entries(want.headers || {})) if (res.headers.get(h) !== v) fail(`${h} ${res.headers.get(h)}, want ${v}`);
    if (res.headers.get("access-control-allow-origin") !== "*") fail("no CORS");
    const cc = res.headers.get("cache-control");
    // a picture, and a table answer fixed in keys.json, for ever; a table read from a publish five minutes (a new
    // publish can change it at the same address); a frame in no pass a minute
    const keep = c.expect.store === "r2" || c.expect.answer !== undefined ? "public, max-age=31536000, immutable"
      : c.expect.no_alias_answer !== undefined ? null : "public, max-age=300";
    if (want.status === 200 && ["r2", "table"].includes(c.expect.store) && keep && cc !== keep) fail(`cache-control ${cc}, want ${keep}`);
    if (c.expect.store === "refused" && cc !== "no-store") fail(`refusal cache-control ${cc}`);
  }
  assert.deepEqual(bad, [], bad.join("\n"));
  console.log(`  ${mirror.cases.length} fixtures:`, JSON.stringify(seen), "special objects", JSON.stringify(mirror.counts));
  assert.ok(seen.marker >= 1 && seen.fallback >= 1 && mirror.counts.sidecar >= 1 && mirror.counts.trimmed >= 1);
});

test("the second ask of a picture comes from the Cache API with the same bytes and headers", async () => {
  const i = mirror.cases.findIndex((c, j) => c.expect.store === "r2" && mirror.expect[j].status === 200 && c.expect.route === "color");
  const c = mirror.cases[i];
  const a = await ask("GET", c.url), ab = await a.text();
  const b = await ask("GET", c.url), bb = await b.text();
  assert.equal(ab, bb);
  assert.equal(a.headers.get("x-composite"), b.headers.get("x-composite"));
  assert.equal(b.headers.get("cache-control"), "public, max-age=31536000, immutable");
});

test("manifest answers: version.json and slices.json from the manifest, kept a minute", async () => {
  const v = await ask("GET", "/version.json");
  assert.deepEqual(await v.json(), MANIFEST.version);
  assert.equal(v.headers.get("cache-control"), "public, max-age=60");
  const s = await ask("GET", "/frames/slices.json");
  assert.deepEqual(await s.json(), MANIFEST.slices);
});

test("health, usage, OPTIONS and HEAD", async () => {
  const h = await ask("GET", "/health");
  assert.equal(h.status, 200); assert.equal(await h.text(), "ok public\n"); assert.equal(h.headers.get("x-site-env"), "local");
  for (const word of ["visit", "nonsense", "x".repeat(200)]) {
    const u = await ask("POST", "/usage", { body: word });
    assert.equal(u.status, 204);
  }
  const o = await ask("OPTIONS", "/frames/color.webp");
  assert.equal(o.status, 204);
  assert.match(o.headers.get("access-control-allow-methods"), /GET/);
  const pic = mirror.cases.find((c, j) => c.expect.route === "frame" && mirror.expect[j].status === 200);
  const hd = await ask("HEAD", pic.url);
  assert.equal(hd.status, 200);
  assert.equal(await hd.text(), "");
  assert.equal(hd.headers.get("content-type"), "image/webp");
});

test("download=1 names the file as the server does; without it there is no Content-Disposition", async () => {
  const id = mirror.cases.find((c, j) => c.expect.route === "frame" && mirror.expect[j].status === 200 && !c.expect.download);
  const plain = await ask("GET", id.url);
  assert.equal(plain.headers.get("content-disposition"), null);
  const sep = id.url.includes("?") ? "&" : "?";
  const d = await ask("GET", id.url + sep + "download=1");
  const frame = /\/frames\/([NW]\d{10}_\d+)\.webp/.exec(id.url)[1];
  assert.equal(d.headers.get("content-disposition"), `attachment; filename="Cassini_${frame}.webp"`);
  const col = mirror.cases.find((c, j) => c.expect.route === "color" && mirror.expect[j].status === 200);
  const dc = await ask("GET", col.url + "&download=1");
  const ids = new URLSearchParams(col.url.split("?")[1]).get("ids").split(",").filter(Boolean).join("_");
  assert.equal(dc.headers.get("content-disposition"), `attachment; filename="Cassini_${ids}_color.webp"`);
});

test("If-None-Match with the ETag answers 304", async () => {
  const pic = mirror.cases.find((c, j) => c.expect.route === "archive" && mirror.expect[j].status === 200);
  const a = await ask("GET", pic.url);
  await a.arrayBuffer();
  const etag = a.headers.get("etag");
  assert.ok(etag);
  const b = await ask("GET", pic.url, { headers: { "If-None-Match": etag } });
  assert.equal(b.status, 304);
});

test("a picture or table that is not published is a 404, a frame in no pass answers as the server does", async () => {
  const miss = await ask("GET", "/frames/N1999999999_1.webp");
  assert.equal(miss.status, 404);
  const kind = await ask("GET", "/frames/mosaic/N1999999999_1.webp?warm=1");
  assert.deepEqual(await kind.json(), { mosaic: false, movie: false, kind: null });
  const map = await ask("GET", "/frames/mosaic/N1999999999_1.json");
  assert.equal(map.status, 404);
  assert.deepEqual(await map.json(), { error: "not a mosaic pass" });
  const fade = await ask("GET", "/frames/movie/N1999999999_1.fade.json?laps=1&w=0&h=0");
  assert.deepEqual(await fade.json(), { local: false });
});

test("no manifest: pictures answer 503, health still answers", async () => {
  const m = await start({ MANIFEST_KEY: "manifest/none.json" });
  try {
    assert.equal((await m.dispatchFetch(ORIGIN + "/frames/N1500060789_2.webp")).status, 503);
    assert.equal((await m.dispatchFetch(ORIGIN + "/health")).status, 200);
  } finally { await m.dispose(); }
});

test("D1: no request ever left the Worker", () => {
  assert.deepEqual(outbound, []);
});
