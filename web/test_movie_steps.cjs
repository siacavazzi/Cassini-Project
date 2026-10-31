// Movie mode steps from one picture the windows show to the next: a NAC and a WAC frame taken together are one
// step (both windows change at once, and a step back skips the pair whole), and in a body's view the film steps
// through that body's pictures only. Run: node web/test_movie_steps.cjs PORT THREE_DIR [UTC]
// (the port serving Cassini OS with replay data and a frame server or a fake one; THREE_DIR an `npm pack three@0.128.0`
// unpacked, for when the CDN is blocked; UTC a time near NAC + WAC pairs, default the 2005-02-17 Enceladus flyby)
const { chromium } = require("playwright");
const [port, three, utc] = process.argv.slice(2);
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage(), errors = [];
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); errors.push(e.message); });
  await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(() => { try { localStorage.clear(); localStorage.setItem("cassini-os-settings-v1", JSON.stringify({ "interface.autohide": false, "interface.tips": false })); } catch (e) {} });
  await page.goto(`http://127.0.0.1:${port}/?t=${utc || "2005-02-17T03:00:00"}&view=saturn&play=0&movie=1`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  await page.waitForTimeout(2500);

  // pairs: every step forward from the clock for 40 steps; no step may leave a pair half taken
  const r = await page.evaluate(() => {
    const F = cassiniFeeds, steps = [];
    let t = state.et;
    for (let i = 0; i < 40; i++) { const n = F.nextPicture(t); if (!isFinite(n)) break; steps.push(n); t = n; }
    const back = [];
    for (let i = 0; i < steps.length - 1; i++) back.push(F.prevPicture(steps[i + 1]));
    // a step that lands between the two frames of a pair: another camera's frame within 2 s after it
    const torn = steps.filter(s => ["N", "W"].some(cam => { const f = F.framesOf(cam); return f.et.some(e => e > s + 1e-3 && e <= s + 2); }));
    const pairs = steps.filter(s => ["N", "W"].every(cam => F.framesOf(cam).et.some(e => e <= s && e > s - 2)));
    return { n: steps.length, torn: torn.length, pairs: pairs.length, backOk: back.every((b, i) => Math.abs(b - steps[i]) < 1e-3) };
  });
  ok(r.n > 10 && r.pairs > 0, `${r.n} steps, ${r.pairs} of them a NAC + WAC pair taken together`);
  ok(r.torn === 0, `no step stops between the two frames of a pair (${r.torn})`);
  ok(r.backOk, "a step back lands on the step before, pairs whole");

  // body view: the film steps through the body's pictures only, and every step is one of them
  const body = await page.evaluate(() => { const c = {}; for (let i = 0; i < catalog.target.length; i++) if (catalog.et[i] > state.et) c[catalog.target[i]] = (c[catalog.target[i]] || 0) + 1; return Object.entries(c).filter(([b]) => b && b !== "SATURN" && b !== "SKY").sort((a, b) => b[1] - a[1])[0][0]; });
  await page.evaluate(b => cassiniBodyMode.enter(b), body);
  await page.waitForTimeout(2500);
  const b = await page.evaluate(b => {
    const t0 = state.et, ts = [];
    let et = t0;
    for (let i = 0; i < 25; i++) { const n = window.studyAdvance(et, 1, 600); cassiniMovie.state.stepAt = -1e9; if (n === et) continue; ts.push(n); et = n; }
    const of = t => { for (let i = 0; i < catalog.et.length; i++) if (Math.abs(catalog.et[i] - t) < 1e-3) return catalog.target[i]; return null; };
    return { n: ts.length, other: ts.filter(t => of(t) !== b).map(of) };
  }, body);
  ok(b.n >= 10 && b.other.length === 0, `${body} view: ${b.n} steps, all ${body} pictures (others: ${JSON.stringify(b.other.slice(0, 5))})`);
  ok(errors.length === 0, "no page errors");
  await br.close();
})();
