// The gate G3 cost model (public site, WP10a): turns zero-origin harness logs into requests and bytes per
// viewer-minute, by what Cloudflare bills (Worker requests and CPU, R2 Class B reads, Analytics Engine data points,
// Pages, egress), and prices them at 1,000 viewers with prices.json (the capacity report's prices).
//
//   node web/public/load/cost_model.mjs [--mix S1=6,S2=2,S3=1] [--edge-hit 0.5] [--cpu-ms 1] [--isolates 300]
//        [--storage-gb 250] [--objects 5000000] [--viewers 1000] [--prices FILE] [--json OUT] LOG...
//
// LOG         harness logs: <session>.json files or zero_origin.mjs --out folders (a summary.json alone is read too,
//             from its per-route counts, and marked "from summary")
// --mix       weight of each session id in the viewer mix (default: every session id weighs the same). Logs of one id
//             from several folders (the ten G3 stretches, each an S1) are pooled into one rate.
// --edge-hit  share of picture requests the Worker's Cache API answers without reading R2 (default 0.5, the capacity
//             report's pessimistic figure). The table reports 0 and 0.9 beside it.
// --cpu-ms    Worker CPU milliseconds per request (default 1: the Worker parses a key and streams R2's body; wall
//             time spent waiting on R2 is not billed). Replace with the rig's measured figure when there is one.
// --isolates  Worker isolates that each read the manifest once a minute (default 300, about one per busy colo)
//
// What each frames request costs, from the Worker's code (web/worker/src/index.mjs):
//   every request          one Worker request, its CPU, one Analytics Engine data point
//   picture (store r2)     answered from the Cache API, or one R2 read (a 404 reads every fallback key too; a marker
//                          is never cached, so one read)
//   table                  two reads (alias shard, pass part); one for a 404; none for an answer fixed in keys.json
//   manifest               none per request (read once per isolate a minute: at most --isolates x 60 reads an hour)
//   worker, refused        none
// Static requests go to Pages, which bills nothing per request or byte; R2 egress is free. Both are counted and shown.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSessions, parseArgs } from "./replay.mjs";
import { loadKeys } from "../keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
export const PRICES = JSON.parse(fs.readFileSync(path.join(here, "prices.json"), "utf8"));
const POLICY = JSON.parse(fs.readFileSync(path.join(here, "..", "policy.json"), "utf8"));
const STORE = Object.fromEntries(POLICY.routes.map(r => [r.id, r.store]));

// one session's counts. R2 reads are split into what the edge cache can save (pictures answered 200) and the rest.
export async function countSession(s) {
  const c = { id: s.id, file: s.file, minutes: (s.seconds || 0) / 60, from: s.requests ? "log" : "summary",
    worker: 0, picture: 0, table: 0, manifest: 0, worker_store: 0, refused: 0, static: 0,
    reads_cacheable: 0, reads_fixed: 0, frames_bytes: 0, static_bytes: 0 };
  if (s.requests) {
    const K = await loadKeys();
    for (const r of s.requests) {
      if (r.cls === "static") { c.static++; c.static_bytes += r.bytes; continue; }
      c.worker++; c.frames_bytes += r.bytes;
      if (r.cls === "picture") {
        c.picture++;
        if (r.status >= 200 && r.status < 400) c.reads_cacheable += 1;
        else if (r.verdict === "marker") c.reads_fixed += 1;
        else { const a = K.canonical(r.method, r.path); c.reads_fixed += 1 + ((a && a.fallback) ? a.fallback.length : 0); }
      } else if (r.cls === "table") {
        c.table++;
        const a = K.canonical(r.method, r.path);
        if (a && a.answer !== undefined) continue;
        c.reads_fixed += r.status === 404 ? 1 : 2;
      } else if (r.cls === "manifest") c.manifest++;
      else if (r.cls === "worker") c.worker_store++;
      else c.refused++;
    }
  } else {
    // a summary: per-route counts and total bytes (static bytes are not split out there, so they are all put on frames)
    const sm = s.summary;
    c.static = sm.counts.static || 0;
    c.frames_bytes = sm.counts.bytes || 0;
    for (const [route, n] of Object.entries(sm.by_route || {})) {
      const store = STORE[route] || "refused";
      c.worker += n;
      if (store === "r2") { c.picture += n; c.reads_cacheable += n; }
      else if (store === "table") { c.table += n; c.reads_fixed += 2 * n; }
      else if (store === "manifest") c.manifest += n;
      else if (store === "worker") c.worker_store += n;
      else c.refused += n;
    }
    const miss = sm.counts.miss || 0;     // a miss read what it could and found nothing: move it from cacheable to fixed
    c.reads_cacheable = Math.max(0, c.reads_cacheable - miss); c.reads_fixed += miss;
  }
  return c;
}

