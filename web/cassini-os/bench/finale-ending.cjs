// Records the end of the Grand Finale (?finale): the last lines of the recap, "Thank you, Cassini", and whatever comes
// after it (the credits roll, or the return to the mission), as an MP4 made from the page's own screencast, with
// stills at each moment. For before/after evidence of the ending.
//   npm i playwright-core
//   node finale-ending.cjs URL OUT [WIDTH HEIGHT]      (URL with ?finale; OUT is a prefix: OUT.mp4, OUT_*.png, OUT.json)
//   CHANNEL=chrome  use the installed Google Chrome; default is Playwright's Chromium (EXE=path for another one)
//   SOFTWARE=1      SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
//   HAND=1          partway into the credits, scroll them by hand with the wheel, then jump near the end
//   FROM='text'     start recording when a caption with this text shows (default: the recap's next-to-last line)
// Needs ffmpeg on the PATH.
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [url, out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, FROM = env.FROM || "Cassini turned points of light";
const T0 = Date.now(), t = () => +((Date.now() - T0) / 1000).toFixed(1);
(async () => {
  const args = ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log(t(), "PAGEERROR", e.message));
  if (env.THREE_DIR) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
    r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (env.THREE_DIR) await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  await page.goto(url);
  await page.waitForFunction(() => window.cassiniFinale && cassiniFinale.running, null, { timeout: 600000, polling: 500 });
  const marks = { start: t() };
  const mark = k => { if (!(k in marks)) { marks[k] = t(); console.log(marks[k], k); } };
  mark("finale running");
  const state = () => page.evaluate(() => {
    const r = document.querySelector("#finale .fx-roll");
    return { running: cassiniFinale.running, caps: [...document.querySelectorAll("#finale .fx-cap, #finale .cs-cap")].map(e => e.textContent).join(" | "),
      roll: !!r && r.classList.contains("on"), top: r ? r.scrollTop : 0, max: r ? r.scrollHeight - r.clientHeight : 0 };
  });
  for (let s = await state(); s.running && !s.caps.includes(FROM); s = await state()) await page.waitForTimeout(250);
  // the page's own screencast, every frame with its time, so the video keeps the page's pace
  const cdp = await ctx.newCDPSession(page), frames = [];
  cdp.on("Page.screencastFrame", f => { frames.push({ ts: f.metadata.timestamp, data: f.data }); cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {}); });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: +W, maxHeight: +H });
  mark("recording");
  const shot = async k => { mark(k); await page.screenshot({ path: `${out}_${k.replace(/\W+/g, "_")}.png` }); };
  let hand = false;
  for (;;) {
    const s = await state();
    if (s.caps.includes("Thank you, Cassini") && !("thank you" in marks)) { await page.waitForTimeout(1500); await shot("thank you"); }
    if (s.roll && !("credits" in marks)) mark("credits");
    if (s.roll && s.top > 120 && !("credits start" in marks)) await shot("credits start");
    if (s.roll && s.top > 800 && !("credits imaging" in marks)) await shot("credits imaging");
    if (env.HAND && s.roll && s.top > 2200 && !hand) {
      hand = true; mark("hand scroll");
      await page.mouse.move(+W / 2, +H / 2);
      for (let i = 0; i < 24; i++) { await page.mouse.wheel(0, 220); await page.waitForTimeout(80); }
      await shot("hand scrolled");
      await page.waitForTimeout(5000);
      mark("hand jump near the end");
      await page.mouse.move(+W / 2, +H / 2);
      await page.evaluate(() => { const r = document.querySelector("#finale .fx-roll"); r.dispatchEvent(new WheelEvent("wheel")); r.scrollTop = r.scrollHeight - r.clientHeight - 700; });
    }
    if (s.roll && s.max > 0 && s.top >= s.max - 1 && !("credits end" in marks)) { await page.waitForTimeout(2500); await shot("credits end"); }
    if (!s.running) break;
    await page.waitForTimeout(200);
  }
  mark("back to the mission");
  await page.waitForTimeout(3500);
  await shot("after");
  await cdp.send("Page.stopScreencast");
  marks.length_s = +(frames.at(-1).ts - frames[0].ts).toFixed(1);
  fs.writeFileSync(`${out}.json`, JSON.stringify(marks, null, 1));
  // frames to MP4 with ffmpeg's concat list, each frame held until the next
  const dir = fs.mkdtempSync(`${out}_frames_`);
  const list = frames.map((f, i) => { const p = path.join(dir, `${String(i).padStart(6, "0")}.jpg`); fs.writeFileSync(p, Buffer.from(f.data, "base64"));
    return `file '${p}'\nduration ${((frames[i + 1] ? frames[i + 1].ts : f.ts + 0.1) - f.ts).toFixed(4)}`; });
  fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n") + `\nfile '${path.join(dir, String(frames.length - 1).padStart(6, "0") + ".jpg")}'\n`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"), "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", `${out}.mp4`]);
  fs.rmSync(dir, { recursive: true });
  console.log(JSON.stringify(marks));
  await br.close();
})();
