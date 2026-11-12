// Tests of the gate G3 tools (web/public/load): the target guard, log reading, the load runner against a stub server
// on this computer (outcomes, per-host limit, timing), the cost model's arithmetic, and the ten stretches.
//   node --test web/public/load/test_load.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { privateAddress, checkTarget, checkWorker, percentile, readSessions, classOf, parseArgs } from "./replay.mjs";
import { runLoad, judge } from "./load_runner.mjs";
import { countSession, mixRates, price, model, PRICES } from "./cost_model.mjs";
import { fixtureLog } from "./fixture_log.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "g3-test-"));

test("the guard allows this computer, the home network and the tailnet, and nothing else", async () => {
  for (const ip of ["127.0.0.1", "192.168.68.52", "10.1.2.3", "172.20.0.1", "100.76.189.126", "::1", "::ffff:192.168.1.1", "fd7a:115c:a1e0::1"])
    assert.ok(privateAddress(ip), ip);
  for (const ip of ["1.1.1.1", "104.16.0.1", "8.8.8.8", "100.128.0.1", "172.32.0.1", "192.169.0.1", "2606:4700::1"])
    assert.ok(!privateAddress(ip), ip);
  assert.equal(await checkTarget("http://127.0.0.1:8915/"), "http://127.0.0.1:8915");
  assert.equal(await checkTarget("http://localhost:8915"), "http://localhost:8915");
  for (const u of ["https://1.1.1.1", "https://cassini-frames.example.workers.dev", "https://staging.cassinios.com", "https://box.tail1234.ts.net", "ftp://127.0.0.1"])
    await assert.rejects(checkTarget(u), /refused|not http/, u);
});

test("the frames host must say it is the Worker running here, not through Cloudflare", async () => {
  // stand-ins for /health: the local Worker, staging, no header, a 404, and `wrangler dev --remote` (local env, edge headers)
  const answers = {
    local: [200, { "X-Site-Env": "local" }], staging: [200, { "X-Site-Env": "staging" }], production: [200, { "X-Site-Env": "production" }],
    none: [200, {}], notfound: [404, { "X-Site-Env": "local" }],
    remote: [200, { "X-Site-Env": "local", "CF-Ray": "8f1e2d3c4b5a6978-SJC" }], server: [200, { "X-Site-Env": "local", Server: "cloudflare" }],
  };
  for (const [name, [status, headers]] of Object.entries(answers)) {
    const srv = http.createServer((req, res) => { res.writeHead(req.url === "/health" ? status : 404, headers); res.end("ok public\n"); });
    await new Promise(r => srv.listen(0, "127.0.0.1", r));
    const origin = `http://127.0.0.1:${srv.address().port}`;
    try {
      if (name === "local") assert.equal(await checkWorker(origin), origin);
      else await assert.rejects(checkWorker(origin), /refused/, name);
    } finally { srv.close(); }
  }
  await assert.rejects(checkWorker("http://127.0.0.1:9", 2000), /did not answer/);
});

test("judging an answer against the logged one", () => {
  assert.equal(judge(200, 200, null), "ok");
  assert.equal(judge(404, 404, null), "ok");          // a probe's or a marker's 404, as logged
  assert.equal(judge(405, 405, null), "ok");          // a refusal, as logged
  assert.equal(judge(200, 304, null), "ok");
  assert.equal(judge(200, 404, null), "miss");
  assert.equal(judge(404, 200, null), "changed");
  assert.equal(judge(200, 503, null), "error");
  assert.equal(judge(200, 0, "ECONNRESET"), "error");
  assert.equal(judge(0, 200, null), "unjudged");
});

test("percentiles are nearest-rank", () => {
  const v = Array.from({ length: 100 }, (_, i) => i + 1);
  assert.equal(percentile(v, 50), 50);
  assert.equal(percentile(v, 95), 95);
  assert.equal(percentile(v, 100), 100);
  assert.equal(percentile([7], 95), 7);
  assert.equal(percentile([], 95), null);
});

test("arguments: bare flags take no value", () => {
  assert.deepEqual(parseArgs(["--keep-requests", "logs", "--viewers", "5"], ["keep-requests"]), { flags: { "keep-requests": "1", viewers: "5" }, rest: ["logs"] });
});

// a harness-shaped log: the site and the frames host apart, as on the rig
const HOST = "http://127.0.0.1:1";
const PIC = "/frames/processed/N1500060789_2.webp?size=1024";
function log(base, reqs, extra = {}) {
  return { session: "S1", site: "http://127.0.0.1:2", frames: base, seconds: 120, error: null, ...extra,
    requests: reqs.map(([p, status, ms, more = {}]) => ({ url: (more.static ? "http://127.0.0.1:2" : base) + p, method: more.method || "GET", type: "fetch", t: 1e12 + ms, status, headers: {}, bytes: more.bytes || 1000 })) };
}

