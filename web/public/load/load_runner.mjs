// The gate G3 load runner (public site, WP10a): replays zero-origin harness logs as N simulated viewers (default 100)
// against the rehearsal rig's Worker and reports errors and picture times (the plan's G3: "100 simulated viewers with
// no errors and their p95 picture time reported").
//
//   node web/public/load/load_runner.mjs --frames http://HOST:8915 [--site http://HOST:8916] [--viewers 100]
//        [--ramp 60] [--speedup 1] [--minutes M] [--per-host 6] [--timeout 30] [--out DIR] [--keep-requests] LOG...
//
// LOG       harness logs: <session>.json files or zero_origin.mjs --out folders. Viewer i plays log i mod n.
// --frames  the frames host (the Worker); --site the page's host, when its static requests should be replayed too
//           (Pages costs nothing per request, so the default replays only what the Worker answers)
// --ramp    seconds over which the viewers arrive, evenly (default 60)
// --speedup plays each log this many times faster than it was recorded (1: as recorded; a smoke run uses more)
// --minutes keeps each viewer replaying its log from the start until this many minutes have passed (default: once)
// --per-host requests one viewer has open to one host at once (a browser's 6 on HTTP/1.1)
// --out     writes DIR/load.json (summary, per-second timeline) and, with --keep-requests, DIR/requests.ndjson
//
// Each request's answer is judged against the status the harness logged for it: the same status is ok (a probe's or
// a marker's 404, a refusal's 404 or 405 included); a network error, a timeout or a 5xx is an error; a logged answer
// that is now 404 is a miss; any other change is "changed". G3 passes when errors + misses + changes are 0.
// Picture time is from sending the request to its last byte; "wait" is time queued behind the per-host limit.
//
// Load only ever goes to this computer, the home network or the tailnet (replay.mjs checkTarget), and only to a frames
// host whose /health says it is the Worker running locally (checkWorker: X-Site-Env local, not through Cloudflare's
// edge, so not `wrangler dev --remote`): a public service, Cloudflare staging or production included, is refused. Exit status 0 when G3 passes, 1 when it does not, 2 for bad
// arguments or a refused target.
import fs from "node:fs";
import path from "node:path";
import { monitorEventLoopDelay } from "node:perf_hooks";
import { readSessions, percentile, checkTarget, checkWorker, parseArgs } from "./replay.mjs";

const sleep = ms => new Promise(r => setTimeout(r, Math.max(0, ms)));

// a counting semaphore: one per viewer per host
function limiter(n) {
  let free = n; const waiting = [];
  return {
    async take() { if (free > 0) { free--; return; } await new Promise(r => waiting.push(r)); },
    give() { const next = waiting.shift(); if (next) next(); else free++; },
  };
}

// the outcome of one answer against the logged one
export function judge(logged, status, err) {
  if (err) return "error";
  if (status >= 500) return "error";
  if (!logged) return "unjudged";
  if (status === logged) return "ok";
  if (status === 304 && logged === 200) return "ok";
  if (status === 404 && logged >= 200 && logged < 400) return "miss";
  return "changed";
}

async function ask(base, r, timeoutMs) {
  const t0 = performance.now();
  let ttfb = null, bytes = 0, status = 0, err = null;
  try {
    const res = await fetch(base + r.path, { method: r.method, redirect: "manual", signal: AbortSignal.timeout(timeoutMs), headers: { "User-Agent": "cassini-load/1 (G3 rehearsal)" } });
    status = res.status;
    ttfb = performance.now() - t0;
    if (res.body) for await (const chunk of res.body) bytes += chunk.byteLength;
  } catch (e) {
    err = e && e.name === "TimeoutError" ? `timeout after ${timeoutMs / 1000} s` : String((e && e.cause && e.cause.code) || (e && e.message) || e);
  }
  return { status, ttfb, ms: performance.now() - t0, bytes, err };
}

