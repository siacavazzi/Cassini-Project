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

// put every object of the mirror into the bucket; returns {objects, bytes, manifest}
export async function loadMirror(dir, bucket, { log } = {}) {
  let objects = 0, bytes = 0;
  const manifests = [];
  for (const key of walk(dir)) {
    const body = fs.readFileSync(path.join(dir, key));
    await bucket.put(key, body, metaOf(dir, key));
    objects++; bytes += body.length;
    if (/^manifest\/[^/]+\.json$/.test(key)) manifests.push(key);
    if (log && objects % 1000 === 0) log(`${objects} objects`);
  }
  manifests.sort();
  return { objects, bytes, manifest: manifests[manifests.length - 1] || null };
}
