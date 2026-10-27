#!/usr/bin/env node
// Summarizes a stream run from stats.jsonl (stream.mjs writes one line a minute):
//   node web/stream/report.mjs ~/server/stream/stats.jsonl [--since 2026-10-26T22:00]
import fs from "node:fs";

const [file, flag, since] = process.argv.slice(2);
if (!file) { console.error("usage: report.mjs stats.jsonl [--since ISO]"); process.exit(1); }
let rows = fs.readFileSync(file, "utf8").split("\n").filter(Boolean).map(l => JSON.parse(l));
if (flag === "--since") rows = rows.filter(r => r.at >= since);
if (!rows.length) { console.log("no samples"); process.exit(0); }
const q = (a, p) => { a = a.filter(x => x != null && !isNaN(x)).sort((x, y) => x - y); return a.length ? a[Math.min(a.length - 1, Math.floor(p * a.length))] : null; };
const mean = a => { a = a.filter(x => x != null && !isNaN(x)); return a.length ? a.reduce((s, x) => s + x, 0) / a.length : null; };
const f = (x, d = 1) => x == null ? "-" : (+x).toFixed(d);
const col = (k, g) => rows.map(r => g ? r[k]?.[g] : r[k]);
const restarts = rows.filter((r, i) => i && r.up < rows[i - 1].up).length;
const hours = (Date.parse(rows.at(-1).at) - Date.parse(rows[0].at)) / 3600e3;
console.log(`${rows[0].at} to ${rows.at(-1).at}: ${f(hours, 2)} h, ${rows.length} samples, ${restarts} restarts\n`);
const table = [
  ["page animation frames/s (rAF)", col("rafFps")], ["page frames/s (screencast)", col("pageFps")], ["frames/s to ffmpeg", col("outFps")], ["ffmpeg encode frames/s", col("ffFps")],
  ["ffmpeg speed (1 = real time)", col("speed").map(parseFloat)],
  ["Chrome CPU, cores", col("cpu", "chrome")], ["ffmpeg CPU, cores", col("cpu", "ffmpeg")], ["capture script CPU, cores", col("cpu", "node")],
  ["Chrome memory, MB", col("rssMb", "chrome")], ["ffmpeg memory, MB", col("rssMb", "ffmpeg")], ["page JS heap, MB", col("heapMb")],
  ["load average", col("load")], ["Mini memory available, GB", col("availGb")],
];
console.log("| measure | mean | median | p5 | p95 | first | last |\n|---|---|---|---|---|---|---|");
for (const [name, a] of table) {
  const v = a.filter(x => x != null && !isNaN(x));
  console.log(`| ${name} | ${f(mean(v), 2)} | ${f(q(v, .5), 2)} | ${f(q(v, .05), 2)} | ${f(q(v, .95), 2)} | ${f(v[0], 2)} | ${f(v.at(-1), 2)} |`);
}
const cores = rows.map(r => ["chrome", "ffmpeg", "node"].reduce((s, k) => s + (r.cpu?.[k] || 0), 0));
const mem = rows.map(r => ["chrome", "ffmpeg", "node"].reduce((s, k) => s + (r.rssMb?.[k] || 0), 0));
console.log(`\nWhole rig: ${f(mean(cores), 2)} cores on average (p95 ${f(q(cores, .95), 2)}), ${f(mean(mem), 0)} MB of memory (max ${f(Math.max(...mem), 0)} MB).`);
const growth = (rows.at(-1).rssMb?.chrome - rows[0].rssMb?.chrome) / Math.max(hours, 1e-9);
if (hours >= 1) console.log(`Chrome memory grew ${f(growth, 0)} MB an hour over the run.`);
