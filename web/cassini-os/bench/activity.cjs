// Checks "What Cassini is doing" (src/activity.html) against things that are known to have happened in 2005, and saves
// a still of each. Needs the replay data for 2005 with its pointing (data/attitude).
//   node activity.cjs ORIGIN OUT        ORIGIN like http://127.0.0.1:8765, OUT a folder for the stills
//   SOFTWARE=1 SwiftShader (cloud containers); THREE_DIR=.../three/package serves three.js locally
// Checks, each from the page's own read-out at that moment (cassiniActivity.now()):
//   - 14 Jan 10:00  dish on Titan, receiving Huygens (the probe is on its parachute)
//   - 15 Feb 07:00 and 7 Sep 08:15  dish on Titan (the T3 and T7 radar passes)
//   - 3 May 03:30  the radio signal crossing the rings (the first radio occultation of the rings, Rev 7)
//   - 20 Aug 17:30  behind Saturn, the signal blocked (Rev 13)
//   - 3 May 05:00  Earth behind Saturn and the dish held on Saturn's limb, following the bent signal (Rev 7)
//   - 1 Jun 00:00  dish on Earth, with a light time between 67 and 84 minutes (Saturn's distance that year)
//   - 9 Mar 09:00  pointed at Enceladus (the close flyby)
//   - the spans of the months loaded around 3 May: the dish on Earth for 30 to 50% of the time, and the eight ring
//     occultations of May to September on their days when their months are loaded
//   - 1 Jun 00:00 (dish on Earth): Earth counts as on stage and its tag shows when the camera faces it, with the
//     range in it; twelve hours later (pointed at the rings) and with the setting off it does not
//   - the strip's legend keys survive the cameras rewriting the legend, and go with the setting; the strip's tooltip
//     reads a span by its own time
let pw; try { pw = require("playwright-core"); } catch (e) { pw = require("playwright"); }
const fs = require("fs"), path = require("path");
const [origin, out] = process.argv.slice(2);
const env = process.env;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
const CASES = [
  ["2005-01-14T10:00:00", 3, "TITAN", /receiving Huygens/],
  ["2005-02-15T07:00:00", 3, "TITAN", /Dish on Titan/],
  ["2005-09-07T08:15:00", 3, "TITAN", /Dish on Titan/],
  ["2005-05-03T03:30:00", 2, "RINGS", /Radio through the rings/],
  ["2005-08-20T17:30:00", 2, "SATURN", /Behind Saturn/],
  ["2005-05-03T05:00:00", 6, "SATURN", /Radio through Saturn's atmosphere/],
  ["2005-06-01T00:00:00", 1, null, /Dish on Earth · data takes (6[7-9]|7\d|8[0-4]) min/],
  ["2005-03-09T09:00:00", 5, "ENCELADUS", /Pointed at Enceladus/],
];
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader");
  const br = await pw.chromium.launch({ args });
  const page = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); process.exitCode = 1; });
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); localStorage.setItem("cassini-os-tour-v1", JSON.stringify({ tour: 1, tips: {} })); } catch (e) {} });
  const open = async utc => {
    await page.goto(`${origin}/?t=${utc}&view=cassini&speed=600&play=0`);
    await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 300000 });
    await page.evaluate(() => cassiniSettings.set("interface.autohide", false));
    await page.waitForFunction("state.pointed && !!document.getElementById('mact')", null, { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(1500);
  };
  for (const [utc, kind, body, text] of CASES) {
    await open(utc);
    const r = await page.evaluate(() => ({ a: cassiniActivity.now(), text: (document.getElementById("mact") || {}).textContent || "" }));
    ok(r.a.kind === kind && r.a.body === body && text.test(r.text), `${utc}: ${r.text || "(nothing)"}`);
    await page.mouse.move(700, 400);
    await page.screenshot({ path: path.join(out, utc.slice(0, 13).replace("T", "_") + "h.png") });
  }
  // the spans of the loaded months
  await open("2005-05-03T03:30:00");
  await page.waitForFunction("cassiniActivity.spans().n > 0 && !cassiniActivity.busy()", null, { timeout: 120000 });
  const s = await page.evaluate(() => {
    const s = cassiniActivity.spans(), share = {}, occ = [];
    let all = 0;
    for (let k = 0; k + 1 < att.count; k++) { const dt = att.t[k + 1] - att.t[k]; if (dt > 0 && dt <= GAP_S) all += dt; }
    for (let i = 0; i < s.n; i++) {
      const k = s.C[i] & 15; share[k] = (share[k] || 0) + (s.T1[i] - s.T0[i]) / all;
      if (k === 2 && s.names[(s.C[i] >> 4) - 1] === "RINGS" && s.T1[i] - s.T0[i] > 1800) occ.push(new Date(etToMs(s.T0[i])).toISOString().slice(0, 10));
    }
    return { share, occ: [...new Set(occ)], from: new Date(etToMs(att.start)).toISOString().slice(0, 10), to: new Date(etToMs(att.end)).toISOString().slice(0, 10) };
  });
  ok(s.share[1] > 0.3 && s.share[1] < 0.5, `dish on Earth ${(s.share[1] * 100).toFixed(1)}% of ${s.from} to ${s.to}`);
  const known = ["2005-05-03", "2005-05-21", "2005-06-08", "2005-06-26", "2005-07-15", "2005-08-02", "2005-08-20", "2005-09-05"].filter(d => d >= s.from && d <= s.to);
  ok(known.every(d => s.occ.includes(d)) && s.occ.every(d => known.includes(d)), `ring occultations on ${s.occ.join(", ")} (known: ${known.join(", ")})`);
  await page.evaluate(() => setView(2 * 86400, state.et));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, "strip_2005-05-03.png") });
  // Earth's marker: look back along the line from Earth through Cassini, a little off to the side
  const earth = async (utc, on) => {
    await page.evaluate(([u, on]) => { cassiniSettings.set("view.earthMarker", on); setFocus("CASSINI"); setTime(utcToEt(u)); setView(5 * 86400, state.et); document.getElementById("moments").hidden = true; }, [utc, on]);
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      const e = meshes.EARTH.group.position.clone().sub(cassini.position).normalize(), d = camera.position.distanceTo(cassini.position);
      const side = new THREE.Vector3().crossVectors(e, new THREE.Vector3(0, 1, 0)).normalize();
      camera.position.copy(cassini.position).addScaledVector(e, -d * 0.9).addScaledVector(side, d * 0.35); camera.lookAt(cassini.position); cassiniPerf.invalidate();
    });
    await page.waitForTimeout(1500);
    return page.evaluate(() => ({ stage: shown("EARTH"), tag: !labels.EARTH.hidden, text: labels.EARTH.textContent, href: location.href }));
  };
  const e1 = await earth("2005-06-01T00:00:00", true);
  ok(e1.stage && e1.tag && /Earth.*r 1,4\d\d,\d{3},\d{3} km/i.test(e1.text), `dish on Earth: Earth's tag shows ("${e1.text.replace(/^Earth/i, "Earth · ")}") ${e1.href}`);
  await page.screenshot({ path: path.join(out, "earth_marker_2005-06-01.png") });
  const e2 = await earth("2005-06-01T12:00:00", true), e3 = await earth("2005-06-01T00:00:00", false);
  ok(!e2.stage && !e2.tag, "twelve hours later, pointed at the rings: no Earth tag");
  ok(!e3.stage && !e3.tag, "with the setting off: no Earth tag");
  // the strip's legend keys: still there after the cameras rewrite the legend for another month, gone with the setting
  const keys = () => page.evaluate(() => document.querySelectorAll("#lkeys [data-activity]").length);
  const keysAre = n => page.waitForFunction(n => document.querySelectorAll("#lkeys [data-activity]").length === n, n, { timeout: 30000 }).then(() => true, () => false);
  await page.evaluate(() => { setTime(utcToEt("2005-08-20T17:30:00")); setView(2 * 86400, state.et); });
  await page.waitForFunction("cassiniActivity.spans().att === att && cassiniActivity.spans().n > 0 && !cassiniActivity.busy()", null, { timeout: 120000 }).catch(() => {});
  const k1 = await keysAre(5);
  await page.evaluate(() => { document.getElementById("lkeys").innerHTML = "<span><i></i>NAC</span>"; setView(2 * 86400 + 60, state.et); });   // as the cameras do on a month load
  const k2 = await keysAre(5);
  await page.evaluate(() => { cassiniSettings.set("view.activity", false); setView(2 * 86400, state.et); });
  const k3 = await keysAre(0);
  await page.evaluate(() => { cassiniSettings.set("view.activity", true); setView(2 * 86400 + 60, state.et); });
  const k4 = await keysAre(5);
  ok(k1 && k2 && k3 && k4, `the strip's legend: there in another month (${k1}), back after the legend is rewritten (${k2}), gone with the setting off (${k3}), back with it on (${k4}); now ${await keys()} keys`);
  // the strip's tooltip words are for the time under the pointer, not the clock's
  const w = await page.evaluate(() => [cassiniActivity.words({ kind: cassiniActivity.KINDS.DISH, body: "TITAN" }, utcToEt("2005-01-14T10:00:00"))[0], cassiniActivity.words({ kind: cassiniActivity.KINDS.DISH, body: "TITAN" })[0]]);
  ok(/receiving Huygens/.test(w[0]) && /radar or radio science/.test(w[1]), "a Titan dish span on 14 January 2005 reads as receiving Huygens whatever the clock says");
  await br.close();
})();
