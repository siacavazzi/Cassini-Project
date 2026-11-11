// The camera windows' public addresses (docs/public-site, WP5): with the public switch on, the page asks for every
// picture and table at its canonical address (steady-local.html PUBLIC_URL, window.cassiniPublicUrl). This holds that
// port to web/public/keys.mjs, the contract the Worker answers from:
//   1. every frames-host fixture of key_fixtures.json the public site answers, and every address the camera windows,
//      the lens and the save menu build (CAMERA below, as head-quiet.html, steady-local.html and loupe.html build
//      them with the switch on), canonicalized by the page, is one keys.mjs answers (not refused), under the same key
//      as the address it came from; and its query is that key's, in the key's order (one address per object), but for
//      the page's one choice of its own: a colour picture's full is asked at 1024, its same picture (D3);
//   2. the page's address is canonical already (canonicalizing it again changes nothing), and a fragment stays;
//   3. what the route refuses stays in the address, so the zero-origin harness counts it rather than the page hiding it.
// Run: node web/test_public_cameras.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "./public/keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const K = await loadKeys();
const page = fs.readFileSync(path.join(here, "cassini-os", "src", "steady-local.html"), "utf8");
const script = page.slice(page.indexOf("<script>") + 8, page.indexOf("</script>"));
const window = {};
new Function("window", script)(window);
const P = window.cassiniPublicUrlMaker();

const F = "https://frames.example.org";
const N = "N1500060789_2", W = "W1500060801_2", R = "N1500060812_2", G = "N1500060830_2", B = "N1500060850_2";
// the addresses the camera windows build with the switch on (cassiniLook, cassiniHdr and cassiniMovieStyle as WP6's
// switch holds Settings: balanced look, natural colours, every step on, Auto center on, HDR off, one lap), at every
// size a window asks (cassiniWM.sized: 256, 512, 1024; full view: full; the filmstrip and tiles: 128, 256)
const CAMERA = [];
for (const sz of [128, 256, 384, 512, 768, 1024, "full"]) {
  CAMERA.push(`${F}/frames/${N}.webp?size=${sz}`,
    `${F}/frames/color.webp?ids=${R},${G},${B}&size=${sz}&center=1`, `${F}/frames/color.webp?ids=${R},${B}&size=${sz}`,
    `${F}/frames/processed/${N}.webp?size=${sz}&center=1`, `${F}/frames/processed/${W}.webp?size=${sz}`,
    `${F}/frames/mosaic/${N}.webp?size=${sz}`, `${F}/frames/mosaic/${N}.webp?size=${sz}&force=1`,
    `${F}/frames/movie/${N}.webp?mode=rolling&size=${sz}`);
}
for (const sz of [128, 512, 1024, "full"]) for (const ex of ["", "&exposure=8"]) CAMERA.push(`${F}/frames/movie/${N}.webp?size=${sz}&color=1${ex}`);
CAMERA.push(
  `${F}/frames/movie/${N}.webp?size=1024&color=0`, `${F}/frames/movie/${N}.webp?size=1024&color=0&detail=0`,
  `${F}/frames/movie/${N}.webp?size=1024&color=0&detail=0#here=s12e8t0c1`, `${F}/frames/movie/${N}.webp?mode=rolling&size=1024#fade=40p35l1`,
  `${F}/frames/color.webp?ids=${R},${G},${B}&size=1024&center=1#ch=2`,
  `${F}/frames/mosaic/${N}.webp?warm=1`, `${F}/frames/mosaic/${N}.json?x=1`,
  `${F}/frames/movie/${N}.json`, `${F}/frames/movie/${N}.steady.json?center=1&color=0`, `${F}/frames/movie/${N}.steady.json?center=1&color=1`,
  `${F}/frames/movie/${N}.fade.json?laps=1&w=1024&h=1024`, `${F}/frames/${N}.png?download=1`,
  // what the windows built before the switch (each param the key drops or reads as its default, as the page added it)
  `${F}/frames/movie/${N}.webp?size=1024&color=0&trail=0&laps=1`, `${F}/frames/movie/${N}.webp?size=512&color=1&trail=0&laps=1&fade=40&persist=35`,
  `${F}/frames/movie/${N}.webp?mode=rolling&size=512&trail=0&laps=1&exposure=8&center=0&whole=1&hdr=1`,
  `${F}/frames/processed/${N}.webp?size=full&center=1&hdr=1&look=balanced&colors=natural&off=`, `${F}/frames/mosaic/${N}.json?x=1&look=balanced`);

