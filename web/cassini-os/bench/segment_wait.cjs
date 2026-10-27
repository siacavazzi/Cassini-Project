// Times the wait after Pre-process, as the page shows it: opens the page at FROM (paused), lets the camera windows
// settle, highlights FROM..UNTIL on the timeline with the mouse (a real drag, as a person does; MODE=mark uses
// cassiniExport.mark instead), waits HOLD ms (the pointer moving to the button), presses Pre-process and records
// every line the bar says (#segstate) with when it said it, the POST /prebuild's own timing (Resource Timing: how
// long it waited for a connection, for the server's answer, in all), the page's requests to the frame server still
// out when it was pressed and those the highlight started, and (FRAME_SERVER_SAMPLE=1 on the server) what the
// server's threads did while the page waited. RUNS stretches, each SHIFT s later than the last (the same stretch
// asked again is the same job, answered as made).
//   npm i playwright-core
//   node segment_wait.cjs URL FROM UNTIL OUT        writes OUT.json, prints one line per run
//   CHANNEL=chrome (the installed Google Chrome, the Mac Mini), WAIT=8000 ms after the page is up, HOLD=1500 ms
//   between the highlight and the press, RUNS=3, SHIFT=60 s, MODE=drag|mark, PLAY=1 (the clock playing when it is
//   pressed), MAXSECS=120 for each stretch, W=1440 H=900 DPR=2, PRE='js' run in the page before the first highlight
//   (PRE='cassiniMovie.start(true)': movie mode playing), NET=ms,down,up the link as Chrome emulates it (NET=20,100,50
//   a home Wi-Fi, NET=80,30,10 Tailscale away from home; play_rate.cjs)
let chromium;
try { ({ chromium } = require("playwright-core")); } catch (e) { ({ chromium } = require("playwright")); }
const fs = require("fs");
const [url, FROM, UNTIL, out] = process.argv.slice(2);
const env = process.env, W = +(env.W || 1440), H = +(env.H || 900), DPR = +(env.DPR || 2);
const WAIT = +(env.WAIT || 8000), HOLD = +(env.HOLD || 1500), RUNS = +(env.RUNS || 3), SHIFT = +(env.SHIFT || 60);
const MODE = env.MODE || "drag", MAXSECS = +(env.MAXSECS || 120);
const iso = s => new Date(s * 1000).toISOString().slice(0, 19);
const secs = s => Date.parse(s + "Z") / 1000;
const now = () => performance.now();

