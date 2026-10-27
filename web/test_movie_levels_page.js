// The Movie Editor's exposure graph and framing, driven in a browser: the stretch's brightness measured, level points
// added and dragged, Even out (when the server has it), Auto center for the movie, zoom, a frame nudged and undone,
// the export taking the edit, and a frame downloaded with it. Screenshots and a screen recording go to OUT.
// Run: node web/test_movie_levels_page.js http://127.0.0.1:PORT OUT [FROM UNTIL] [THREE_DIR] [--film]
// (a frame server with replay data; THREE_DIR an `npm pack three@0.128.0` unpacked, for when the CDN is blocked;
// --film also makes the edited film, NAC only, 512 px, no sound)
const { chromium } = require("playwright");
const fs = require("fs");
const args = process.argv.slice(2).filter(a => !a.startsWith("--")), film = process.argv.includes("--film");
const [base, out, from = "2000-12-13T03:00:00", until = "2000-12-13T06:00:00", three] = args;
fs.mkdirSync(out, { recursive: true });
const check = (ok, what) => { console.log(ok ? "ok" : "FAIL", what); if (!ok) process.exitCode = 1; };
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true, recordVideo: { dir: out, size: { width: 1440, height: 900 } } });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); errs.push(e.message); });
  if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  // keep the interface awake (it fades when the pointer rests) until the editor is open
  const awake = setInterval(() => { page.mouse.move(1300 + Math.random() * 20, 880).catch(() => {}); }, 1500);
  await page.goto(`${base}/?t=${from}&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  await page.waitForTimeout(1500);
  await page.evaluate(([a, b]) => cassiniExport.mark(utcToEt(a), utcToEt(b), "new"), [from, until]);
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById("segedit").click());
  await page.waitForFunction(() => cassiniMovieEdit.state.frames.length > 0 && !cassiniMovieEdit.state.loading, null, { timeout: 120000 });
  await page.waitForFunction(() => { const l = cassiniMovieEdit.state.lv; return l.error || l.total != null && l.done >= l.total; }, null, { timeout: 600000 });
  clearInterval(awake);
  await page.waitForTimeout(2500);
  const lv = await page.evaluate(() => { const s = cassiniMovieEdit.state; return { n: s.frames.length, measured: Object.values(s.lv.level).filter(v => v != null).length, ready: s.lv.ready, error: s.lv.error }; });
  console.log(JSON.stringify(lv));
  check(!lv.error && lv.measured > 0, `brightness measured for ${lv.measured} of ${lv.n} frames`);
  await page.screenshot({ path: `${out}/1_graph.png` });

  // two level points, the second dragged up
  const g = await page.locator("#melevels").boundingBox();
  await page.mouse.dblclick(g.x + g.width * 0.25, g.y + g.height / 2); await page.waitForTimeout(400);
  await page.mouse.dblclick(g.x + g.width * 0.75, g.y + g.height / 2); await page.waitForTimeout(400);
  check(await page.evaluate(() => cassiniMovieEdit.state.levels.size) === 2, "double-click adds level points");
  let at = null;
  for (let dy = -34; dy <= 34 && at == null; dy += 2) {
    await page.mouse.move(g.x + g.width * 0.75, g.y + g.height / 2 + dy);
    if (await page.evaluate(() => document.getElementById("melevels").classList.contains("onpt"))) at = g.y + g.height / 2 + dy;
  }
  if (at != null) { await page.mouse.down(); await page.mouse.move(g.x + g.width * 0.75, at - 12, { steps: 8 }); await page.mouse.up(); }
  await page.waitForTimeout(1500);
  const lvl = await page.evaluate(() => [...cassiniMovieEdit.state.levels.values()]);
  check(lvl[1] > 0.5 || lvl[0] > 0.5, `dragging a point up raises the movie there (${JSON.stringify(lvl)})`);
  await page.screenshot({ path: `${out}/2_levels.png` });

  // Even out, when the frame server has movie mode's normalization
  if (lv.ready) {
    await page.evaluate(() => { const z = document.getElementById("meeven"); z.value = 8; z.dispatchEvent(new Event("input")); z.dispatchEvent(new Event("change")); });
    await page.waitForFunction(() => cassiniMovieEdit.state.lv.even && Object.keys(cassiniMovieEdit.state.lv.even).length >= 0, null, { timeout: 120000 });
    await page.waitForTimeout(3000);
    console.log("even", JSON.stringify(await page.evaluate(() => Object.keys(cassiniMovieEdit.state.lv.even).length)), "pictures changed");
    await page.screenshot({ path: `${out}/3_even.png` });
  } else console.log("skip Even out: this frame server has no exposure normalization");

  // framing: Auto center off then on, zoom, a nudge, undone
  for (const v of ["0", "1"]) { await page.click(`#mectr button[data-v="${v}"]`); await page.waitForTimeout(2500); await page.screenshot({ path: `${out}/4_center_${v === "1" ? "on" : "off"}.png` }); }
  await page.evaluate(() => { const z = document.getElementById("mezoom"); z.value = 1.5; z.dispatchEvent(new Event("input")); z.dispatchEvent(new Event("change")); });
  await page.waitForTimeout(1000);
  const c = await page.locator("#mecanvas").boundingBox();
  await page.mouse.move(c.x + c.width / 2, c.y + c.height / 2); await page.mouse.down();
  await page.mouse.move(c.x + c.width / 2 + 50, c.y + c.height / 2 - 25, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/5_framing.png` });
  const rec = await page.evaluate(() => cassiniMovieEdit.recipe());
  console.log("recipe", decodeURIComponent(rec));
  check(/levels=/.test(rec) && /ctr=1/.test(rec) && /zoom=1\.5/.test(rec) && /nudge=/.test(rec), "the recipe carries levels, Auto center, zoom and the nudge");
  await page.keyboard.press("Control+z"); await page.waitForTimeout(500);
  check(await page.evaluate(() => cassiniMovieEdit.state.nudge.size) === 0, "undo takes the nudge back");

  // the export plans the edit; a frame downloads with it
  const plan = await page.evaluate(async ([a, b]) => { cassiniExport.mark(); const r = await fetch(`/export/plan.json?from=${a}&until=${b}&cams=NW${cassiniMovieCut()}`); return [r.status, cassiniMovieCut()]; }, [from, until]);
  check(plan[0] === 200 && /levels=/.test(plan[1]), "the export takes the edit");
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), page.click("#medl")]);
  await dl.saveAs(`${out}/${dl.suggestedFilename()}`);
  check(/_edited\.jpg$/.test(dl.suggestedFilename()), `downloaded ${dl.suggestedFilename()}`);
  if (film) {
    const j = await page.evaluate(async ([a, b]) => {
      const q = `from=${a}&until=${b}&cams=N&fps=6&size=512&sound=0&caption=1${cassiniMovieCut()}`;
      let j = await (await fetch(`/export?${q}`, { method: "POST" })).json();
      for (let k = 0; k < 1800 && j.state !== "done" && j.state !== "failed"; k++) { await new Promise(r => setTimeout(r, 1000)); j = await (await fetch(`/export/${j.id}.json`)).json(); }
      return j;
    }, [from, until]);
    check(j.state === "done", `film ${j.id} ${j.state} ${j.error || ""}`);
    fs.writeFileSync(`${out}/film.txt`, `${base}/export/${j.id}.mp4\n`);
  }
  check(!errs.length, `no page errors (${errs.length})`);
  await ctx.close(); await br.close();
})();
