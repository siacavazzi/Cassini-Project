// Plays the Huygens landing cutscene on a hand-stepped clock and logs the camera every frame (and optionally
// screenshots every frame into a video). The page comes from BASE (a running preview); with LOCAL=path/to/index.html
// the document itself is served from that file instead (data and pictures still come from BASE).
//   node step.cjs OUT [WIDTH HEIGHT]
//   BASE=http://host:port  LOCAL=index.html  PHONE=1  FPS=30  REC=1 (screenshots -> OUT.mp4)  FROM=s TO=s
//   INPUT=json   [{T, do:"drag"|"wheel"|"key"|"release", dx, dy, dz, key}] applied at screen second T
const { chromium } = require(process.env.PLAYWRIGHT || "playwright-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const [out, W = 1280, H = 720] = process.argv.slice(2);
const env = process.env, FPS = +env.FPS || 30, FROM = +env.FROM || 0, TO = +env.TO || 1e9, BASE = env.BASE || "http://127.0.0.1:8765";
const INPUT = env.INPUT ? JSON.parse(fs.readFileSync(env.INPUT, "utf8")) : [];
(async () => {
  const br = await chromium.launch({ args: ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required", "--use-angle=metal"] });
  const ctx = await br.newContext(env.PHONE ? { viewport: { width: +W, height: +H }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" }
    : { viewport: { width: +W, height: +H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  page.on("console", m => { if (m.type() === "error") console.log("console", m.text().slice(0, 200)); });
  if (env.LOCAL) await page.route(u => { const p = new URL(u).pathname; return p === "/" || p === "/index.html"; },
    r => r.fulfill({ path: env.LOCAL, headers: { "Content-Type": "text/html; charset=utf-8" } }));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  await page.addInitScript(() => {
    const realNow = performance.now.bind(performance), rRAF = window.requestAnimationFrame.bind(window), q = [];
    let virt = false, vt = 0;
    performance.now = () => virt ? vt : realNow();
    window.requestAnimationFrame = cb => { if (!virt) return rRAF(cb); q.push(cb); return q.length; };
    window.__virtStart = () => { vt = realNow(); virt = true; };
    window.__step = ms => { vt += ms; q.splice(0).forEach(cb => cb(vt)); };
    window.__snd = [];
  });
  await page.goto(BASE + "/?huygens-landing");
  await page.waitForFunction(() => window.cassiniHuygensLanding && cassiniHuygensLanding.running, null, { timeout: 600000, polling: 500 });
  await page.evaluate(() => {
    // log the sound calls the cutscene makes (they do nothing without a running audio context)
    const S = window.cassiniSound; if (!S) return;
    for (const k of ["chord", "rumble", "carrier", "bed"]) { const f = S[k]; S[k] = (...a) => { window.__snd.push([cassiniHuygensLanding.T, k, JSON.stringify(a)]); return f && f(...a); }; }
  });
  console.log("numbers", JSON.stringify(await page.evaluate(() => cassiniHuygensLanding.numbers)));
  console.log("body", await page.evaluate(() => document.body.className));
  const dir = `${out}_frames`; fs.rmSync(dir, { recursive: true, force: true }); if (env.REC) fs.mkdirSync(dir, { recursive: true });
  await page.evaluate(() => window.__virtStart());
  const log = [], caps = [];
  let n = 0, kept = 0, endAt = 0, lastCap = "", inputAt = 0, dragging = false;
  const gl = await page.$("#gl"), box = await gl.boundingBox(), cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  let mx = cx, my = cy;
  for (;;) {
    await page.evaluate(ms => window.__step(ms), 1000 / FPS);
    const s = await page.evaluate(() => {
      const L = window.cassiniHuygensLanding, T = L.T;
      const root = scene.children.find(o => o.children.length === 6 && o.children[3].userData && o.children[3].userData.canopy);
      const sub = state.focus === "HUYGENS" ? (root && root.visible ? root.position : probeObj.position) : cassini.position;
      const p = sub.clone().project(camera), d = new THREE.Vector3(); camera.getWorldDirection(d);
      const black = document.querySelector("#hland .cs-black");
      const cap = [...document.querySelectorAll("#hland .cs-cap")].map(e => e.textContent).join(" | ");
      const look = cassiniCutscene.look;
      return { running: L.running, T, focus: state.focus, et: state.et, cam: camera.position.toArray(), dir: d.toArray(), up: camera.up.toArray(),
        sub: sub.toArray(), sx: p.x, sy: p.y, black: +black.style.opacity || 0, cap, read: document.querySelector("#hland .cs-read").textContent,
        look: [look.yaw, look.pitch, look.zoom], cls: document.body.className, active: cassiniCutscene.active, playing: state.playing, follow: state.follow };
    });
    const T = s.T == null ? -1 : s.T;
    while (inputAt < INPUT.length && T >= INPUT[inputAt].T) {
      const e = INPUT[inputAt++];
      if (e.do === "drag") { if (!dragging) { await page.mouse.move(mx, my); await page.mouse.down(); dragging = true; } mx += e.dx || 0; my += e.dy || 0; await page.mouse.move(mx, my, { steps: 4 }); }
      else if (e.do === "release") { await page.mouse.up(); dragging = false; mx = cx; my = cy; }
      else if (e.do === "wheel") { await page.mouse.move(cx, cy); await page.mouse.wheel(0, e.dz); }
      else if (e.do === "key") await page.keyboard.press(e.key);
      console.log("input", T.toFixed(2), JSON.stringify(e));
    }
    if (env.REC && (s.running ? T >= FROM && T <= TO : true)) await page.screenshot({ path: path.join(dir, `${String(kept++).padStart(6, "0")}.jpg`), type: "jpeg", quality: 85 });
    log.push(s);
    if (s.cap !== lastCap) { lastCap = s.cap; caps.push([+T.toFixed(2), s.cap.slice(0, 160)]); }
    if (n % (FPS * 10) === 0) console.log(T.toFixed(1), s.focus, s.read.slice(0, 100));
    n++;
    if (!s.running && !endAt) endAt = n + (+env.TAIL || 5) * FPS;
    if ((endAt && n >= endAt) || T > TO) break;
  }
  const snd = await page.evaluate(() => window.__snd);
  const after = await page.evaluate(() => ({ focus: state.focus, playing: state.playing, follow: state.follow, cls: document.body.className, href: location.href,
    et: state.et, controls: controls.enabled, camUp: camera.up.toArray(), hidden: document.getElementById("hland").hidden }));
  fs.writeFileSync(`${out}.json`, JSON.stringify({ log, caps, snd, after }));
  console.log("after", JSON.stringify(after));
  if (env.REC) {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(dir, "%06d.jpg"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", `${out}.mp4`]);
    fs.rmSync(dir, { recursive: true });
  }
  await br.close();
})();
