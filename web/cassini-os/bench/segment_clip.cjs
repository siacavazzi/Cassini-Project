// Records a stretch's Pre-process as the page shows it: highlights FROM..UNTIL on the timeline (cassiniExport.mark,
// as a drag does), presses Pre-process, follows the frame server's job (/prebuild/<id>.json) every half second until
// it is done, then lets the stretch play as a movie (Settings > Playback > play when ready) for PLAYSECS. Writes
// OUT.webm (the page, W x H) and OUT.json (the job every half second: [s, state, done, total, through]); prints how
// long it took and every stall (no new picture for 10 s).
//   npm i playwright-core
//   node segment_clip.cjs URL FROM UNTIL OUT [W=1440 H=900 DPR=2]
//   CHANNEL=chrome  the installed Google Chrome (the Mac Mini); SOFTWARE=1 SwiftShader and THREE_DIR=.../three/package
//               for a cloud container; PLAYSECS (default 8) of the movie after it is ready; MAXSECS (default 600)
//   PRE='js'    runs in the page before the highlight (e.g. cassiniSettings.set("movie.fps", 12))
let chromium;
try { ({ chromium } = require("playwright-core")); } catch (e) { ({ chromium } = require("playwright")); }
const fs = require("fs");
const [url, FROM, UNTIL, out, W = 1440, H = 900, DPR = 2] = process.argv.slice(2);
const env = process.env, MAXSECS = +(env.MAXSECS || 600), PLAYSECS = +(env.PLAYSECS || 8);

(async () => {
  const args = ["--ignore-gpu-blocklist"];
  if (env.SOFTWARE) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
  const br = await chromium.launch({ channel: env.CHANNEL || undefined, executablePath: env.EXE || undefined, headless: !env.HEADED, args });
  const ctx = await br.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: +DPR,
    recordVideo: { dir: require("os").tmpdir(), size: { width: +W, height: +H } } });
  const opened = Date.now();
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERROR", e.message));
  if (env.THREE_DIR) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r =>
      r.fulfill({ path: `${env.THREE_DIR}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", headers: { "Content-Type": "text/css" } }));
  }
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  let jobId = null;
  page.on("response", async r => {
    if (r.request().method() === "POST" && /\/prebuild\?/.test(r.url())) { try { jobId = (await r.json()).id; } catch (e) {} }
  });
  const u = new URL(url); u.searchParams.set("t", FROM); u.searchParams.set("play", "0");
  await page.goto(u.href);
  await page.waitForFunction("document.getElementById('loading').hidden && typeof catalog !== 'undefined' && catalog && catalog.byCam && window.cassiniFeeds && window.cassiniExport", null, { timeout: 300000 });
  // the interface stays up (it rests out of the way after a few seconds without the pointer otherwise)
  await page.evaluate(() => cassiniSettings.set("interface.autohide", false));
  if (env.PRE) await page.evaluate(env.PRE);
  await page.waitForTimeout(3000);
  await page.evaluate(([a, b]) => cassiniExport.mark(utcToEt(a), utcToEt(b), "new"), [FROM, UNTIL]);
  await page.waitForTimeout(1500);
  const videoStartS = (Date.now() - opened) / 1000;
  await page.evaluate(() => document.getElementById("segprep").click());   // (a DOM click: a dock tucked away still takes it)
  const t0 = Date.now(), log = [], stalls = [];
  let job = null, lastDone = -1, lastMove = t0;
  while ((Date.now() - t0) / 1000 < MAXSECS) {
    await page.waitForTimeout(500);
    if (!jobId) continue;
    try { job = await (await fetch(`${u.origin}/prebuild/${jobId}.json`, { cache: "no-store" })).json(); } catch (e) { continue; }
    const s = (Date.now() - t0) / 1000;
    log.push([+s.toFixed(1), job.state, job.done, job.total, job.through]);
    if (job.done !== lastDone) {
      if (lastDone >= 0 && Date.now() - lastMove >= 10000) stalls.push([+((lastMove - t0) / 1000).toFixed(1), +s.toFixed(1), lastDone, job.total]);
      lastDone = job.done; lastMove = Date.now();
    }
    if (/^(done|failed|stopped)$/.test(job.state)) break;
  }
  const took = (Date.now() - t0) / 1000;
  if (job && Date.now() - lastMove >= 10000 && job.state !== "done") stalls.push([+((lastMove - t0) / 1000).toFixed(1), +took.toFixed(1), lastDone, job.total]);
  await page.waitForTimeout(PLAYSECS * 1000);
  fs.writeFileSync(`${out}.json`, JSON.stringify({ url, from: FROM, until: UNTIL, job, took, videoStartS, stalls, log }, null, 1));
  console.log(`pre-process: ${job ? `${job.state} ${job.done}/${job.total}` : "no job"} pictures in ${took.toFixed(1)} s (the server says ${job && job.took != null ? job.took.toFixed(1) : "?"} s); ${stalls.length} stalls${stalls.map(s => `\n   stall ${s[0]}-${s[1]} s at ${s[2]}/${s[3]}`).join("")}; video from ${videoStartS.toFixed(1)} s`);
  await ctx.close();
  await page.video().saveAs(`${out}.webm`);
  await br.close();
})();
