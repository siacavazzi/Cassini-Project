#!/usr/bin/env node
// The "live, 10 years ago" stream: one headless Chrome draws Cassini OS in ambient mode, the DevTools screencast hands
// its frames to ffmpeg, and ffmpeg encodes them (on the Mac's hardware encoder) to a stream or a file.
// Node 22 or newer, no npm packages. Run it through run.sh, which keeps it at low priority and restarts it.
//
//   node web/stream/stream.mjs --url 'http://127.0.0.1:8765/?ambient=live' --out /path/hls/index.m3u8
//   node web/stream/stream.mjs --out youtube --out /path/hls/index.m3u8     (key from YOUTUBE_STREAM_KEY or --key-file)
//   node web/stream/stream.mjs --out /tmp/clip.mp4 --duration 60
//
// --out takes an rtmp:// or rtmps:// URL, "youtube", a .m3u8 path (HLS, a rolling window) or a .mp4/.mkv/.flv file;
// give it several times to send the same encode to each (one that fails does not stop the others).
// Every --stats-every seconds a line goes to <state>/stats.jsonl: frames from Chrome and to ffmpeg, ffmpeg's own fps
// and speed, the CPU (in cores) and memory of Chrome and ffmpeg, and the page's JS heap. report.mjs summarizes it.
// The process exits (and run.sh starts it again) when Chrome or ffmpeg dies, the page stops sending frames for
// --stall seconds, or ffmpeg falls behind real time.
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const DEFAULTS = {
  url: "http://127.0.0.1:8765/?ambient=live", out: [], width: 1920, height: 1080, fps: 30, bitrate: "6M", quality: 85,
  encoder: os.platform() === "darwin" ? "h264_videotoolbox" : "libx264", threads: 2, chrome: "", state: "",
  "key-file": path.join(os.homedir(), ".config/cassini-stream/youtube.key"), duration: 0, stall: 90,
  "stats-every": 60, "reload-hours": 0, settings: "", "hls-seconds": 4, "hls-window": 15, audio: "silence", "min-free-gb": 3,
};
const opt = parseArgs(process.argv.slice(2));
if (!opt.out.length) die("give at least one --out");
const STATE = path.resolve(opt.state || path.join(os.tmpdir(), "cassini-stream"));
fs.mkdirSync(STATE, { recursive: true });
const t0 = Date.now();
const log = (...a) => console.log(new Date().toISOString().slice(0, 19) + "Z", ...a);

// the stream key never reaches a log, the stats file or the process list's ffmpeg banner: it is masked everywhere we print
let KEY = "";
const outs = opt.out.map(o => {
  if (o !== "youtube") return o;
  KEY = (process.env.YOUTUBE_STREAM_KEY || readIf(opt["key-file"]) || "").trim();
  if (!KEY) die(`--out youtube needs YOUTUBE_STREAM_KEY or a key in ${opt["key-file"]}`);
  return "rtmps://a.rtmps.youtube.com:443/live2/" + KEY;
});
const mask = s => KEY ? String(s).split(KEY).join("****") : String(s);

