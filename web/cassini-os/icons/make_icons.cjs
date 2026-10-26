// Renders the dock icons (make_icons.html) to web/cassini-os/icons/<name>.webp, 256 px.
//   node web/cassini-os/icons/make_icons.cjs [name ...]
// Serves web/cassini-os from disk (data/ is web/replay/data, with data/textures/rings/saturn_rings.png). three.js
// comes from jsDelivr, or from THREE_DIR (an unpacked three@0.128.0 package) where the CDN is out of reach.
const { chromium } = require("playwright"), fs = require("fs"), path = require("path");
const SITE = path.join(__dirname, ".."), THREE_DIR = process.env.THREE_DIR;
const MIME = { ".html": "text/html", ".js": "application/javascript", ".webp": "image/webp", ".png": "image/png", ".txt": "text/plain" };
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
  const p = await b.newPage();
  p.on("pageerror", e => console.error("page:", e.message));
  await p.route("http://icons.local/**", r => {
    const f = path.join(SITE, decodeURIComponent(new URL(r.request().url()).pathname));
    fs.existsSync(f) ? r.fulfill({ path: f, contentType: MIME[path.extname(f)] || "application/octet-stream" }) : r.fulfill({ status: 404 });
  });
  if (THREE_DIR) await p.route(/cdn\.jsdelivr\.net\/npm\/three@0\.128\.0\//, r => r.fulfill({ path: path.join(THREE_DIR, r.request().url().split("three@0.128.0/")[1]), contentType: "application/javascript" }));
  await p.goto("http://icons.local/icons/make_icons.html");
  const names = process.argv.slice(2).length ? process.argv.slice(2) : await p.evaluate(() => Object.keys(ICONS).filter(k => k[0] !== "_"));
  for (const n of names) {
    const png = Buffer.from((await p.evaluate(n => ICONS[n](), n)).split(",")[1], "base64");
    const out = path.join(__dirname, n + ".webp");
    await p.evaluate(async src => { window._im = new Image(); window._im.src = src; await window._im.decode(); }, "data:image/png;base64," + png.toString("base64"));
    const webp = await p.evaluate(() => { const c = document.createElement("canvas"); c.width = _im.width; c.height = _im.height; c.getContext("2d").drawImage(_im, 0, 0); return c.toDataURL("image/webp", 0.92); });
    fs.writeFileSync(out, Buffer.from(webp.split(",")[1], "base64"));
    if (process.env.PNG_DIR) fs.writeFileSync(path.join(process.env.PNG_DIR, n + ".png"), png);
    console.log(n, fs.statSync(out).size);
  }
  await b.close();
})();
