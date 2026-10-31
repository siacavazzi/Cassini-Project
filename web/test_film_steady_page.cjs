// Additional stabilization in the Movie Editor (Framing, under Auto center; film-steady.html), driven in a browser: a
// stretch of a small moon whose centering wobbles, which the editor steadies by itself (film_steady.auto: the moon is
// a few px across), played with it slid to Off and then to 12. With it on, the
// note counts the pictures it gets and matches, every frame of the film gets a move, the preview is drawn with it, the
// recipe keeps the setting (stab=), Reset puts it back as Settings has it (on by itself), and a film the frame server makes is sent
// the moves (POST /export's body, steadied=). Each frame of the stage is saved to OUT as off-NN.png and on-NN.png
// (the before/after: web/frames/film_steady_evidence.py measures where the moon is in them).
// Run: node web/test_film_steady_page.cjs http://127.0.0.1:PORT OUT [FROM UNTIL] [THREE_DIR] [MUXER_DIR]
// (a frame server with replay data, or the cloud rig /mnt/project-files/film-steady/fakeserver.py; THREE_DIR an `npm
// pack three@0.128.0` unpacked and MUXER_DIR an `npm pack mp4-muxer@5.1.5` unpacked, for when the CDN is blocked)
const { chromium } = require("playwright");
const fs = require("fs");
const [base, out, from = "2005-08-18T03:00:00", until = "2005-08-18T04:00:00", three, muxer] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const check = (ok, what) => { console.log(ok ? "ok" : "FAIL", what); if (!ok) process.exitCode = 1; };
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  if (muxer) await page.route("https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.5/**", r => r.fulfill({ path: `${muxer}/${r.request().url().split("mp4-muxer@5.1.5/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.setItem("cassini-os-settings-v1", JSON.stringify({ "interface.autohide": false, "interface.tips": false })); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: true })); } catch (e) {} });
  await page.goto(`${base}/?t=${from}&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  await page.waitForTimeout(1000);
  await page.evaluate(([a, b]) => cassiniExport.mark(utcToEt(a), utcToEt(b), "new"), [from, until]);
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById("segedit").click());
  await page.waitForFunction(() => cassiniMovieEdit.state.frames.length > 0 && !cassiniMovieEdit.state.loading, null, { timeout: 120000 });
  await page.waitForTimeout(1500);
  const n = await page.evaluate(() => cassiniMovieEdit.state.frames.length);
  check(n > 5, `the stretch has ${n} frames`);
  // a small moon: on by itself
  const notes = new Set();
  for (const t0 = Date.now(); Date.now() - t0 < 120000;) {
    const t = await page.evaluate(() => document.getElementById("mestabnote").textContent);
    notes.add(t.replace(/\d[\d,]*/g, "#"));
    if (/^Steadied/.test(t)) break;
    await page.waitForTimeout(100);
  }
  const auto = await page.evaluate(() => [document.getElementById("mestabv").textContent, document.getElementById("mestabnote").textContent]);
  console.log("  on by itself:", auto.join(" | "));
  check(auto[0] === "Auto · 12 pictures" && /On by itself: the body is about \d+ px across/.test(auto[1]), "a small moon is steadied by itself");
  // slid to Off: the frames as Auto center has them
  await page.evaluate(() => { const el = document.getElementById("mestab"); el.value = 0; el.dispatchEvent(new Event("input")); el.dispatchEvent(new Event("change")); });
  await page.waitForTimeout(800);
  check(await page.evaluate(() => cassiniMovieEdit.state.stab === 0 && /^Off/.test(document.getElementById("mestabnote").textContent) && document.getElementById("mestabv").textContent === "Off" && !cassiniFilmSteady.at(cassiniMovieEdit.state.frames[3].id)), "slid to Off, it is off");

  // each frame of the film, as the stage draws it
  async function frames(tag) {
    for (let i = 0; i < n; i++) {
      await page.evaluate(k => document.querySelector(`.meth[data-i="${k}"]`).click(), i);
      await page.waitForFunction(k => cassiniMovieEdit.state.sel === k, i);
      await page.waitForTimeout(350);
      await page.locator("#mestage").screenshot({ path: `${out}/${tag}-${String(i).padStart(2, "0")}.png` });
    }
  }
  await frames("off");

  // on: 12 pictures (the slider, as a hand would move it)
  await page.evaluate(() => { const el = document.getElementById("mestab"); el.value = 12; el.dispatchEvent(new Event("input")); el.dispatchEvent(new Event("change")); });
  const t0 = Date.now();
  while (Date.now() - t0 < 120000) {
    const t = await page.evaluate(() => document.getElementById("mestabnote").textContent);
    notes.add(t.replace(/\d[\d,]*/g, "#"));
    if (/^Steadied/.test(t)) break;
    await page.waitForTimeout(100);
  }
  const note = await page.evaluate(() => document.getElementById("mestabnote").textContent);
  console.log("  note:", note, "| on the way:", [...notes].filter(t => /Steadying/.test(t)).join(" / "));
  check(/^Steadied \d+ pictures/.test(note), "it says how it steadied the movie");
  check([...notes].some(t => /getting pictures|matching pictures/.test(t)), "it showed its progress while it worked");
  const moves = await page.evaluate(() => cassiniMovieEdit.state.frames.map(e => cassiniFilmSteady.at(e.id)));
  check(moves.filter(Boolean).length >= n - 1, `frames moved: ${moves.filter(Boolean).length} of ${n}`);
  console.log("  moves (px at 1024):", moves.map(m => m ? `${(m[0] * 1024).toFixed(1)},${(m[1] * 1024).toFixed(1)}` : "-").join(" "));
  check(/(^|&)stab=12(&|$)/.test(await page.evaluate(() => cassiniMovieEdit.recipe())), "the recipe keeps it (stab=12)");
  const body = await page.evaluate(() => cassiniFilmSteady.body());
  check(/^steadied=N\d+_\d:-?\d+:-?\d+(,N\d+_\d:-?\d+:-?\d+)+$/.test(body), `the moves go with a server film (${body.length} bytes)`);
  await frames("on");

  // the film made by the frame server gets the moves in its body (the rig keeps it)
  await page.evaluate(async () => {
    const FS = window.cassiniFilmSteady;
    await fetch(`${location.origin}/export?from=x`, { method: "POST", body: FS.body(), headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  });
  // Reset: as Settings has it (on by itself, for this moon)
  await page.evaluate(() => document.getElementById("mefrclear").click());
  await page.waitForTimeout(800);
  check(await page.evaluate(() => cassiniMovieEdit.state.stab === null && !!cassiniFilmSteady.at(cassiniMovieEdit.state.frames[3].id) && document.getElementById("mestabv").textContent === "Auto · 12 pictures"), "Reset puts it back as Settings has it (on by itself)");
  // undo brings it back, at once (the matching is kept)
  await page.evaluate(() => document.getElementById("meundo").click());
  await page.waitForTimeout(1200);
  check(await page.evaluate(() => cassiniMovieEdit.state.stab === 12 && !!cassiniFilmSteady.at(cassiniMovieEdit.state.frames[3].id)), "undo puts it back without matching again");
  await br.close();
})();