const SUM_KEYS = ["minutes", "worker", "picture", "table", "manifest", "worker_store", "refused", "static", "reads_cacheable", "reads_fixed", "frames_bytes", "static_bytes"];

// per viewer-minute rates of the mix: sessions of one id pooled, then ids weighted
export function mixRates(counts, mix = {}) {
  const groups = {};
  for (const c of counts) {
    if (!(c.minutes > 0)) continue;
    const g = groups[c.id] || (groups[c.id] = { id: c.id, logs: 0, from: new Set() });
    g.logs++; g.from.add(c.from);
    for (const k of SUM_KEYS) g[k] = (g[k] || 0) + c[k];
  }
  const ids = Object.keys(groups).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  if (!ids.length) throw new Error("no session with a duration to rate");
  const weight = id => (Object.keys(mix).length ? (mix[id] || 0) : 1);
  const total = ids.reduce((a, id) => a + weight(id), 0);
  if (!(total > 0)) throw new Error(`--mix names none of the sessions in the logs (${ids.join(", ")})`);
  const per = {}, rate = {};
  for (const id of ids) {
    const g = groups[id];
    per[id] = { logs: g.logs, from: [...g.from].join("+"), minutes: g.minutes, weight: weight(id) / total };
    for (const k of SUM_KEYS) if (k !== "minutes") per[id][k] = g[k] / g.minutes;
  }
  for (const k of SUM_KEYS) if (k !== "minutes") rate[k] = ids.reduce((a, id) => a + per[id].weight * per[id][k], 0);
  return { per_session: per, rate };
}

// quantities and dollars for a number of viewer-hours. included: whether the plan's monthly allowances apply (a month)
export function price(rate, viewerHours, o = {}, P = PRICES) {
  const hit = o.edgeHit ?? 0.5, cpuMs = o.cpuMs ?? 1, isolates = o.isolates ?? 300, hours = o.wallHours ?? 0;
  const m = viewerHours * 60;
  const q = {
    worker_requests: rate.worker * m,
    cpu_ms: rate.worker * m * cpuMs,
    // the manifest: each isolate reads it at most once a minute, and never more often than requests arrive
    class_b: (rate.reads_cacheable * (1 - hit) + rate.reads_fixed) * m + (hours > 0 ? hours * Math.min(isolates * 60, rate.worker * m / hours) : 0),
    data_points: rate.worker * m,
    static_requests: rate.static * m,
    egress_gb: (rate.frames_bytes + rate.static_bytes) * m / 1e9,
  };
  const over = (n, free) => Math.max(0, n - (o.included ? free : 0));
  const usd = {
    worker_requests: over(q.worker_requests, P.workers.included_requests_month) * P.workers.per_million_requests / 1e6,
    cpu: over(q.cpu_ms, P.workers.included_cpu_ms_month) * P.workers.per_million_cpu_ms / 1e6,
    r2_class_b: over(q.class_b, P.r2.included_class_b_month) * P.r2.class_b_per_million / 1e6,
    analytics: over(q.data_points, P.analytics_engine.included_data_points_month) * P.analytics_engine.per_million_data_points / 1e6,
    pages: q.static_requests * P.pages.per_request,
    egress: q.egress_gb * P.r2.egress_per_gb,
  };
  if (o.included) {
    usd.plan = P.workers.plan_month;
    usd.storage = Math.max(0, (o.storageGb ?? 0) - P.r2.included_storage_gb) * P.r2.storage_gb_month;
  }
  usd.total = Object.values(usd).reduce((a, v) => a + v, 0);
  return { viewer_hours: viewerHours, quantities: q, usd };
}

