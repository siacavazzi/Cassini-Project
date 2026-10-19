// Reader and interpolator for the track files written by export_tracks.py.
// Works in the browser (fetch) and in Node (pass an ArrayBuffer to parseTrack).

export function parseTrack(buffer) {
  const head = new DataView(buffer, 0, 16);
  const magic = String.fromCharCode(head.getUint8(0), head.getUint8(1), head.getUint8(2), head.getUint8(3));
  if (magic !== "CTRK") throw new Error("not a track file");
  const count = head.getUint32(8, true);
  const t = new Float64Array(buffer, 16, count);
  const pos = new Float64Array(buffer, 16 + 8 * count, 3 * count);
  const vel = new Float32Array(buffer, 16 + 32 * count, 3 * count);
  return { count, t, pos, vel, start: t[0], end: t[count - 1] };
}

export async function loadTrack(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return parseTrack(await res.arrayBuffer());
}

// Index of the last sample at or before et (binary search).
function bracket(track, et) {
  let lo = 0, hi = track.count - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (track.t[mid] <= et) lo = mid; else hi = mid;
  }
  return lo;
}

// Position in km (J2000, solar system barycentre) at ephemeris time et, by cubic Hermite.
// Writes into out (length 3) and returns it; returns null outside the track's coverage.
export function positionAt(track, et, out = new Float64Array(3)) {
  if (et < track.start || et > track.end) return null;
  const i = bracket(track, et);
  const j = Math.min(i + 1, track.count - 1);
  const t0 = track.t[i], h = track.t[j] - t0;
  if (h <= 0) {
    out[0] = track.pos[3 * i]; out[1] = track.pos[3 * i + 1]; out[2] = track.pos[3 * i + 2];
    return out;
  }
  const u = (et - t0) / h, u2 = u * u, u3 = u2 * u;
  const h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
  for (let k = 0; k < 3; k++) {
    out[k] = h00 * track.pos[3 * i + k] + h10 * h * track.vel[3 * i + k]
           + h01 * track.pos[3 * j + k] + h11 * h * track.vel[3 * j + k];
  }
  return out;
}

// UTC ISO string to ephemeris time, good to about a millisecond after 2017 (37 leap seconds, fixed).
// Cassini's whole mission (1997 to 2017) needs the leap second table below.
const LEAPS = [[Date.UTC(1999, 0, 1), 32], [Date.UTC(2006, 0, 1), 33], [Date.UTC(2009, 0, 1), 34],
               [Date.UTC(2012, 6, 1), 35], [Date.UTC(2015, 6, 1), 36], [Date.UTC(2017, 0, 1), 37]];
const J2000_MS = Date.UTC(2000, 0, 1, 11, 58, 55, 816); // J2000 TDB expressed in UTC

export function utcToEt(iso) {
  const ms = Date.parse(iso.endsWith("Z") ? iso : iso + "Z");
  let leap = 31;
  for (const [when, n] of LEAPS) if (ms >= when) leap = n;
  return (ms - J2000_MS) / 1000 + (leap - 32);
}

// ---- Spacecraft attitude (attitude/<year>.bin from export_attitude.py) ----
// Quaternions are SPICE style (w, x, y, z) for the rotation J2000 -> CASSINI_SC_COORD:
// a J2000 vector v maps to body coordinates as q v q*. For three.js, which wants the
// body -> world rotation in (x, y, z, w) order, use new Quaternion(-x, -y, -z, w).

// Fixed camera -> CASSINI_SC_COORD rotations from the frames kernel cas_v41.tf
// (verify_attitude.py checks these against the FK).
const CAM_TO_BODY = {
  N: [0.50047271, 0.5002705, 0.49981488, -0.49944126],
  W: [0.50048319, 0.4997469, 0.5001258, -0.49964368],
};
const GAP_S = 3600; // samples further apart than this are a data gap: hold, then ease in
const EASE_S = 600; // length of the ease into the sample after a gap

// SPICE qxq: the rotation "b, then a".
function qmul(a, b, out, o) {
  const [aw, ax, ay, az] = a, bw = b[0], bx = b[1], by = b[2], bz = b[3];
  out[o] = aw * bw - ax * bx - ay * by - az * bz;
  out[o + 1] = aw * bx + ax * bw + ay * bz - az * by;
  out[o + 2] = aw * by - ax * bz + ay * bw + az * bx;
  out[o + 3] = aw * bz + ax * by - ay * bx + az * bw;
}

