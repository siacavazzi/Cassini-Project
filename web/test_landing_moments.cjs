// Landing moments (settings.html, window.cassiniLandings): a visit with no moment of its own lands on one of a few
// famous moments at random, written into the address as a link (time and the moment's own speed); a
// shared link still opens on its own moment; Settings > Start time pins one moment, or an older fixed start time,
// which opens the old way (time only, the Starting speed setting).
// Run: node web/test_landing_moments.cjs http://127.0.0.1:PORT [THREE_DIR]
// (the port serving Cassini OS with replay data, a frame server or a fake one; THREE_DIR an `npm pack three@0.128.0`
// unpacked, for when the CDN is blocked)
const { chromium } = require("playwright");
const [base, three] = process.argv.slice(2);
const KEY = "cassini-os-settings-v1";
async function open(br, path, seed, keepLast, slices) {
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  // a picture cache of some years only (Settings > Only years with pictures built)
  if (slices) await page.route("**/frames/slices.json", r => r.fulfill({ status: 200, body: JSON.stringify({ spans: slices }), headers: { "Content-Type": "application/json" } }));
  if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
  await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  await page.addInitScript(([key, seed, last]) => {
    localStorage.clear();
    if (seed) localStorage.setItem(key, JSON.stringify(seed));
    if (last) localStorage.setItem("cassini-os-landing", last);
  }, [KEY, seed, keepLast]);
  await page.goto(`${base}/${path}`);
  await page.waitForFunction(() => document.getElementById("loading").hidden && typeof state !== "undefined", null, { timeout: 240000 });
  await page.waitForTimeout(700);
  const r = await page.evaluate(() => ({
    t: new Date(etToMs(state.et)).toISOString().slice(0, 19), speed: state.speed, follow: state.follow, focus: state.focus,
    landing: window.cassiniLanding || null, list: window.cassiniLandings, q: new URLSearchParams(location.search).toString()
  }));
  await ctx.close();
  return r;
}
(async () => {
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let bad = 0;
  const check = (name, ok, got) => { bad += !ok; console.log(`${ok ? "ok  " : "FAIL"} ${name}${got !== undefined ? ": " + JSON.stringify(got) : ""}`); };
  const near = (a, b, s) => Math.abs(Date.parse(a + "Z") - Date.parse(b + "Z")) <= s * 1000;

  // a bare URL, several fresh visits: each lands on a listed moment, at its time and speed, the view on Cassini
  const seen = new Set();
  let list;
  for (let k = 0; k < 6; k++) {
    const r = await open(br, "", null);
    list = r.list;
    const l = r.landing;
    check(`bare visit ${k + 1} lands on a listed moment`, !!l && list.some(m => m.t === l.t), l && l.label);
    if (!l) continue;
    seen.add(l.t);
    check(`  ... opens at its time (${l.t})`, near(r.t, l.t, 8 * l.speed), r.t);
    check(`  ... at its speed`, r.speed === l.speed, r.speed);
    check(`  ... the view on Cassini`, r.focus === "CASSINI");
    check(`  ... and the address holds it as a link`, !!new URLSearchParams(r.q).get("t") && new URLSearchParams(r.q).get("speed") === String(l.speed), r.q);
  }
  check("In Saturn's Shadow is one of the moments", list.some(m => m.t === "2006-09-15T14:28:00" && /Saturn's Shadow/.test(m.label)));
  check("random visits do not all land in the same place", seen.size > 1, seen.size);
  // no landing plays into a cutscene in its first minutes: those are for visitors who go to them (Sam, 2026-11-01)
  const CUTS = [["Saturn arrival", "2004-07-01T01:12:00"], ["Huygens release", "2004-12-25T02:00:00"], ["Huygens entry", "2005-01-14T09:05:52"], ["Grand Finale", "2017-09-15T10:31:00"]];
  for (const l of list) {
    const a = Date.parse(l.t + "Z"), b = a + 300 * l.speed * 1000;   // five minutes of playback
    const hit = CUTS.find(([, c]) => Date.parse(c + "Z") >= a - 86400e3 && Date.parse(c + "Z") <= b);
    check(`${l.label}: no cutscene in its first five minutes`, !hit, hit && hit[0]);
  }
  // not the same moment twice in a row on one browser
  for (let k = 0; k < 4; k++) {
    const last = list[k % list.length].t, r = await open(br, "", null, last);
    check(`last visit ${list[k % list.length].label}: this one lands elsewhere`, r.landing && r.landing.t !== last, r.landing && r.landing.label);
  }
  // a shared link wins
  const s = await open(br, "?t=2008-03-12T19:06:00&view=enceladus&speed=60&play=0", null);
  check("a shared link opens on its own moment", !s.landing && near(s.t, "2008-03-12T19:06:00", 2) && s.focus === "ENCELADUS", [s.t, s.focus]);
  // pinned in Settings: a listed moment opens there every time, at its speed
  const pin = list[2];
  for (let k = 0; k < 2; k++) {
    const r = await open(br, "", { "playback.start": pin.t });
    check(`pinned ${pin.label}, visit ${k + 1}`, r.landing && r.landing.t === pin.t && r.speed === pin.speed && near(r.t, pin.t, 8 * pin.speed), [r.t, r.speed]);
  }
  // an older fixed start time still opens the old way: its time, the Starting speed setting, no landing
  const old = await open(br, "", { "playback.start": "2004-07-01T00:00:00", "playback.speed": 3600 });
  check("older start time (Saturn arrival 00:00) opens the old way", !old.landing && near(old.t, "2004-07-01T00:00:00", 8 * 3600) && old.speed === 3600, [old.t, old.speed]);
  // a browser that saved the old default (In Saturn's Shadow) before the defaults were kept follows the new one
  const was = await open(br, "", { "playback.start": "2006-09-15T14:28:00" });
  check("saved at the old default: lands at random now", !!was.landing, was.landing && was.landing.label);
  // ...but one that chose In Saturn's Shadow while the default was random keeps it
  const chose = await open(br, "", { "playback.start": "2006-09-15T14:28:00", "~defaults": { "playback.start": "random" } });
  check("chose In Saturn's Shadow: stays there", chose.landing && chose.landing.t === "2006-09-15T14:28:00", chose.landing && chose.landing.label);
  // a picture cache of 2017 only: a random landing keeps to the landings inside it
  for (let k = 0; k < 3; k++) {
    const r = await open(br, "", null, null, [["2017-01-01T00:00:00", null]]);
    check(`cache of 2017 only, visit ${k + 1}: lands on a 2017 moment`, r.landing && /^2017/.test(r.landing.t) && near(r.t, r.landing.t, 8 * r.landing.speed) && r.speed === r.landing.speed
      && new URLSearchParams(r.q).get("speed") === String(r.landing.speed), [r.landing && r.landing.label, r.t, r.speed]);
  }
  // ... and one with no landing inside it starts on its first moment, as before
  const none = await open(br, "", null, null, [["2003-01-01T00:00:00", "2004-01-01T00:00:00"]]);
  check("cache of 2003 only: opens in 2003", /^2003/.test(none.t), none.t);
  await br.close();
  console.log(bad ? `${bad} FAILED` : "ok");
  process.exit(bad ? 1 : 0);
})();
