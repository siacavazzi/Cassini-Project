// What the gate G3 tools share (public site, WP10a): reading the zero-origin harness's logs (harness/zero_origin.mjs
// --out DIR writes <DIR>/<session>.json with every request and <DIR>/summary.json with the counts), the request
// classes the load runner and the cost model count by, the guard that keeps load off public services, and percentiles.
//
// A session log's request is {url, method, type, t, status, headers, bytes, failed?, k}; k is the harness's class
// ({cls: static|frames|cdn|inline|other, route, store, verdict}). Logs written before k existed are classed here with
// keys.mjs, as the harness would.
import fs from "node:fs";
import path from "node:path";
import dns from "node:dns/promises";
import net from "node:net";
import { loadKeys } from "../keys.mjs";

let K = null;
const keys = async () => K || (K = await loadKeys());

// the class a frames-host request is counted in: the store that answers it (policy.json), pictures apart
export function classOf(k) {
  if (!k || k.cls === "static") return "static";
  if (k.cls !== "frames") return k.cls;               // cdn, inline, other: not replayed, not the site's bill
  if (k.store === "r2") return "picture";
  return k.store || "refused";                          // table, manifest, worker, refused
}

const hostOf = u => { try { return new URL(u).host; } catch (e) { return ""; } };

// the harness's classify(), for a log that has no k (frames when the URL is a frames route on the frames host)
function classify(K, r, siteHost, framesHost) {
  const u = new URL(r.url);
  if (u.protocol === "data:" || u.protocol === "blob:") return { cls: "inline" };
  const ans = u.host === framesHost || u.host === siteHost ? K.canonical(r.method, u.pathname + u.search) : null;
  const framesRoute = ans && (ans.route !== null || /^\/(frames|reel|export|prebuild|flags|stats|jumplog|usage|health|version\.json)/.test(u.pathname));
  if (u.host === framesHost && (framesRoute || framesHost !== siteHost)) return { cls: "frames", route: ans.route, store: ans.store };
  if (u.host === siteHost) return { cls: "static" };
  return { cls: "other" };
}

// every *.json under the paths given (a file or a harness --out folder), read as a session log or a summary
export function logFiles(paths) {
  const out = [];
  for (const p of paths) {
    if (!fs.existsSync(p)) throw new Error(`no such log: ${p}`);
    if (fs.statSync(p).isDirectory()) {
      for (const f of fs.readdirSync(p).sort()) if (f.endsWith(".json")) out.push(path.join(p, f));
    } else out.push(p);
  }
  return out;
}

