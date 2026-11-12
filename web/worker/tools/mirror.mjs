// A publish mirror (web/frames/publish.py --to-dir, WP3) read into an R2 bucket binding, for wrangler dev and the tests.
//
// The mirror holds every object at its R2 key as a file, and beside each object its metadata as <key>.meta.json, in
// the shape of R2's put() options:
//   {"httpMetadata": {"contentType": "image/webp"}, "customMetadata": {"x-composite": "{...}", "x-status": "404", ...}}
// A flat map is read as customMetadata too (with an optional "contentType"), and a missing content type comes from
// the extension. Sidecars (<key>.h.json) are objects like any other. The newest manifest/<publish_id>.json names
// the publish to serve.
import fs from "node:fs";
import path from "node:path";

const BY_EXT = { webp: "image/webp", png: "image/png", json: "application/json" };

export function* walk(dir, rel = "") {
  for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) yield* walk(dir, r);
    else if (e.isFile() && !r.endsWith(".meta.json")) yield r;
  }
}

export function metaOf(dir, key) {
  const f = path.join(dir, key + ".meta.json");
  const raw = fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : {};
  let httpMetadata = raw.httpMetadata, customMetadata = raw.customMetadata;
  if (!httpMetadata && !customMetadata) {
    const { contentType, ...rest } = raw;
    httpMetadata = contentType ? { contentType } : undefined;
    customMetadata = rest;
  }
  httpMetadata = { ...(httpMetadata || {}) };
  if (!httpMetadata.contentType) {
    const ext = key.split("~")[0].split(".").pop();
    if (BY_EXT[ext]) httpMetadata.contentType = BY_EXT[ext];
  }
  return { httpMetadata, customMetadata: customMetadata || {} };
}

// The loader Worker for big mirrors: one request carries a batch of objects (a 4-byte header length, the header JSON
// [{key, size, meta}], then the bodies one after another) and puts each into its BUCKET binding. A put through
// Miniflare's bucket proxy opens a connection of its own, so a sampler mirror (about 100,000 objects) used up the
// Mac's ephemeral ports (EADDRNOTAVAIL near 16,000 puts); a batch of a few hundred objects needs one.
export const LOADER_SCRIPT = `export default {
  async fetch(req, env) {
    const buf = new Uint8Array(await req.arrayBuffer());
    const n = new DataView(buf.buffer, buf.byteOffset, 4).getUint32(0);
    const head = JSON.parse(new TextDecoder().decode(buf.subarray(4, 4 + n)));
    let off = 4 + n;
    for (const o of head) { await env.BUCKET.put(o.key, buf.slice(off, off + o.size), o.meta); off += o.size; }
    return new Response(String(head.length));
  }
};`;

const TRANSIENT = /EADDRNOTAVAIL|ECONNRESET|ECONNREFUSED|EPIPE|ETIMEDOUT|socket hang up|fetch failed|other side closed/i;
const pause = ms => new Promise(r => setTimeout(r, ms));

// a call that failed because of the connection (not the data) is tried again, up to `tries` times, waiting longer each time
export async function retrying(what, call, { tries = 8, log } = {}) {
  for (let i = 1; ; i++) {
    try { return await call(); } catch (e) {
      const why = `${e && e.message} ${e && e.cause && (e.cause.code || e.cause.message) || ""} ${e && e.code || ""}`;
      if (i >= tries || !TRANSIENT.test(why)) throw e;
      if (log) log(`retry ${i} of ${what}: ${why.trim()}`);
      await pause(Math.min(250 * 2 ** (i - 1), 10000));
    }
  }
}

// put every object of the mirror into an R2 bucket; returns {objects, bytes, manifest, retries}.
// target is either a Miniflare instance whose script is LOADER_SCRIPT (batched: one request per batch, for any size of
// mirror) or an R2 bucket binding such as mf.getR2Bucket() returns (one put per object, for small mirrors and tests).
export async function loadMirror(dir, target, { log, batchBytes = 32 * 1024 * 1024, batchObjects = 500 } = {}) {
  let objects = 0, bytes = 0, retries = 0;
  const manifests = [];
  const counted = log ? m => { if (m.startsWith("retry")) retries++; log(m); } : m => { if (m.startsWith("retry")) retries++; };
  const batched = typeof target.dispatchFetch === "function";
  let batch = [], size = 0;
  const flush = async () => {
    if (!batch.length) return;
    const head = Buffer.from(JSON.stringify(batch.map(o => ({ key: o.key, size: o.body.length, meta: o.meta }))));
    const len = Buffer.alloc(4); len.writeUInt32BE(head.length);
    const body = Buffer.concat([len, head, ...batch.map(o => o.body)]);
    const want = batch.length, first = batch[0].key;
    await retrying(`batch from ${first}`, async () => {
      const res = await target.dispatchFetch("http://loader.local/", { method: "POST", body });
      const text = await res.text();
      if (!res.ok || text !== String(want)) throw new Error(`loader answered ${res.status} ${text.slice(0, 200)}`);
    }, { log: counted });
    batch = []; size = 0;
  };
  for (const key of walk(dir)) {
    const body = fs.readFileSync(path.join(dir, key));
    const meta = metaOf(dir, key);
    if (batched) {
      if (batch.length && (size + body.length > batchBytes || batch.length >= batchObjects)) await flush();
      batch.push({ key, body, meta }); size += body.length;
    } else {
      await retrying(key, () => target.put(key, body, meta), { log: counted });
    }
    objects++; bytes += body.length;
    if (/^manifest\/[^/]+\.json$/.test(key)) manifests.push(key);
    if (log && objects % 1000 === 0) log(`${objects} objects`);
  }
  await flush();
  manifests.sort();
  return { objects, bytes, manifest: manifests[manifests.length - 1] || null, retries };
}
