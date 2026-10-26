// Movie-mode playback rate bench for Cassini OS: plays a stretch of the timeline in movie mode at FPS frames a second
// and reports how fast it really stepped (pictures a second), how long the steps waited for the camera windows, the
// 3D view's frame rate meanwhile, and where each picture's time went (the browser's queue for a connection, the
// frame server, the transfer), from the page's Resource Timing. Writes OUT.json; prints a summary line.
//   npm i playwright-core
//   node movie_rate.cjs URL FROM UNTIL OUT [FPS=24 W=1440 H=900 DPR=2]
//     URL    the page (the frame server serving Cassini OS, e.g. http://localhost:8790/)
//     FROM, UNTIL   the stretch, UTC (2006-09-15T14:30:00)
//   WARM=1      play the stretch once first in a browser of its own, so every picture the windows ask for is made
//               and in the frame server's cache before the timed run (which starts with an empty browser cache)
//   REPLAY=1    after the timed run, play the stretch again in the same browser (pictures from its own cache too)
//   CHANNEL=chrome  the installed Google Chrome (the Mac Mini); SOFTWARE=1 SwiftShader and THREE_DIR=.../three/package
//               for a cloud container; HEADED=1 shows the window; MAXSECS (default 600) caps each run
//   PRE='js'    runs in the page before each run (e.g. cassiniSettings.set("cameras.autoCenter", false))
let chromium;
try { ({ chromium } = require("playwright-core")); } catch (e) { ({ chromium } = require("playwright")); }
const fs = require("fs");
const [url, FROM, UNTIL, out, FPS = 24, W = 1440, H = 900, DPR = 2] = process.argv.slice(2);
const env = process.env, MAXSECS = +(env.MAXSECS || 600);

async function open(br) {
  const ctx = await br.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: +DPR });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  const u = new URL(url); u.searchParams.set("t", FROM); u.searchParams.set("play", "0"); u.searchParams.set("speed", "60");
  const t0 = Date.now();
  await page.goto(u.href);
  await page.waitForFunction("document.getElementById('loading').hidden && typeof catalog !== 'undefined' && catalog && catalog.byCam && window.cassiniMovie && window.cassiniFeeds", null, { timeout: 300000 });
  const loadMs = Date.now() - t0;
  await page.evaluate(fps => { cassiniSettings.set("movie.fps", fps); }, +FPS);
  if (env.PRE) await page.evaluate(env.PRE);
  await page.waitForTimeout(3000);   // the windows put up the pictures at the start
  return { ctx, page, loadMs };
}

