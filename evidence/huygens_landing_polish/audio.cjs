// Plays the cutscene in real time with sound started, and records what the page's audio graph sends to the speakers
// (muted on this machine) as OUT.webm, with OUT.json = { offset: seconds into the recording at which screen second 0 of
// the cutscene falls, errors }. For muxing under a stepped recording of the same cutscene.
//   node audio.cjs OUT   BASE=http://127.0.0.1:8936   [SKIPAT=s  press Escape at that screen second]  [MUTEAT=s  press S]
const { chromium } = require(process.env.PLAYWRIGHT || "playwright-core");
const fs = require("fs");
const [out] = process.argv.slice(2), env = process.env, BASE = env.BASE || "http://127.0.0.1:8936";
(async () => {
  const br = await chromium.launch({ args: ["--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required", "--use-angle=metal", "--mute-audio"] });
  const errors = [];
  try {
    const page = await (await br.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
    page.on("pageerror", e => { errors.push(e.message); console.log("PAGEERROR", e.message); });
    await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
    await page.addInitScript(() => {
      const connect = AudioNode.prototype.connect;
      AudioNode.prototype.connect = function (to, ...a) {
        const ctx = this.context;
        if (to === ctx.destination && !(ctx instanceof OfflineAudioContext)) {
          if (!ctx.__tap) {
            ctx.__tap = ctx.createMediaStreamDestination();
            const rec = new MediaRecorder(ctx.__tap.stream, { mimeType: "audio/webm;codecs=opus", audioBitsPerSecond: 128000 }), chunks = [];
            rec.ondataavailable = e => chunks.push(e.data);
            window.__rec = { rec, chunks, t0: 0 };
            rec.onstart = () => { window.__rec.t0 = performance.now(); };
            rec.start(250);
          }
          connect.call(this, ctx.__tap);
        }
        return connect.call(this, to, ...a);
      };
    });
    await page.goto(BASE + "/?huygens-landing");
    await page.waitForFunction(() => window.cassiniSound && window.cassiniHuygensLanding, null, { timeout: 120000 });
    await page.evaluate(() => cassiniSound.unlock());
    await page.waitForFunction(() => cassiniHuygensLanding.running && cassiniHuygensLanding.T > 1, null, { timeout: 120000, polling: 100 });
    const sync = await page.evaluate(() => ({ runAt: performance.now() - cassiniHuygensLanding.T * 1000, t0: window.__rec && window.__rec.t0, blocked: cassiniSound.blocked }));
    console.log("sync", JSON.stringify(sync));
    let skipped = false, muted = false;
    for (;;) {
      await page.waitForTimeout(250);
      const s = await page.evaluate(() => ({ r: cassiniHuygensLanding.running, T: cassiniHuygensLanding.T }));
      if (!s.r) break;
      if (env.SKIPAT && !skipped && s.T >= +env.SKIPAT) { skipped = true; await page.keyboard.press("Escape"); }
      if (env.MUTEAT && !muted && s.T >= +env.MUTEAT) { muted = true; await page.keyboard.press("s"); }
    }
    await page.waitForTimeout(6000);
    const b64 = await page.evaluate(() => new Promise(res => {
      const R = window.__rec; R.rec.onstop = async () => { const buf = await new Blob(R.chunks).arrayBuffer(); let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); res(btoa(s)); };
      R.rec.stop();
    }));
    fs.writeFileSync(out + ".webm", Buffer.from(b64, "base64"));
    fs.writeFileSync(out + ".json", JSON.stringify({ offset: (sync.runAt - sync.t0) / 1000, blocked: sync.blocked, errors }));
    console.log("offset", ((sync.runAt - sync.t0) / 1000).toFixed(3), "bytes", Buffer.from(b64, "base64").length, "errors", errors.length);
  } finally { await br.close(); }
})();
