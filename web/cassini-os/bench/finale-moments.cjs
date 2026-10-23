// Records the two hardest moments of the Grand Finale (?finale) frame by frame, on a virtual clock so the video keeps
// the cutscene's real pace however slowly the machine renders: loss of signal (the dish lost and the tumble) and the cut
// to Saturn where Cassini burns up. For before/after evidence.
//   npm i playwright-core
//   node finale-moments.cjs URL OUT [WIDTH HEIGHT]     (URL with ?finale; writes OUT.mp4 and OUT_<second>.png stills)
//   SOFTWARE=1      SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
//   FROM='text'     start recording when a caption with this text shows (default: "It keeps sending", 11 s before LOS)
//   SECONDS=24      how long to record; FPS=30; STILLS=10,12.5,14  seconds into the recording to keep as stills
// Needs ffmpeg on the PATH.
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [url, out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, FROM = env.FROM || "It keeps sending", SECS = +(env.SECONDS || 24), FPS = +(env.FPS || 30);
const STILLS = (env.STILLS || "").split(",").filter(Boolean).map(Number);
(async () => {
  const args = ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ executablePath: env.EXE || undefined, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
    r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (env.THREE_DIR) await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  // a clock the recorder drives: once started, time moves only when a frame is stepped
  await page.addInitScript(() => {
    try { localStorage.clear(); } catch (e) {}
    const realNow = performance.now.bind(performance), realRaf = window.requestAnimationFrame.bind(window);
    let manual = false, vnow = 0, q = [];
    performance.now = () => manual ? vnow : realNow();
    window.requestAnimationFrame = cb => manual ? (q.push(cb), 1) : realRaf(t => manual ? q.push(cb) : cb(t));
    window.__vc = { start() { vnow = realNow(); manual = true; }, step(ms) { vnow += ms; const c = q; q = []; c.forEach(f => f(vnow)); return c.length; } };
  });
  await page.goto(url);
  await page.waitForFunction(() => window.cassiniFinale && cassiniFinale.running, null, { timeout: 600000, polling: 500 });
  await page.evaluate(() => __vc.start());
  const caps = () => page.evaluate(() => [...document.querySelectorAll("#finale .fx-cap, #finale .cs-cap")].map(e => e.textContent).join(" | "));
  // fast forward in 100 ms frames (the viewer's longest step) until the line shows
  for (let i = 0; !(await caps()).includes(FROM); i++) {
    await page.evaluate(() => { for (let k = 0; k < 5; k++) __vc.step(100); });
    if (i > 3000) throw new Error("never saw " + FROM);
  }
  const dir = fs.mkdtempSync(`${out}_frames_`), n = Math.round(SECS * FPS);
  for (let i = 0; i < n; i++) {
    await page.evaluate(ms => __vc.step(ms), 1000 / FPS);
    const p = path.join(dir, `${String(i).padStart(6, "0")}.jpg`);
    await page.screenshot({ path: p, type: "jpeg", quality: 88 });
    for (const s of STILLS) if (i === Math.round(s * FPS)) fs.copyFileSync(p, `${out}_${s}.jpg`);
    if (i % 60 === 0) console.log(`${(i / FPS).toFixed(1)} s`, await caps());
  }
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(dir, "%06d.jpg"),
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", `${out}.mp4`]);
  fs.rmSync(dir, { recursive: true });
  await br.close();
})().catch(e => { console.error(e); process.exit(1); });