// the whole model: rates, 1,000 viewers for an hour, months, one publish
export function model(counts, o = {}, P = PRICES) {
  const { per_session, rate } = mixRates(counts, o.mix || {});
  const viewers = o.viewers ?? 1000;
  const hour = price(rate, viewers, { ...o, wallHours: 1 }, P);
  const perViewerHour = price(rate, 1, { ...o, wallHours: 0 }, P);
  const sensitivity = Object.fromEntries([0, o.edgeHit ?? 0.5, 0.9].map(h => [String(h), price(rate, viewers, { ...o, edgeHit: h, wallHours: 1 }, P).usd.total]));
  const months = (o.months || [
    { name: "quiet month: 100 visits a day, 8 minutes each", viewer_hours: 100 * 30 * 8 / 60 },
    { name: "steady month: 1,000 visits a day, 8 minutes each", viewer_hours: 1000 * 30 * 8 / 60 },
    { name: "1,000 viewers at once, 4 hours every day", viewer_hours: 1000 * 4 * 30 },
    { name: "1,000 viewers at once, all month", viewer_hours: 1000 * 24 * 30 },
  ]).map(mo => ({ name: mo.name, ...price(rate, mo.viewer_hours, { ...o, included: true, wallHours: 24 * 30 }, P) }));
  const objects = o.objects ?? 5e6;
  const publish = { objects, class_a_usd: Math.max(0, objects - P.r2.included_class_a_month) * P.r2.class_a_per_million / 1e6 };
  return {
    when: new Date().toISOString(),
    assumptions: { edge_hit: o.edgeHit ?? 0.5, cpu_ms_per_request: o.cpuMs ?? 1, isolates: o.isolates ?? 300, storage_gb: o.storageGb ?? 0, viewers, mix: o.mix || "equal", prices_checked: P.checked, prices_extra_checked: P.checked_extra },
    per_viewer_minute: rate, per_session,
    worker_rps_at_viewers: rate.worker * viewers / 60,
    per_viewer_hour: perViewerHour,
    viewers_for_an_hour: hour,
    edge_hit_sensitivity_usd: sensitivity,
    months, publish,
  };
}

const f = (v, d = 2) => v === undefined || v === null ? "-" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

