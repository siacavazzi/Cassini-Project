// Normal playback bench for Cassini OS: plays a stretch of the timeline at SPEED mission seconds a second (not movie
// mode) and reports how fast the clock really ran, how much of the time it was held back while a camera window caught
// up on pictures (playback.maxBehind: "catching up on pictures") or slowed in an imaging burst (playback.maxImageRate,
// the burst limit, which is by design), how many frames behind the windows' pictures were, how many pictures each
// window put up, and where each picture's time went (the browser's queue for a connection, the frame server, the
// transfer), from the page's Resource Timing. Writes OUT.json; prints a summary line.
//   npm i playwright-core
//   node play_rate.cjs URL FROM UNTIL OUT [SPEED=600 W=1440 H=900 DPR=2]
//     URL    the page (the frame server serving Cassini OS, e.g. http://localhost:8790/)
//     FROM, UNTIL   the stretch, UTC (2006-09-15T14:30:00)
//   WARM=1      play the stretch once first in a browser of its own, so every picture is made before the timed run
//   REPLAY=1    after the timed run, play the stretch again in the same browser (pictures from its own cache too)
//   CHANNEL=chrome  the installed Google Chrome (the Mac Mini); SOFTWARE=1 SwiftShader and THREE_DIR=.../three/package
//               for a cloud container; HEADED=1 shows the window; MAXSECS (default 300) caps each run
//   PRE='js'    runs in the page before each run (e.g. cassiniSettings.set("playback.maxImageRate", 0))
//   VIDEO=OUT.webm  records the timed run's page (W x H) to that file; OUT.json's videoStartS is where in it the run starts
//   NET=ms,down,up  the link to the server as Chrome emulates it: ms latency added to each request, down and up
//               Mbit/s (NET=20,100,50 a home Wi-Fi; NET=80,30,10 Tailscale away from home)
//   NOTE_DELAY=ms  holds each look-ahead note (/frames/mosaic/<id>.webp?warm=1) that long, as a server busy working
//               out a pass would: the windows must not ask a pass's mosaic before the note says what the pass is
let chromium;
try { ({ chromium } = require("playwright-core")); } catch (e) { ({ chromium } = require("playwright")); }
const fs = require("fs");
const [url, FROM, UNTIL, out, SPEED = 600, W = 1440, H = 900, DPR = 2] = process.argv.slice(2);
const env = process.env, MAXSECS = +(env.MAXSECS || 300);

async function open(br, video) {
  const ctx = await br.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: +DPR,
    ...(video ? { recordVideo: { dir: require("os").tmpdir(), size: { width: +W, height: +H } } } : {}) });
  ctx.openedAt = Date.now();
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (env.NOTE_DELAY) await page.route(/\/frames\/mosaic\/[^?]*\?warm=1/, r => setTimeout(() => r.continue().catch(() => {}), +env.NOTE_DELAY));
  if (env.NET) {
    const [ms, down, up] = env.NET.split(",").map(Number), cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: ms || 0,
      downloadThroughput: down ? down * 125000 : -1, uploadThroughput: up ? up * 125000 : -1 });
  }
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  const u = new URL(url); u.searchParams.set("t", FROM); u.searchParams.set("play", "0"); u.searchParams.set("speed", String(SPEED));
  const t0 = Date.now();
  await page.goto(u.href);
  await page.waitForFunction("document.getElementById('loading').hidden && typeof catalog !== 'undefined' && catalog && catalog.byCam && window.cassiniFeeds", null, { timeout: 300000 });
  const loadMs = Date.now() - t0;
  if (env.PRE) await page.evaluate(env.PRE);
  await page.waitForTimeout(3000);   // the windows put up the pictures at the start
  return { ctx, page, loadMs };
}

