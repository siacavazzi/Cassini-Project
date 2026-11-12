// The zero-origin harness (public site, WP0): loads a build of Cassini OS, runs the scripted visitor sessions S1 to S9
// (harness/sessions/), records every request each makes and counts, per session, what the public site's gates count
// (docs/public-site/README.md, Gates):
//   origin    requests a viewer's browser would send to an origin, which must be 0 on the public site: in --mode before,
//             every request to the frame server (the Mini serves them today); in --mode public, any request to a host
//             that is neither the site (Pages) nor the frames host (the Worker) nor an allowed CDN
//   refused   frames-host requests policy.json refuses (keys.mjs canonical): must be 0
//   miss      frames-host requests policy.json allows that answered 404 or worse (Auto center's marker 404s, with an
//             X-Center header, are counted apart as marker): must be 0. A request the page cancelled itself
//             (net::ERR_ABORTED: a picture it no longer wants as playback moves on) is no miss; it is counted
//             apart as cancelled
//   cdn       requests to the CDNs listed in --cdn (three.js, fonts): reported, so WP6 can bring them onto Pages
//
//   node web/public/harness/zero_origin.mjs --site http://127.0.0.1:8955 [--frames URL] [--mode before|public]
//        [--sessions S1,S3] [--minutes 3] [--out DIR] [--channel chrome] [--three DIR] [--headed]
//
// --site      the page (a frame server with --site, a static copy, or Pages); --frames the frames host when it is not
//             the site (passed to the page as ?frames=); --minutes how long the playing sessions play (S1, S2, S8: the
//             plan says three minutes; shorter for a smoke run); --out writes <out>/<session>.json with every request
//             and summary.json; --channel chrome uses Google Chrome (the Mini's page bench), else Playwright's Chromium.
// Exit status 0 when every session ran; the counts are the result (a "before" run is expected to count origins).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "../keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : "1"]);
  return acc;
}, []));
const site = (args.site || "").replace(/\/$/, "");
if (!site) { console.error("--site URL is needed"); process.exit(2); }
const frames = (args.frames || site).replace(/\/$/, "");
const mode = args.mode || "before";
const minutes = +(args.minutes || 3);
const CDN = (args.cdn || "cdn.jsdelivr.net,fonts.googleapis.com,fonts.gstatic.com").split(",").filter(Boolean);
const K = await loadKeys();

const { chromium } = await import("playwright");
const sessionFiles = fs.readdirSync(path.join(here, "sessions")).filter(f => /^s\d+\.mjs$/.test(f)).sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)));
const want = args.sessions ? new Set(args.sessions.split(",").map(s => s.trim().toUpperCase())) : null;
const sessions = [];
for (const f of sessionFiles) {
  const s = (await import(path.join(here, "sessions", f))).default;
  if (!want || want.has(s.id)) sessions.push(s);
}

// routes whose 404 is an answer the page expects (policy.json probe_404), counted apart from misses
const PROBE = new Set(JSON.parse(fs.readFileSync(path.join(here, "..", "policy.json"), "utf8")).routes.filter(r => r.probe_404).map(r => r.id));
// the headers a log keeps: the reports (x-*) and the type
const keep = hd => Object.fromEntries(Object.entries(hd || {}).filter(([k]) => /^x-|^content-type$/.test(k)));
const hostOf = u => { try { return new URL(u).host; } catch (e) { return ""; } };
const siteHost = hostOf(site), framesHost = hostOf(frames);

// one request's class, from its URL, method, status and headers
function classify(r) {
  const u = new URL(r.url);
  if (u.protocol === "data:" || u.protocol === "blob:") return { cls: "inline" };
  const host = u.host;
  const onFrames = host === framesHost;
  const ans = onFrames || host === siteHost ? K.canonical(r.method, u.pathname + u.search) : null;
  const isFramesRoute = ans && ans.route !== null || (ans && /^\/(frames|reel|export|prebuild|flags|stats|jumplog|usage|health|version\.json)/.test(u.pathname));
  if (onFrames && (isFramesRoute || framesHost !== siteHost)) {
    const out = { cls: "frames", route: ans.route, store: ans.store, refused: ans.refused };
    out.origin = mode === "before";
    if (ans.refused) out.verdict = "refused";
    else if (r.status === 404 && r.headers["x-center"]) out.verdict = "marker";
    else if (r.pending) out.verdict = "pending";
    else if (r.status === 404 && ans.route && PROBE.has(ans.route)) out.verdict = "probe";
    else if (r.failed === "net::ERR_ABORTED") out.verdict = "cancelled";
    else if (r.failed || r.status >= 400 || r.status === 0) out.verdict = "miss";
    else out.verdict = "ok";
    return out;
  }
  if (host === siteHost) return { cls: "static" };
  if (CDN.includes(host)) return { cls: "cdn" };
  return { cls: "other", origin: true };
}

