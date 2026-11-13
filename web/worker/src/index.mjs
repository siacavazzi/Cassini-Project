// The public site's frames host (docs/public-site/briefs/WP4.md): answers every request the page sends to the frame
// server from R2 alone, by the contracts in web/public/. Nothing here reaches an origin (decision D1): there is no
// outbound request anywhere in this file, and the tests check that both by reading the source and by failing any
// outbound request while every fixture is answered.
//
// One request:
//   1. keys.canonical(method, url, manifest.families) (web/public/keys.mjs, imported as it is) says which store answers;
//   2. r2:       the object at its canonical key, then each fallback key in order; an object whose metadata holds
//                x-status is a marker (headers.json markers), answered with that status, X-Center and body;
//      table:    the frame's alias shard, then the pass-table part it names (tables.schema.json); info gets the alias's n;
//      manifest: a field of the published manifest (version.json, slices.json);
//      worker:   GET /health and POST /usage;
//      refused:  404 (405 when the path is a route of another method), counted;
//   3. CORS, caching and download names per headers.json worker_adds; the Cache API in front of R2, for pictures and
//      for the alias shards and pass-table parts a table answer reads, and the last few alias shards kept parsed in
//      the isolate. A table's key carries its family's tag, which follows the picture versions only: a new publish
//      under the same versions rewrites the same keys (an alias shard gains the frames of years added, a pass's maps
//      follow its built tiles). So the table copies are kept under the publish too (cache key and isolate memo), and
//      a new manifest starts them cold: one R2 read per colo per object, once a publish.
//
// Bindings (web/deploy/ fills them; wrangler.toml here is the local template): BUCKET the R2 bucket, MANIFEST_KEY the
// manifest's key (manifest/<publish_id>.json), USAGE an Analytics Engine dataset (optional), USAGE_SAMPLE (optional,
// a whole number N; staging and production set 10), SITE_ENV (local, staging or production; reported on /health).
//
// Analytics Engine data points, for the cost sheet (WP8) and the gates (refusals and misses). A point costs about as
// much as the Worker request itself, so ordinary answers are sampled: an answer that came back whole (status below
// 400, outcome ok or fallback) is written with chance 1 in N, weighing N (double3), so the weighted total is unbiased
// however short-lived the isolates are; the others not at all. Every
// refusal, miss, marker, none, error, 4xx and 5xx and every POST /usage word is written, weighing 1, so the gates
// count them exactly. Sum double3 (times _sample_interval) for requests; double1 and double2 times double3 for bytes
// and R2 reads. One point:
//   index1 the policy route id ("none" when no route fits)
//   blob1 the store (r2, table, manifest, worker, refused; "usage" for a POST /usage word), blob2 the status (the
//   word for usage), blob3 cache "hit" or "miss" ("" when the Cache API is not used), blob4 the colo, blob5 the
//   outcome (ok, miss, marker, refused, fallback, none, error), double1 the response bytes, double2 the R2 reads made,
//   double3 the answers it stands for (1, or N for a sampled one).
import { makeKeys } from "../../public/keys.mjs";
import KEYS from "../../public/keys.json" with { type: "json" };
import POLICY from "../../public/policy.json" with { type: "json" };
import HEADERS from "../../public/headers.json" with { type: "json" };

const K = makeKeys(KEYS, POLICY);
const ROUTES = Object.fromEntries(POLICY.routes.map(r => [r.id, { ...r, _re: new RegExp(r.pattern) }]));
const ROUTE_LIST = Object.values(ROUTES);
const ADDS = HEADERS.worker_adds;
const NAMES = HEADERS.download_names;
const FOREVER = "public, max-age=31536000, immutable";
const MINUTE = "public, max-age=60";
// a table answer in the viewer's browser: its address (/frames/movie/<id>.steady.json ...) is the same in every
// publish, and a new publish under the same picture versions can change what it answers (an alias shard gains the
// frames of years added; a pass's maps follow its built tiles), so a browser keeps it five minutes, not for ever
// (a picture's answer for an address does not change between publishes; a table's can)
const TABLE_TIME = "public, max-age=300";
const NO_STORE = "no-store";
const MANIFEST_SECONDS = 60;
// the page's one word for POST /usage (web/frames/usage.py BEACONS); anything else is ignored, as the server does
const BEACONS = new Set(["visit", "visit-link", "copy-link"]);
const USAGE_MAX = 64;
// the X-* reports kept in an object's metadata: lower-case metadata name -> header name (headers.json storage)
const REPORTS = Object.fromEntries(Object.keys(HEADERS.page_reads).map(h => [h.toLowerCase(), h]));
const BY_EXT = { webp: "image/webp", png: "image/png", json: "application/json" };

