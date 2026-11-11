// Checks that "What Cassini is doing", "Seen so far" and "Pictures of a place" (src/activity.html, src/coverage.html)
// start cleanly whatever settings a visitor has saved, and stay quiet on a site whose coverage table is not built.
// The other two checks clear the saved settings first, so they only ever see the defaults.
// Needs the replay data for 2005 with its pointing, and data/coverage built from it (see coverage.cjs).
//   node saved.cjs ORIGIN               ORIGIN like http://127.0.0.1:8765
//   SOFTWARE=1 SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
// Checks:
//   - with each of the five settings saved away from its default (and with all five at once), the page loads with no
//     script error, both modules are in place, and the feature works once the setting is put back
//   - with the table missing (data/coverage answers 404): a visit with the default settings asks for nothing; a
//     click on a moon asks once, a second click straight after does not ask again, and nothing throws; with the table
//     back, a click after the retry pause opens the window, with no reload
//   - with the table missing and Seen so far saved on: one request, not one per frame
let pw; try { pw = require("playwright-core"); } catch (e) { pw = require("playwright"); }
const [origin] = process.argv.slice(2);
const env = process.env;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
const DEFAULTS = { "view.activity": true, "view.radioBeam": true, "view.earthMarker": true, "view.seenSoFar": false, "view.places": true };
const URL = `${origin}/?t=2005-06-01T00:00:00&view=enceladus&speed=600&play=0`;
(async () => {
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await pw.chromium.launch({ args });
  // a fresh visitor with these settings saved; `missing` makes data/coverage answer 404 until it is set to false
  const open = async (saved, gate) => {
    const page = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    const errors = [], asked = [];
    page.on("pageerror", e => errors.push(e.message));
    if (env.THREE_DIR) {
      await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
        r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
      await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
    }
    await page.route("**/data/coverage/**", r => { asked.push(r.request().url().split("/data/coverage/")[1]); return gate && gate.missing ? r.fulfill({ status: 404, body: "" }) : r.continue(); });
    await page.addInitScript(s => {
      try { localStorage.clear(); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: 1, tips: {} })); localStorage.setItem("cassini-os-settings-v1", JSON.stringify(s)); } catch (e) {}
    }, saved);
    await page.goto(URL);
    await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 300000 });
    await page.evaluate(() => { document.getElementById("moments").hidden = true; });
    await page.waitForTimeout(2500);
    return { page, errors, asked };
  };
  const click = async page => {
    const at = await page.evaluate(() => { const v = new THREE.Vector3().project(camera), r = document.getElementById("gl").getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; });
    await page.mouse.click(at[0], at[1]);
  };
  const rows = page => page.evaluate(() => { const w = document.getElementById("placewin"); return w && !w.hidden ? w.querySelectorAll("li button").length : 0; });
  const until = (page, js, ms = 60000) => page.waitForFunction(js, null, { timeout: ms }).then(() => true, () => false);

  // ---- each setting saved away from its default, then all of them ----
  const cases = Object.keys(DEFAULTS).map(k => ({ [k]: !DEFAULTS[k] }));
  cases.push(Object.fromEntries(Object.keys(DEFAULTS).map(k => [k, !DEFAULTS[k]])));
  for (const saved of cases) {
    const name = Object.keys(saved).length > 1 ? "all five" : `${Object.keys(saved)[0]} = ${Object.values(saved)[0]}`;
    const { page, errors } = await open(saved);
    const s = await page.evaluate(keys => ({ took: keys.map(k => cassiniSettings.get(k)), act: !!window.cassiniActivity, cov: !!window.cassiniCoverage }), Object.keys(saved));
    ok(!errors.length && s.act && s.cov && s.took.every((v, i) => v === Object.values(saved)[i]), `saved ${name}: the page starts clean${errors.length ? " (" + errors[0] + ")" : ""}`);
    // back to the defaults, and every feature answers
    await page.evaluate(d => { for (const k in d) cassiniSettings.set(k, d[k]); }, DEFAULTS);
    const line = await until(page, "/Dish on Earth/.test((document.getElementById('mact') || {}).textContent || '') && shown('EARTH')", 20000);
    await click(page);
    const win = await until(page, "(() => { const w = document.getElementById('placewin'); return !!w && !w.hidden && w.querySelectorAll('li button').length > 0; })()");
    await page.evaluate(() => cassiniSettings.set("view.seenSoFar", true));
    const seen = await until(page, "cassiniCoverage.patched('ENCELADUS') && /seen so far/.test(document.getElementById('mcov').textContent)", 120000);
    ok(line && win && seen && !errors.length, `saved ${name}, then the defaults: the status line${line ? "" : " (missing)"}, the places window${win ? "" : " (missing)"} and Seen so far${seen ? "" : " (missing)"} all work${errors.length ? " (" + errors[0] + ")" : ""}`);
    await page.context().close();
  }

  // ---- the table is not built on this site ----
  {
    const gate = { missing: true };
    const { page, errors, asked } = await open({}, gate);
    ok(asked.length === 0, `no table, default settings: nothing is asked for on the visit (${asked.length} requests)`);
    await click(page); await page.waitForTimeout(1500);
    const one = asked.length;
    await click(page); await page.waitForTimeout(1500);
    ok(one === 1 && asked.length === 1 && !errors.length && await rows(page) === 0, `no table: a click asks once (${one}), a second click does not ask again (${asked.length}), nothing throws`);
    gate.missing = false;
    await page.waitForTimeout(16000);   // the first retry pause is 15 s
    await click(page);
    const back = await until(page, "(() => { const w = document.getElementById('placewin'); return !!w && !w.hidden && w.querySelectorAll('li button').length > 0; })()");
    ok(back && !errors.length, "the table appears: a click after the pause opens the window, with no reload");
    await page.context().close();
  }
  {
    const { page, errors, asked } = await open({ "view.seenSoFar": true }, { missing: true });
    await page.waitForTimeout(4000);
    ok(asked.length === 1 && !errors.length, `no table, Seen so far saved on: asked once in the first seconds (${asked.length}), nothing throws`);
    await page.context().close();
  }
  await br.close();
})();