// sessions from logs: [{id, file, site, frames, seconds, requests: [{offset, method, path, cls, route, store, status,
// bytes, verdict, host: "site"|"frames"}], summary?}]. A summary.json gives its sessions without requests (the cost
// model can still use their counts); a session that also has its own log is taken from the log.
export async function readSessions(paths) {
  const Kx = await keys();
  const full = [], summaries = [];
  for (const file of logFiles(paths)) {
    let d;
    try { d = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { throw new Error(`${file}: not JSON (${e.message})`); }
    if (Array.isArray(d.sessions) && !d.requests) {
      for (const s of d.sessions) summaries.push({ id: s.session, file, site: s.site || d.site, frames: s.frames || d.frames, seconds: s.seconds, error: s.error, summary: s });
      continue;
    }
    if (!Array.isArray(d.requests)) continue;   // some other JSON beside the logs
    const site = d.site, frames = d.frames || d.site;
    const siteHost = hostOf(site), framesHost = hostOf(frames);
    const parses = u => { try { new URL(u); return true; } catch (e) { return false; } };
    const reqs = d.requests.filter(r => r && r.url && typeof r.t === "number" && parses(r.url)).sort((a, b) => a.t - b.t);
    const t0 = reqs.length ? reqs[0].t : 0;
    const out = [];
    for (const r of reqs) {
      const k = r.k || classify(Kx, r, siteHost, framesHost);
      const cls = classOf(k);
      if (cls !== "static" && !["picture", "table", "manifest", "worker", "refused"].includes(cls)) continue;
      const u = new URL(r.url);
      out.push({
        offset: r.t - t0, method: r.method || "GET", path: u.pathname + u.search, cls,
        route: k.route || null, store: k.store || null, verdict: k.verdict || null,
        status: r.failed ? 0 : (r.status || 0), bytes: r.bytes || 0,
        host: cls === "static" ? "site" : "frames",
      });
    }
    const span = out.length ? out[out.length - 1].offset / 1000 : 0;
    full.push({ id: d.session || path.basename(file, ".json"), file, site, frames, seconds: d.seconds || Math.max(1, Math.round(span)), error: d.error || null, requests: out });
  }
  const have = new Set(full.map(s => `${s.id}|${s.site}|${s.frames}`));
  return [...full, ...summaries.filter(s => !have.has(`${s.id}|${s.site}|${s.frames}`))];
}

// nearest-rank percentile of numbers (p in 0..100); null for none
export function percentile(values, p) {
  if (!values.length) return null;
  const v = Float64Array.from(values).sort();
  const i = Math.min(v.length - 1, Math.max(0, Math.ceil((p / 100) * v.length) - 1));
  return v[i];
}

// ---- the guard: load only ever goes to this computer, the home network or the tailnet -------------------------------
// The rehearsal rig's Worker (wrangler dev on the MacBook) is the only target G3 has. A public service, Cloudflare
// staging or production included, is refused whatever the flags: pointing load at one is a change to this file,
// through review, with Sam's word.
function v4Private(ip) {
  const [a, b] = ip.split(".").map(Number);
  return a === 127 || a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31)
    || (a === 100 && b >= 64 && b <= 127);   // 100.64/10: Tailscale's addresses
}
export function privateAddress(ip) {
  if (net.isIPv4(ip)) return v4Private(ip);
  if (net.isIPv6(ip)) {
    const s = ip.toLowerCase();
    if (s === "::1") return true;
    const m = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(s);
    if (m) return v4Private(m[1]);
    return /^f[cd]/.test(s) || /^fe[89ab]/.test(s);   // unique local, link local
  }
  return false;
}
// resolves the base URL's host; throws unless every address it has is private
export async function checkTarget(base) {
  let u;
  try { u = new URL(base); } catch (e) { throw new Error(`not a URL: ${base}`); }
  if (!/^https?:$/.test(u.protocol)) throw new Error(`not http(s): ${base}`);
  const host = u.hostname.replace(/^\[|\]$/g, "");
  if (/\.(ts\.net|workers\.dev|pages\.dev|r2\.dev)$/i.test(host) || /cassinios/i.test(host))
    throw new Error(`refused: ${host} is a public service; the load runner only targets the local rehearsal Worker`);
  let addrs;
  if (net.isIP(host)) addrs = [host];
  else {
    try { addrs = (await dns.lookup(host, { all: true })).map(a => a.address); } catch (e) { throw new Error(`cannot resolve ${host}: ${e.message}`); }
  }
  const pub = addrs.filter(a => !privateAddress(a));
  if (!addrs.length || pub.length)
    throw new Error(`refused: ${host} (${addrs.join(", ")}) is not on this computer, the home network or the tailnet; the load runner only targets the local rehearsal Worker`);
  return u.origin;
}

// --flag value pairs; the flags named in `bare` take no value ("1"); the rest of the arguments are positional
export function parseArgs(argv, bare = []) {
  const flags = {}, rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const next = argv[i + 1];
      if (bare.includes(a.slice(2))) { flags[a.slice(2)] = "1"; continue; }
      if (next !== undefined && !next.startsWith("--")) { flags[a.slice(2)] = next; i++; } else flags[a.slice(2)] = "1";
    } else rest.push(a);
  }
  return { flags, rest };
}