// ---- the manifest, read once per isolate and kept a minute -------------------------------------------------------
let manifestMemo = null;   // {key, at, value}
export function forgetManifest() { manifestMemo = null; }

async function manifestOf(env, note) {
  const key = env.MANIFEST_KEY;
  if (!key) return null;
  const now = Date.now();
  if (manifestMemo && manifestMemo.key === key && now - manifestMemo.at < MANIFEST_SECONDS * 1000) return manifestMemo.value;
  note.reads++;
  const obj = await env.BUCKET.get(key);
  const value = obj ? await obj.json() : null;
  manifestMemo = { key, at: now, value };
  return value;
}

// ---- answers --------------------------------------------------------------------------------------------------------
function cors(h) {
  h.set("Access-Control-Allow-Origin", ADDS["Access-Control-Allow-Origin"]);
  h.set("Access-Control-Expose-Headers", ADDS["Access-Control-Expose-Headers"]);
  return h;
}

function text(status, body, extra = {}) {
  const h = cors(new Headers({ "Content-Type": "text/plain; charset=utf-8", "Cache-Control": NO_STORE, ...extra }));
  h.set("Content-Length", String(new TextEncoder().encode(body).length));
  return new Response(body, { status, headers: h });
}

function json(status, value, cache) {
  const body = typeof value === "string" ? value : JSON.stringify(value);
  const h = cors(new Headers({ "Content-Type": "application/json", "Cache-Control": cache }));
  h.set("Content-Length", String(new TextEncoder().encode(body).length));
  return new Response(body, { status, headers: h });
}

function contentTypeOf(obj, key) {
  const t = obj.httpMetadata && obj.httpMetadata.contentType;
  if (t) return t;
  return BY_EXT[key.split("~")[0].split(".").pop()] || "application/octet-stream";
}

// a picture's answer from its R2 object (and the sidecar, when the report did not fit the metadata)
async function fromObject(env, obj, key, route, note) {
  const meta = obj.customMetadata || {};
  const h = cors(new Headers());
  if (meta["x-status"]) {
    // a marker: a deliberate negative answer (Auto center's 404 with X-Center)
    note.outcome = "marker";
    h.set("Content-Type", "application/json");
    h.set("Cache-Control", NO_STORE);
    if (meta["x-center"]) h.set("X-Center", meta["x-center"]);
    return new Response(meta["x-body"] || "", { status: parseInt(meta["x-status"], 10) || 404, headers: h });
  }
  h.set("Content-Type", contentTypeOf(obj, key));
  h.set("Cache-Control", FOREVER);
  h.set("Content-Length", String(obj.size));
  if (obj.httpEtag) h.set("ETag", obj.httpEtag);
  for (const [name, header] of Object.entries(REPORTS)) if (meta[name]) h.set(header, meta[name]);
  if (meta["x-report-sidecar"] === "1" && route.header) {
    note.reads++;
    const side = await env.BUCKET.get(`${key}.h.json`);
    if (side) h.set(route.header, JSON.stringify(JSON.parse(await side.text())));
  }
  note.bytes = obj.size;
  return new Response(obj.body, { status: 200, headers: h });
}

// the name a download=1 answer is saved as (headers.json download_names)
function downloadName(ans, path) {
  const pattern = NAMES[ans.route];
  if (!pattern) return null;
  const m = ROUTES[ans.route]._re.exec(path);
  const id = m && m[1];
  const ids = (ans.params.ids || "").split(",").filter(Boolean).join("_");
  if ((pattern.includes("{id}") && !id) || (pattern.includes("{ids}") && !ids)) return null;
  return pattern.replace("{id}", id || "").replace("{ids}", ids);
}

