// The public switch (docs/public-site, WP6; settings.html, build.py --public): with it on, every setting
// web/public/policy.json page_settings hides is hidden and every value it forces is forced, whatever the browser had
// saved; the flag button, Flagged Pictures and the body reels are gone; pictures, version.json, slices.json and the
// usage counts go to the frames host and nothing the policy refuses is asked; no jump log is posted; three.js and the
// fonts come from the build's vendor/ folder. With it off (the checked-in index.html, the Mini's page) nothing changes:
// every setting is listed, every option offered, saved values kept, the flags and the reels are there.
//
// Run: node web/test_public_switch.cjs [PUBLIC_DIR] [THREE_DIR]
//   PUBLIC_DIR  a public build made with `python web/cassini-os/src/build.py --public --frames https://frames.invalid
//               --out PUBLIC_DIR`; left out (or "-"), the test makes one in a temporary folder (it needs the replay
//               data with coverage, and three.js in ~/.cache/cassini-vendor or jsDelivr)
//   THREE_DIR   an `npm pack three@0.128.0` unpacked, for the switch-off page when jsDelivr is blocked
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path"), os = require("os"), { execFileSync } = require("child_process");
const ROOT = path.join(__dirname, "cassini-os"), HOST = "https://frames.invalid";
let [pub, three] = process.argv.slice(2);
if (!pub || pub === "-") {
  pub = fs.mkdtempSync(path.join(os.tmpdir(), "cassini-public-"));
  execFileSync("python3", [path.join(ROOT, "src", "build.py"), "--public", "--frames", HOST, "--out", pub], { stdio: "inherit" });
}
const policy = JSON.parse(fs.readFileSync(path.join(__dirname, "public", "policy.json"), "utf8")).page_settings;
const SAVED = { "processing.align": false, "processing.calibrate": false, "cameras.balancedColor": false, "cameras.colors": "raw",
  "cameras.autoCenter": false, "cameras.hdr": "auto", "cameras.hdrGlow": 40, "movies.laps": 4, "movies.stabilizeLocal": false,
  "cameras.passes": "mosaic", "interface.flags": false };

// policy.json page_settings, line by line: what each hidden line means on the page (a new line fails here until it has one)
const HIDDEN = {
  "processing.* (the 18 step toggles, calibration.STEPS)": d => d.filter(x => x.key.startsWith("processing.")).length === 18 && d.filter(x => x.key.startsWith("processing.")),
  "cameras.balancedColor": d => d.filter(x => x.key === "cameras.balancedColor"),
  "cameras.autoCenter (D4: always on)": d => d.filter(x => x.key === "cameras.autoCenter"),
  "cameras.hdr and cameras.hdrGlow (D8)": d => d.filter(x => x.key === "cameras.hdr" || x.key === "cameras.hdrGlow"),
  "movies.laps above 1": d => d.filter(x => x.key === "movies.laps"),
};
const OPTIONS = { "cameras.colors values raw and false": ["cameras.colors", ["raw", "false"]], "cameras.passes value mosaic (Always mosaic)": ["cameras.passes", ["mosaic"]] };
const ELSEWHERE = {   // lines met by a part of the page rather than a setting
  "Pre-process (segment.html)": "WP7b (segment.html)", "Studio tile tuning": "WP7b (studio.html)",
  "the flag button and /flags links": "flags", "the reel window (D2)": "reels",
};

