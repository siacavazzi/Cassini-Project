// node web/test_tracks.mjs <track.bin> <et> [<et> ...]
// Prints the interpolated position for each ephemeris time as JSON, for comparison with SPICE.
import { readFileSync } from "node:fs";
import { parseTrack, positionAt, utcToEt } from "./tracks.js";

const [file, ...rest] = process.argv.slice(2);
const buf = readFileSync(file);
const track = parseTrack(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const out = rest.map((arg) => {
  const et = arg.includes("T") ? utcToEt(arg) : Number(arg);
  const p = positionAt(track, et);
  return { arg, et, pos: p && Array.from(p) };
});
console.log(JSON.stringify(out));
