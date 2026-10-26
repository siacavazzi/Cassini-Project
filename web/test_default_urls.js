// Settings > Processing must not change what the page asks for with every step on: the pre-built cache is named by
// those addresses. Opens two builds of Cassini OS at the same paused moments with fresh settings and compares every
// /frames/ and /reel/ address each requests (by form: route and query, frame ids aside).
// Run: node web/test_default_urls.js http://127.0.0.1:BEFORE http://127.0.0.1:AFTER [THREE_DIR]
// (each port serving a build's index.html with replay data, a frame server or a fake one; THREE_DIR an
// `npm pack three@0.128.0` unpacked, for when the CDN is blocked)
const { chromium } = require("playwright");
const [before, after, three] = process.argv.slice(2);
const MOMENTS = ["2005-02-17T05:46:09&view=enceladus", "2005-02-15T06:10:00&view=titan", "2005-03-09T09:08:00&view=enceladus",
  "2005-07-14T19:55:00&view=enceladus", "2005-11-26T22:30:00&view=rhea"];
async function asked(br, base, moment) {
  const page = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  const urls = new Set();
  let last = Date.now();
  page.on("request", r => { const u = new URL(r.url()); if (/^\/(frames|reel)\//.test(u.pathname)) { urls.add(u.pathname + u.search); last = Date.now(); } });
  await page.goto(`${base}/?t=${moment}&play=0`);
  await page.waitForFunction("document.getElementById('loading').hidden", null, { timeout: 240000 });
  // until the windows have asked for everything: no new picture for 5 s (at most a minute)
  const t0 = Date.now();
  while (Date.now() - last < 5000 && Date.now() - t0 < 60000) await page.waitForTimeout(500);
  await page.close();
  return [...urls].sort();
}
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let bad = 0, total = 0;
  for (const m of MOMENTS) {
    const [a, b] = [await asked(br, before, m), await asked(br, after, m)];
    total += b.length;
    // which frames a window reaches before the page goes quiet varies a little from load to load (look-ahead timing),
    // so the addresses are compared by form: the route and every query parameter, the frame ids left out
    const form = u => { const x = new URL(u, "http://h"); x.pathname = x.pathname.replace(/[NW]\d{10}_\d+/g, "ID"); if (x.searchParams.has("ids")) x.searchParams.set("ids", "ID"); return x.pathname + "?" + x.searchParams.toString(); };
    const fa = new Set(a.map(form)), fb = new Set(b.map(form));
    const gone = [...fa].filter(u => !fb.has(u)), added = [...fb].filter(u => !fa.has(u));
    const same = a.filter(u => b.includes(u)).length;
    console.log(m, `before ${a.length} after ${b.length} (${same} identical), forms ${fa.size}/${fb.size}`, gone.length || added.length ? "DIFFERENT" : "same");
    if (gone.length || added.length) { bad++; console.log("  only before:", gone, "\n  only after:", added); }
    if (b.some(u => u.includes("off="))) { bad++; console.log("  off= asked at defaults"); }
  }
  await br.close();
  console.log(bad ? "FAIL" : `ok (${total} addresses, every one in a form the build before asks for)`);
  process.exit(bad ? 1 : 0);
})();
