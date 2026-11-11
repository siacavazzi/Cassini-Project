// A stand-in Worker for WP8's local dry run ONLY, until WP4's web/worker/ exists. It answers just enough to prove
// the deploy, switch and rollback steps: the manifest named by MANIFEST_KEY (/version.json, /frames/slices.json,
// with X-Manifest naming the publish), /health, POST /usage, and r2-store pictures by their canonical key (keys.mjs).
// Tables, markers, headers and caching are WP4's. deploy.sh refuses to deploy this file to staging or production.
import { makeKeys } from "../../public/keys.mjs";
import KEYS from "../../public/keys.json";
import POLICY from "../../public/policy.json";

const K = makeKeys(KEYS, POLICY);
let cached = null;

async function manifest(env) {
  if (cached && cached.key === env.MANIFEST_KEY && Date.now() - cached.t < 60000) return cached.m;
  const o = await env.BUCKET.get(env.MANIFEST_KEY);
  if (!o) throw new Error("no manifest at " + env.MANIFEST_KEY);
  const m = await o.json();
  cached = { key: env.MANIFEST_KEY, t: Date.now(), m };
  return m;
}

const json = (body, m) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json", "X-Manifest": m.publish_id, "X-Stub": "wp8" } });

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    let m;
    try { m = await manifest(env); } catch (e) { return new Response(String(e.message), { status: 503 }); }
    const ans = K.canonical(req.method, u.pathname + u.search, m.families);
    const count = (store, status) => { try { env.USAGE && env.USAGE.writeDataPoint({ indexes: [String(ans.route || "none")], blobs: [store, String(status)] }); } catch (e) {} };
    if (ans.store === "refused" || ans.route === null) { count("refused", 404); return new Response("not on the public site", { status: 404 }); }
    if (ans.store === "manifest") return json(u.pathname === "/version.json" ? m.version : m.slices, m);
    if (ans.store === "worker") {
      if (u.pathname === "/health") return new Response("ok public", { headers: { "X-Manifest": m.publish_id } });
      count("usage", 204);
      return new Response(null, { status: 204 });
    }
    if (ans.store === "r2") {
      for (const key of [ans.key, ...(ans.fallback || [])]) {
        const o = await env.BUCKET.get(key);
        if (o) {
          count("r2", 200);
          return new Response(o.body, { headers: { "Content-Type": o.httpMetadata?.contentType || "application/octet-stream", "X-Manifest": m.publish_id, "X-Key": key } });
        }
      }
    }
    count(ans.store, 404);
    return new Response("not published", { status: 404, headers: { "X-Manifest": m.publish_id } });
  },
};
