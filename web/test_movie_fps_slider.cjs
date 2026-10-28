// Movie mode switches the dock speed slider to pictures a second (movie.fps), pauses on the way in, and gives the
// mission-time scale back on the way out. Run: node web/test_movie_fps_slider.cjs PORT THREE_DIR
// (the port serving Cassini OS with replay data, a frame server or a fake one; THREE_DIR an `npm pack three@0.128.0`
// unpacked, for when the CDN is blocked)
const { chromium } = require("playwright");
const [port, three] = process.argv.slice(2);
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const open = async (q, settings = {}) => {
    const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage(); page.errors = [];
    page.on("pageerror", e => { console.log("PAGEERROR", e.message); page.errors.push(e.message); });
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
    await page.addInitScript(s => { try { localStorage.clear(); localStorage.setItem("cassini-os-settings-v1", JSON.stringify(Object.assign({ "interface.autohide": false, "interface.tips": false }, s.v))); if (s.d) localStorage.setItem("cassini-os-settings-defaults-v1", JSON.stringify(s.d)); } catch (e) {} }, settings);
    await page.goto(`http://127.0.0.1:${port}/?${q}`);
    await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
    await page.waitForTimeout(2500);
    return page;
  };
  const read = p => p.evaluate(() => ({ speed: state.speed, playing: state.playing, movie: cassiniMovie.on, fps: cassiniMovie.fps(), set: cassiniSettings.get("movie.fps"),
    v: document.getElementById("speedv").textContent, eff: document.getElementById("speedeff").hidden ? "" : document.getElementById("speedeff").textContent,
    aria: document.getElementById("speed").getAttribute("aria-label"), pos: +document.getElementById("speed").value, mday: document.getElementById("mday").textContent, href: location.href }));

  let p = await open("t=2005-06-21T07:15:00&view=follow&speed=600&play=1", {});
  let r = await read(p); ok(r.playing && !r.movie && r.v === "10 min/s", `normal: playing at "${r.v}" (${r.mday})`);
  await p.click("#movie"); await p.waitForTimeout(600);
  r = await read(p);
  ok(r.movie && !r.playing, `Movie button: movie mode on and paused (playing ${r.playing})`);
  ok(r.v === "5 fps" && r.fps === 5 && r.set === 5, `slider reads "${r.v}" (default movie.fps ${r.set})`);
  ok(r.aria === "Movie mode speed" && r.eff === "movie mode", `aria "${r.aria}", under it "${r.eff}"`);
  ok(!/min\/s/.test(r.mday) && /movie, 5 fps/.test(r.mday), `status line "${r.mday}"`);
  // keyboard: two right arrows step 5 -> 6 -> 8 fps; mission speed stays 600
  await p.focus("#speed"); await p.keyboard.press("ArrowRight"); await p.keyboard.press("ArrowRight"); await p.waitForTimeout(400);
  r = await read(p); ok(r.fps === 8 && r.set === 8 && r.speed === 600 && r.v === "8 fps", `two right arrows: ${r.v}, movie.fps ${r.set}, mission speed still ${r.speed}`);
  // drag to the left end: 1 fps
  const box = await (await p.$("#speed")).boundingBox(), y = box.y + box.height / 2;
  await p.mouse.move(box.x + 30, y); await p.mouse.down(); await p.mouse.move(box.x + 1, y, { steps: 5 }); await p.mouse.up(); await p.waitForTimeout(400);
  r = await read(p); ok(r.fps === 1 && r.speed === 600, `drag to the left end: ${r.v} (speed ${r.speed})`);
  await p.mouse.move(box.x + 1, y); await p.mouse.down(); await p.mouse.move(box.x + box.width * Math.log(5) / Math.log(30), y, { steps: 5 }); await p.mouse.up(); await p.waitForTimeout(400);
  r = await read(p); ok(r.fps === 5, `drag back to ${r.v}`);
  // play: the clock steps picture to picture at about 5 a second (swiftshader draws slowly, so only a loose check)
  await p.click("#play"); await p.waitForTimeout(6000);
  const steps = await p.evaluate(() => cassiniMovie.state.steps.length); r = await read(p);
  ok(r.playing && steps >= 3, `playing in movie mode: ${steps} steps in the last 3 s, "${r.v}" / "${r.eff}"`);
  // leave with M: the normal scale is back, still playing at 10 min/s
  await p.click("#movie"); await p.waitForTimeout(800);
  r = await read(p); ok(!r.movie && r.v === "10 min/s" && r.speed === 600 && r.aria === "Playback speed" && r.eff !== "movie mode", `left movie mode: "${r.v}" "${r.eff}" playing ${r.playing} (${r.mday})`);
  await p.evaluate(() => document.activeElement.blur()); await p.keyboard.press("m"); await p.waitForTimeout(500);
  r = await read(p); ok(r.movie && !r.playing && r.v === "5 fps", `M key: movie mode, paused, "${r.v}"`);
  await p.keyboard.press("Escape"); await p.waitForTimeout(500);
  r = await read(p); ok(!r.movie && r.v === "10 min/s", `Escape: back to "${r.v}"`);
  ok(p.errors.length === 0, "no page errors");
  await p.context().close();

  // a movie=1 link opens in movie mode with the fps scale (and leaves play as the link says)
  p = await open("t=2005-06-21T07:15:00&view=follow&speed=600&play=0&movie=1");
  r = await read(p); ok(r.movie && r.v === "5 fps", `movie=1 link: "${r.v}" (${r.mday})`);
  await p.context().close();

  // saved settings: the old default 8 follows the new default 5; a chosen 12 stays
  p = await open("t=2005-06-21T07:15:00&play=0", { v: { "movie.fps": 8 } });
  r = await read(p); ok(r.set === 5, `saved old default 8 -> ${r.set}`);
  await p.context().close();
  p = await open("t=2005-06-21T07:15:00&play=0", { v: { "movie.fps": 12 } });
  r = await read(p); ok(r.set === 12, `saved choice 12 -> ${r.set}`);
  const d = await p.evaluate(() => { const d = cassiniSettings.defined.find(d => d.key === "movie.fps"); return [d.type, d.log, d.min, d.max, d.value]; });
  ok(d[1] && d[2] === 1 && d[3] === 30 && d[4] === 5, `setting ${JSON.stringify(d)}`);
  await p.context().close();
  await br.close();
})();