test("logs are read with the harness's classes; CDN and inline requests are left out; summaries count", async () => {
  const dir = tmp();
  const L = log(HOST, [[PIC, 200, 0], ["/frames/mosaic/N1500060789_2.json", 200, 500], ["/frames/slices.json", 200, 900], ["/flags", 404, 1000], ["/index.html", 200, 5, { static: true }]]);
  L.requests.push({ url: "https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js", method: "GET", t: 1e12 + 10, status: 200, bytes: 5 });
  L.requests.push({ url: "data:image/png;base64,AAAA", method: "GET", t: 1e12 + 11, status: 200, bytes: 5 });
  fs.writeFileSync(path.join(dir, "S1.json"), JSON.stringify(L));
  fs.writeFileSync(path.join(dir, "summary.json"), JSON.stringify({ sessions: [{ session: "S1", site: L.site, frames: L.frames, seconds: 120, counts: {} }, { session: "S9", site: L.site, frames: L.frames, seconds: 60, counts: { bytes: 10, miss: 0 }, by_route: { processed: 3 } }] }));
  const ss = await readSessions([dir]);
  assert.deepEqual(ss.map(s => s.id), ["S1", "S9"]);   // S1's summary entry gives way to its log
  const s1 = ss[0];
  assert.deepEqual(s1.requests.map(r => r.cls), ["picture", "static", "table", "manifest", "refused"]);
  assert.deepEqual(s1.requests.map(r => r.offset), [0, 5, 500, 900, 1000]);
  assert.equal(s1.requests[1].host, "site");
  assert.ok(!ss[1].requests && ss[1].summary);
  assert.equal(classOf({ cls: "frames", store: "r2" }), "picture");
});

// a stub frames host: answers by path, slowly, and counts how many requests are open at once
function stub(answers, delay = 30) {
  let open = 0;
  const s = { peak: 0, seen: 0 };
  s.server = http.createServer((req, res) => {
    open++; s.peak = Math.max(s.peak, open); s.seen++;
    setTimeout(() => {
      const status = answers[req.url] ?? 200;
      if (status === "drop") { req.socket.destroy(); open--; return; }
      res.writeHead(status, { "Content-Type": "image/webp" });
      res.end(Buffer.alloc(status === 200 ? 5000 : 10));
      open--;
    }, delay);
  });
  return new Promise(r => s.server.listen(0, "127.0.0.1", () => { s.base = `http://127.0.0.1:${s.server.address().port}`; r(s); }));
}

test("the runner replays each viewer's log and judges every answer", async () => {
  const S = await stub({ "/frames/processed/N1500060790_2.webp?size=1024": 500, "/frames/processed/N1500060791_2.webp?size=1024": 404, "/frames/mosaic/N1500060792_2.webp": 404, "/frames/processed/N1500060793_2.webp?size=1024": "drop" });
  try {
    const dir = tmp();
    fs.writeFileSync(path.join(dir, "S1.json"), JSON.stringify(log(S.base, [
      [PIC, 200, 0], ["/frames/processed/N1500060790_2.webp?size=1024", 200, 100], ["/frames/processed/N1500060791_2.webp?size=1024", 200, 200],
      ["/frames/mosaic/N1500060792_2.webp", 404, 300], ["/frames/processed/N1500060793_2.webp?size=1024", 200, 400], ["/frames/slices.json", 200, 500],
      ["/usage", 204, 600, { method: "POST" }], ["/index.html", 200, 0, { static: true }],
    ])));
    const sessions = await readSessions([dir]);
    const { summary, results } = await runLoad({ sessions, frames: S.base, viewers: 5, ramp: 0.2, speedup: 10, timeout: 5 });
    assert.equal(results.length, 5 * 6);   // POST and static (no --site) are not replayed
    assert.deepEqual(summary.run.skipped, { other_methods: 5, static_without_site: 5 });
    assert.equal(summary.all.ok, 5 * 3);
    assert.equal(summary.all.error, 5 * 2);    // the 500 and the dropped connection
    assert.equal(summary.all.miss, 5);
    assert.equal(summary.gate.errors, 15);
    assert.equal(summary.gate.pass, false);
    assert.ok(summary.by_class.picture.p95_ms >= 30, "picture time includes the server's 30 ms");
    assert.equal(summary.by_class.picture.bytes, 5 * 5000 + 3 * 5 * 10);   // the 500, the miss and the probe answer 10 bytes each
    assert.ok(summary.timeline.length >= 1 && summary.not_ok.length >= 3);
  } finally { S.server.close(); }
});