// ---- Chrome -------------------------------------------------------------------------------------------------------
const profile = path.join(STATE, "chrome-profile");
fs.mkdirSync(profile, { recursive: true });
try { fs.unlinkSync(path.join(profile, "DevToolsActivePort")); } catch (e) {}
const chromeBin = opt.chrome || findChrome();
const chrome = spawn(chromeBin, [
  "--headless=new", `--user-data-dir=${profile}`, "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
  `--window-size=${opt.width},${opt.height}`, "--hide-scrollbars", "--mute-audio", "--no-first-run", "--no-default-browser-check",
  "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
  "--disable-features=CalculateNativeWinOcclusion,MediaRouter,Translate", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
  "--renderer-process-limit=1", "--disable-extensions", "--disable-component-update", "--disable-sync",
  ...(os.platform() === "darwin" ? [] : ["--enable-unsafe-swiftshader"]), ...(process.getuid?.() === 0 ? ["--no-sandbox"] : []), "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });
chrome.stderr.pipe(fs.createWriteStream(path.join(STATE, "chrome.log"), { flags: "a" }));
chrome.on("exit", (c, s) => quit(3, `Chrome exited (${c ?? s})`));

// ---- ffmpeg -------------------------------------------------------------------------------------------------------
// input: the latest screencast JPEG, written at exactly --fps; wall-clock stamps plus fps= keep it real time even if
// a write is skipped while ffmpeg catches up
const vf = `fps=${opt.fps},scale=${opt.width}:${opt.height}:in_range=full:out_range=tv:flags=bicubic,format=yuv420p`;
const enc = opt.encoder === "h264_videotoolbox"
  ? ["-c:v", "h264_videotoolbox", "-realtime", "1", "-prio_speed", "1", "-allow_sw", "0", "-profile:v", "high"]
  : ["-c:v", opt.encoder, "-preset", "veryfast", "-tune", "zerolatency", "-profile:v", "high"];
const audioIn = opt.audio === "silence" ? ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] : ["-stream_loop", "-1", "-re", "-i", opt.audio];
const ff = ["-hide_banner", "-loglevel", "warning", "-nostdin", "-stats_period", "5", "-progress", "pipe:3",
  "-thread_queue_size", "64", "-use_wallclock_as_timestamps", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-i", "pipe:0",
  ...audioIn, "-map", "0:v", "-map", "1:a", "-threads", String(opt.threads), "-filter_threads", "1", "-vf", vf,
  ...enc, "-b:v", opt.bitrate, "-maxrate", opt.bitrate, "-bufsize", doubleRate(opt.bitrate),
  "-g", String(opt.fps * 2), "-keyint_min", String(opt.fps * 2), "-bf", "0",
  "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
  ...(opt.duration ? ["-t", String(opt.duration)] : []), ...outputArgs(outs)];
log("ffmpeg", mask(ff.join(" ")));
const ffmpeg = spawn("ffmpeg", ff, { stdio: ["pipe", "ignore", "pipe", "pipe"] });
ffmpeg.stderr.on("data", d => process.stderr.write("[ffmpeg] " + mask(d)));
ffmpeg.stdin.on("error", () => {});
const prog = {};
let progBuf = "";
ffmpeg.stdio[3].on("data", d => {
  progBuf += d; let i;
  while ((i = progBuf.indexOf("\n")) >= 0) { const [k, v] = progBuf.slice(0, i).split("="); progBuf = progBuf.slice(i + 1); if (k) prog[k.trim()] = (v || "").trim(); }
});
ffmpeg.on("exit", (c, s) => quit(opt.duration && c === 0 ? 0 : 4, `ffmpeg exited (${c ?? s})`));

// ---- DevTools ------------------------------------------------------------------------------------------------------
let ws, nextId = 1;
const pending = new Map(), handlers = {};
const cdp = (method, params = {}, sessionId) => new Promise((ok, no) => {
  const id = nextId++; pending.set(id, { ok, no, method });
  ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
});
let latest = null, fresh = false, lastWrite = 0, framesIn = 0, framesOut = 0, skipped = 0, lastFrameAt = Date.now(), session = "";

(async () => {
  const port = await waitFor(() => readIf(path.join(profile, "DevToolsActivePort"))?.split("\n")[0], 30000, "Chrome's DevTools port");
  const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  ws = new WebSocket(ver.webSocketDebuggerUrl);
  await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = () => no(new Error("DevTools socket failed")); });
  ws.onclose = () => quit(3, "DevTools socket closed");
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); if (!p) return; m.error ? p.no(new Error(`${p.method}: ${m.error.message}`)) : p.ok(m.result); return; }
    handlers[m.method]?.(m.params, m.sessionId);
  };
  const { targetInfos } = await cdp("Target.getTargets");
  const page = targetInfos.find(t => t.type === "page");
  session = (await cdp("Target.attachToTarget", { targetId: page.targetId, flatten: true })).sessionId;
  const s = (m, p) => cdp(m, p, session);
  await s("Page.enable"); await s("Runtime.enable"); await s("Performance.enable");
  await s("Emulation.setDeviceMetricsOverride", { width: opt.width, height: opt.height, deviceScaleFactor: 1, mobile: false });
  await s("Emulation.setFocusEmulationEnabled", { enabled: true });
  // counts the page's own animation frames, to tell a page that draws slowly from a screencast that drops frames
  await s("Page.addScriptToEvaluateOnNewDocument", { source: "window.__streamRaf = 0; (function f() { window.__streamRaf++; requestAnimationFrame(f); })();" });
  if (opt.settings) await s("Page.addScriptToEvaluateOnNewDocument", { source:
    `try { const k = "cassini-os-settings-v1", o = JSON.parse(localStorage.getItem(k) || "{}"); localStorage.setItem(k, JSON.stringify(Object.assign(o, ${JSON.stringify(JSON.parse(opt.settings))}))); } catch (e) {}` });
  handlers["Runtime.exceptionThrown"] = p => log("page error:", (p.exceptionDetails.exception?.description || p.exceptionDetails.text || "").split("\n")[0]);
  handlers["Inspector.targetCrashed"] = () => quit(5, "page crashed");
  handlers["Page.screencastFrame"] = (p, sid) => {
    cdp("Page.screencastFrameAck", { sessionId: p.sessionId }, sid).catch(() => {});
    latest = Buffer.from(p.data, "base64"); fresh = true; framesIn++; lastFrameAt = Date.now();
  };
  log("opening", opt.url, "in", chromeBin);
  await s("Page.navigate", { url: opt.url });
  await waitFor(async () => (await s("Runtime.evaluate", { expression: "!!(document.getElementById('loading') && document.getElementById('loading').hidden)", returnByValue: true })).result.value, 300000, "the page to load");
  const gl = (await s("Runtime.evaluate", { returnByValue: true, expression:
    `(() => { const g = document.createElement("canvas").getContext("webgl"); const x = g && g.getExtension("WEBGL_debug_renderer_info"); return x ? g.getParameter(x.UNMASKED_RENDERER_WEBGL) : "no WebGL"; })()` })).result.value;
  log("loaded; WebGL renderer:", gl, /swiftshader|llvmpipe|software/i.test(gl) ? "(software, this will be slow)" : "");
  await s("Page.startScreencast", { format: "jpeg", quality: opt.quality, maxWidth: opt.width, maxHeight: opt.height, everyNthFrame: 1 });
  lastFrameAt = Date.now();
  // the pump, at most --fps times a second: the newest JPEG when the page drew a new one (ffmpeg's fps filter repeats
  // it until the next, by wall-clock stamps), and the same one again after a second without change; so ffmpeg only
  // decodes what the page actually drew
  const frameMs = 1000 / opt.fps;
  let due = Date.now();
  const pump = () => {
    if (latest && (fresh || Date.now() - lastWrite > 1000)) {
      if (ffmpeg.stdin.writableLength > 4 * latest.length) skipped++; // ffmpeg is behind: let it catch up
      else { ffmpeg.stdin.write(latest); framesOut++; fresh = false; lastWrite = Date.now(); }
    }
    due += frameMs; const wait = due - Date.now();
    if (wait < -1000) due = Date.now();
    setTimeout(pump, Math.max(0, wait));
  };
  pump();
  setInterval(() => { if (Date.now() - lastFrameAt > opt.stall * 1000) quit(6, `no frame from the page for ${opt.stall} s`); }, 5000);
  // the Mini's other work comes first: below --min-free-gb of free plus reclaimable memory the stream steps aside
  // (run.sh waits ten minutes before trying again)
  setInterval(() => { const gb = availableGb(); if (gb != null && gb < opt["min-free-gb"]) quit(8, `only ${gb.toFixed(1)} GB of memory available`); }, 15000);
  if (+opt["reload-hours"] > 0) setInterval(() => { log("scheduled reload"); s("Page.reload", {}).catch(() => {}); }, opt["reload-hours"] * 3600e3);
  setInterval(stats, opt["stats-every"] * 1000);
})().catch(e => quit(2, e.message));

