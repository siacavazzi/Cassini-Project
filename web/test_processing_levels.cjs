// The processing level bar under the camera windows, driven in a browser: at a moment, each window stepped through
// Raw, Processed, Color and Full; what each picture was made from (its src), its tag, and a screenshot of each.
// Run: node web/test_processing_levels.cjs http://127.0.0.1:PORT OUT TIME [--video]  (a frame server with replay data and a
// cache holding that moment; TIME e.g. 1999-08-18T02:10:45, the Moon flyby's first color set)
const { chromium } = require("playwright");
const fs = require("fs");
const [base, out, t] = process.argv.slice(2).filter(a => !a.startsWith("--")), video = process.argv.includes("--video");
fs.mkdirSync(out, { recursive: true });
const check = (ok, what) => { console.log(ok ? "ok" : "FAIL", what); if (!ok) process.exitCode = 1; };
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: video ? 1 : 2, ...(video ? { recordVideo: { dir: out, size: { width: 1440, height: 900 } } } : {}) });
  const page = await ctx.newPage();
  await page.addInitScript(() => { try { const k = "cassini-os-settings-v1", s = JSON.parse(localStorage.getItem(k) || "{}"); s["interface.tips"] = false; s["interface.idleDelay"] = 600; localStorage.setItem(k, JSON.stringify(s)); } catch (e) {} });
  page.on("pageerror", e => { console.log("PAGEERROR", e.message); process.exitCode = 1; });
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.goto(`${base}/?t=${t}&play=0&welcome=0&tour=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  await page.waitForTimeout(6000);
  const has = await page.evaluate(() => !!document.querySelector("#imgcard .levels"));
  if (!has) { console.log("no level bar (before page)"); await page.screenshot({ path: `${out}/page.png` }); await ctx.close(); await br.close(); return; }
  for (const cam of ["imgcard", "wacard"]) {
    const vis = await page.evaluate(c => { const w = document.getElementById(c); return !!w && !w.hidden && w.querySelector(".well").classList.contains("has-frame"); }, cam);
    if (!vis) { console.log(cam, "no picture up"); continue; }
    for (const lv of ["raw", "processed", "color", "full"]) {
      await page.click(`#${cam} .levels button[data-v="${lv}"]`);
      try { await page.waitForFunction(([c, lv]) => { const w = document.getElementById(c), s = w.querySelector(".shot"), src = s.dataset.src || "";
        const okSrc = lv === "raw" ? /\/frames\/[NW]\d+_\d+\.webp/.test(src) : lv === "processed" ? src.includes("/frames/processed/") : true;
        return okSrc && s.complete && s.naturalWidth > 0 && !w.querySelector(".well").classList.contains("loading"); }, [cam, lv], { timeout: 90000 }); } catch (e) {}
      await page.waitForTimeout(2500);
      const r = await page.evaluate(c => { const w = document.getElementById(c); return { src: (w.querySelector(".shot").dataset.src || "").replace(/^https?:\/\/[^/]+/, ""), tag: w.querySelector(".kindtag").textContent, checked: w.querySelector('.levels [aria-checked="true"]').dataset.v, mosaic: w.querySelector(".well").classList.contains("mosaic") }; }, cam);
      console.log(cam, lv, JSON.stringify(r));
      check(r.checked === lv, `${cam} ${lv}: bar shows ${r.checked}`);
      if (lv === "raw") check(/^\/frames\/[NW]\d+_\d+\.webp/.test(r.src) && !r.mosaic, `${cam} raw: archive frame`);
      if (lv === "processed") check(r.src.startsWith("/frames/processed/") && !r.mosaic, `${cam} processed: pipeline frame`);
      if (lv === "color") check((r.src.startsWith("/frames/color.webp") || r.src.startsWith("/frames/processed/")) && !r.mosaic, `${cam} color: color set or processed frame, no mosaic/movie`);
      const box = await page.locator(`#${cam}`).boundingBox();
      await page.screenshot({ path: `${out}/${cam}_${lv}.png`, clip: box });
      if (video) await page.waitForTimeout(1500);
    }
  }
  // Settings > Processing > Processing level: every window without its own level follows it
  await page.evaluate(() => cassiniSettings.set("cameras.level", "raw"));
  await page.waitForTimeout(4000);
  const g = await page.evaluate(() => ["imgcard", "wacard"].map(c => { const w = document.getElementById(c); return [w.querySelector('.levels [aria-checked="true"]').dataset.v, (w.querySelector(".shot").dataset.src || "").replace(/^https?:\/\/[^/]+/, "")]; }));
  console.log("settings raw", JSON.stringify(g));
  check(g.every(([v, src]) => v === "raw" && /^\/frames\/[NW]\d+_\d+\.webp/.test(src)), "Settings level Raw: both windows raw");
  await page.evaluate(() => cassiniSettings.set("cameras.level", "full"));
  await page.screenshot({ path: `${out}/page.png` });
  await ctx.close(); await br.close();
})();
