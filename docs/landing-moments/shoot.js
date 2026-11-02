// Screenshots of candidate landing moments, for picking where a bare-URL visitor lands.
// Run on the Mini against the live site (light: it only views cached pictures):
//   cd ~/Documents/landing-moments && node shoot.js http://127.0.0.1:8765 moments.json
// For each moment it opens the link playing, as a new visitor would, and saves the screen at 3, 15, 30 and 50 s
// after the page has loaded (<slug>_03.jpg ...), plus moments_done.json with the mission time at each shot.
const { chromium } = require("playwright");
const fs = require("fs");
const [host, list] = process.argv.slice(2);
const SHOTS = [3, 15, 30, 50];
(async () => {
  const moments = JSON.parse(fs.readFileSync(list, "utf8")), done = [];
  const br = await chromium.launch({ headless: true, args: ["--ignore-gpu-blocklist", "--enable-gpu"] });
  for (const m of moments) {
    const ctx = await br.newContext({ viewport: { width: 1600, height: 1000 } });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
    const url = `${host}/?${m.q}`, row = { slug: m.slug, url, at: [] };
    try {
      const t0 = Date.now();
      await page.goto(url);
      await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
      row.load_s = (Date.now() - t0) / 1000;
      const start = Date.now();
      for (const s of SHOTS) {
        await page.waitForTimeout(Math.max(0, s * 1000 - (Date.now() - start)));
        await page.mouse.move(800 + (s % 2), 500);
        await page.screenshot({ path: `${m.slug}_${String(s).padStart(2, "0")}.jpg`, type: "jpeg", quality: 82 });
        row.at.push([s, await page.evaluate(() => new Date(etToMs(state.et)).toISOString().slice(0, 19))]);
      }
    } catch (e) { row.error = String(e); }
    done.push(row); console.log(JSON.stringify(row));
    fs.writeFileSync("moments_done.json", JSON.stringify(done, null, 1));
    await ctx.close();
  }
  await br.close();
})();