// ---- the stores -----------------------------------------------------------------------------------------------------
async function answerR2(env, ans, route, cache, origin, ctx, note) {
  const keys = [ans.key, ...ans.fallback];
  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const cacheKey = new Request(`${origin}/__r2/${encodeURIComponent(key)}`);
    if (cache) {
      const hit = await cache.match(cacheKey);
      if (hit) {
        note.cache = "hit";
        note.outcome = i ? "fallback" : "ok";
        note.bytes = +(hit.headers.get("Content-Length") || 0);
        return hit;
      }
      note.cache = "miss";
    }
    note.reads++;
    const obj = await env.BUCKET.get(key);
    if (!obj) continue;
    note.outcome = i ? "fallback" : "ok";
    const res = await fromObject(env, obj, key, route, note);
    if (cache && res.status === 200 && ctx) ctx.waitUntil(cache.put(cacheKey, res.clone()));
    return res;
  }
  return null;
}

// a table object's text: from the Cache API when the colo holds it for this publish, else from R2 (one read), then
// kept there under this publish (pub: the manifest's publish_id). A missing object is not kept.
async function readText(env, key, pub, cache, origin, ctx, note) {
  const cacheKey = cache ? new Request(`${origin}/__r2/${encodeURIComponent(pub)}/${encodeURIComponent(key)}`) : null;
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) { if (note.cache !== "miss") note.cache = "hit"; return hit.text(); }
    note.cache = "miss";
  }
  note.reads++;
  const obj = await env.BUCKET.get(key);
  if (!obj) return null;
  const body = await obj.text();
  if (cache && ctx) ctx.waitUntil(cache.put(cacheKey, new Response(body, { headers: { "Content-Type": "application/json", "Cache-Control": FOREVER } })));
  return body;
}

// the last SHARDS_KEPT alias shards this isolate read, parsed (a camera window asks the tables of many frames of the
// same shard in a row; a shard is parsed once, not once per frame)
const SHARDS_KEPT = 16;
const shards = new Map();   // publish id and alias key -> its frames object
async function shardOf(env, key, pub, cache, origin, ctx, note) {
  const memo = pub + " " + key;
  if (shards.has(memo)) {
    const frames = shards.get(memo);
    shards.delete(memo); shards.set(memo, frames);
    if (note.cache !== "miss") note.cache = "hit";
    return frames;
  }
  const text = await readText(env, key, pub, cache, origin, ctx, note);
  if (text === null) return null;
  const frames = JSON.parse(text).frames || {};
  shards.set(memo, frames);
  if (shards.size > SHARDS_KEPT) shards.delete(shards.keys().next().value);
  return frames;
}
export function forgetShards() { shards.clear(); }

async function answerTable(env, ans, pub, cache, origin, ctx, note) {
  if (ans.answer !== undefined) return json(200, ans.answer, FOREVER);
  const frames = await shardOf(env, ans.alias_key, pub, cache, origin, ctx, note);
  const entry = frames ? frames[ans.frame] : undefined;
  // a frame in no pass (or, for tile_map, in a pass with no tile map) answers as the server does
  const noAlias = () => {
    if (ans.no_alias_answer !== undefined) return json(200, ans.no_alias_answer, MINUTE);
    note.outcome = "none";
    return json(404, ans.route === "tile_map" ? { error: "not a mosaic pass" } : { error: "not in a pass" }, NO_STORE);
  };
  if (!entry || (ans.part_key.includes("{m}") && !entry.m)) return noAlias();
  const partKey = ans.part_key.replace("{pass}", entry.p).replace("{m}", entry.m || "");
  const part = await readText(env, partKey, pub, cache, origin, ctx, note);
  if (part === null) { note.outcome = "miss"; return json(404, { error: "no table published for this pass" }, NO_STORE); }
  if (ans.route === "pass_info") return json(200, { ...JSON.parse(part), n: entry.n }, TABLE_TIME);
  return json(200, part, TABLE_TIME);
}

// ---- counting (Workers Analytics Engine) ----------------------------------------------------------------------------
let random = Math.random;   // the sampling's draw (tests set a fixed one)
export function sampleWith(draw) { random = draw || Math.random; }
function count(env, request, note) {
  try {
    if (!env.USAGE) return;
    const every = Math.max(1, Math.floor(+env.USAGE_SAMPLE) || 1);
    const whole = note.store !== "usage" && (note.outcome === "ok" || note.outcome === "fallback") && +note.status < 400;
    if (whole && every > 1 && random() * every >= 1) return;
    const colo = (request.cf && request.cf.colo) || "";
    env.USAGE.writeDataPoint({
      indexes: [(note.route || "none").slice(0, 96)],
      blobs: [note.store, String(note.status), note.cache, colo, note.outcome],
      doubles: [note.bytes, note.reads, whole ? every : 1],
    });
  } catch (e) { /* counting never fails an answer */ }
}

