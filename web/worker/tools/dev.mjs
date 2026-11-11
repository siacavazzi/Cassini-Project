// The Worker on this computer, serving a publish mirror (web/frames/publish.py --to-dir, WP3) through wrangler dev.
//
//   node tools/dev.mjs --mirror DIR [--port 8911] [--manifest manifest/<id>.json] [--fresh] [--no-serve]
//   node tools/dev.mjs --fixtures            the hand-made mirror of every key fixture (test/fixture_mirror.mjs)
//
// It loads the mirror into wrangler's local R2 (.wrangler/state, the same store wrangler dev reads; --fresh empties it
// first), then starts `wrangler dev` on the port with MANIFEST_KEY set to the mirror's newest manifest (or --manifest).
// Point the page at it with ?frames=http://HOST:8911 and run the harness with --frames http://HOST:8911 --mode public.
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { loadMirror } from "./mirror.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : "1"]);
  return acc;
}, []));
const port = args.port || "8911";
const state = path.join(root, ".wrangler", "state");
const toml = fs.readFileSync(path.join(root, "wrangler.toml"), "utf8");
const bucketName = /\[\[r2_buckets\]\][^[]*?bucket_name\s*=\s*"([^"]+)"/s.exec(toml)[1];

let dir = args.mirror;
if (args.fixtures) {
  const { makeFixtureMirror } = await import("../test/fixture_mirror.mjs");
  dir = path.join(root, ".mirror-fixtures");
  await makeFixtureMirror(dir);
}
if (!dir || !fs.existsSync(dir)) { console.error("--mirror DIR (a publish.py --to-dir folder) or --fixtures is needed"); process.exit(2); }
if (args.fresh) fs.rmSync(path.join(state, "v3", "r2"), { recursive: true, force: true });

// wrangler dev keeps local R2 under <persist-to>/v3/r2, one namespace per bucket_name
const mf = new Miniflare({
  modules: true, script: "export default { fetch() { return new Response(null, { status: 204 }); } }",
  r2Buckets: { BUCKET: bucketName }, r2Persist: path.join(state, "v3", "r2"),
});
const t0 = Date.now();
const loaded = await loadMirror(dir, await mf.getR2Bucket("BUCKET"), { log: m => process.stdout.write(`\r${m}`) });
await mf.dispose();
const manifest = args.manifest || loaded.manifest;
console.log(`\rloaded ${loaded.objects} objects, ${(loaded.bytes / 1e6).toFixed(1)} MB from ${dir} in ${((Date.now() - t0) / 1000).toFixed(1)} s; manifest ${manifest}`);
if (!manifest) { console.error("the mirror holds no manifest/<id>.json"); process.exit(1); }
if (args["no-serve"]) process.exit(0);

const wr = spawn(path.join(root, "node_modules", ".bin", "wrangler"),
  ["dev", "--port", port, "--ip", "0.0.0.0", "--persist-to", state, "--var", `MANIFEST_KEY:${manifest}`, "--show-interactive-dev-session=false"],
  { cwd: root, stdio: "inherit" });
wr.on("exit", code => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => wr.kill(sig));