test("one viewer never has more than --per-host requests open to the frames host", async () => {
  const S = await stub({}, 80);
  try {
    const dir = tmp();
    fs.writeFileSync(path.join(dir, "S1.json"), JSON.stringify(log(S.base, Array.from({ length: 12 }, (_, i) => [`/frames/processed/N15000607${String(i).padStart(2, "0")}_2.webp?size=512`, 200, 0]))));
    const { summary } = await runLoad({ sessions: await readSessions([dir]), frames: S.base, viewers: 1, perHost: 3, timeout: 5 });
    assert.equal(S.peak, 3);
    assert.equal(summary.gate.pass, true);
    assert.ok(summary.by_class.picture.wait_p95_ms >= 150, "the last requests waited for two rounds");
  } finally { S.server.close(); }
});

test("the cost model's arithmetic, by hand", async () => {
  // two minutes: 10 pictures, 2 table answers, 1 manifest, 1 refusal, 4 static requests
  const s = { id: "S1", seconds: 120, requests: [
    ...Array.from({ length: 10 }, () => ({ cls: "picture", method: "GET", path: PIC, status: 200, bytes: 50000 })),
    ...Array.from({ length: 2 }, () => ({ cls: "table", method: "GET", path: "/frames/mosaic/N1500060789_2.json", status: 200, bytes: 300 })),
    { cls: "manifest", method: "GET", path: "/frames/slices.json", status: 200, bytes: 30 },
    { cls: "refused", method: "GET", path: "/flags", status: 404, bytes: 0 },
    ...Array.from({ length: 4 }, () => ({ cls: "static", method: "GET", path: "/x.js", status: 200, bytes: 1e6 })),
  ] };
  const c = await countSession(s);
  assert.deepEqual([c.worker, c.picture, c.table, c.static, c.reads_cacheable, c.reads_fixed], [14, 10, 2, 4, 10, 4]);
  const { rate } = mixRates([c]);
  assert.equal(rate.worker, 7); assert.equal(rate.reads_cacheable, 5); assert.equal(rate.reads_fixed, 2);
  const p = price(rate, 1, { edgeHit: 0.5, cpuMs: 1, isolates: 0 });
  assert.equal(p.quantities.worker_requests, 420);
  assert.equal(p.quantities.class_b, (5 * 0.5 + 2) * 60);
  const want = 420 * 0.30e-6 + 420 * 0.02e-6 + 270 * 0.36e-6 + 420 * 0.25e-6;
  assert.ok(Math.abs(p.usd.total - want) < 1e-12);
  assert.equal(p.usd.pages, 0); assert.equal(p.usd.egress, 0);
  // a month inside every allowance costs the plan and the storage over 10 GB
  const mo = price(rate, 100, { included: true, storageGb: 250, isolates: 0 });
  assert.ok(Math.abs(mo.usd.total - (5 + 240 * 0.015)) < 1e-9);
  // a 404 picture reads its fallbacks too; a mix weighs session ids
  const c2 = await countSession({ id: "S2", seconds: 60, requests: [{ cls: "picture", method: "GET", path: PIC, status: 404, bytes: 0 }] });
  assert.equal(c2.reads_fixed, 1); assert.equal(c2.reads_cacheable, 0);
  const m = mixRates([c, c2], { S1: 3, S2: 1 });
  assert.equal(m.rate.worker, 0.75 * 7 + 0.25 * 1);
  const M = model([c, c2], { isolates: 0 });
  assert.equal(M.worker_rps_at_viewers, M.per_viewer_minute.worker * 1000 / 60);
  assert.equal(M.publish.class_a_usd, 4e6 * PRICES.r2.class_a_per_million / 1e6);
});

test("ten stretches, spread from 2000 to 2017, each a moment the page offers", () => {
  const S = JSON.parse(fs.readFileSync(path.join(here, "stretches.json"), "utf8"));
  assert.equal(S.stretches.length, 10);
  const ts = S.stretches.map(s => s.t);
  for (const t of ts) assert.match(t, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$/);
  assert.deepEqual([...ts].sort(), ts);
  assert.ok(ts[0] < "2001" && ts[9] >= "2017");
  assert.ok(new Set(ts.map(t => t.slice(0, 4))).size >= 7);
  assert.equal(new Set(S.stretches.map(s => s.label)).size, 10);
  const pageMoments = fs.readFileSync(path.join(here, "..", "..", "cassini-os", "src", "settings.html"), "utf8") + fs.readFileSync(path.join(here, "..", "harness", "sessions", "moments.mjs"), "utf8");
  for (const s of [...S.stretches, ...S.spares]) assert.ok(pageMoments.includes(s.t), `${s.t} is a page or harness moment`);
  const harness = fs.readFileSync(path.join(here, "..", "harness", "zero_origin.mjs"), "utf8");
  assert.match(harness, /args\.moment/); assert.match(harness, /args\.speed/);
});

test("the fixture log holds every key fixture with the status the fixture mirror answers", async () => {
  const L = await fixtureLog({ seconds: 10, host: "http://127.0.0.1:8911" });
  assert.equal(L.requests.length, 232);
  assert.ok(L.requests.every(r => r.url.startsWith("http://127.0.0.1:8911/") && [200, 204, 404, 405].includes(r.status)));
});