function serve(dir) {
  return new Promise(ok => {
    const srv = http.createServer((q, r) => {
      let f = path.join(dir, decodeURIComponent(q.url.split("?")[0]));
      try {
        if (fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
        const type = { ".html": "text/html", ".js": "application/javascript", ".mjs": "text/javascript", ".json": "application/json", ".woff2": "font/woff2", ".webp": "image/webp" }[path.extname(f)] || "application/octet-stream";
        r.writeHead(200, { "Content-Type": type }); r.end(fs.readFileSync(f));
      } catch (e) { r.writeHead(404); r.end(); }
    }).listen(0, "127.0.0.1", () => ok(srv));
  });
}

(async () => {
  const { loadKeys } = await import(path.join(__dirname, "public", "keys.mjs"));
  const K = await loadKeys();
  const br = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let bad = 0;
  const check = (name, ok, detail) => { bad += !ok; console.log(`${ok ? "ok  " : "FAIL"} ${name}${ok || detail === undefined ? "" : `: ${JSON.stringify(detail)}`}`); };

  async function open(dir, seed) {
    const srv = await serve(dir), site = `http://127.0.0.1:${srv.address().port}`;
    const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage(), reqs = [];
    page.on("request", q => reqs.push({ method: q.method(), url: q.url() }));
    if (three) await page.route("https://cdn.jsdelivr.net/npm/three@0.128.0/**", r => r.fulfill({ path: `${three}/${r.request().url().split("three@0.128.0/")[1]}`, headers: { "Content-Type": "application/javascript" } }));
    await page.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, body: "", contentType: "text/css" }));
    await page.route(`${HOST}/**`, r => r.fulfill(/\/version\.json$/.test(r.request().url()) ? { status: 200, contentType: "application/json", body: '{"version":"test","server_version":"test"}' } : { status: 404, body: "" }));
    await page.addInitScript(([key, seed]) => { if (seed) localStorage.setItem(key, JSON.stringify(seed)); }, ["cassini-os-settings-v1", seed]);
    await page.goto(`${site}/?t=2006-09-15T14:30:00&play=0`);
    await page.waitForFunction(() => window.cassiniSettings && cassiniSettings.defined.some(d => d.key === "playback.maxImageRate"), null, { timeout: 120000 });
    await page.waitForTimeout(3000);
    return { srv, ctx, page, reqs, site };
  }
  const defs = page => page.evaluate(() => cassiniSettings.defined.filter(d => d.type !== "action")
    .map(d => ({ key: d.key, hidden: !!d.hidden, value: cassiniSettings.get(d.key), def: d.value, options: d.options ? d.options.map(o => o[0]) : null })));
  // every row the Settings window lists, section by section
  const listed = page => page.evaluate(async () => {
    cassiniSettings.open(); const keys = [];
    for (const s of [...document.querySelectorAll("#snav button")].map(b => b.dataset.s)) {   // the nav is drawn again on each click
      document.querySelector(`#snav button[data-s="${s}"]`).click(); await new Promise(r => setTimeout(r, 30));
      keys.push(...[...document.querySelectorAll("#spane .srow")].map(r => r.dataset.key));
    }
    cassiniSettings.close(); return keys;
  });

  // ---------- switch on ----------
  {
    const { srv, ctx, page, reqs } = await open(pub, SAVED);
    check("public: window.cassiniPublic", await page.evaluate(() => window.cassiniPublic === true));
    check("public: frames host", await page.evaluate(() => window.cassiniFrames) === HOST, await page.evaluate(() => window.cassiniFrames));
    const d = await defs(page), rows = new Set(await listed(page));
    for (const line of policy.hidden) {
      if (HIDDEN[line]) {
        const hit = HIDDEN[line](d);
        check(`public hides: ${line}`, hit && hit.length && hit.every(x => x.hidden && !rows.has(x.key)), hit && hit.filter(x => !x.hidden || rows.has(x.key)).map(x => x.key));
      } else if (OPTIONS[line]) {
        const [key, gone] = OPTIONS[line], x = d.find(x => x.key === key);
        check(`public hides: ${line}`, x && !x.hidden && rows.has(key) && gone.every(o => !x.options.includes(o)) && !gone.includes(x.value), x);
      } else check(`public hides: ${line} (${ELSEWHERE[line] || "no check for this policy line"})`, !!ELSEWHERE[line]);
    }
    for (const [key, want] of Object.entries(policy.forced)) {
      const x = d.find(x => x.key === key);
      check(`public forces ${key} = ${JSON.stringify(want)} (saved ${JSON.stringify(SAVED[key])})`, x && x.value === want && x.hidden && !rows.has(key), x);
    }
    check("public: every hidden setting at its forced value or its default", d.filter(x => x.hidden).every(x => x.value === (x.key in policy.forced ? policy.forced[x.key] : x.def)), d.filter(x => x.hidden && x.value !== x.def));
    check("public: a hidden setting cannot be set", await page.evaluate(() => { cassiniSettings.set("cameras.autoCenter", false); cassiniSettings.set("processing.align", false); return cassiniSettings.get("cameras.autoCenter") === true && cassiniSettings.get("processing.align") === true; }));
    check("public: picture queries carry no look, off, hdr, center=0 or laps above 1", await page.evaluate(() =>
      window.cassiniLook({ center: true }) === "&center=1" && window.cassiniOff() === "" && window.cassiniHdr(1024) === "" && !/center=0|laps=[2-9]/.test(window.cassiniMovieStyle())), await page.evaluate(() => [window.cassiniLook(), window.cassiniMovieStyle()]));
    check("public: no flag button, no Flagged Pictures, no flag settings", await page.evaluate(() => !document.querySelector(".flagbtn, [data-flags]") && !window.cassiniFlags));
    check("public: no body reels", await page.evaluate(() => !document.querySelector("#goreel") && !window.cassiniReel));
    const third = reqs.filter(r => /cdn\.jsdelivr\.net\/npm\/three|fonts\.(googleapis|gstatic)\.com/.test(r.url));
    check("public: three.js and the fonts from vendor/", !third.length && reqs.some(r => /\/vendor\/three\/three\.min\.js$/.test(r.url)), third.map(r => r.url));
    check("public: the film muxer imports from vendor/", await page.evaluate(async () => { try { const m = await import("./vendor/mp4-muxer/mp4-muxer.mjs"); return typeof m.Muxer === "function"; } catch (e) { return String(e); } }) === true);
    check("public: no jump log", !reqs.some(r => /\/jumplog/.test(r.url)));
    const frames = reqs.filter(r => r.url.startsWith(HOST));
    check("public: version.json and slices.json from the frames host", ["/version.json", "/frames/slices.json"].every(p => frames.some(r => r.url === HOST + p)), frames.map(r => r.url));
    // every visible setting toggled in turn, as harness S9 does, and nothing the policy refuses is asked for
    await page.evaluate(async () => {
      for (const d of cassiniSettings.defined.filter(d => d.type !== "action" && !d.hidden && !d.reload)) {
        const was = cassiniSettings.get(d.key);
        const vals = d.type === "toggle" ? [!was] : d.type === "choice" ? d.options.map(o => o[0]).filter(v => v !== was) : d.type === "range" ? [was === d.max ? d.min : d.max] : [];
        for (const v of vals) { cassiniSettings.set(d.key, v); await new Promise(r => setTimeout(r, 20)); }
        cassiniSettings.set(d.key, was);
      }
    });
    await page.waitForTimeout(1500);
    const refused = reqs.filter(r => r.url.startsWith(HOST)).map(r => ({ r, a: K.canonical(r.method, r.url.slice(HOST.length)) })).filter(x => x.a.refused);
    check("public: nothing the policy refuses asked of the frames host", !refused.length, refused.map(x => `${x.r.method} ${x.r.url}: ${x.a.refused}`));
    check("public: no request to another host", !reqs.some(r => !/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url) && !r.url.startsWith(HOST)), reqs.filter(r => !/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url) && !r.url.startsWith(HOST)).map(r => r.url));
    await ctx.close(); srv.close();
  }

  // ---------- switch off: the checked-in page, as the Mini serves it ----------
  {
    const { srv, ctx, page, site } = await open(ROOT, SAVED);
    check("off: window.cassiniPublic is false", await page.evaluate(() => window.cassiniPublic === false));
    check("off: frames from the page's own origin", await page.evaluate(() => window.cassiniFrames) === site);
    const d = await defs(page), rows = new Set(await listed(page));
    check("off: no setting hidden", !d.some(x => x.hidden), d.filter(x => x.hidden).map(x => x.key));
    check("off: every setting listed", d.every(x => rows.has(x.key)), d.filter(x => !rows.has(x.key)).map(x => x.key));
    check("off: every option offered", d.find(x => x.key === "cameras.colors").options.includes("raw") && d.find(x => x.key === "cameras.passes").options.includes("mosaic"));
    for (const [key, v] of Object.entries(SAVED)) {
      const x = d.find(x => x.key === key);
      if (x) check(`off: saved ${key} = ${JSON.stringify(v)} kept`, x.value === v, x.value);
    }
    check("off: the saved look reaches the picture queries", await page.evaluate(() => window.cassiniLook() === "&look=classic&off=calibrate,align" || window.cassiniLook().startsWith("&look=classic&off=")), await page.evaluate(() => window.cassiniLook()));
    check("off: flag button setting, Flagged Pictures and body reels there", await page.evaluate(() => !!document.querySelector("[data-flags]") && !!window.cassiniFlags && !!document.querySelector("#goreel") && !!window.cassiniReel));
    await ctx.close(); srv.close();
  }
  await br.close();
  console.log(bad ? `${bad} FAILED` : "ok");
  process.exit(bad ? 1 : 0);
})();