export function printModel(M, out = console.log) {
  out(`Per viewer-minute, by session (requests; reads are R2 Class B before the edge cache):`);
  out(`session  logs  minutes   worker  picture   table  static  reads(cacheable+fixed)  frames MB  static MB  weight`);
  for (const [id, s] of Object.entries(M.per_session))
    out(`${id.padEnd(7)} ${String(s.logs).padStart(5)} ${f(s.minutes, 1).padStart(8)} ${f(s.worker, 1).padStart(8)} ${f(s.picture, 1).padStart(8)} ${f(s.table, 1).padStart(7)} ${f(s.static, 1).padStart(7)} ${(f(s.reads_cacheable, 1) + " + " + f(s.reads_fixed, 1)).padStart(22)} ${f(s.frames_bytes / 1e6).padStart(10)} ${f(s.static_bytes / 1e6).padStart(10)} ${f(s.weight).padStart(7)}${s.from !== "log" ? "  (from " + s.from + ")" : ""}`);
  const r = M.per_viewer_minute;
  out(`mix     ${"".padStart(14)} ${f(r.worker, 1).padStart(8)} ${f(r.picture, 1).padStart(8)} ${f(r.table, 1).padStart(7)} ${f(r.static, 1).padStart(7)} ${(f(r.reads_cacheable, 1) + " + " + f(r.reads_fixed, 1)).padStart(22)} ${f(r.frames_bytes / 1e6).padStart(10)} ${f(r.static_bytes / 1e6).padStart(10)}`);
  const a = M.assumptions;
  out(`\nAssumptions: edge cache answers ${a.edge_hit * 100}% of pictures; ${a.cpu_ms_per_request} CPU ms a request; ${a.isolates} isolates; prices of ${a.prices_checked}${a.prices_extra_checked ? "" : " (CPU, Class A, Analytics Engine not rechecked)"}`);
  const h = M.viewers_for_an_hour, q = h.quantities;
  out(`\n${f(a.viewers, 0)} viewers for one hour (no monthly allowance): Worker ${f(M.worker_rps_at_viewers, 0)} req/s`);
  out(`  Worker requests ${f(q.worker_requests / 1e6, 2)} M  $${f(h.usd.worker_requests)}   CPU ${f(q.cpu_ms / 1e6, 2)} M ms  $${f(h.usd.cpu)}   R2 Class B ${f(q.class_b / 1e6, 2)} M  $${f(h.usd.r2_class_b)}   Analytics ${f(q.data_points / 1e6, 2)} M  $${f(h.usd.analytics)}`);
  out(`  Pages ${f(q.static_requests / 1e6, 2)} M requests $0   egress ${f(q.egress_gb, 1)} GB $0   total $${f(h.usd.total)}  ($${f(M.per_viewer_hour.usd.total, 4)} a viewer-hour)`);
  out(`  edge cache share 0 / ${a.edge_hit} / 0.9: $${Object.values(M.edge_hit_sensitivity_usd).map(v => f(v)).join(" / $")}`);
  out(`\nMonths (Workers Paid $5 with its allowances, storage ${a.storage_gb} GB):`);
  for (const mo of M.months) out(`  ${mo.name.padEnd(50)} ${f(mo.viewer_hours, 0).padStart(9)} viewer-hours  $${f(mo.usd.total)}  (Worker $${f(mo.usd.worker_requests)}, CPU $${f(mo.usd.cpu)}, R2 reads $${f(mo.usd.r2_class_b)}, Analytics $${f(mo.usd.analytics)}, storage $${f(mo.usd.storage)})`);
  out(`\nOne full publish: ${f(M.publish.objects / 1e6, 1)} M objects, Class A $${f(M.publish.class_a_usd)} once`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  const { flags, rest } = parseArgs(process.argv.slice(2));
  if (!rest.length) { console.error("give one or more harness logs (session .json files or zero_origin --out folders)"); process.exit(2); }
  const mix = flags.mix ? Object.fromEntries(flags.mix.split(",").map(p => p.split("=")).map(([k, v]) => [k.trim().toUpperCase(), +v])) : {};
  const P = flags.prices ? JSON.parse(fs.readFileSync(flags.prices, "utf8")) : PRICES;
  const sessions = (await readSessions(rest)).filter(s => !s.error || s.requests);
  const counts = await Promise.all(sessions.map(countSession));
  const M = model(counts, {
    mix, edgeHit: +(flags["edge-hit"] ?? 0.5), cpuMs: +(flags["cpu-ms"] ?? 1), isolates: +(flags.isolates ?? 300),
    storageGb: +(flags["storage-gb"] ?? 250), objects: +(flags.objects ?? 5e6), viewers: +(flags.viewers ?? 1000),
  }, P);
  printModel(M);
  if (flags.json) { fs.writeFileSync(flags.json, JSON.stringify({ ...M, sessions: counts }, null, 1)); console.log(`wrote ${flags.json}`); }
}