// one movie-mode run over the stretch: records each step of the clock, each animation frame, each picture put up in a
// camera window and every request, until movie mode leaves at the stretch's end (or MAXSECS)
async function run(page, label, profile) {
  const cdp = profile ? await page.context().newCDPSession(page) : null;
  await page.evaluate(([from, until]) => {
    performance.setResourceTimingBufferSize(200000); performance.clearResourceTimings();
    const R = window.__rec = { steps: [], raf: [], shots: [], long: [], t0: performance.now(), from: utcToEt(from), until: utcToEt(until) };
    R.due = catalog.sorted.filter(t => t >= R.from && t <= R.until).length;
    let lastEt = state.et;
    const tick = t => { R.raf.push(t); if (state.et !== lastEt) { R.steps.push([t, state.et]); lastEt = state.et; } R.rid = requestAnimationFrame(tick); };
    R.rid = requestAnimationFrame(tick);
    for (const shot of document.querySelectorAll(".win .shot")) {
      const win = shot.closest(".win");
      new MutationObserver(() => R.shots.push([performance.now(), win.id || win.dataset.body || "", shot.src.slice(0, 160)])).observe(shot, { attributes: true, attributeFilter: ["src"] });
    }
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) R.long.push([e.startTime, e.duration]); }).observe({ type: "longtask", buffered: false }); } catch (e) {}
    cassiniMovie.start(true, { from: R.from, until: R.until });
  }, [FROM, UNTIL]);
  if (cdp) { await cdp.send("Profiler.enable"); await cdp.send("Profiler.setSamplingInterval", { interval: 1000 }); await cdp.send("Profiler.start"); }
  const t0 = Date.now();
  while (Date.now() - t0 < MAXSECS * 1000) {
    await page.waitForTimeout(500);
    if (!(await page.evaluate(() => cassiniMovie.on))) break;
  }
  const prof = cdp ? (await cdp.send("Profiler.stop")).profile : null;
  const r = await page.evaluate(label => {
    const R = window.__rec; cancelAnimationFrame(R.rid);
    const ended = !cassiniMovie.on; if (cassiniMovie.on) { cassiniMovie.stop(); setPlaying(false); }
    const q = (a, p) => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(s.length * p))].toFixed(1); };
    const iv = (a) => a.slice(1).map((t, i) => t - a[i]);
    const st = R.steps.map(s => s[0]), steps = st.length, span = steps > 1 ? st[steps - 1] - st[0] : 0;
    const stepIv = iv(st), rafIv = iv(R.raf.filter(t => !steps || (t >= st[0] && t <= st[steps - 1])));
    const nominal = 1000 / cassiniMovie.fps();
    // every picture request of the run, by what it asks for
    const kindOf = n => { const u = new URL(n); const p = u.pathname;
      if (p.startsWith("/frames/movie/")) return p.endsWith(".json") ? "movie.json" : u.searchParams.get("mode") === "rolling" ? "rolling" : "movie";
      if (p.startsWith("/frames/mosaic/")) return u.searchParams.get("warm") ? "mosaic.warm" : p.endsWith(".json") ? "mosaic.json" : "mosaic";
      if (p === "/frames/color.webp") return u.searchParams.get("channel") ? "color.channel" : "color";
      if (p.startsWith("/frames/processed/")) return "processed";
      if (p.startsWith("/frames/")) return "frame";
      if (p.startsWith("/data/")) return "data";
      return null; };
    const res = performance.getEntriesByType("resource").map(e => ({ kind: kindOf(e.name), e })).filter(x => x.kind);
    const by = {};
    for (const { kind, e } of res) {
      const b = by[kind] = by[kind] || { n: 0, fromCache: 0, bytes: 0, dur: [], ttfb: [], queue: [], recv: [] };
      b.n++; b.bytes += e.encodedBodySize || 0;
      if (e.transferSize === 0 && e.decodedBodySize > 0) { b.fromCache++; continue; }
      b.dur.push(e.duration); if (e.requestStart > 0) { b.queue.push(e.requestStart - e.startTime); b.ttfb.push(e.responseStart - e.requestStart); b.recv.push(e.responseEnd - e.responseStart); }
    }
    const kinds = Object.fromEntries(Object.entries(by).map(([k, b]) => [k, { n: b.n, fromBrowserCache: b.fromCache, kb: Math.round(b.bytes / 1024),
      durP50: q(b.dur, .5), durP95: q(b.dur, .95), durMax: q(b.dur, 1), serverP50: q(b.ttfb, .5), serverP95: q(b.ttfb, .95), serverMax: q(b.ttfb, 1),
      queueP50: q(b.queue, .5), queueP95: q(b.queue, .95), recvP95: q(b.recv, .95) }]));
    // requests in flight at once (picture routes), its peak and mean over the run
    const ev = []; for (const { e } of res) { ev.push([e.startTime, 1], [e.responseEnd, -1]); }
    ev.sort((a, b) => a[0] - b[0] || a[1] - b[1]); let cur = 0, peak = 0, area = 0, prev = ev.length ? ev[0][0] : 0;
    for (const [t, d] of ev) { area += cur * (t - prev); prev = t; cur += d; peak = Math.max(peak, cur); }
    const longMs = R.long.filter(([t]) => !steps || (t >= st[0] && t <= st[steps - 1])).reduce((a, [, d]) => a + d, 0);
    return { label, ended, utcEnd: new Date(etToMs(state.et)).toISOString(), fps: cassiniMovie.fps(),
      picturesDue: R.due, steps, seconds: +(span / 1000).toFixed(2),
      stepsPerSecond: span ? +((steps - 1) / span * 1000).toFixed(2) : 0,
      stepMsP50: q(stepIv, .5), stepMsP90: q(stepIv, .9), stepMsP99: q(stepIv, .99), stepMsMax: q(stepIv, 1),
      // the share of the run spent past each step's due time (waiting for a window's picture), and the steps that waited
      waitShare: span ? +(stepIv.reduce((a, d) => a + Math.max(0, d - nominal - 17), 0) / span).toFixed(3) : 0,
      stepsLate: stepIv.filter(d => d > nominal + 50).length,
      rafFps: rafIv.length ? +(1000 * rafIv.length / rafIv.reduce((a, b) => a + b, 0)).toFixed(1) : null, rafMsP95: q(rafIv, .95), rafMsMax: q(rafIv, 1),
      longTaskMsPerSecond: span ? +(longMs / span * 1000).toFixed(1) : 0,
      requests: res.length, inFlightPeak: peak, inFlightMean: ev.length ? +(area / (prev - ev[0][0] || 1)).toFixed(2) : 0,
      shots: R.shots.length, kinds,
      urls: res.filter(x => !/^(data|mosaic\.warm)$/.test(x.kind)).map(x => [Math.round(x.e.startTime - R.t0), x.kind, x.e.name.replace(location.origin, ""), Math.round(x.e.duration), x.e.transferSize === 0 ? "cache" : Math.round(x.e.responseStart - x.e.requestStart)]),
      stepTimes: st.map(t => Math.round(t - R.t0)), shotLog: R.shots.map(([t, w, s]) => [Math.round(t - R.t0), w, s.replace(location.origin, "")]) };
  }, label);
  if (prof) {
    const self = {}, byId = {}; for (const nd of prof.nodes) byId[nd.id] = nd;
    prof.samples.forEach((id, i) => { const c = byId[id].callFrame, k = `${c.functionName || "(anonymous)"}:${c.lineNumber + 1}`; self[k] = (self[k] || 0) + (prof.timeDeltas[i] || 0) / 1000; });
    const total = Object.values(self).reduce((a, b) => a + b, 0);
    r.mainThreadMsPerSecond = Object.entries(self).filter(([k]) => !/^\((idle|program|garbage collector)\)/.test(k)).sort((a, b) => b[1] - a[1]).slice(0, 20)
      .map(([k, v]) => [k, +(v / Math.max(1, r.seconds)).toFixed(1)]);
    r.idleShare = +((self["(idle):0"] || 0) / Math.max(1, total)).toFixed(3);
  }
  const k = r.kinds, line = Object.entries(k).filter(([n]) => n !== "data").map(([n, b]) => `${n} ${b.n}${b.fromBrowserCache ? ` (${b.fromBrowserCache} cached)` : ""} server p50/p95 ${b.serverP50}/${b.serverP95} ms queue p95 ${b.queueP95}`).join("; ");
  console.log(`${label}: ${r.steps}/${r.picturesDue} steps in ${r.seconds} s = ${r.stepsPerSecond}/s at ${r.fps} fps asked; step p50/p90/max ${r.stepMsP50}/${r.stepMsP90}/${r.stepMsMax} ms; waiting ${Math.round(r.waitShare * 100)}%; 3D ${r.rafFps} fps (p95 ${r.rafMsP95} ms); long tasks ${r.longTaskMsPerSecond} ms/s; requests ${r.requests}, in flight peak ${r.inFlightPeak}\n   ${line}`);
  return r;
}

(async () => {
  const args = ["--ignore-gpu-blocklist", "--enable-precise-memory-info"];
  if (env.SOFTWARE) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, headless: !env.HEADED, args });
  const result = { url, from: FROM, until: UNTIL, viewport: [+W, +H, +DPR], runs: [] };
  if (env.WARM) {
    const w = await open(br);
    result.runs.push(await run(w.page, "warm-up (makes what is missing)", false));
    await w.ctx.close();
  }
  const m = await open(br);
  result.loadMs = m.loadMs;
  result.runs.push(await run(m.page, "timed (server cache, empty browser cache)", true));
  if (env.REPLAY) {
    await m.page.evaluate(from => { setPlaying(false); setTime(utcToEt(from)); }, FROM);
    await m.page.waitForTimeout(3000);
    result.runs.push(await run(m.page, "replay (browser cache too)", false));
  }
  await m.page.screenshot({ path: `${out}.png` });
  fs.writeFileSync(`${out}.json`, JSON.stringify(result, null, 1));
  await br.close();
})();
