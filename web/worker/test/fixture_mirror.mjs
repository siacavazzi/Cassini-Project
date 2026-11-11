// A hand-made mirror (the WP3 mirror's layout, tools/mirror.mjs) holding one object for every answer in
// web/public/key_fixtures.json, so the tests can ask the Worker every fixture and know what it must answer.
//
//   node test/fixture_mirror.mjs DIR      writes the mirror and prints its manifest key
//
// makeFixtureMirror(dir) returns {manifestKey, manifest, expect}: expect[i] is what case i of the fixtures must answer:
//   {status, body?, json?, headers?}. Some cases are given special objects so every way of answering is covered:
//   a marker (Auto center's 404), a report in a sidecar, a trimmed report, a fallback key (the first key missing).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "../../public/keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.join(here, "..", "..", "public");
const read = f => JSON.parse(fs.readFileSync(path.join(PUBLIC, f), "utf8"));
const FIXTURES = read("key_fixtures.json");
const POLICY = read("policy.json");
const ROUTES = Object.fromEntries(POLICY.routes.map(r => [r.id, r]));
const KEYS = read("keys.json");

export const PUBLISH_ID = "20261111T210000Z-daa7e64";
export const FAMILIES = Object.fromEntries(Object.keys(KEYS.families.list).map((f, i) => [f, "t" + String(i + 1).padStart(12, "0")]));
export const MANIFEST = {
  publish_id: PUBLISH_ID, published: "2026-11-11T21:00:00Z", commit: "daa7e64",
  versions: { "frame_server.FRAME_VERSION": "test" }, families: FAMILIES,
  slices: { spans: [["2004-06-01T00:00:00", "2004-07-01T00:00:00"]], phases: {} },
  version: { site: "test", pictures: "test" },
};

const compact = v => JSON.stringify(v);
const isId = s => /^[NW]\d{10}_\d+$/.test(s);