const fixtures = JSON.parse(fs.readFileSync(path.join(here, "public", "key_fixtures.json"), "utf8")).cases
  .filter(c => (c.method || "GET") === "GET" && /^\/frames\//.test(c.url) && !c.expect.refused).map(c => F + c.url);

let bad = 0, n = 0;
const fail = (u, why) => { bad++; console.log(`FAIL ${u}\n  ${why}`); };
const query = key => (key.includes("~") ? key.slice(key.indexOf("~") + 1) : "");
for (const u of [...fixtures, ...CAMERA]) {
  n++;
  const out = P(u), want = K.canonical("GET", u), got = K.canonical("GET", out);
  if (got.refused) { fail(u, `page asks ${out}, which keys.mjs refuses: ${got.refused}`); continue; }
  if (want.refused) { fail(u, `fixture refused: ${want.refused}`); continue; }
  if (P(out) !== out) fail(u, `not canonical: ${out} -> ${P(out)}`);
  const frag = u.includes("#") ? u.slice(u.indexOf("#")) : "";
  if (!out.endsWith(frag)) fail(u, `fragment lost: ${out}`);
  const bare = out.replace(/#.*$/, ""), q = bare.includes("?") ? bare.slice(bare.indexOf("?") + 1) : "";
  const colourFull = got.route === "color" && want.params.size === "full";
  if (got.key !== undefined && got.key !== null) {
    const expectKey = colourFull ? want.key.replace("size=full", "size=1024") : want.key;
    if (got.key !== expectKey) fail(u, `key ${got.key}, the address it came from ${want.key}`);
    // the page's query is the key's, but for what routes the address (mode=rolling, kept in the key too) and download
    const asked = q.split("&").filter(p => p && !/^download=/.test(p)).join("&");
    if (asked !== query(got.key)) fail(u, `address ${q} is not the key's ${query(got.key)}`);
  } else {
    // a table: the same part, and only what the part reads
    if (got.part_key !== want.part_key || got.alias_key !== want.alias_key) fail(u, `table ${got.part_key} / ${want.part_key}`);
    const kept = q.split("&").filter(p => p && !/^warm=/.test(p));
    if (kept.some(p => !(p.split("=")[0] in got.params))) fail(u, `address ${q} asks more than the table reads (${JSON.stringify(got.params)})`);
  }
}
// 3. a refusal stays in the address (the harness counts it)
for (const u of [`${F}/frames/color.webp?ids=${R},${G},${B}&size=512&channel=1`, `${F}/frames/movie/${N}.webp?mode=rolling&size=512&laps=3`,
  `${F}/frames/movie/${N}.webp?size=512&steady=12`, `${F}/frames/processed/${N}.webp?size=512&look=classic`]) {
  n++;
  if (!K.canonical("GET", P(u)).refused) fail(u, `the page's ${P(u)} hides a refusal`);
}
// with the switch off, nothing changes
window.cassiniPublic = false;
for (const u of CAMERA) if (window.cassiniPublicUrl(u) !== u) fail(u, "changed with the public switch off");
window.cassiniPublic = true;
if (window.cassiniPublicUrl(CAMERA[1]) !== P(CAMERA[1])) fail(CAMERA[1], "not canonical with the switch on");
console.log(`${n - bad} of ${n} addresses as keys.mjs keys them${bad ? `, ${bad} failures` : ""}`);
process.exit(bad ? 1 : 0);