// runs the load; returns {summary, results}
export async function runLoad(opts) {
  const { sessions, frames, site = null, viewers = 100, ramp = 60, speedup = 1, minutes = 0, perHost = 6, timeout = 30, log = () => {} } = opts;
  const playable = sessions.filter(s => s.requests && s.requests.some(r => r.method === "GET" || r.method === "HEAD"));
  if (!playable.length) throw new Error("no session log with GET requests to replay (summary.json files hold counts only)");
  const bases = { frames, site };
  const results = [];
  const skipped = { other_methods: 0, static_without_site: 0 };
  const lag = monitorEventLoopDelay({ resolution: 20 }); lag.enable();
  const start = performance.now();
  const until = minutes > 0 ? start + minutes * 60000 : Infinity;
  let open = 0, peakOpen = 0;

  async function viewer(i) {
    const s = playable[i % playable.length];
    const reqs = s.requests.filter(r => {
      if (r.method !== "GET" && r.method !== "HEAD") { skipped.other_methods++; return false; }
      if (r.host === "site" && !site) { skipped.static_without_site++; return false; }
      return true;
    });
    const lim = { frames: limiter(perHost), site: limiter(perHost) };
    const arrive = start + (viewers > 1 ? (ramp * 1000 * i) / viewers : 0);
    const span = reqs.length ? reqs[reqs.length - 1].offset / speedup : 0;
    const inflight = [];
    for (let lap = 0; ; lap++) {
      const lapStart = arrive + lap * (span + 1000);
      if (lap > 0 && lapStart >= until) break;
      for (const r of reqs) {
        const due = lapStart + r.offset / speedup;
        if (due >= until) break;
        await sleep(due - performance.now());
        inflight.push((async () => {
          const l = lim[r.host];
          const q0 = performance.now();
          await l.take();
          const wait = performance.now() - q0;
          open++; peakOpen = Math.max(peakOpen, open);
          let a;
          try { a = await ask(bases[r.host], r, timeout * 1000); } finally { open--; l.give(); }
          const outcome = judge(r.status, a.status, a.err);
          results.push({ viewer: i, session: s.id, lap, cls: r.cls, route: r.route, path: r.path, logged: r.status, status: a.status, ms: a.ms, ttfb: a.ttfb, wait, bytes: a.bytes, outcome, err: a.err, at: (performance.now() - start) / 1000 });
        })());
      }
      if (minutes <= 0) break;
    }
    await Promise.all(inflight);
  }

  const tick = setInterval(() => log(`\r${Math.round((performance.now() - start) / 1000)} s  ${results.length} answers  ${open} open  ${results.filter(r => r.outcome !== "ok" && r.outcome !== "unjudged").length} not ok   `), 1000);
  try { await Promise.all(Array.from({ length: viewers }, (_, i) => viewer(i))); } finally { clearInterval(tick); lag.disable(); }
  log("\n");
  const seconds = (performance.now() - start) / 1000;
  return { summary: summarize(results, { frames, site, viewers, ramp, speedup, minutes, perHost, timeout, seconds, sessions: playable.map(s => s.id), skipped, peakOpen, lagP95: lag.percentile(95) / 1e6 }), results };
}

const round = (v, d = 1) => v === null || v === undefined ? null : Math.round(v * 10 ** d) / 10 ** d;

export function summarize(results, run) {
  const count = (rs, o) => rs.filter(r => r.outcome === o).length;
  const block = rs => {
    const ok = rs.filter(r => !r.err);
    const ms = ok.map(r => r.ms), tt = ok.map(r => r.ttfb);
    return {
      requests: rs.length, ok: count(rs, "ok"), error: count(rs, "error"), miss: count(rs, "miss"), changed: count(rs, "changed"), unjudged: count(rs, "unjudged"),
      p50_ms: round(percentile(ms, 50)), p95_ms: round(percentile(ms, 95)), p99_ms: round(percentile(ms, 99)), max_ms: round(percentile(ms, 100)),
      ttfb_p50_ms: round(percentile(tt, 50)), ttfb_p95_ms: round(percentile(tt, 95)), wait_p95_ms: round(percentile(rs.map(r => r.wait), 95)),
      bytes: rs.reduce((a, r) => a + r.bytes, 0),
    };
  };
  const byClass = {};
  for (const c of [...new Set(results.map(r => r.cls))].sort()) byClass[c] = block(results.filter(r => r.cls === c));
  const all = block(results);
  const bad = all.error + all.miss + all.changed;
  // per-second timeline: answers, MB and the picture p95 of the answers finished in that second
  const secs = Math.ceil(run.seconds) || 1, timeline = [];
  for (let s = 0; s < secs; s++) timeline.push({ s, answers: 0, bytes: 0, bad: 0, ms: [] });
  for (const r of results) {
    const b = timeline[Math.min(secs - 1, Math.floor(r.at))];
    b.answers++; b.bytes += r.bytes;
    if (r.outcome !== "ok" && r.outcome !== "unjudged") b.bad++;
    if (r.cls === "picture" && !r.err) b.ms.push(r.ms);
  }
  const tl = timeline.map(b => ({ s: b.s, answers: b.answers, mb: round(b.bytes / 1e6, 2), bad: b.bad, picture_p95_ms: round(percentile(b.ms, 95)) }));
  const errs = {};
  for (const r of results) if (r.outcome !== "ok" && r.outcome !== "unjudged") {
    const k = `${r.outcome} ${r.err || r.status} (logged ${r.logged}) ${r.route || r.cls}`;
    (errs[k] = errs[k] || { n: 0, example: r.path }).n++;
  }
  const busy = tl.filter(b => b.answers);
  return {
    when: new Date().toISOString(),
    target: { frames: run.frames, site: run.site },
    run: { viewers: run.viewers, ramp_s: run.ramp, speedup: run.speedup, minutes: run.minutes || null, per_host: run.perHost, timeout_s: run.timeout, seconds: round(run.seconds), sessions: run.sessions, skipped: run.skipped, peak_open: run.peakOpen },
    gate: { errors: bad, pass: bad === 0 && all.requests > 0, picture_p95_ms: byClass.picture ? byClass.picture.p95_ms : null, picture_p50_ms: byClass.picture ? byClass.picture.p50_ms : null },
    all, by_class: byClass,
    throughput: { mean_rps: round(all.requests / (run.seconds || 1)), peak_rps: Math.max(0, ...tl.map(b => b.answers)), mean_mbps: round(all.bytes * 8 / 1e6 / (run.seconds || 1)), peak_mbps: round(Math.max(0, ...tl.map(b => b.mb)) * 8) },
    runner: { loop_lag_p95_ms: round(run.lagP95), warning: run.lagP95 > 50 ? "the runner's own event loop lagged (p95 over 50 ms): its times are pessimistic; run fewer viewers per process" : null, busy_seconds: busy.length },
    not_ok: Object.entries(errs).sort((a, b) => b[1].n - a[1].n).slice(0, 30).map(([what, v]) => ({ what, n: v.n, example: v.example })),
    timeline: tl,
  };
}