// Parse one year's file into a single time-sorted body attitude series: the background
// samples plus every pointed image (camera pointing turned into body pointing).
// cams is the catalog's `cam` column (N or W per image), in the same order as the file.
export function parseAttitude(buffer, cams) {
  const head = new DataView(buffer, 0, 16);
  const magic = String.fromCharCode(head.getUint8(0), head.getUint8(1), head.getUint8(2), head.getUint8(3));
  if (magic !== "CATT") throw new Error("not an attitude file");
  const nImg = head.getUint32(8, true), nBg = head.getUint32(12, true);
  if (cams.length !== nImg) throw new Error(`catalog has ${cams.length} images, attitude file ${nImg}`);
  const imgQ = new Float32Array(buffer, 16, 4 * nImg);
  const bgT = new Float64Array(buffer, 16 + 16 * nImg, nBg);
  const bgQ = new Float32Array(buffer, 16 + 16 * nImg + 8 * nBg, 4 * nBg);
  return { nImg, nBg, imgQ, bgT, bgQ };
}

// Build the interpolation series from parsed years plus their catalogs' `et` and `cam` columns:
// buildAttitude([{ file: parseAttitude(buf, cat.cam), et: cat.et, cam: cat.cam }, ...]).
export function buildAttitude(years) {
  const ts = [], qs = [];
  const tmp = new Float64Array(4);
  for (const { file, et, cam } of years) {
    for (let i = 0; i < file.nBg; i++) {
      ts.push(file.bgT[i]);
      qs.push([file.bgQ[4 * i], file.bgQ[4 * i + 1], file.bgQ[4 * i + 2], file.bgQ[4 * i + 3]]);
    }
    for (let i = 0; i < file.nImg; i++) {
      const q = file.imgQ.subarray(4 * i, 4 * i + 4);
      if (Number.isNaN(q[0])) continue;
      qmul(CAM_TO_BODY[cam[i]], q, tmp, 0);
      ts.push(et[i]);
      qs.push([tmp[0], tmp[1], tmp[2], tmp[3]]);
    }
  }
  const order = ts.map((_, i) => i).sort((a, b) => ts[a] - ts[b]);
  const t = new Float64Array(order.length), q = new Float64Array(4 * order.length);
  let n = 0;
  for (const i of order) {
    if (n && ts[i] === t[n - 1]) continue; // simultaneous NAC and WAC frames
    const [w, x, y, z] = qs[i];
    let s = Math.hypot(w, x, y, z);
    // keep neighbours in the same hemisphere so slerp takes the short way round
    if (n && w * q[4 * n - 4] + x * q[4 * n - 3] + y * q[4 * n - 2] + z * q[4 * n - 1] < 0) s *= -1;
    t[n] = ts[i];
    q[4 * n] = w / s; q[4 * n + 1] = x / s; q[4 * n + 2] = y / s; q[4 * n + 3] = z / s;
    n++;
  }
  return { count: n, t: t.subarray(0, n), q: q.subarray(0, 4 * n), start: t[0], end: t[n - 1] };
}

// Body attitude quaternion (w, x, y, z), J2000 -> CASSINI_SC_COORD, at ephemeris time et.
// Slerps between neighbouring samples; across a gap longer than GAP_S it holds the earlier
// sample and eases into the next one over its last EASE_S. Returns null outside coverage.
export function attitudeAt(att, et, out = new Float64Array(4)) {
  if (!att.count || et < att.start || et > att.end) return null;
  const i = bracket(att, et);
  const j = Math.min(i + 1, att.count - 1);
  const t0 = att.t[i], t1 = att.t[j];
  let u = t1 > t0 ? (et - t0) / (t1 - t0) : 0;
  if (t1 - t0 > GAP_S) u = Math.max(0, (et - (t1 - EASE_S)) / EASE_S);
  const a = att.q.subarray(4 * i, 4 * i + 4), b = att.q.subarray(4 * j, 4 * j + 4);
  const dot = Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]);
  let ka = 1 - u, kb = u;
  if (dot < 0.9999) {
    const th = Math.acos(dot), s = Math.sin(th);
    ka = Math.sin((1 - u) * th) / s; kb = Math.sin(u * th) / s;
  }
  let len = 0;
  for (let k = 0; k < 4; k++) { out[k] = ka * a[k] + kb * b[k]; len += out[k] * out[k]; }
  len = Math.sqrt(len);
  for (let k = 0; k < 4; k++) out[k] /= len;
  return out;
}
