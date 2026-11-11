// keys.mjs reproduces every answer in key_fixtures.json exactly (the same file test_keys.py holds keys.py to).
// Run: node web/public/test_keys.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadKeys } from "./keys.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(fs.readFileSync(path.join(here, "key_fixtures.json"), "utf8"));
const K = await loadKeys();
const sorted = v => Array.isArray(v) ? v.map(sorted) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])])) : v;
let bad = 0;
for (const c of fx.cases) {
  const got = JSON.stringify(sorted(K.canonical(c.method || "GET", c.url)));
  const want = JSON.stringify(sorted(c.expect));
  if (got !== want) { bad++; console.log(`FAIL ${c.method} ${c.url}\n  want ${want}\n  got  ${got}`); }
}
// tags fill in: a family's tag replaces {tag}
const t = K.canonical("GET", "/frames/N1500060789_2.webp?size=1024", { frame: "tabc" });
if (t.key !== "frame/tabc/frames/N1500060789_2.webp~size=1024") { bad++; console.log("FAIL tags", t.key); }
const a = K.canonical("GET", "/frames/movie/N1500060789_2.steady.json", { table: "tdef" });
if (a.alias_key !== "table/tdef/alias/N15000.json" || a.part_key !== "table/tdef/pass/{pass}/steady/c1k0.json") { bad++; console.log("FAIL table tags", a); }
console.log(`${fx.cases.length - bad + 0} of ${fx.cases.length} fixtures match${bad ? `, ${bad} failures` : ""}`);
process.exit(bad ? 1 : 0);