(async () => {
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, headless: !env.HEADED, args });
  const ctx = await br.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DPR });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
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
  const origin = new URL(url).origin;
  // every request to the frame server, by when it went out and came back (this script's clock)
  const reqs = [];
  const byReq = new Map();
  page.on("request", r => { if (r.url().startsWith(origin)) { const e = { m: r.method(), u: r.url().slice(origin.length), t0: now(), t1: null, s: null }; reqs.push(e); byReq.set(r, e); } });
  page.on("requestfinished", async r => { const e = byReq.get(r); if (!e) return; e.t1 = now(); try { const x = await r.response(); e.s = x && x.status(); } catch (err) {} });
  page.on("requestfailed", r => { const e = byReq.get(r); if (e) { e.t1 = now(); e.s = "failed"; } });
  const samples = async () => { try { const r = await fetch(`${origin}/debug/samples`); return r.ok ? await r.text() : null; } catch (e) { return null; } };
  // the samples taken while the page waited for the POST's answer, read as soon as it comes
  let postSamples = null;
  page.on("response", async r => { if (r.request().method() === "POST" && /\/prebuild\?/.test(r.url())) postSamples = await samples(); });

  const u = new URL(url); u.searchParams.set("t", FROM); u.searchParams.set("play", env.PLAY ? "1" : "0");
  await page.goto(u.href);
  await page.waitForFunction("document.getElementById('loading').hidden && typeof catalog !== 'undefined' && catalog && catalog.byCam && window.cassiniFeeds && window.cassiniExport && window.cassiniSegment", null, { timeout: 300000 });
  await page.evaluate(() => cassiniSettings.set("interface.autohide", false));
  if (env.PRE) await page.evaluate(env.PRE);
  await page.waitForTimeout(WAIT);

  const runs = [];
  for (let k = 0; k < RUNS; k++) {
    const A = iso(secs(FROM) + k * SHIFT), B = iso(secs(UNTIL) + k * SHIFT);
    // the last stretch let go (its ×), as a person does before highlighting another
    await page.evaluate(() => { if (!document.getElementById("segbar").hidden) document.getElementById("segx").click(); });
    await page.waitForTimeout(300);
    const marked = now();
    if (MODE === "drag") {
      // the timeline shows the stretch across its middle; a press in its lanes, dragged from one end to the other
      const box = await page.evaluate(([a, b]) => {
        const ea = utcToEt(a), eb = utcToEt(b), pad = (eb - ea) * 0.4;
        state.tlFollow = false; state.view = [ea - pad, eb + pad]; drawTimeline();
        const r = document.getElementById("tl").getBoundingClientRect();
        return { left: r.left, top: r.top, w: r.width, h: r.height, xa: etToX(ea, r.width), xb: etToX(eb, r.width) };
      }, [A, B]);
      const y = box.top + Math.max(24, box.h * 0.65);
      await page.mouse.move(box.left + box.xa, y);
      await page.mouse.down();
      for (let i = 1; i <= 12; i++) { await page.mouse.move(box.left + box.xa + (box.xb - box.xa) * i / 12, y); await page.waitForTimeout(16); }
      await page.mouse.up();
    }
    // (a drag that did not reach the timeline, something over it: the marks as the drag would set them)
    if (MODE !== "drag" || !(await page.waitForFunction("!document.getElementById('segbar').hidden", null, { timeout: 3000 }).then(() => true, () => false))) {
      if (MODE === "drag") console.log("  (the drag did not highlight the stretch; marked instead)");
      await page.evaluate(([a, b]) => cassiniExport.mark(utcToEt(a), utcToEt(b), "new"), [A, B]);
    }
    await page.waitForFunction("!document.getElementById('segbar').hidden", null, { timeout: 10000 });
    const ends = await page.evaluate(() => { const P = cassiniSegment.state; return [new Date(etToMs(P.a)).toISOString().slice(0, 19), new Date(etToMs(P.b)).toISOString().slice(0, 19)]; });
    await page.waitForTimeout(HOLD);
    await samples();   // (from here on)
    postSamples = null;
    await page.evaluate(() => {
      const el = document.getElementById("segstate");
      window.__seg = { t0: null, log: [] };
      const note = () => { const t = el.textContent; const L = window.__seg.log; if (!L.length || L[L.length - 1][1] !== t) L.push([performance.now(), t]); };
      if (window.__segObs) window.__segObs.disconnect();
      window.__segObs = new MutationObserver(note); window.__segObs.observe(el, { childList: true, characterData: true, subtree: true });
      document.getElementById("segprep").addEventListener("click", () => { window.__seg.t0 = performance.now(); }, { capture: true, once: true });
    });
    const box = await page.evaluate(() => { const r = document.getElementById("segprep").getBoundingClientRect(); return r.width ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null; });
    const pressed = now();
    if (box) await page.mouse.click(box.x, box.y); else await page.evaluate(() => document.getElementById("segprep").click());
    let job = null;
    while ((now() - pressed) / 1000 < MAXSECS) {
      await page.waitForTimeout(50);
      job = await page.evaluate(() => { const j = cassiniSegment.state.job; return j && { id: j.id, state: j.state, done: j.done, total: j.total, took: j.took, errors: j.errors }; });
      if (job && /^(done|failed|stopped)$/.test(job.state)) break;
    }
    await page.waitForTimeout(200);
    const got = await page.evaluate(() => {
      const t0 = window.__seg.t0, rel = t => +(t - t0).toFixed(1);
      const post = performance.getEntriesByType("resource").filter(e => /\/prebuild\?/.test(e.name) && e.startTime >= t0 - 5).pop();
      return { t0, log: window.__seg.log.map(([t, s]) => [rel(t), s]),
        post: post && { start: rel(post.startTime), queued: +(post.requestStart - post.startTime).toFixed(1), connect: +(post.connectEnd - post.connectStart).toFixed(1),
          server: +(post.responseStart - post.requestStart).toFixed(1), total: +(post.responseEnd - post.startTime).toFixed(1) } };
    });
    // the bar's lines, each with how long it stayed
    const lines = got.log.map(([t, s], i) => ({ at: t, for: got.log[i + 1] ? +(got.log[i + 1][0] - t).toFixed(1) : null, says: s }));
    const asking = lines.find(l => /^Asking the frame server/.test(l.says));
    const first = lines.find(l => /^(Pre-processing [1-9]|Ready)/.test(l.says));
    const ready = lines.find(l => /^Ready/.test(l.says));
    const out1 = (e, t) => ({ m: e.m, u: e.u.slice(0, 140), age: +(t - e.t0).toFixed(0), left: e.t1 == null ? null : +(e.t1 - t).toFixed(0), s: e.s });
    const outAtPress = reqs.filter(e => e.t0 < pressed && (e.t1 == null || e.t1 > pressed)).map(e => out1(e, pressed));
    const sinceMark = reqs.filter(e => e.t0 >= marked && e.t0 < pressed).map(e => ({ m: e.m, u: e.u.slice(0, 140), at: +(e.t0 - pressed).toFixed(0), took: e.t1 == null ? null : +(e.t1 - e.t0).toFixed(0), s: e.s }));
    const r = { stretch: ends, job, post: got.post, asking: asking ? asking.for : null, first: first ? first.at : null, ready: ready ? ready.at : null,
      lines, outAtPress, sinceMark, postSamples, samplesAfter: await samples() };
    runs.push(r);
    // the requests out at the press, by route (a picture, a pass's mosaic, a look-ahead note, ...) and how much longer each took
    const route = e => e.u.replace(/\?.*/, "").replace(/[NW]\d{10}_\d+(_[NW]\d{10}_\d+)*/g, "ID").replace(/[0-9a-f]{16}/g, "JOB") + (/[?&]warm=1/.test(e.u) ? "?warm" : "");
    const routes = {};
    for (const e of outAtPress) { const k2 = `${e.m} ${route(e)}`; (routes[k2] = routes[k2] || []).push(e.left); }
    r.outByRoute = routes;
    console.log(`run ${k + 1} ${ends[0]}..${ends[1]}: asking ${r.asking} ms (POST queued ${got.post ? got.post.queued : "?"} + server ${got.post ? got.post.server : "?"} ms, ${outAtPress.length} requests out at the press), ` +
      `first picture shown done ${r.first} ms, ready ${r.ready} ms; ${job ? `${job.state} ${job.done}/${job.total}, server took ${job.took != null ? job.took.toFixed(2) : "?"} s` : "no job"}\n` +
      lines.map(l => `     ${String(l.at).padStart(8)} ms  ${String(l.for).padStart(8)} ms  ${l.says}`).join("\n") +
      Object.entries(routes).map(([k2, v]) => `\n     out at the press: ${v.length} x ${k2}, done ${v.map(x => x == null ? "never" : `${x} ms`).join(", ")} after it`).join(""));
  }
  fs.writeFileSync(`${out}.json`, JSON.stringify({ url, from: FROM, until: UNTIL, mode: MODE, hold: HOLD, wait: WAIT, play: !!env.PLAY, net: env.NET || null, pre: env.PRE || null, runs }, null, 1));
  await br.close();
})();
