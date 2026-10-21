// Frame-rate bench for Cassini OS: opens the page in Chromium, lets it play for SECS seconds of real time and reports
// frame intervals (uncapped: vsync and the 60 fps limit are off), the CPU time of each step of the render loop,
// draw calls, and the GPU it ran on. Writes OUT.json and OUT.png.
//   npm i playwright-core
//   node fps.js URL OUT [WIDTH HEIGHT DPR SECS]
//   CHANNEL=chrome  use the installed Google Chrome (real GPU on a Mac); default is Playwright's Chromium
//   HEADED=1        show the window
//   SOFTWARE=1      SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
//   VSYNC=1         keep the display's frame cap (60 fps), as a person sees it
//   PRE='js'        runs in the page before measuring (e.g. cassiniSettings.set(...))
const { chromium } = require("playwright-core");
const fs = require("fs");
const [url, out, W = 1440, H = 900, DPR = 2, SECS = 10] = process.argv.slice(2);
const env = process.env;
(async () => {
  const args = ["--ignore-gpu-blocklist", "--enable-precise-memory-info"];
  if (!env.VSYNC) args.push("--disable-gpu-vsync", "--disable-frame-rate-limit");
  if (env.SOFTWARE) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, headless: !env.HEADED, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: +DPR });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
    r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (env.THREE_DIR) await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  const t0 = Date.now();
  await page.goto(url);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 300000 });
  const loadMs = Date.now() - t0;
  if (env.PRE) await page.evaluate(env.PRE);
  await page.waitForTimeout(4000);
  const cdp = await ctx.newCDPSession(page);
  await page.evaluate(() => {
    const T = window.__T = {}, wrap = (obj, k) => { const f = obj && obj[k]; if (typeof f !== "function") return;
      obj[k] = function () { const a = performance.now(); try { return f.apply(this, arguments); } finally { T[k] = (T[k] || 0) + performance.now() - a; } }; };
    for (const k of ["frame", "updateBodies", "updateTrail", "updateOrbits", "updateLabels", "updateHud", "drawTimeline", "updateFocusRow",
                     "updateProbeTrail", "studyAfterRender", "studyHud", "studyBeforeHud"]) wrap(window, k);
    T.render = 0; const r0 = renderer.render; renderer.render = function () { const a = performance.now(); r0.apply(this, arguments); T.render += performance.now() - a; };
    for (const [proto, k] of [[CanvasRenderingContext2D.prototype, "getImageData"], [CanvasRenderingContext2D.prototype, "drawImage"], [CanvasRenderingContext2D.prototype, "putImageData"]]) {
      const f = proto[k], name = "2d." + k; T[name + ".calls"] = 0;
      proto[k] = function () { const a = performance.now(); try { return f.apply(this, arguments); } finally { T[name] = (T[name] || 0) + performance.now() - a; T[name + ".calls"]++; } };
    }
    // camera windows: each picture put up, and how far the clock had gone past its frame's time by then
    window.__shots = []; window.__et0 = state.et; const idx = new Map(); catalog.id.forEach((id, k) => idx.set(id, k));
    document.querySelectorAll(".camwin").forEach(card => { const shot = card.querySelector(".shot"); if (!shot) return;
      new MutationObserver(() => { const m = shot.src.match(/ids=([^&]+)/), ids = m ? decodeURIComponent(m[1]).split(",") : [(shot.src.split("/frames/")[1] || "").split(".")[0]]; const ks = ids.map(i => idx.get(i)).filter(k => k !== undefined); if (ks.length) window.__shots.push(state.et - Math.max(...ks.map(k => catalog.et[k]))); })
        .observe(shot, { attributes: true, attributeFilter: ["src"] }); });
    window.__iv = []; window.__t0 = performance.now(); let last = 0; const tick = t => { if (last) window.__iv.push(t - last); last = t; window.__rid = requestAnimationFrame(tick); }; requestAnimationFrame(tick);
  });
  await cdp.send("Profiler.enable"); await cdp.send("Profiler.setSamplingInterval", { interval: 500 }); await cdp.send("Profiler.start");
  await page.waitForTimeout(SECS * 1000);
  const { profile } = await cdp.send("Profiler.stop");
  const r = await page.evaluate(() => {
    cancelAnimationFrame(window.__rid);
    const iv = window.__iv.slice().sort((a, b) => a - b), n = iv.length, sum = iv.reduce((a, b) => a + b, 0);
    const gl = renderer.getContext(), dbg = gl.getExtension("WEBGL_debug_renderer_info");
    return { gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      frames: n, fps: +(1000 * n / sum).toFixed(1), p50ms: +iv[n >> 1].toFixed(1), p95ms: +iv[Math.floor(n * 0.95)].toFixed(1), maxms: +iv[n - 1].toFixed(1),
      cpuMsPerFrame: Object.fromEntries(Object.entries(window.__T).map(([k, v]) => [k, +(v / n).toFixed(2)]).sort((a, b) => b[1] - a[1])),
      drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles, textures: renderer.info.memory.textures,
      pictures: (() => { const L = window.__shots.slice().sort((a, b) => a - b), sim = state.et - window.__et0, due = catalog.et.filter(t => t > window.__et0 && t <= state.et).length;
        return { due, shown: L.length, missionSecondsPerSecond: +(sim / (performance.now() - window.__t0) * 1000).toFixed(1),
                 lagMissionSecondsP50: L.length ? Math.round(L[L.length >> 1]) : null, lagMissionSecondsP90: L.length ? Math.round(L[Math.floor(L.length * 0.9)]) : null }; })(),
      canvas: [renderer.domElement.width, renderer.domElement.height], heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null,
      quality: window.cassiniPerf ? window.cassiniPerf.status() : null, scalePath: window.__q || null, utc: new Date(etToMs(state.et)).toISOString() };
  });
  const self = {}, byId = {}; for (const nd of profile.nodes) byId[nd.id] = nd;
  profile.samples.forEach((id, i) => { const c = byId[id].callFrame, k = `${c.functionName || "(anonymous)"}:${c.lineNumber + 1}`; self[k] = (self[k] || 0) + (profile.timeDeltas[i] || 0) / 1000; });
  r.mainThreadTop = Object.entries(self).sort((a, b) => b[1] - a[1]).slice(0, 15).map(([k, v]) => [k, +(v / r.frames).toFixed(2)]);
  Object.assign(r, { url, viewport: [+W, +H, +DPR], seconds: +SECS, loadMs });
  fs.writeFileSync(`${out}.json`, JSON.stringify(r, null, 1));
  console.log(JSON.stringify(r));
  await page.screenshot({ path: `${out}.png` });
  await br.close();
})();