export function makeFixtureMirror(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  const files = new Map();   // key -> {body: Buffer, meta}
  const put = (key, body, meta) => files.set(key, { body: Buffer.from(body), meta });
  return loadKeys().then(K => {
    const manifestKey = `manifest/${PUBLISH_ID}.json`;
    put(manifestKey, compact(MANIFEST), { httpMetadata: { contentType: "application/json" } });
    const expect = [];
    const shards = {};
    let marker = 0, sidecar = 0, trimmed = 0, fellBack = 0;
    const needed = new Set();
    const tagged = FIXTURES.cases.map(c => K.canonical(c.method || "GET", c.url, FAMILIES));
    for (const a of tagged) if (a.store === "r2") needed.add(a.key);

    FIXTURES.cases.forEach((c, i) => {
      const e = c.expect, a = tagged[i];
      if (e.store === "refused") {
        // 405 when the path is a route of another method (keys answer no route at all for it)
        const other = e.route === null && POLICY.routes.some(r => r.method !== (c.method || "GET") && new RegExp(r.pattern).test(c.url.split("?")[0]));
        expect.push({ status: other ? 405 : 404, bodyStarts: "Not on the public site: " + e.refused });
        return;
      }
      if (e.store === "worker") {
        expect.push(e.route === "health" ? { status: 200, body: "ok public\n" } : { status: 204 });
        return;
      }
      if (e.store === "manifest") {
        expect.push({ status: 200, json: MANIFEST[e.field] });
        return;
      }
      if (e.store === "table") {
        const frame = e.frame;
        shards[a.alias_key] = shards[a.alias_key] || { shard: a.alias_key.split("/").pop().replace(".json", ""), frames: {} };
        const p = "P-" + frame, m = "L-" + frame;
        shards[a.alias_key].frames[frame] = { p, n: 7, m };
        if (a.answer !== undefined) { expect.push({ status: 200, json: a.answer }); return; }
        const partKey = a.part_key.replace("{pass}", p).replace("{m}", m);
        const part = { local: true, part: a.part, pass: p };
        if (e.route === "pass_info") Object.assign(part, { observation: "TEST", target: "SATURN", camera: frame[0], pass: p, movie: true, mosaic: false, cadence: 60, frames: [[frame, 0, "CL1"]] });
        if (e.route === "mosaic_kind") Object.assign(part, { mosaic: true, movie: false, kind: "mosaic" });
        if (e.route === "tile_map") Object.assign(part, { pointings: [] });
        put(partKey, compact(part), { httpMetadata: { contentType: "application/json" } });
        expect.push({ status: 200, json: e.route === "pass_info" ? { ...part, n: 7 } : part });
        return;
      }
      // r2
      const route = ROUTES[e.route];
      const header = route.header;
      const report = { observation: "TEST", kind: e.route, url: c.url, filters: ["CL1", "CL2"] };
      const body = `picture ${a.key}`;
      const ext = a.key.split("~")[0].split(".").pop();
      const ctype = ext === "png" ? "image/png" : "image/webp";
      if (route.markers && a.params.center === "1" && marker < 3) {
        marker++;
        const x = compact({ centre: false, why: "test: Auto center leaves this pass as it is" });
        if (!files.has(a.key)) put(a.key, "", { httpMetadata: { contentType: "application/json" }, customMetadata: { "x-status": "404", "x-center": x, "x-body": x } });
        expect.push({ status: 404, body: files.get(a.key).meta.customMetadata ? files.get(a.key).meta.customMetadata["x-body"] : x, headers: { "x-center": x } });
        return;
      }
      if (a.fallback.length && !needed.has(a.fallback[0]) && fellBack < 3 && !files.has(a.key)) {
        fellBack++;
        const fbBody = `picture ${a.fallback[0]}`;
        put(a.fallback[0], fbBody, { httpMetadata: { contentType: ctype }, customMetadata: header ? { [header.toLowerCase()]: compact(report) } : {} });
        needed.delete(a.key);
        expect.push({ status: 200, body: fbBody, headers: header ? { [header.toLowerCase()]: compact(report) } : {}, fallback: true });
        return;
      }
      if (files.has(a.key)) {
        const f = files.get(a.key), cm = f.meta.customMetadata || {};
        expect.push(cm["x-status"] ? { status: 404, body: cm["x-body"], headers: { "x-center": cm["x-center"] } }
          : { status: 200, body: f.body.toString(), headers: f.expectHeaders || {} });
        return;
      }
      const meta = { httpMetadata: { contentType: ctype }, customMetadata: {} };
      let shown = compact(report);
      if (header && sidecar < 2 && e.route !== "thumb") {
        sidecar++;
        meta.customMetadata["x-report-sidecar"] = "1";
        put(a.key + ".h.json", JSON.stringify(report, null, 1), { httpMetadata: { contentType: "application/json" } });
      } else if (header && trimmed < 2) {
        trimmed++;
        shown = compact({ observation: "TEST", kind: e.route });
        meta.customMetadata[header.toLowerCase()] = shown;
        meta.customMetadata["x-report-trimmed"] = "1";
      } else if (header) meta.customMetadata[header.toLowerCase()] = shown;
      put(a.key, body, meta);
      files.get(a.key).expectHeaders = header ? { [header.toLowerCase()]: shown, "content-type": ctype } : { "content-type": ctype };
      expect.push({ status: 200, body, headers: files.get(a.key).expectHeaders });
    });
    for (const [key, shard] of Object.entries(shards)) put(key, compact(shard), { httpMetadata: { contentType: "application/json" } });

    for (const [key, f] of files) {
      const file = path.join(dir, key);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, f.body);
      fs.writeFileSync(file + ".meta.json", JSON.stringify(f.meta));
    }
    return { manifestKey, manifest: MANIFEST, expect, cases: FIXTURES.cases, objects: files.size, counts: { marker, sidecar, trimmed, fellBack } };
  });
}

if (process.argv[1] && import.meta.url === new URL(`file://${path.resolve(process.argv[1])}`).href) {
  const dir = process.argv[2] || path.join(here, "..", ".mirror-fixtures");
  const m = await makeFixtureMirror(dir);
  console.log(`${m.objects} objects in ${dir}; manifest ${m.manifestKey}; ${JSON.stringify(m.counts)}`);
}