function summarize(reqs) {
  const c = { requests: reqs.length, static: 0, frames: 0, origin: 0, refused: 0, miss: 0, marker: 0, probe: 0, cancelled: 0, pending: 0, cdn: 0, other_hosts: 0, bytes: 0 };
  const byRoute = {}, refusedWhy = {}, missRoutes = {}, otherHosts = {};
  for (const r of reqs) {
    const k = r.k;
    c.bytes += r.bytes || 0;
    if (k.cls === "static") c.static++;
    if (k.cls === "cdn") c.cdn++;
    if (k.cls === "other") { c.other_hosts++; otherHosts[hostOf(r.url)] = (otherHosts[hostOf(r.url)] || 0) + 1; }
    if (k.origin) c.origin++;
    if (k.cls === "frames") {
      c.frames++;
      byRoute[k.route || "(no route)"] = (byRoute[k.route || "(no route)"] || 0) + 1;
      if (k.verdict === "refused") { c.refused++; refusedWhy[k.refused] = (refusedWhy[k.refused] || 0) + 1; }
      if (k.verdict === "miss") { c.miss++; missRoutes[k.route || "(no route)"] = (missRoutes[k.route || "(no route)"] || 0) + 1; }
      if (k.verdict === "marker") c.marker++;
      if (k.verdict === "probe") c.probe++;
      if (k.verdict === "cancelled") c.cancelled++;
      if (k.verdict === "pending") c.pending++;
    }
  }
  return { counts: c, by_route: byRoute, refused_why: refusedWhy, miss_routes: missRoutes, other_hosts: otherHosts };
}