// ---- one request ----------------------------------------------------------------------------------------------------
async function answer(request, env, ctx, note) {
  const url = new URL(request.url);
  const method = request.method === "HEAD" ? "GET" : request.method;

  if (request.method === "OPTIONS") {
    note.store = "worker";
    return new Response(null, { status: 204, headers: cors(new Headers({
      "Access-Control-Allow-Methods": "GET, HEAD, POST",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      "Cache-Control": NO_STORE,
    })) });
  }

  // which store answers does not depend on the tags, so refusals and the Worker's own answers need no manifest
  let ans = K.canonical(method, url.pathname + url.search, null);
  note.route = ans.route;
  note.store = ans.store;
  if (ans.store === "refused") {
    note.outcome = "refused";
    const allow = ans.route === null ? [...new Set(ROUTE_LIST.filter(r => r._re.test(url.pathname)).map(r => r.method))] : [];
    if (allow.length) {
      if (allow.includes("GET")) allow.push("HEAD");
      return text(405, "Not on the public site: " + ans.refused + "\n", { Allow: allow.join(", ") });
    }
    return text(404, "Not on the public site: " + ans.refused + "\n");
  }

  if (ans.store === "worker") {
    if (ans.route === "health") return text(200, "ok public\n", env.SITE_ENV ? { "X-Site-Env": env.SITE_ENV } : {});
    // usage: one word from the page, nothing else read or kept
    const body = await request.text().catch(() => "");
    const word = body.length <= USAGE_MAX ? body.trim() : "";
    if (BEACONS.has(word)) { note.store = "usage"; note.word = word; }
    return new Response(null, { status: 204, headers: cors(new Headers({ "Cache-Control": NO_STORE })) });
  }

  const manifest = await manifestOf(env, note);
  if (!manifest) { note.outcome = "miss"; return text(503, "Nothing is published yet (no manifest)\n"); }

  if (ans.store === "manifest") {
    const value = manifest[ans.field];
    if (value === undefined) { note.outcome = "miss"; return json(404, { error: `the manifest has no ${ans.field}` }, NO_STORE); }
    return json(200, value, MINUTE);
  }

  ans = K.canonical(method, url.pathname + url.search, manifest.families);
  const cache = typeof caches !== "undefined" && caches.default ? caches.default : null;
  if (ans.store === "table") return answerTable(env, ans, manifest.publish_id || env.MANIFEST_KEY, cache, url.origin, ctx, note);

  // r2
  let res = await answerR2(env, ans, ROUTES[ans.route], cache, url.origin, ctx, note);
  if (!res) { note.outcome = "miss"; return text(404, "No picture published at this address\n"); }
  if (res.status === 200) {
    const etag = res.headers.get("ETag");
    if (etag && request.headers.get("If-None-Match") === etag) {
      note.bytes = 0;
      return new Response(null, { status: 304, headers: new Headers(res.headers) });
    }
    if (ans.download) {
      const name = downloadName(ans, url.pathname);
      if (name) {
        res = new Response(res.body, res);
        res.headers.set("Content-Disposition", `attachment; filename="${name}"`);
      }
    }
  }
  return res;
}

export async function handle(request, env, ctx) {
  const note = { route: null, store: "", status: 0, cache: "", outcome: "ok", bytes: 0, reads: 0, word: null };
  let res;
  try {
    res = await answer(request, env, ctx, note);
  } catch (e) {
    note.outcome = "error";
    res = text(500, "The frames host failed on this request\n");
  }
  note.status = res.status;
  if (!note.bytes && res.status !== 304 && res.headers.get("Content-Length")) note.bytes = +res.headers.get("Content-Length");
  count(env, request, note.word ? { ...note, status: note.word } : note);
  if (request.method === "HEAD" && res.body) return new Response(null, { status: res.status, headers: res.headers });
  return res;
}

export default { fetch: handle };