// one run over the stretch at SPEED: records the clock and the windows' state every animation frame, each picture put
// up in a camera window and every request, until the clock passes UNTIL (or MAXSECS)
async function run(page, label) {
  await page.evaluate(([from, until, speed]) => {
    performance.setResourceTimingBufferSize(200000); performance.clearResourceTimings();
    setPlaying(false); setTime(utcToEt(from)); keepNowInView(); setSpeed(speed);
    const R = window.__rec = { frames: [], shots: [], long: [], t0: performance.now(), from: utcToEt(from), until: utcToEt(until), speed };
    R.due = catalog.sorted.filter(t => t >= R.from && t <= R.until).length;
    const tick = t => {
      const hud = (document.getElementById("mday") || {}).textContent || "";
      const m = hud.match(/catching up on pictures, (\d+)% speed/);
      // [time, mission time, frames behind (the furthest window), paced share (1 = full speed), burst-slowed]
      R.frames.push([t, state.et, window.cassiniFeeds.behind(), m ? +m[1] / 100 : 1, /imaging burst/.test(hud) ? 1 : 0]);
      if (state.et >= R.until) setPlaying(false);
      R.rid = requestAnimationFrame(tick);
    };
    R.rid = requestAnimationFrame(tick);
    for (const shot of document.querySelectorAll(".win .shot")) {
      const win = shot.closest(".win");
      new MutationObserver(() => R.shots.push([performance.now(), win.id || win.dataset.body || "", shot.src.slice(0, 160)])).observe(shot, { attributes: true, attributeFilter: ["src"] });
    }
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) R.long.push([e.startTime, e.duration]); }).observe({ type: "longtask", buffered: false }); } catch (e) {}
    setPlaying(true);
  }, [FROM, UNTIL, +SPEED]);
  const t0 = Date.now(), videoStartS = (t0 - page.context().openedAt) / 1000;
  while (Date.now() - t0 < MAXSECS * 1000) {
    await page.waitForTimeout(500);
    if (!(await page.evaluate(() => state.playing))) break;
  }
  const r = await page.evaluate(label => {
    const R = window.__rec; cancelAnimationFrame(R.rid);
    const ended = state.et >= R.until; setPlaying(false);
    const q = (a, p) => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(s.length * p))].toFixed(1); };
    const fr = R.frames.filter(f => f[1] >= R.from);
    const span = fr.length > 1 ? fr[fr.length - 1][0] - fr[0][0] : 0, mission = fr.length > 1 ? fr[fr.length - 1][1] - fr[0][1] : 0;
    // the share of the run's wall time spent caught up (paced below 1) or slowed by a burst, frame by frame
    let pacedMs = 0, burstMs = 0, pacedArea = 0;
    for (let i = 1; i < fr.length; i++) { const d = fr[i][0] - fr[i - 1][0]; if (fr[i][3] < 1) { pacedMs += d; pacedArea += d * (1 - fr[i][3]); } if (fr[i][4]) burstMs += d; }
    const behind = fr.map(f => f[2]);
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
    const ev = []; for (const { e } of res) { if (e.transferSize === 0 && e.decodedBodySize > 0) continue; ev.push([e.startTime, 1], [e.responseEnd, -1]); }
    ev.sort((a, b) => a[0] - b[0] || a[1] - b[1]); let cur = 0, peak = 0, area = 0, prev = ev.length ? ev[0][0] : 0;
    for (const [t, d] of ev) { area += cur * (t - prev); prev = t; cur += d; peak = Math.max(peak, cur); }
    const t1 = fr.length ? fr[0][0] : 0, t2 = fr.length ? fr[fr.length - 1][0] : 0;
    const longMs = R.long.filter(([t]) => t >= t1 && t <= t2).reduce((a, [, d]) => a + d, 0);
    const rafIv = fr.slice(1).map((f, i) => f[0] - fr[i][0]);
    const shotsBy = {}; for (const [t, w] of R.shots) if (t >= t1 && t <= t2) shotsBy[w] = (shotsBy[w] || 0) + 1;
    return { label, ended, utcEnd: new Date(etToMs(state.et)).toISOString(), speedAsked: R.speed, picturesDue: R.due,
      seconds: +(span / 1000).toFixed(2), missionSeconds: Math.round(mission),
      // the speed the clock really ran at over the stretch, and the share of the asked speed
      speedReal: span ? Math.round(mission / span * 1000) : 0, speedShare: span ? +(mission / span * 1000 / R.speed).toFixed(3) : 0,
      // the share of the wall time the clock was held back to let a window catch up (and the speed it lost to it), and
      // the share in an imaging burst (the burst limit)
      catchingUpShare: span ? +(pacedMs / span).toFixed(3) : 0, catchingUpLoss: span ? +(pacedArea / span).toFixed(3) : 0,
      burstShare: span ? +(burstMs / span).toFixed(3) : 0,
      behindP50: q(behind, .5), behindP90: q(behind, .9), behindP99: q(behind, .99), behindMax: q(behind, 1),
      rafFps: rafIv.length ? +(1000 * rafIv.length / rafIv.reduce((a, b) => a + b, 0)).toFixed(1) : null, rafMsP95: q(rafIv, .95), rafMsMax: q(rafIv, 1),
      longTaskMsPerSecond: span ? +(longMs / span * 1000).toFixed(1) : 0,
      requests: res.length, inFlightPeak: peak, inFlightMean: ev.length ? +(area / (prev - ev[0][0] || 1)).toFixed(2) : 0,
      shots: shotsBy, kinds,
      urls: res.filter(x => !/^(data|mosaic\.warm)$/.test(x.kind)).map(x => [Math.round(x.e.startTime - R.t0), x.kind, x.e.name.replace(location.origin, ""), Math.round(x.e.duration),
        x.e.transferSize === 0 ? "cache" : Math.round(x.e.responseStart - x.e.requestStart), Math.round(x.e.requestStart > 0 ? x.e.requestStart - x.e.startTime : -1)]),
      // the clock every tenth of a second: [ms from the start, mission time, behind, paced, burst]
      timeline: fr.filter((f, i) => i === 0 || Math.floor(f[0] / 100) !== Math.floor(fr[i - 1][0] / 100)).map(f => [Math.round(f[0] - R.t0), Math.round(f[1] - R.from), f[2], f[3], f[4]]),
      shotLog: R.shots.map(([t, w, s]) => [Math.round(t - R.t0), w, s.replace(location.origin, "")]) };
  }, label);
  r.videoStartS = +videoStartS.toFixed(2);
  const k = r.kinds, line = Object.entries(k).filter(([n]) => n !== "data").map(([n, b]) => `${n} ${b.n}${b.fromBrowserCache ? ` (${b.fromBrowserCache} cached)` : ""} server p50/p95 ${b.serverP50}/${b.serverP95} ms queue p95 ${b.queueP95}`).join("; ");
  console.log(`${label}: ${r.missionSeconds} mission s in ${r.seconds} s = ${r.speedReal} s/s (${Math.round(r.speedShare * 100)}% of ${r.speedAsked}); catching up ${Math.round(r.catchingUpShare * 100)}% of the time (speed lost ${Math.round(r.catchingUpLoss * 100)}%); burst-slowed ${Math.round(r.burstShare * 100)}%; behind p50/p90/max ${r.behindP50}/${r.behindP90}/${r.behindMax}; 3D ${r.rafFps} fps; long tasks ${r.longTaskMsPerSecond} ms/s; requests ${r.requests}, in flight peak ${r.inFlightPeak} mean ${r.inFlightMean}; shots ${JSON.stringify(r.shots)}\n   ${line}`);
  return r;
}

(async () => {
  const args = ["--ignore-gpu-blocklist", "--enable-precise-memory-info"];
  if (env.SOFTWARE) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, headless: !env.HEADED, args });
  const result = { url, net: env.NET || null, from: FROM, until: UNTIL, speed: +SPEED, viewport: [+W, +H, +DPR], runs: [] };
  if (env.WARM) {
    const w = await open(br);
    result.runs.push(await run(w.page, "warm-up (makes what is missing)"));
    await w.ctx.close();
  }
  const m = await open(br, env.VIDEO);
  result.loadMs = m.loadMs;
  result.runs.push(await run(m.page, "timed (server cache, empty browser cache)"));
  if (env.REPLAY) result.runs.push(await run(m.page, "replay (browser cache too)"));
  await m.page.screenshot({ path: `${out}.png` });
  fs.writeFileSync(`${out}.json`, JSON.stringify(result, null, 1));
  if (env.VIDEO) { await m.ctx.close(); await m.page.video().saveAs(env.VIDEO); }
  await br.close();
})();
