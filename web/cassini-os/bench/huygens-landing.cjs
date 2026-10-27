// Records the Huygens landing cutscene (?huygens-landing) from start to the return to the mission, on a hand-stepped
// clock (smooth however slowly the page renders), as an MP4 plus a log of the readout and captions. For evidence.
//   npm i playwright-core
//   node huygens-landing.cjs URL OUT [WIDTH HEIGHT]   (URL with ?huygens-landing; OUT is a prefix: OUT.mp4, OUT.json)
//   SOFTWARE=1     SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
//   FPS=30         frames per second of the video (each one stepped by hand and screenshotted)
//   STRIDE=n       keep only every nth frame as a still in OUT_frames/ (a quick contact sheet instead of a video)
//   FROM=s TO=s    only the screen seconds between these (the clock still runs from the start)
// Needs ffmpeg on the PATH.
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [url, out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, FPS = +env.FPS || 30, STRIDE = +env.STRIDE || 1, FROM = +env.FROM || 0, TO = +env.TO || 1e9;
(async () => {
  const args = ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ executablePath: env.EXE || undefined, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  page.on("console", m => { if (m.type() === "error") console.log("console", m.text().slice(0, 200)); });
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
    r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  await page.addInitScript(() => {
    const realNow = performance.now.bind(performance), rRAF = window.requestAnimationFrame.bind(window), q = [];
    let virt = false, vt = 0;
    performance.now = () => virt ? vt : realNow();
    window.requestAnimationFrame = cb => { if (!virt) return rRAF(cb); q.push(cb); return q.length; };
    window.__virtStart = () => { vt = realNow(); virt = true; };
    window.__step = ms => { vt += ms; q.splice(0).forEach(cb => cb(vt)); };
  });
  await page.goto(url);
  await page.waitForFunction(() => window.cassiniHuygensLanding && cassiniHuygensLanding.running, null, { timeout: 600000, polling: 500 });
  console.log("numbers", JSON.stringify(await page.evaluate(() => cassiniHuygensLanding.numbers)));
  const dir = `${out}_frames`; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  await page.evaluate(() => window.__virtStart());
  const log = [];
  let n = 0, kept = 0, endAt = 0, lastLog = -1;
  for (;;) {
    await page.evaluate(ms => window.__step(ms), 1000 / FPS);
    const s = await page.evaluate(() => ({ running: cassiniHuygensLanding.running, T: cassiniHuygensLanding.T }));
    const T = s.T == null ? -1 : s.T;
    if (T >= FROM && T <= TO && n % STRIDE === 0) {
      await page.screenshot({ path: path.join(dir, `${String(kept++).padStart(6, "0")}.jpg`), type: "jpeg", quality: 88 });
    }
    if (Math.floor(T) !== lastLog && T >= 0) {
      lastLog = Math.floor(T);
      const r = await page.evaluate(() => ({ et: state.et, focus: state.focus, read: document.querySelector("#hland .cs-read").textContent,
        caps: [...document.querySelectorAll("#hland .cs-cap")].map(e => e.textContent).join(" | ") }));
      log.push({ T: lastLog, ...r });
      if (lastLog % 4 === 0) console.log(lastLog, r.focus, r.read, "|", r.caps.slice(0, 90));
    }
    n++;
    if (!s.running && !endAt) endAt = n + 2 * FPS;
    if ((endAt && n >= endAt) || T > TO) break;
  }
  fs.writeFileSync(`${out}.json`, JSON.stringify(log, null, 1));
  if (STRIDE === 1) {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(dir, "%06d.jpg"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", `${out}.mp4`]);
    fs.rmSync(dir, { recursive: true });
  }
  await br.close();
})();