// ---- stats -------------------------------------------------------------------------------------------------------
let slowFor = 0;
let last = { at: Date.now(), cpu: {}, framesIn: 0, framesOut: 0 };
async function stats() {
  const now = Date.now(), dt = (now - last.at) / 1000;
  const procs = psTree();
  const groups = { chrome: procs.filter(p => p.cmd.includes(profile)), ffmpeg: procs.filter(p => p.pid === ffmpeg.pid), node: procs.filter(p => p.pid === process.pid) };
  const cpu = {}, rss = {};
  for (const [k, ps] of Object.entries(groups)) {
    const t = ps.reduce((a, p) => a + p.cpuSec, 0);
    cpu[k] = last.cpu[k] == null ? null : +((t - last.cpu[k]) / dt).toFixed(3);
    rss[k] = Math.round(ps.reduce((a, p) => a + p.rssKb, 0) / 1024);
    last.cpu[k] = t;
  }
  let heap = null, page = null;
  try {
    const m = (await cdp("Performance.getMetrics", {}, session)).metrics;
    heap = Math.round(m.find(x => x.name === "JSHeapUsedSize").value / 1048576);
    page = (await cdp("Runtime.evaluate", { returnByValue: true, expression:
      `({ t: typeof state === "object" && typeof etToMs === "function" ? new Date(etToMs(state.et)).toISOString().slice(0, 19) : null,
          mode: window.cassiniAmbient ? cassiniAmbient.mode : null, subject: window.cassiniAmbient ? cassiniAmbient.subject : null,
          shots: [...document.querySelectorAll("#imgcard .well.has-frame, #wacard .well.has-frame")].length, raf: window.__streamRaf || 0 })` }, session)).result.value;
  } catch (e) {}
  const line = { at: new Date(now).toISOString().slice(0, 19) + "Z", up: Math.round((now - t0) / 1000),
    rafFps: page && last.raf != null ? +((page.raf - last.raf) / dt).toFixed(1) : null,
    pageFps: +((framesIn - last.framesIn) / dt).toFixed(1), outFps: +((framesOut - last.framesOut) / dt).toFixed(1), skipped,
    ffFps: +prog.fps || null, speed: prog.speed || null, bitrate: prog.bitrate || null, dup: +prog.dup_frames || 0, drop: +prog.drop_frames || 0,
    cpu, rssMb: rss, heapMb: heap, load: +os.loadavg()[0].toFixed(1), availGb: +(availableGb() ?? 0).toFixed(1), page };
  fs.appendFileSync(path.join(STATE, "stats.jsonl"), JSON.stringify(line) + "\n");
  log(`raf ${line.rafFps}, page ${line.pageFps} fps, out ${line.outFps} fps, ffmpeg ${line.ffFps} fps x${line.speed}, cpu chrome ${cpu.chrome} ffmpeg ${cpu.ffmpeg} cores, rss chrome ${rss.chrome} ffmpeg ${rss.ffmpeg} MB, heap ${heap} MB, ${page?.t || ""}`);
  last = { at: now, cpu: last.cpu, framesIn, framesOut, raf: page?.raf };
  // a slow patch (the Mini busy) is ridden out: a restart would not make it faster. Only ten minutes in a row under
  // half of real time stops it, and run.sh then waits ten minutes before starting again
  const sp = parseFloat(prog.speed);
  slowFor = sp > 0 && sp < 0.5 ? slowFor + opt["stats-every"] : 0;
  if (slowFor >= 600) quit(7, `ffmpeg under half of real time (${prog.speed}) for ten minutes`);
}

