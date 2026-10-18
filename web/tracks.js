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
