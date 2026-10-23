// Plays a mosaic movie in Cassini OS in headless Chrome and measures what the NAC window shows: how many new
// pictures a second, how far (in frames) the picture on screen is behind the clock, how long the window waited
// for its first mosaic, and how long each /frames/movie request took.
//
//   node web/frames/bench_mosaic_rate.mjs http://127.0.0.1:8790 out.json [speed=600] [seconds=90] [t=2000-11-28T12:50]
//
// Needs the playwright package (NODE_PATH or a node_modules beside it) and a Chromium.
import { createRequire } from "module";
import fs from "fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [base, out, speed = "600", secs = "90", t = "2000-11-28T12:50"] = process.argv.slice(2);
const exe = process.env.CHROME || undefined;
const browser = await chromium.launch({ executablePath: exe, args: ["--use-gl=swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(`${base}/?t=${t}`, { waitUntil: "load", timeout: 120000 });
// hold the clock until the page has its catalog, so every speed starts from the same moment
await page.waitForFunction(() => typeof state !== "undefined", null, { timeout: 120000 });
await page.evaluate(() => { setPlaying(false); performance.setResourceTimingBufferSize(100000); });
await page.waitForFunction(() => typeof catalog !== "undefined" && catalog && catalog.byCam && catalog.byCam.N, null, { timeout: 180000 });
await page.waitForTimeout(3000);
const t0 = await page.evaluate(sp => { performance.clearResourceTimings(); setSpeed(+sp); setPlaying(true); return performance.now(); }, speed);
const samples = [];
const end = Date.now() + secs * 1000;
while (Date.now() < end) {
  samples.push(await page.evaluate(() => {
    const card = document.querySelector('.camwin[data-cam="N"]:not([data-body])');
    const shot = card && card.querySelector(".shot"), src = shot ? shot.dataset.src || "" : "";
    const F = window.cassiniFeeds, ks = F.framesOf("N", null).ks, pc = F.lastOfCam("N", state.et);
    const m = src.match(/\/frames\/(?:movie\/|processed\/)?([NW]\d{10}_\d+)\.webp/);
    const k = m ? catalog.id.indexOf(m[1]) : -1;
    return { t: performance.now(), et: state.et, speed: state.speed, clock: pc >= 0 ? catalog.id[ks[pc]] : null,
      clockObs: pc >= 0 ? catalog.obs[ks[pc]] : null, pc, ps: k >= 0 ? F.lastOfCam("N", catalog.et[k]) : -1,
      src: src.replace(/^https?:\/\/[^/]+/, ""), tag: card ? card.querySelector(".kindtag").textContent : "",
      rolling: /mode=rolling/.test(src), hud: (document.getElementById("mday") || {}).textContent || "" };
  }));
  await page.waitForTimeout(100);
}
const res = await page.evaluate(() => performance.getEntriesByType("resource").filter(e => /\/frames\//.test(e.name))
  .map(e => ({ url: e.name.replace(/^https?:\/\/[^/]+/, ""), start: e.startTime, wait: e.responseStart - e.requestStart, dur: e.duration })));
await browser.close();

// the pass: samples whose clock frame is in the observation
const OBS = "ISS_C23JU_6ATM2X2B115_PRIME";
const inPass = samples.filter(s => s.clockObs === OBS);
const changes = [];
for (let i = 1; i < inPass.length; i++) if (inPass[i].src !== inPass[i - 1].src) changes.push(inPass[i]);
const span = inPass.length ? (inPass[inPass.length - 1].t - inPass[0].t) / 1000 : 0;
const firstRolling = inPass.find(s => s.rolling);
const lags = inPass.filter(s => s.ps >= 0).map(s => s.pc - s.ps).sort((a, b) => a - b);
const pct = (a, q) => a.length ? a[Math.min(a.length - 1, Math.floor(q * a.length))] : null;
const movie = res.filter(r => /\/frames\/movie\//.test(r.url));
const rollingReq = movie.filter(r => /mode=rolling/.test(r.url)).map(r => r.dur).sort((a, b) => a - b);
const summary = {
  speed: +speed, seconds_in_pass: +span.toFixed(1), pictures_in_pass: changes.length,
  rolling_pictures: changes.filter(s => s.rolling).length,
  pictures_per_s: span ? +(changes.length / span).toFixed(2) : 0,
  rolling_per_s: span ? +(changes.filter(s => s.rolling).length / span).toFixed(2) : 0,
  first_mosaic_after_s: firstRolling ? +((firstRolling.t - inPass[0].t) / 1000).toFixed(1) : null,
  lag_frames: { median: pct(lags, 0.5), p90: pct(lags, 0.9), max: lags.length ? lags[lags.length - 1] : null },
  clock_frames_passed: inPass.length ? inPass[inPass.length - 1].pc - inPass[0].pc : 0,
  rolling_requests: rollingReq.length, rolling_ms: { median: pct(rollingReq, 0.5), p90: pct(rollingReq, 0.9), max: rollingReq[rollingReq.length - 1] },
  movie_thumb_requests: movie.filter(r => /size=128/.test(r.url)).length,
  all_frame_requests: res.length,
};
fs.writeFileSync(out, JSON.stringify({ summary, samples, res }, null, 1));
console.log(JSON.stringify(summary, null, 1));
