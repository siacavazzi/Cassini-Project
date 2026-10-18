// node web/test_attitude.mjs <attitude/<year>.bin> <catalog/<year>.json[.gz]> < ets.json
// Reads a JSON array of ephemeris times on stdin and prints attitudeAt() for each as JSON
// (null outside coverage), for comparison with SPICE in verify_attitude.py.
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { parseAttitude, buildAttitude, attitudeAt } from "./tracks.js";

const [binPath, catPath] = process.argv.slice(2);
const raw = readFileSync(catPath);
// catalogs written by Python can hold bare NaN (range_km etc.), which JSON.parse rejects
const cat = JSON.parse((catPath.endsWith(".gz") ? gunzipSync(raw) : raw).toString().replace(/\bNaN\b/g, "null"));
const buf = readFileSync(binPath);
const file = parseAttitude(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), cat.cam);
const att = buildAttitude([{ file, et: cat.et, cam: cat.cam }]);
const ets = JSON.parse(readFileSync(0, "utf8"));
console.log(JSON.stringify(ets.map((et) => { const q = attitudeAt(att, et); return q && Array.from(q); })));