export function printSummary(s, out = console.log) {
  const pad = (v, n) => String(v ?? "-").padStart(n);
  out(`${s.run.viewers} viewers on ${s.target.frames}${s.target.site ? " + " + s.target.site : ""}, ${s.run.seconds} s, sessions ${[...new Set(s.run.sessions)].join(",")}, speedup ${s.run.speedup}`);
  out(`class        requests   error  miss changed     p50     p95     p99     max  ttfb95  wait95       MB`);
  for (const [c, b] of [...Object.entries(s.by_class), ["all", s.all]])
    out(`${c.padEnd(10)} ${pad(b.requests, 10)} ${pad(b.error, 7)} ${pad(b.miss, 5)} ${pad(b.changed, 7)} ${pad(b.p50_ms, 7)} ${pad(b.p95_ms, 7)} ${pad(b.p99_ms, 7)} ${pad(b.max_ms, 7)} ${pad(b.ttfb_p95_ms, 7)} ${pad(b.wait_p95_ms, 7)} ${pad((b.bytes / 1e6).toFixed(1), 8)}`);
  out(`throughput: mean ${s.throughput.mean_rps} req/s, peak ${s.throughput.peak_rps} req/s, mean ${s.throughput.mean_mbps} Mbit/s, peak ${s.throughput.peak_mbps} Mbit/s; runner loop lag p95 ${s.runner.loop_lag_p95_ms} ms`);
  if (s.runner.warning) out(`WARNING ${s.runner.warning}`);
  for (const e of s.not_ok.slice(0, 10)) out(`  ${String(e.n).padStart(6)} x ${e.what}  e.g. ${e.example}`);
  out(`G3: ${s.gate.pass ? "PASS" : "FAIL"}, ${s.gate.errors} errors; picture p50 ${s.gate.picture_p50_ms} ms, p95 ${s.gate.picture_p95_ms} ms`);
}

// ---- command line ---------------------------------------------------------------------------------------------------
const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname);
if (isMain) {
  const { flags, rest } = parseArgs(process.argv.slice(2), ["keep-requests"]);
  const fail = m => { console.error(m); process.exit(2); };
  if (!flags.frames) fail("--frames URL (the rehearsal Worker) is needed");
  if (!rest.length) fail("give one or more harness logs (session .json files or zero_origin --out folders)");
  let frames, site = null;
  try { frames = await checkWorker(await checkTarget(flags.frames)); if (flags.site) site = await checkTarget(flags.site); } catch (e) { fail(e.message); }
  const sessions = await readSessions(rest);
  const { summary, results } = await runLoad({
    sessions, frames, site,
    viewers: +(flags.viewers || 100), ramp: +(flags.ramp ?? 60), speedup: +(flags.speedup || 1), minutes: +(flags.minutes || 0),
    perHost: +(flags["per-host"] || 6), timeout: +(flags.timeout || 30), log: m => process.stderr.write(m),
  });
  printSummary(summary);
  if (flags.out) {
    fs.mkdirSync(flags.out, { recursive: true });
    fs.writeFileSync(path.join(flags.out, "load.json"), JSON.stringify(summary, null, 1));
    if (flags["keep-requests"]) fs.writeFileSync(path.join(flags.out, "requests.ndjson"), results.map(r => JSON.stringify(r)).join("\n") + "\n");
    console.log(`wrote ${path.join(flags.out, "load.json")}`);
  }
  process.exit(summary.gate.pass ? 0 : 1);
}
