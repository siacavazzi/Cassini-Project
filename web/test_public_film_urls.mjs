// A film's and its exposure graph's public addresses (docs/public-site, WP9c): with the public switch on, every picture
// a film made in the page asks for (export.html pictureUrl, through cassiniExport.publicUrl, which levels-local.js,
// the Movie Editor, the Gallery and Studio use too) is at the page's one canonical address, the one the camera
// windows ask (steady-local.html cassiniPublicUrlMaker, held to keys.mjs by web/test_public_cameras.mjs):
//   1. every address a film builds, for every kind of try, size and Settings > Movie choice the public site allows,
//      is one keys.mjs answers (not refused), under the same key as before this change (the same picture), and its
//      query is that key's, in the key's order (one address per object, so one Worker cache entry);
//   2. it is canonical already (canonicalizing it again changes nothing);
//   3. with the switch off, nothing changes;
//   4. the movie and mosaic movie frames whose steps the page works out (movieHere, rollingHere) ask through publicUrl.
// Prints how many distinct addresses the film asked per object before (export.html's own rules alone) and now.
// Run: node web/test_public_film_urls.mjs [--show]   (--show: the object asked at the most addresses before, and its addresses)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "./public/keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const K = await loadKeys();
const src = f => fs.readFileSync(path.join(here, "cassini-os", "src", f), "utf8");
const steady = src("steady-local.html"), ex = src("export.html");
const window = {};
new Function("window", steady.slice(steady.indexOf("<script>") + 8, steady.indexOf("</script>")))(window);
const P = window.cassiniPublicUrlMaker();

// export.html's publicUrl and pictureUrl as they are, with the page around them stood in for
const cut = (from, to) => { const a = ex.indexOf(from); if (a < 0) throw new Error(`export.html: ${from} not found`); return ex.slice(a, ex.indexOf("\n  }\n", ex.indexOf(to, a)) + 4); };
const code = cut("  const EXPOSURE_BUILT = 8;", "function publicUrl") + cut("  const onHost = ", "function pictureUrl");
const make = new Function("window", "location", "PUB", "FRAMES", "centreOn", "wholeLaps", code + "\nreturn { publicUrl, pictureUrl };");
const location = { href: "https://site.example.org/" };

// settings.html's cassiniLook and cassiniMovieStyle as the public switch holds Settings (balanced look, natural
// colours, every step on, Auto center on, one lap), with each Settings > Movie choice a viewer can still make
const look = (o = {}) => (o.center ? "&center=1" : "");
const styles = [];
for (const trail of [0, 3]) for (const fade of [0, 40]) for (const steady of [0, 12]) for (const exposure of [0, 5, 8]) for (const whole of [false, true])
  styles.push((o = {}) => `${o.center === false ? "&center=0" : ""}&trail=${o.trail ?? trail}&laps=1` +
    ((o.fade ?? fade) && !whole ? `&fade=${o.fade ?? fade}&persist=35` : "") + ((o.steady ?? steady) ? `&steady=${o.steady ?? steady}` : "") +
    ((o.exposure ?? exposure) ? `&exposure=${o.exposure ?? exposure}` : ""));

const N = "N1500060789_2", R = "N1500060812_2", G = "N1500060830_2", B = "N1500060850_2";
// plan-local.js source(): each kind of try's address
const TRIES = [["movie", `/frames/movie/${N}.webp`], ["rolling", `/frames/movie/${N}.webp?mode=rolling`], ["mosaic", `/frames/mosaic/${N}.webp`],
  ["color", `/frames/color.webp?ids=${R},${G},${B}`], ["color", `/frames/color.webp?ids=${R},${B}`], ["processed", `/frames/processed/${N}.webp`], ["frame", `/frames/${N}.webp`]];

