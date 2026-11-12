// tools/mirror.mjs: the batched loader (one request per batch, for mirrors of any size) puts exactly what the
// one-put-per-object loader puts, and a load survives connection errors (EADDRNOTAVAIL on the Mac at ~16,000 puts).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Miniflare } from "miniflare";
import { loadMirror, LOADER_SCRIPT, retrying } from "../tools/mirror.mjs";
import { makeFixtureMirror } from "./fixture_mirror.mjs";

async function contents(bucket) {
  const out = {};
  let cursor;
  do {
    const l = await bucket.list({ cursor, limit: 1000, include: ["httpMetadata", "customMetadata"] });
    for (const o of l.objects) {
      const got = await bucket.get(o.key);
      out[o.key] = { body: Buffer.from(await got.arrayBuffer()).toString("base64"), type: got.httpMetadata.contentType, meta: got.customMetadata };
    }
    cursor = l.truncated ? l.cursor : undefined;
  } while (cursor);
  return out;
}

test("batched loading puts the same objects, bytes and metadata as one put per object", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wp4-load-"));
  await makeFixtureMirror(dir);
  // a big body, so a batch is cut by size as well as by count
  fs.writeFileSync(path.join(dir, "archive", "big.png"), Buffer.alloc(3 * 1024 * 1024, 7));
  const a = new Miniflare({ modules: true, script: LOADER_SCRIPT, r2Buckets: ["BUCKET"] });
  const b = new Miniflare({ modules: true, script: LOADER_SCRIPT, r2Buckets: ["BUCKET"] });
  try {
    const batched = await loadMirror(dir, a, { batchObjects: 7, batchBytes: 1024 * 1024 });
    const single = await loadMirror(dir, await b.getR2Bucket("BUCKET"));
    assert.equal(batched.objects, single.objects);
    assert.equal(batched.bytes, single.bytes);
    assert.equal(batched.manifest, single.manifest);
    const ca = await contents(await a.getR2Bucket("BUCKET")), cb = await contents(await b.getR2Bucket("BUCKET"));
    assert.equal(Object.keys(ca).length, batched.objects);
    assert.deepEqual(ca, cb);
  } finally {
    await a.dispose(); await b.dispose();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a connection error is tried again; any other error is not", async () => {
  let calls = 0;
  const flaky = async () => { if (++calls < 3) { const e = new TypeError("fetch failed"); e.cause = { code: "EADDRNOTAVAIL" }; throw e; } return "ok"; };
  const log = [];
  assert.equal(await retrying("x", flaky, { log: m => log.push(m) }), "ok");
  assert.equal(calls, 3);
  assert.equal(log.length, 2);
  let other = 0;
  await assert.rejects(retrying("y", async () => { other++; throw new Error("loader answered 500"); }), /500/);
  assert.equal(other, 1);
});
