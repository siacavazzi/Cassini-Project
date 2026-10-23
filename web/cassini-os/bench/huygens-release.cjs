// Records the Huygens release cutscene (huygens-release.html) as an MP4 from the page's own screencast, with stills, then
// what comes after it: the view left on Huygens, a zoom in, a drag round it and a zoom out.
//   npm i playwright-core
//   node huygens-release.cjs URL OUT [WIDTH HEIGHT]   (URL with ?huygens, or CROSS=1 to play through the release)
//   EXE=path       a Chromium to use (default Playwright's); SOFTWARE=1 SwiftShader (cloud containers)
//   THREE_DIR=.../three/package serves three.js locally; PHONE=1 a touch phone viewport; NOPROBE=1 hides data/huygens.json
//   SHOTS=3,13,...  seconds into the cutscene for stills
// Needs ffmpeg on the PATH.
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [url, out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, T0 = Date.now(), t = () => +((Date.now() - T0) / 1000).toFixed(1);
(async () => {
  const args = ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ executablePath: env.EXE || undefined, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H }, isMobile: !!env.PHONE, hasTouch: !!env.PHONE, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log(t(), "PAGEERROR", e.message, e.stack));
  page.on("console", m => { if (m.type() === "error" || m.type() === "warning") console.log(t(), "console", m.type(), m.text().slice(0, 200)); });
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (env.THREE_DIR) await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  if (env.NOPROBE) await page.route("**/data/huygens.json", r => r.fulfill({ status: 404, body: "" }));
  await page.goto(url);
  if (env.CROSS) {
    // play through the release from the timeline, like a user
    await page.waitForFunction(() => typeof yearReady === "function" && yearReady() && $("loading").hidden, null, { timeout: 600000, polling: 500 });
    await page.evaluate(() => { setTime(utcToEt("2004-12-25T01:58:30")); setSpeed(60); setPlaying(true); });
  }
  await page.waitForFunction(() => window.cassiniHuygensRelease && cassiniHuygensRelease.running, null, { timeout: 600000, polling: 300 });
  console.log(t(), "running");
  const cdp = await ctx.newCDPSession(page), frames = [];
  cdp.on("Page.screencastFrame", f => { frames.push({ ts: f.metadata.timestamp, data: f.data }); cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {}); });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: +W, maxHeight: +H });
  const shots = (env.SHOTS || "3,13,18,26,34,44,56,70").split(",").map(Number);
  const start = Date.now();
  while (await page.evaluate(() => cassiniHuygensRelease.running)) {
    const el = (Date.now() - start) / 1000;
    if (shots.length && el >= shots[0]) {
      const k = shots.shift();
      const info = await page.evaluate(() => [document.querySelector("#hrel .hr-read").textContent, [...document.querySelectorAll("#hrel .cs-cap")].map(e => e.textContent).join(" | ")]);
      console.log(t(), "shot", k, info.join(" || "));
      await page.screenshot({ path: `${out}_${String(k).padStart(2, "0")}.png` });
    }
    await page.waitForTimeout(150);
  }
  console.log(t(), "ended");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${out}_after.png` });
  const after = async k => { await page.screenshot({ path: `${out}_after_${k}.png` }); console.log("after", k, await page.evaluate(() => JSON.stringify({ focus: state.focus, et: new Date(etToMs(state.et)).toISOString(), coast: !!(window.studyCoast && studyCoast.modelShown(state.et)), cam: camera.position.length() }))); };
  await after("stay");
  await page.mouse.move(+W / 2, +H / 2);
  for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, -200); await page.waitForTimeout(120); }
  await page.waitForTimeout(1500); await after("zoom");
  await page.mouse.move(+W / 2, +H / 2); await page.mouse.down(); await page.mouse.move(+W / 2 + 250, +H / 2 + 60, { steps: 12 }); await page.mouse.up();
  await page.waitForTimeout(1500); await after("turn");
  for (let i = 0; i < 14; i++) { await page.mouse.wheel(0, 300); await page.waitForTimeout(120); }
  await page.waitForTimeout(1500); await after("out");
  const back = await page.evaluate(() => ({ et: new Date(etToMs(state.et)).toISOString(), playing: state.playing, ui: getComputedStyle($("gl")).cursor }));
  console.log("after", JSON.stringify(back));
  await cdp.send("Page.stopScreencast");
  const dir = fs.mkdtempSync(`${out}_frames_`);
  const list = frames.map((f, i) => { const p = path.join(dir, `${String(i).padStart(6, "0")}.jpg`); fs.writeFileSync(p, Buffer.from(f.data, "base64"));
    return `file '${p}'\nduration ${((frames[i + 1] ? frames[i + 1].ts : f.ts + 0.1) - f.ts).toFixed(4)}`; });
  fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n") + `\nfile '${path.join(dir, String(frames.length - 1).padStart(6, "0") + ".jpg")}'\n`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"), "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", `${out}.mp4`]);
  fs.rmSync(dir, { recursive: true });
  await br.close();
})();
