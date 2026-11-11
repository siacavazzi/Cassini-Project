// Loads a mirror (WP3's `publish.py --to-dir` layout: an object per key, <key>.meta.json beside it) into the local R2
// that `wrangler dev` reads (its --persist-to folder plus /v3), through wrangler's own platform proxy, so the local Worker
// answers from exactly the mirror's objects. Used by deploy.sh --local; never touches real R2.
//
//   node web/deploy/local_r2.mjs --config DIR/wrangler.toml --persist DIR --mirror DIR [--only manifest/]
import fs from "node:fs";
import path from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1]]);
  return acc;
}, []));
const { getPlatformProxy } = await import(process.env.WRANGLER_MODULE || "wrangler");
const { env, dispose } = await getPlatformProxy({ configPath: args.config, persist: { path: args.persist }, remoteBindings: false });

function* walk(d, rel = "") {
  for (const e of fs.readdirSync(path.join(d, rel), { withFileTypes: true })) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) yield* walk(d, r);
    else if (!r.endsWith(".meta.json")) yield r;
  }
}
let n = 0, bytes = 0;
for (const key of walk(args.mirror)) {
  if (args.only && !key.startsWith(args.only)) continue;
  const file = path.join(args.mirror, key);
  const metaFile = file + ".meta.json";
  const meta = fs.existsSync(metaFile) ? JSON.parse(fs.readFileSync(metaFile, "utf8")) : {};
  const body = fs.readFileSync(file);
  await env.BUCKET.put(key, body, { httpMetadata: { contentType: meta["content-type"] }, customMetadata: meta.custom || {} });
  n++; bytes += body.length;
}
await dispose();
console.log(`local R2: ${n} objects, ${bytes} bytes from ${args.mirror}`);
