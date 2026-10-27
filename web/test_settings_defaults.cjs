// Saved settings and changed defaults (settings.html): a value saved at its default follows a new default, a value
// chosen is kept, and a value saved before the defaults were kept with it follows a new default when it was one of
// the defaults the setting had before (was). The burst limit (playback.maxImageRate) went from 5 to 10, was [5].
// Run: node web/test_settings_defaults.cjs http://127.0.0.1:PORT [THREE_DIR]
// (the port serving Cassini OS with replay data, a frame server or a fake one; THREE_DIR an `npm pack three@0.128.0`
// unpacked, for when the CDN is blocked)
const { chromium } = require("playwright");
const [base, three] = process.argv.slice(2);
const KEY = "cassini-os-settings-v1", RATE = "playback.maxImageRate";
async function open(br, seed) {
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  // the settings this browser has saved when the page opens (once: a reload keeps what the page saved since)
  await page.addInitScript(([key, seed]) => {
    if (sessionStorage.getItem("seeded")) return;
    sessionStorage.setItem("seeded", "1");
    localStorage.clear();
    if (seed) localStorage.setItem(key, JSON.stringify(seed));
  }, [KEY, seed]);
  await page.goto(`${base}/?t=2006-09-15T14:30:00&play=0`);
  await ready(page);
  return { ctx, page };
}
const ready = page => page.waitForFunction(k => window.cassiniSettings && cassiniSettings.defined.some(d => d.key === k), RATE, { timeout: 240000 });
const get = (page, key) => page.evaluate(k => cassiniSettings.get(k), key);
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let bad = 0;
  const check = (name, got, want) => { const ok = got === want; bad += !ok; console.log(`${ok ? "ok  " : "FAIL"} ${name}: ${JSON.stringify(got)}${ok ? "" : ` (expected ${JSON.stringify(want)})`}`); };
  const cases = [
    ["fresh browser", null, RATE, 10],
    ["saved 5 before the defaults were kept (the old default)", { [RATE]: 5, "cameras.stale": 3 }, RATE, 10],
    ["... another setting saved with it stays", { [RATE]: 5, "cameras.stale": 3 }, "cameras.stale", 3],
    ["saved 12 before the defaults were kept (a choice)", { [RATE]: 12 }, RATE, 12],
    ["saved 0 before the defaults were kept (no limit)", { [RATE]: 0 }, RATE, 0],
    ["saved at its default 8, the default now 10", { [RATE]: 8, "~defaults": { [RATE]: 8 } }, RATE, 10],
    ["saved 5 while the default was 10", { [RATE]: 5, "~defaults": { [RATE]: 10 } }, RATE, 5],
  ];
  for (const [name, seed, key, want] of cases) {
    const { ctx, page } = await open(br, seed);
    check(name, await get(page, key), want);
    await ctx.close();
  }
  // a choice made on the page is saved with the default it had, and kept after a reload; Restore defaults
  const { ctx, page } = await open(br, null);
  await page.evaluate(k => cassiniSettings.set(k, 5), RATE);
  const saved = await page.evaluate(k => JSON.parse(localStorage.getItem(k)), KEY);
  check("5 chosen: saved with the default it had", saved && saved["~defaults"] && saved["~defaults"][RATE], 10);
  await page.reload(); await ready(page);
  check("5 chosen: after a reload", await get(page, RATE), 5);
  await page.evaluate(() => cassiniSettings.reset());
  check("Restore defaults", await get(page, RATE), 10);
  await ctx.close();
  await br.close();
  console.log(bad ? `${bad} FAILED` : "ok");
  process.exit(bad ? 1 : 0);
})();
