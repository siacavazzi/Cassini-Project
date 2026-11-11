// Checks "Seen so far" and "Pictures of a place" (src/coverage.html) against Enceladus in 2005, and saves stills.
// Needs the replay data for 2005 with its pointing, and data/coverage built from it:
//   python web/replay/build_coverage.py --data web/replay/data --years 2005-2006
//   node coverage.cjs ORIGIN OUT        ORIGIN like http://127.0.0.1:8765, OUT a folder for the stills
//   SOFTWARE=1 SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
// Checks:
//   - the share of Enceladus seen never falls as the clock runs, and the share seen in detail rises over the
//     14 July 2005 flyby (the south pole, at 168 km)
//   - with Seen so far on, Enceladus's shader is the patched one and is switched on; off, it is switched off
//   - the sharpest picture of 80 S, 150 E (the south polar terrain) is from 14 July 2005, at under 200 m per pixel
//   - a click on the globe opens the window with rows; a row puts the clock on its picture, paused
let pw; try { pw = require("playwright-core"); } catch (e) { pw = require("playwright"); }
const fs = require("fs"), path = require("path");
const [origin, out] = process.argv.slice(2);
const env = process.env;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await pw.chromium.launch({ args });
  const page = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); process.exitCode = 1; });
  page.on("console", m => { if (m.type() === "error" && /shader|WebGL|program/i.test(m.text())) { console.log("CONSOLE", m.text().slice(0, 400)); process.exitCode = 1; } });
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: 1, tips: {} })); } catch (e) {} });
  await page.goto(`${origin}/?t=2005-07-15T06:00:00&view=enceladus&speed=600&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 300000 });
  await page.evaluate(() => { cassiniSettings.set("interface.autohide", false); cassiniSettings.set("view.seenSoFar", true); document.getElementById("moments").hidden = true; });
  await page.waitForFunction("cassiniCoverage.patched('ENCELADUS')", null, { timeout: 120000 });
  // look at the globe from over 50 S, 150 E (where Cassini came in from), three radii out
  const look = () => page.evaluate(() => {
    const m = meshes.ENCELADUS.mesh, la = -50 * Math.PI / 180, lo = 150 * Math.PI / 180;
    camera.position.copy(new THREE.Vector3(Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)).applyQuaternion(m.quaternion).multiplyScalar(1.3));
    cassiniPerf.invalidate();
  });
  const s = await page.evaluate(() => {
    const days = [], t0 = utcToEt("2005-01-01T00:00:00");
    for (let d = 0; d <= 364; d++) days.push(cassiniCoverage.seen("ENCELADUS", t0 + d * 86400));
    return { days, before: cassiniCoverage.seen("ENCELADUS", utcToEt("2005-07-14T00:00:00")), after: cassiniCoverage.seen("ENCELADUS", utcToEt("2005-07-15T00:00:00")),
      on: meshes.ENCELADUS.mat.uniforms.covOn.value, text: document.getElementById("mcov").textContent };
  });
  ok(s.days.every((v, i) => !i || (v[0] >= s.days[i - 1][0] && v[1] >= s.days[i - 1][1])), "the share of Enceladus seen never falls through 2005");
  ok(s.after[1] > s.before[1] + 0.01, `seen in detail: ${(s.before[1] * 100).toFixed(1)}% before the 14 July flyby, ${(s.after[1] * 100).toFixed(1)}% after`);
  ok(s.on === 1 && /Enceladus · \d+% seen so far · \d+% in detail/.test(s.text), `Seen so far is on: "${s.text}"`);
  for (const [utc, name] of [["2005-07-13T00:00:00", "seen_2005-07-13"], ["2005-07-15T06:00:00", "seen_2005-07-15"]]) {
    await page.evaluate(u => setTime(utcToEt(u)), utc); await page.waitForTimeout(1200); await look(); await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(out, name + ".png") });
  }
  await page.evaluate(() => cassiniSettings.set("view.seenSoFar", false)); await page.waitForTimeout(1500);
  ok(await page.evaluate(() => meshes.ENCELADUS.mat.uniforms.covOn.value) === 0, "off: the shader draws the whole map again");
  await page.screenshot({ path: path.join(out, "seen_off.png") });

  const p = await page.evaluate(async () => (await cassiniCoverage.pick("ENCELADUS", -80, 150))[0]);
  const day = p ? await page.evaluate(et => new Date(etToMs(et)).toISOString().slice(0, 10), p.et) : "";
  ok(p && day === "2005-07-14" && p.res_m < 200, `sharpest picture of 80 S, 150 E: ${p ? `${p.id}, ${day}, ${p.res_m} m per pixel from ${p.range_km} km` : "none"}`);
  // a click in the middle of the globe
  const at = await page.evaluate(() => { const v = new THREE.Vector3().project(camera), r = document.getElementById("gl").getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; });
  await page.mouse.click(at[0], at[1]);
  await page.waitForFunction("cassiniCoverage.place().rows.length > 0 && document.querySelectorAll('#placewin li button').length > 0", null, { timeout: 30000 }).catch(() => {});
  const w = await page.evaluate(() => ({ moon: cassiniCoverage.place().moon, lat: cassiniCoverage.place().lat, n: document.querySelectorAll("#placewin li button").length, head: document.querySelector("#placewin .plhead").textContent }));
  ok(w.moon === "ENCELADUS" && w.n > 0 && Math.abs(w.lat + 50) < 12, `a click on the globe: ${w.head}`);
  await page.screenshot({ path: path.join(out, "place.png") });
  await page.evaluate(() => { setPlaying(true); document.querySelector("#placewin li button").click(); });
  await page.waitForTimeout(2500);
  const j = await page.evaluate(() => ({ d: Math.abs(state.et - cassiniCoverage.place().rows[0].et), playing: state.playing, href: location.href }));
  ok(j.d < 1 && !j.playing, `its first row puts the clock on the picture, paused: ${j.href}`);
  await page.screenshot({ path: path.join(out, "place_picture.png") });
  await br.close();
})();
