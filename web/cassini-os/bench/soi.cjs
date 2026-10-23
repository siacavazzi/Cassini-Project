// Records the Saturn arrival cutscene (?soi) from start to the return to the mission, as an MP4 made from the page's
// own screencast, with stills at each moment. For before/after evidence.
//   npm i playwright-core
//   node soi.cjs URL OUT [WIDTH HEIGHT]      (URL with ?soi; OUT is a prefix: OUT.mp4, OUT_*.png, OUT.json)
//   CHANNEL=chrome  use the installed Google Chrome; default is Playwright's Chromium (EXE=path for another one)
//   SOFTWARE=1      SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
//   STILLS_ONLY=1   no video, stills only
//   VIRTUAL=30      a smooth video however slowly the page renders (software GL): the page's clock and animation frames
//                   are stepped by hand, 30 a second, and each frame is a screenshot (slow, but every frame is there)
//   STRIDE=n        with VIRTUAL, keep only every nth frame (a quick contact sheet instead of a video)
// Needs ffmpeg on the PATH.
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [url, out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, T0 = Date.now(), t = () => +((Date.now() - T0) / 1000).toFixed(1);
(async () => {
  const args = ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log(t(), "PAGEERROR", e.message));
  page.on("console", m => { if (m.type() === "error" || m.type() === "warning") console.log(t(), "console", m.type(), m.text().slice(0, 200)); });
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
    r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (env.THREE_DIR) await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  // the hand-stepped clock for VIRTUAL: performance.now and requestAnimationFrame, once __virtStart() is called
  await page.addInitScript(() => {
    const realNow = performance.now.bind(performance), rRAF = window.requestAnimationFrame.bind(window), q = [];
    let virt = false, vt = 0;
    performance.now = () => virt ? vt : realNow();
    window.requestAnimationFrame = cb => { if (!virt) return rRAF(cb); q.push(cb); return q.length; };
    window.__virtStart = () => { vt = realNow(); virt = true; };
    window.__step = ms => { vt += ms; q.splice(0).forEach(cb => cb(vt)); };
  });
  await page.goto(url);
  await page.waitForFunction(() => window.cassiniSOI && cassiniSOI.running, null, { timeout: 600000, polling: 500 });
  const marks = { start: t() };
  const mark = k => { if (!(k in marks)) { marks[k] = t(); console.log(marks[k], k); } };
  mark("running");
  const cdp = await ctx.newCDPSession(page), frames = [];
  const VIRT = +env.VIRTUAL || 0;
  if (VIRT) {
    // every frame by hand: step the clock, screenshot, until the cutscene is over and the mission has been back 3 s
    const dir = fs.mkdtempSync(`${out}_frames_`);
    await page.evaluate(() => window.__virtStart());
    let n = 0, endAt = 0;
    for (;;) {
      await page.evaluate(ms => window.__step(ms), 1000 / VIRT);
      if (n % (+env.STRIDE || 1) === 0) await page.screenshot({ path: path.join(dir, `${String(n / (+env.STRIDE || 1)).padStart(6, "0")}.jpg`), type: "jpeg", quality: 88 });
      n++;
      if (n % VIRT === 0) {
        const s = await page.evaluate(() => ({ running: cassiniSOI.running, caps: [...document.querySelectorAll("#soi .cs-cap")].map(e => e.textContent).join(" | "), read: document.querySelector("#soi .sx-read").textContent }));
        if (n % (VIRT * 5) === 0) console.log(t(), "frame", n, s.read, "|", s.caps.slice(0, 60));
        if (!s.running && !endAt) endAt = n + 3 * VIRT;
      }
      if (endAt && n >= endAt) break;
    }
    if (env.STRIDE) { console.log("frames in", dir); await br.close(); return; }
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(VIRT), "-i", path.join(dir, "%06d.jpg"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", `${out}.mp4`]);
    fs.rmSync(dir, { recursive: true });
    marks.frames = n;
    fs.writeFileSync(`${out}.json`, JSON.stringify(marks, null, 1));
    console.log(JSON.stringify(marks));
    await br.close();
    return;
  }
  if (!env.STILLS_ONLY) {
    cdp.on("Page.screencastFrame", f => { frames.push({ ts: f.metadata.timestamp, data: f.data }); cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {}); });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: +W, maxHeight: +H });
  }
  const shot = async k => { mark(k); await page.screenshot({ path: `${out}_${k.replace(/\W+/g, "_")}.png` }); };
  const st = () => page.evaluate(() => ({ running: cassiniSOI.running, et: state.et, caps: [...document.querySelectorAll("#soi .cs-cap")].map(e => e.textContent).join(" | "),
    read: document.querySelector("#soi .sx-read").textContent }));
  const WANT = [["Arriving", "July 1, 2004"], ["ring plane", "crosses the ring plane"], ["turn", "turns end for end"], ["ignition", "Main engine on"],
    ["thrust", "gentle push"], ["light time", "Nobody on Earth"], ["A ring", "behind the A ring"], ["steering", "steers as it burns"], ["closest", "Closest approach"],
    ["engine off", "Engine off"], ["in orbit", "Saturn has caught it"]];
  for (;;) {
    const s = await st();
    for (const [k, txt] of WANT) if (!(k in marks) && s.caps.includes(txt)) { await page.waitForTimeout(1300); await shot(k); console.log("   ", s.read); }
    if (!s.running) break;
    await page.waitForTimeout(150);
  }
  mark("back to the mission");
  await page.waitForTimeout(3000);
  await shot("after");
  marks.et_after = await page.evaluate(() => state.et);
  if (!env.STILLS_ONLY) {
    await cdp.send("Page.stopScreencast");
    marks.length_s = +(frames.at(-1).ts - frames[0].ts).toFixed(1);
    const dir = fs.mkdtempSync(`${out}_frames_`);
    const list = frames.map((f, i) => { const p = path.join(dir, `${String(i).padStart(6, "0")}.jpg`); fs.writeFileSync(p, Buffer.from(f.data, "base64"));
      return `file '${p}'\nduration ${((frames[i + 1] ? frames[i + 1].ts : f.ts + 0.1) - f.ts).toFixed(4)}`; });
    fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n") + `\nfile '${path.join(dir, String(frames.length - 1).padStart(6, "0") + ".jpg")}'\n`);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"), "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", `${out}.mp4`]);
    fs.rmSync(dir, { recursive: true });
  }
  fs.writeFileSync(`${out}.json`, JSON.stringify(marks, null, 1));
  console.log(JSON.stringify(marks));
  await br.close();
})();