const launch = { args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"], headless: !args.headed };
if (args.channel) launch.channel = args.channel;
const browser = await chromium.launch(launch);
const results = [];
for (const s of sessions) {
  const ctx = await browser.newContext(s.context || { viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const reqs = [], live = new Map(), steps = [];
  if (args.three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${args.three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  page.on("request", q => live.set(q, { url: q.url(), method: q.method(), type: q.resourceType(), t: Date.now() }));
  page.on("requestfinished", async q => {
    const r = live.get(q); if (!r) return; live.delete(q);
    try { const res = await q.response(); r.status = res ? res.status() : 0; r.headers = res ? await res.allHeaders() : {}; r.bytes = (await q.sizes()).responseBodySize; } catch (e) { r.status = r.status || 0; }
    r.headers = keep(r.headers);
    reqs.push(r);
  });
  // an answer whose body the page never reads (a 404 it only checks .ok of) has no requestfinished: its status and
  // headers are kept when they come, so the request is counted, and idle() does not wait on it
  page.on("response", async res => {
    const r = live.get(res.request()); if (!r) return; r.status = res.status(); r.answered = true;
    let all = {}; try { all = await res.allHeaders(); } catch (e) {}
    if (live.get(res.request()) === r) r.headers = keep(all);   // (requestfinished may have taken it meanwhile)
  });
  page.on("requestfailed", q => { const r = live.get(q); if (!r) return; live.delete(q); r.failed = q.failure() ? q.failure().errorText : "failed"; r.status = 0; reqs.push(r); });
  const h = {
    site, frames, minutes, page, ctx, browser,
    // the page's address for a moment (CLAUDE.md "Showing Sam a moment"), with ?frames= when the frames host is not the site
    url(q) {
      const p = new URLSearchParams(q);
      if (frames !== site) p.set("frames", frames);
      return `${site}/?${p.toString()}`;
    },
    async open(q, timeout = 240000) {
      await page.goto(h.url(q));
      await page.waitForFunction(() => document.getElementById("loading") && document.getElementById("loading").hidden && typeof state !== "undefined", null, { timeout });
      h.step(`opened ${new URLSearchParams(q).toString()}`);
    },
    wait: ms => page.waitForTimeout(ms),
    // until no request has been in flight for `quiet` ms (at most `cap` ms): a step's pictures asked and answered
    async idle(quiet = 400, cap = 8000) {
      const end = Date.now() + cap; let since = Date.now();
      while (Date.now() < end) { await page.waitForTimeout(100); if ([...live.values()].some(r => !r.answered)) since = Date.now(); else if (Date.now() - since >= quiet) return true; }
      if (process.env.HARNESS_DEBUG_IDLE) console.log("still live:", [...live.values()].filter(r => !r.answered).map(r => `${Math.round((Date.now() - r.t) / 1000)}s ${r.type} ${r.url.slice(0, 140)}`).join("\n  "));
      return false;
    },
    step: text => steps.push({ t: Date.now(), text }),
    skip: (text, owner) => steps.push({ t: Date.now(), skipped: true, text, owner }),
    // the first of these moments inside what the cache holds (/frames/slices.json spans; null: the whole mission)
    async moment(list) {
      const sl = await page.evaluate(async f => { try { const r = await fetch(`${f}/frames/slices.json`, { cache: "no-store" }); return r.ok ? r.json() : null; } catch (e) { return null; } }, frames).catch(() => null);
      const spans = sl && sl.spans;
      if (!spans) return list[0];
      const inside = t => spans.some(([a, b]) => t >= a && t < b);
      return list.find(m => inside(m.t)) || { ...list[0], t: spans[0][0], note: "no listed moment is in the cache; the first span's start" };
    }
  };
  const t0 = Date.now();
  let error = null;
  // a blank page first, on the site's origin, so moment() can ask the frames host before the session opens a moment
  try { await page.goto(`${site}/robots.txt`).catch(() => {}); await s.run(h); } catch (e) { error = String(e && e.stack || e).slice(0, 2000); }
  await page.waitForTimeout(1500);
  // still in flight at the end: answered but never read (counted from its answer), or never answered at all (counted
  // as pending, so a hung picture shows in the counts rather than being left out)
  for (const r of live.values()) { if (r.answered) r.unread = true; else { r.pending = true; r.status = 0; } r.headers = keep(r.headers); reqs.push(r); }
  live.clear();
  for (const r of reqs) r.k = classify(r);
  const sum = summarize(reqs);
  const out = { session: s.id, title: s.title, proves: s.proves, mode, site, frames, seconds: Math.round((Date.now() - t0) / 1000), error, steps, ...sum };
  results.push(out);
  if (args.out) {
    fs.mkdirSync(args.out, { recursive: true });
    fs.writeFileSync(path.join(args.out, `${s.id}.json`), JSON.stringify({ ...out, requests: reqs }, null, 1));
  }
  const c = sum.counts;
  console.log(`${s.id.padEnd(3)} ${String(c.requests).padStart(6)} req  origin ${String(c.origin).padStart(5)}  refused ${String(c.refused).padStart(5)}  miss ${String(c.miss).padStart(4)}  marker ${String(c.marker).padStart(4)}  probe ${String(c.probe).padStart(4)}  cancelled ${String(c.cancelled).padStart(4)}  pending ${String(c.pending).padStart(3)}  cdn ${String(c.cdn).padStart(3)}  other ${String(c.other_hosts).padStart(3)}  ${(c.bytes / 1e6).toFixed(1)} MB  ${out.seconds}s${error ? "  ERROR " + error.split("\n")[0] : ""}${steps.some(x => x.skipped) ? "  (" + steps.filter(x => x.skipped).length + " steps skipped)" : ""}`);
  await ctx.close();
}
await browser.close();
if (args.out) fs.writeFileSync(path.join(args.out, "summary.json"), JSON.stringify({ mode, site, frames, minutes, when: new Date().toISOString(), sessions: results }, null, 1));
process.exit(results.every(r => !r.error) ? 0 : 1);