// ps reports cumulative CPU time; differences over the interval give cores in use
function psTree() {
  try {
    return execFileSync("ps", ["-A", "-o", "pid=,rss=,time=,command="], { encoding: "utf8", maxBuffer: 16 << 20 }).split("\n").filter(Boolean).map(l => {
      const m = l.trim().match(/^(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/); if (!m) return null;
      return { pid: +m[1], rssKb: +m[2], cpuSec: cpuSeconds(m[3]), cmd: m[4] };
    }).filter(Boolean);
  } catch (e) { return []; }
}
function cpuSeconds(t) { // [[dd-]hh:]mm:ss.ss
  let d = 0; if (t.includes("-")) { [d, t] = t.split("-"); }
  return t.split(":").reduce((a, x) => a * 60 + parseFloat(x), 0) + d * 86400;
}

// ---- helpers --------------------------------------------------------------------------------------------------------
function outputArgs(list) {
  const spec = o => /^rtmps?:\/\//.test(o) ? ["flv", {}]
    : /\.m3u8$/.test(o) ? ["hls", { hls_time: opt["hls-seconds"], hls_list_size: opt["hls-window"], hls_flags: "delete_segments+independent_segments+omit_endlist", hls_allow_cache: 0 }]
    : [path.extname(o).slice(1) === "mkv" ? "matroska" : path.extname(o).slice(1) || "mp4", path.extname(o) === ".mp4" ? { movflags: "+faststart" } : {}];
  for (const o of list) if (!/^rtmps?:/.test(o)) {
    fs.mkdirSync(path.dirname(path.resolve(o)), { recursive: true });
    // an HLS folder gets a page that plays it (Safari natively, other browsers through hls.js)
    if (/\.m3u8$/.test(o)) fs.writeFileSync(path.join(path.dirname(path.resolve(o)), "index.html"),
      fs.readFileSync(new URL("player.html", import.meta.url), "utf8").replaceAll("STREAM.m3u8", path.basename(o)));
  }
  if (list.length === 1) { const [f, o] = spec(list[0]); return ["-f", f, ...Object.entries(o).flatMap(([k, v]) => ["-" + k, String(v)]), "-y", list[0]]; }
  return ["-f", "tee", list.map(o => { const [f, x] = spec(o); return `[${["f=" + f, "onfail=ignore", ...Object.entries(x).map(([k, v]) => `${k}=${v}`)].join(":")}]${o}`; }).join("|")];
}
// free plus inactive and speculative pages (macOS vm_stat), or MemAvailable (Linux): what the system can hand out
function availableGb() {
  try {
    if (os.platform() === "darwin") {
      const v = execFileSync("vm_stat", { encoding: "utf8" }), page = +(v.match(/page size of (\d+)/) || [0, 16384])[1];
      const n = k => +((v.match(new RegExp(`Pages ${k}:\\s+(\\d+)`)) || [0, 0])[1]);
      return (n("free") + n("inactive") + n("speculative")) * page / 2 ** 30;
    }
    const m = fs.readFileSync("/proc/meminfo", "utf8").match(/MemAvailable:\s+(\d+)/); return m ? m[1] / 2 ** 20 : null;
  } catch (e) { return null; }
}
function doubleRate(r) { const m = String(r).match(/^([\d.]+)([kKmM]?)$/); return m ? +m[1] * 2 + m[2] : r; }
function findChrome() {
  const c = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/opt/pw-browsers/chromium/chrome-linux/chrome", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"];
  const f = c.find(p => fs.existsSync(p)); if (!f) die("no Chrome found; pass --chrome"); return f;
}
function readIf(p) { try { return fs.readFileSync(p, "utf8"); } catch (e) { return null; } }
async function waitFor(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) { try { const v = await fn(); if (v) return v; } catch (e) {} if (Date.now() > end) throw new Error(`timed out waiting for ${what}`); await new Promise(r => setTimeout(r, 500)); }
}
function parseArgs(a) {
  const o = { ...DEFAULTS, out: [] };
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, ""); if (!(k in DEFAULTS)) die(`unknown option ${a[i]}`);
    const v = a[++i]; if (v == null) die(`${a[i - 1]} needs a value`);
    if (k === "out") o.out.push(v); else o[k] = typeof DEFAULTS[k] === "number" ? +v : v;
  }
  return o;
}
let quitting = false;
function quit(code, why) {
  if (quitting) return; quitting = true;
  log(code ? "stopping:" : "done:", mask(why));
  try { ffmpeg?.stdin.end(); } catch (e) {}
  try { chrome.kill("SIGTERM"); } catch (e) {}
  // give ffmpeg a moment to close the file or stream cleanly
  setTimeout(() => { try { ffmpeg.kill("SIGKILL"); chrome.kill("SIGKILL"); } catch (e) {} process.exit(code); }, code ? 5000 : 30000).unref();
  if (!code) { if (ffmpeg.exitCode !== null) process.exit(0); ffmpeg.once("exit", () => process.exit(0)); }
}
function die(m) { console.error(m); process.exit(1); }
process.on("SIGTERM", () => quit(0, "SIGTERM"));
process.on("SIGINT", () => quit(0, "SIGINT"));
process.on("SIGHUP", () => quit(0, "SIGHUP"));