let bad = 0, n = 0;
const failed = new Set(), shown = new Set();
const fail = (u, why) => { bad++; failed.add(u); if (shown.size < 20 && !shown.has(why)) { shown.add(why); console.log(`FAIL ${u}\n  ${why}`); } };
const query = key => (key.includes("~") ? key.slice(key.indexOf("~") + 1) : "");
const before = new Map(), after = new Map();   // key -> the distinct addresses asked for it
const note = (m, key, u) => { if (!m.has(key)) m.set(key, new Set()); m.get(key).add(u.replace(/^https?:\/\/[^/]*/, "")); };
for (const FRAMES of ["", "https://frames.example.org"]) {
  for (const style of styles) {
    window.cassiniLook = look; window.cassiniMovieStyle = style;
    for (const centre of [true, false]) for (const whole of [false, true]) {
      const now = make(Object.assign({}, window), location, () => true, FRAMES, () => centre, () => whole);
      const old = make(Object.assign({}, window, { cassiniPublicUrlMaker: undefined }), location, () => true, FRAMES, () => centre, () => whole);
      for (const size of [128, 256, 512, 768, 1024]) for (const [kind, s] of TRIES) for (const plain of [false, true]) {
        n++;
        const out = now.pictureUrl(kind, s, size, plain), was = old.pictureUrl(kind, s, size, plain);
        const abs = u => (/^https?:/.test(u) ? u : "https://site.example.org" + u);
        if (FRAMES && !out.startsWith(FRAMES)) fail(out, "lost the frames host");
        if (!FRAMES && /^https?:/.test(out)) fail(out, "a same-host address became absolute");
        const got = K.canonical("GET", abs(out)), prev = K.canonical("GET", abs(was));
        if (got.refused) { fail(out, `keys.mjs refuses it: ${got.refused}`); continue; }
        if (prev.refused) { fail(was, `before, refused: ${prev.refused}`); continue; }
        if (got.key !== prev.key) fail(out, `key ${got.key}, before ${prev.key}`);
        const q = out.includes("?") ? out.slice(out.indexOf("?") + 1) : "";
        if (q !== query(got.key)) fail(out, `query ${q} is not the key's ${query(got.key)}`);
        if (P(out) !== out) fail(out, `not canonical: ${P(out)}`);
        note(before, got.key, was); note(after, got.key, out);
      }
    }
  }
}
// with the switch off, publicUrl gives back what it is given
{
  const off = make(Object.assign({}, window), location, () => false, "", () => true, () => false);
  for (const u of [`/frames/movie/${N}.webp?size=1024&color=1&trail=3&laps=1&fade=40&persist=35&steady=12&exposure=5`, `/frames/${N}.webp?size=512&download=1`]) {
    n++;
    if (off.publicUrl(u) !== u) fail(u, `changed with the switch off: ${off.publicUrl(u)}`);
  }
}
// 4. movieHere and rollingHere ask through publicUrl
for (const f of ["movieHere", "rollingHere"]) {
  n++;
  const body = cut(`  async function ${f}(`, `async function ${f}(`);
  if (!/await fetch\(publicUrl\(/.test(body)) fail(f, "fetches its picture without publicUrl");
}
const spread = m => { let k = 0, most = 0; for (const s of m.values()) { k += s.size; most = Math.max(most, s.size); } return { objects: m.size, addresses: k, most }; };
const b = spread(before), a = spread(after);
if (process.argv.includes("--show")) {
  const [key, was] = [...before.entries()].sort((x, y) => y[1].size - x[1].size)[0];
  console.log(`the object asked at the most addresses before, ${key}:\n  before:\n    ${[...was].sort().join("\n    ")}\n  now:\n    ${[...after.get(key)].join("\n    ")}`);
}
console.log(`objects asked: ${a.objects}; addresses asked for them: before ${b.addresses} (up to ${b.most} for one object), now ${a.addresses} (up to ${a.most})`);
console.log(`${n - failed.size} of ${n} film addresses as keys.mjs keys them${bad ? `; ${failed.size} not (${bad} failures)` : ""}`);
process.exit(bad ? 1 : 0);
