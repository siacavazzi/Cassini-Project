// Input probes on the Huygens landing cutscene, on a hand-stepped clock: one scenario per page load.
//   node input.cjs OUTDIR SCENARIO...     BASE=http://127.0.0.1:8936   PHONE=1
// Scenarios: pitch zoom keys click pinch skip:<T> end:<stay|back|auto> replay dragcut
const { chromium } = require(process.env.PLAYWRIGHT || "playwright-core");
const fs = require("fs"), path = require("path");
const [outDir, ...scenarios] = process.argv.slice(2);
const env = process.env, BASE = env.BASE || "http://127.0.0.1:8936", FPS = 30;
fs.mkdirSync(outDir, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function open(br, query) {
  const ctx = await br.newContext(env.PHONE ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" }
    : { viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  await page.addInitScript(() => {
    const realNow = performance.now.bind(performance), rRAF = window.requestAnimationFrame.bind(window), q = [];
    let virt = false, vt = 0;
    performance.now = () => virt ? vt : realNow();
    window.requestAnimationFrame = cb => { if (!virt) return rRAF(cb); q.push(cb); return q.length; };
    window.__virtStart = () => { vt = realNow(); virt = true; };
    // a frame is stepped only when the page has asked for one (never run the clock ahead of the render loop)
    window.__step = (ms, n) => { let done = 0; for (let i = 0; i < (n || 1); i++) { if (!q.length) break; vt += ms; q.splice(0).forEach(cb => cb(vt)); done++; } return done; };
  });
  await page.goto(BASE + "/?" + (query || "huygens-landing"));
  await page.waitForFunction(() => window.cassiniHuygensLanding && cassiniHuygensLanding.running, null, { timeout: 120000, polling: 250 });
  await page.evaluate(() => window.__virtStart());
  return { ctx, page };
}
async function step(page, secs) {
  let left = Math.max(1, Math.round(secs * FPS)), idle = 0;
  while (left > 0 && idle < 200) { const d = await page.evaluate(([ms, n]) => window.__step(ms, n), [1000 / FPS, Math.min(left, 30)]); left -= d; if (!d) { idle++; await sleep(20); } else idle = 0; }
}
async function stepTo(page, T) {
  for (let i = 0; i < 20000; i++) {
    const s = await page.evaluate(() => ({ r: cassiniHuygensLanding.running, T: cassiniHuygensLanding.T, ph: document.body.classList.contains("cutscene") }));
    if (!s.r || s.T >= T) return s.T;
    await step(page, Math.min(1, Math.max(1 / FPS, T - s.T)));
  }
}
const snap = (page, name) => page.screenshot({ path: path.join(outDir, name + ".jpg"), type: "jpeg", quality: 80 });
const st = page => page.evaluate(() => {
  const look = cassiniCutscene.look, vis = [...document.querySelectorAll("#app > *")].filter(e => !e.hidden && e.id && getComputedStyle(e).display !== "none" && +getComputedStyle(e).opacity > 0.05).map(e => e.id);
  const root = scene.children.find(o => o.children.length === 6 && o.children[3].userData && o.children[3].userData.canopy);
  return { T: cassiniHuygensLanding.T, running: cassiniHuygensLanding.running, active: cassiniCutscene.active, focus: state.focus, playing: state.playing, speed: state.speed, follow: state.follow,
    utc: new Date(etToMs(state.et)).toISOString().slice(0, 19), look: [look.yaw, look.pitch, look.zoom].map(x => +x.toFixed(3)), cls: document.body.className, vis: vis.join(","),
    controls: controls.enabled, camUp: camera.up.toArray().map(x => +x.toFixed(2)), camDist: +(camera.position.length() * 1e6).toFixed(1),
    camAboveProbeM: root ? +((camera.position.clone().sub(root.position)).dot(camera.up.clone().normalize()) * 1e6).toFixed(2) : null, sound: cassiniSettings.get("sound.on"), href: location.search };
});
const scen = {
  // drag far up and far down on the ground and in the air: can the camera go under the ground or flip?
  async pitch(page) {
    for (const T of [30, 68]) {
      await stepTo(page, T);
      for (const [name, dy] of [["up", -500], ["down", 500]]) {
        await page.mouse.move(640, 360); await page.mouse.down(); await page.mouse.move(640, 360 + dy, { steps: 10 }); await step(page, 0.2);
        console.log(`pitch T${T} drag ${name}`, JSON.stringify(await st(page))); await snap(page, `pitch_T${T}_${name}`);
        await page.mouse.up(); await page.mouse.move(640, 360); await page.mouse.down(); await page.mouse.move(640, 360 - dy, { steps: 10 }); await page.mouse.up(); await step(page, 0.1);
      }
      await step(page, 4.5); console.log(`pitch T${T} 4.5 s after`, JSON.stringify((await st(page)).look));
      await step(page, 3); console.log(`pitch T${T} 7.5 s after`, JSON.stringify((await st(page)).look));
    }
  },
  async zoom(page) {
    for (const T of [10, 30, 38, 58, 68, 80]) {
      await stepTo(page, T); await page.mouse.move(640, 360);
      for (const [name, dz] of [["in", -3000], ["out", 6000]]) {
        await page.mouse.wheel(0, dz); await sleep(100); await step(page, 0.2);
        console.log(`zoom T${T} ${name}`, JSON.stringify((await st(page)).look)); await snap(page, `zoom_T${T}_${name}`);
      }
      await page.mouse.wheel(0, -1155); await sleep(100); await step(page, 0.1);
    }
  },
  // every plain key: does anything outside the cutscene react?
  async keys(page) {
    await stepTo(page, 30);
    const base = JSON.stringify(await st(page).then(s => ({ ...s, T: 0, utc: 0, look: 0, camDist: 0, camAboveProbeM: 0 })));
    const keys = [..."abcdefghijklmnopqrtuvwxyz0123456789,./;'[]-=`", "Space", "Enter", "Tab", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown", "Backspace", "Delete", "?", "+", "Shift+Space", "s"];
    for (const k of keys.filter(k => !(env.SKIPKEYS || "").split(" ").includes(k))) {
      const before = await st(page);
      await page.keyboard.press(k).catch(e => console.log("key error", k, e.message)); await sleep(60); await step(page, 0.3);
      const after = await st(page), diff = Object.keys(after).filter(f => !["T", "utc", "camDist", "camAboveProbeM"].includes(f) && JSON.stringify(after[f]) !== JSON.stringify(before[f]));
      const jump = Math.abs(Date.parse(after.utc + "Z") - Date.parse(before.utc + "Z")) / 1000;
      if (diff.length || jump > 900) { console.log(`key ${k}: changed ${diff.map(f => `${f}: ${JSON.stringify(before[f])} -> ${JSON.stringify(after[f])}`).join("; ")} clock moved ${jump} s`); await snap(page, `key_${k.replace(/[^a-z0-9]/gi, "_")}`); }
      if (!after.running) { console.log(`key ${k} ENDED the cutscene`); break; }
    }
    console.log("keys done", JSON.stringify(await st(page)));
  },
  // clicks and double clicks on the 3D view: do they pick bodies behind the cutscene?
  async click(page) {
    await stepTo(page, 38);
    const titan = await page.evaluate(() => { const p = relScene("TITAN", new THREE.Vector3()).project(camera); return [(p.x + 1) / 2 * innerWidth, (1 - p.y) / 2 * innerHeight]; });
    console.log("titan at", titan.map(Math.round));
    for (const [name, f] of [["click Titan", () => page.mouse.click(titan[0], titan[1])], ["dblclick Titan", () => page.mouse.dblclick(titan[0], titan[1])], ["dblclick Cassini", () => page.mouse.dblclick(900, 440)], ["right click", () => page.mouse.click(titan[0], titan[1], { button: "right" })]]) {
      const before = await st(page); await f(); await sleep(80); await step(page, 0.5); const after = await st(page);
      console.log(name, "focus", before.focus, "->", after.focus, "vis", after.vis === before.vis ? "same" : after.vis, "look", JSON.stringify(after.look));
    }
    await snap(page, "click_after");
  },
  // two fingers on a phone: what does the look-around do?
  async pinch(page) {
    await stepTo(page, 30);
    const cdp = await page.context().newCDPSession(page), log = [];
    const touch = (type, pts) => cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id, radiusX: 4, radiusY: 4, force: 1 })) });
    await touch("touchStart", [[150, 400]]); await touch("touchStart", [[150, 400], [250, 400]]);
    for (let i = 1; i <= 12; i++) { await touch("touchMove", [[150 - 4 * i, 400], [250 + 4 * i, 400]]); await step(page, 1 / 30); log.push((await st(page)).look); }
    await snap(page, "pinch_mid");
    await touch("touchEnd", []); await step(page, 0.2);
    console.log("pinch out by 96 px: look [yaw, pitch, zoom] per move:", JSON.stringify(log));
    console.log("after pinch", JSON.stringify(await st(page)));
    // one finger drag
    await touch("touchStart", [[200, 400]]); for (let i = 1; i <= 10; i++) await touch("touchMove", [[200 + 10 * i, 400]]); await step(page, 0.1);
    console.log("one finger 100 px right", JSON.stringify((await st(page)).look)); await touch("touchEnd", []);
  },
  async skip(page, arg) {
    const how = arg.startsWith("e") ? "Escape" : "button", T = +arg.replace(/^e/, "");
    await stepTo(page, T); await snap(page, `skip${arg}_0before`);
    if (how === "Escape") await page.keyboard.press("Escape"); else await page.click("#hland .cs-skip");
    await sleep(100); await step(page, 0.1); console.log(`skip ${how} at T${T} +0.1s`, JSON.stringify(await st(page))); await snap(page, `skip${arg}_1`);
    await step(page, 0.9); await snap(page, `skip${arg}_2`);
    await step(page, 2); console.log(`skip ${how} at T${T} +3s`, JSON.stringify(await st(page))); await snap(page, `skip${arg}_3`);
  },
  async end(page, arg) {
    await stepTo(page, arg === "auto" ? 200 : +(env.CARD || 100));
    if (arg !== "auto") { await snap(page, `end_${arg}_0card`); await page.click(`#hland [data-hl="${arg}"]`); await sleep(100); }
    for (const [i, d] of [[1, 0.1], [2, 0.9], [3, 2], [4, 5]]) { await step(page, d); console.log(`end ${arg} step ${i}`, JSON.stringify(await st(page))); await snap(page, `end_${arg}_${i}`); }
    // can the view be dragged now, and does it behave?
    await page.mouse.move(640, 360); await page.mouse.down(); await page.mouse.move(840, 300, { steps: 8 }); await page.mouse.up(); await step(page, 0.5);
    console.log(`end ${arg} after a drag`, JSON.stringify(await st(page))); await snap(page, `end_${arg}_5drag`);
  },
  async replay(page) {
    await stepTo(page, 200); await step(page, 3);
    console.log("ended", JSON.stringify(await st(page)));
    await page.evaluate(() => cassiniHuygensLanding.play());
    for (let i = 0; i < 40 && !(await page.evaluate(() => cassiniHuygensLanding.running)); i++) { await sleep(250); await step(page, 0.25); }
    await stepTo(page, 3); console.log("replay T3", JSON.stringify(await st(page))); await snap(page, "replay_T3");
    await stepTo(page, 16); await snap(page, "replay_T16");
    await stepTo(page, 68); console.log("replay T68", JSON.stringify(await st(page))); await snap(page, "replay_T68");
  },
  // where the Sun is in Cassini's shots
  async geom(page) {
    for (const T of [38, 80]) {
      await stepTo(page, T);
      console.log("T", T, JSON.stringify(await page.evaluate(() => {
        const C = cassini.position, tW = relScene("TITAN", new THREE.Vector3()).sub(C).normalize(), up = new THREE.Vector3(0, 1, 0), side = new THREE.Vector3().crossVectors(tW, up).normalize();
        const up2 = new THREE.Vector3().crossVectors(side, tW), s = uSun.value;
        return { sunTitan: +s.dot(tW).toFixed(3), sunSide: +s.dot(side).toFixed(3), sunUp: +s.dot(up2).toFixed(3), aspect: camera.aspect };
      })));
    }
  },
  // a still at a screen second
  async snap(page, arg) { for (const T of arg.split(",")) { await stepTo(page, +T); await step(page, 0.05); await snap(page, `snap_${process.env.PHONE ? "phone_" : ""}T${T}`); } },
  // a drag held across a cut
  async dragcut(page) {
    await stepTo(page, 33); await page.mouse.move(640, 360); await page.mouse.down(); await page.mouse.move(840, 360, { steps: 5 });
    await step(page, 0.3); console.log("held before cut", JSON.stringify((await st(page)).look));
    await stepTo(page, 36); console.log("held after cut", JSON.stringify((await st(page)).look)); await page.mouse.move(900, 360, { steps: 3 }); await step(page, 0.1);
    console.log("moved after cut", JSON.stringify((await st(page)).look)); await page.mouse.up();
  },
};
(async () => {
  const br = await chromium.launch({ args: ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required", "--use-angle=metal"] });
  try {
    for (const s of scenarios) {
      const [name, arg] = s.split(":");
      console.log(`\n=== ${s}`);
      const { ctx, page } = await open(br);
      try { await scen[name](page, arg); } catch (e) { console.log("SCENARIO ERROR", e.message.slice(0, 400)); }
      await ctx.close();
    }
  } finally { await br.close(); }
})();
