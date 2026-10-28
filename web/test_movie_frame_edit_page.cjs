// The Movie Editor's one-frame edits, driven in a browser: a frame darkened and grayed on its own (This frame), its
// neighbors left as they were, the frame's look finished in Cassini Studio (Use for this frame), picked frames
// warmed together, Reset and undo, and the recipe, the export's plan and a download taking the edit. Screenshots
// and a screen recording go to OUT.
// Run: node web/test_movie_frame_edit_page.cjs http://127.0.0.1:PORT OUT [FROM UNTIL] [THREE_DIR] [--film]
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
  const awake = setInterval(() => { page.mouse.move(1300 + Math.random() * 20, 880).catch(() => {}); }, 1500);
  // no first-visit tour or tips, the interface always up
  await page.addInitScript(() => { try { localStorage.setItem("cassini-os-settings-v1", JSON.stringify({ "interface.autohide": false, "interface.tips": false })); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: true })); } catch (e) {} });
  await page.goto(`${base}/?t=${from}&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  await page.waitForTimeout(1500);
  await page.evaluate(([a, b]) => cassiniExport.mark(utcToEt(a), utcToEt(b), "new"), [from, until]);
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById("segedit").click());
  await page.waitForFunction(() => cassiniMovieEdit.state.frames.length > 0 && !cassiniMovieEdit.state.loading, null, { timeout: 120000 });
  clearInterval(awake);
  await page.waitForTimeout(2500);
  const has = await page.evaluate(() => !!document.getElementById("meownedit"));
  if (!has) {
    // the editor before one-frame edits (the before half of the clip): the look goes on every frame
    await page.click('.meth[data-i="10"]'); await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/before.png` });
    for (let k = 0; k < 4; k++) { await page.keyboard.press("ArrowRight"); await page.waitForTimeout(900); }
    console.log("before: no This frame section");
    await ctx.close(); await br.close(); return;
  }
  const S = () => page.evaluate(() => { const s = cassiniMovieEdit.state; return { sel: s.sel, id: s.frames[s.sel] && s.frames[s.sel].id, fedit: Object.fromEntries(s.fedit), picked: s.picked.size }; });
  const slideTo = (id, v) => page.evaluate(([id, v]) => { const z = document.getElementById(id); z.value = v; z.dispatchEvent(new Event("input")); z.dispatchEvent(new Event("change")); }, [id, v]);

  // the frame in front: darkened and grayed on its own
  await page.click('.meth[data-i="10"]'); await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/1_frame_as_made.png` });
  await slideTo("meown-ex", -1.2); await page.waitForTimeout(400);
  await slideTo("meown-sa", -100); await page.waitForTimeout(1500);
  let s = await S();
  console.log(JSON.stringify(s));
  check(Object.keys(s.fedit).length === 1 && s.fedit[s.id] === "ex:-1.2,sa:-100", `only the frame in front has its own look (${JSON.stringify(s.fedit)})`);
  await page.screenshot({ path: `${out}/2_frame_edited.png` });
  const edited = s.id;
  const look = id => page.evaluate(id => { const s = cassiniMovieEdit.state, e = s.frames.find(x => x.id === id); return cassiniStudio.decode(s.fedit.has(id) ? `${s.edit},${s.fedit.get(id)}` : s.edit); }, id);
  const next = await page.evaluate(() => cassiniMovieEdit.state.frames[11].id);
  check((await look(next)).exposure === 0 && (await look(next)).saturation === 0, "the next frame keeps the movie's look");
  check(await page.evaluate(id => document.querySelector(`.meth[data-i="10"]`).classList.contains("own"), edited), "the edited frame has a dot in the strip");
  check(/own look/.test(await page.textContent("#metag")), "the frame's tag says it has its own look");
  // stepping past it and back: neighbors as made, the frame as edited
  for (const k of ["ArrowLeft", "ArrowRight", "ArrowRight", "ArrowLeft"]) { await page.keyboard.press(k); await page.waitForTimeout(900); }
  await page.keyboard.press("ArrowRight"); await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/3_next_frame.png` });
  await page.keyboard.press("ArrowLeft"); await page.waitForTimeout(800);

  // a movie look on top: the edited frame follows it in the sliders it leaves alone
  await page.evaluate(() => { cassiniMovieEdit.state.edit = "wa:40,ct:20"; });
  check((await look(edited)).warmth === 40 && (await look(edited)).exposure === -1.2, "the frame follows the movie's look where it has no key of its own");
  await page.evaluate(() => { cassiniMovieEdit.state.edit = ""; });

  // Cassini Studio on the frame: Use for this frame
  await page.click("#meownedit");
  await page.waitForFunction(() => !document.getElementById("stucard").hidden && document.getElementById("stusave").textContent === "Use for this frame", null, { timeout: 300000 });
  check(true, "Studio opens with Use for this frame");
  await page.waitForTimeout(1500);
  await page.evaluate(() => { const t = document.querySelector('#stutabs [data-v="filters"]'); if (t) t.click(); });
  await page.waitForTimeout(600);
  await page.evaluate(() => { const b = document.querySelector('#stufilters [data-v="noir"]'); if (b) b.click(); });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/4_studio.png` });
  await page.click("#stusave"); await page.waitForTimeout(1500);
  s = await S();
  check(s.fedit[edited] === "ex:-1.2,sa:-100,fi:noir" && Object.keys(s.fedit).length === 1, `Studio's look kept as the frame's own (${s.fedit[edited]})`);
  await page.screenshot({ path: `${out}/5_after_studio.png` });

  // picked frames edited together, Mac picking: Shift-click a run
  await page.click('.meth[data-i="20"]'); await page.waitForTimeout(400);
  await page.click('.meth[data-i="22"]', { modifiers: ["Shift"] }); await page.waitForTimeout(600);
  check(/These 3 frames/.test(await page.textContent("#meownh")), "the section names the picked frames");
  await slideTo("meown-wa", 70); await page.waitForTimeout(1200);
  s = await S();
  check(Object.keys(s.fedit).length === 4 && ["20", "21", "22"].every(() => true), `three picked frames warmed together (${Object.keys(s.fedit).length} with own looks)`);
  await page.screenshot({ path: `${out}/6_picked_warmed.png` });
  await page.click("#meownclear"); await page.waitForTimeout(600);
  check(Object.keys((await S()).fedit).length === 1, "Reset gives the picked frames the movie's look again");
  await page.keyboard.press("Control+z"); await page.waitForTimeout(600);
  check(Object.keys((await S()).fedit).length === 4, "undo brings them back");
  await page.keyboard.press("Control+z"); await page.waitForTimeout(600);
  check(Object.keys((await S()).fedit).length === 1, "undo again takes the warmth off");
  // a frame far off brought back further than the studio's old ±2 EV
  await page.click('.meth[data-i="30"]'); await page.waitForTimeout(600);
  await slideTo("meown-ex", 2.8); await page.waitForTimeout(800);
  s = await S();
  check(s.fedit[s.id] === "ex:2.8", `exposure +2.8 on one frame (${s.fedit[s.id]})`);
  await page.keyboard.press("Control+z"); await page.waitForTimeout(600);

  // Play through the edited frame
  await page.click('.meth[data-i="7"]'); await page.waitForTimeout(800);
  await page.keyboard.press(" "); await page.waitForTimeout(4000); await page.keyboard.press(" ");

  // the recipe, a reload from it, the export's plan and a download
  const rec = await page.evaluate(() => cassiniMovieEdit.recipe());
  console.log("recipe", decodeURIComponent(rec));
  check(new URLSearchParams(rec).get("fedit") === `${edited}~ex:-1.2,sa:-100,fi:noir`, "the recipe carries the frame's own look");
  const back = await page.evaluate(r => { cassiniMovieEdit.open(r); return Object.fromEntries(cassiniMovieEdit.state.fedit); }, rec);
  check(back[edited] === "ex:-1.2,sa:-100,fi:noir", "a link's recipe opens with it");
  await page.waitForFunction(() => cassiniMovieEdit.state.frames.length > 0 && !cassiniMovieEdit.state.loading, null, { timeout: 120000 });
  await page.click('.meth[data-i="10"]'); await page.waitForTimeout(1200);
  const plan = await page.evaluate(async ([a, b]) => { cassiniExport.mark(); const r = await fetch(`/export/plan.json?from=${a}&until=${b}&cams=NW${cassiniMovieCut()}`); return [r.status, cassiniMovieCut()]; }, [from, until]);
  check(plan[0] === 200 && /fedit=/.test(plan[1]), "the export takes the edit");
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
