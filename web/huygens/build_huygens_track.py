#!/usr/bin/env python3
"""
Build the Huygens probe track for the mission replay.

One continuous track from separation (2004-12-25T02:00 UTC) to 2005-01-15T00:00 UTC:

  coast     SPK -150 (050214R_SCPSE) until 10 minutes before entry interface
  blend     SPK plus a cubic Hermite fade of the SPK-vs-DTWG offset (position and velocity),
            so the track is C1 and equals DTWG exactly at entry interface
  entry     DTWG V2.0 HUY_DTWG_ENTRY until the first descent row (09:12:19 UTC), then a 60 s
            fade into HUY_DTWG_DESCENT_POS (the two tables agree to about 60 m there)
  descent   DTWG V2.0 HUY_DTWG_DESCENT_POS to landing (11:38:10.769 UTC)
  surface   the landing point held fixed in IAU_TITAN (rotating with Titan)

DTWG rows are planetocentric latitude, west longitude and altitude above a 2575 km sphere in
IAU_TITAN; they reproduce the DTWG's own EME2000 table to under a metre with pck00011.

Writes tracks/huygens/<year>.bin in the export_tracks.py format and manifest_huygens.json.

Usage: python tools/build_huygens_track.py --root /Users/sam/Development/huygens-data
"""

import argparse
import json
import os
import struct

import numpy as np
import spiceypy as sp
from scipy.interpolate import CubicSpline

PROBE, CASSINI, TITAN = -150, -82, 606
R_REF = 2575.0
SEPARATION_UTC = "2004-12-25T02:00:00"
END_UTC = "2005-01-15T00:00:00"
BLEND_S = 600.0          # SPK -> DTWG fade length before entry interface
STITCH_S = 60.0          # entry -> descent table fade length
ANGULAR_TOL = 5e-6       # coast: error seen from Cassini, radians
TOL_FLOOR, TOL_CAP = 0.01, 50.0   # km
DESCENT_TOL = 0.01       # km, against every DTWG source row (and the landed point)


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def hermite(t0, s0, t1, s1, t):
    h = t1 - t0
    u = (t - t0) / h
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    return (np.multiply.outer(h00, s0[:3]) + np.multiply.outer(h10 * h, s0[3:])
            + np.multiply.outer(h01, s1[:3]) + np.multiply.outer(h11 * h, s1[3:]))


class Source:
    def __init__(self, root):
        k = os.path.join(root, "raw/spice")
        for f in ("lsk/naif0012.tls", "pck/pck00011.tpc", "spk/050214R_SCPSE_04336_05015.bsp"):
            sp.furnsh(os.path.join(k, f))
        d = os.path.join(root, "raw/psa/DTWG/HP-SSA-DTWG-6-TRAJECTORY-V2.0/DATA")
        entry = np.loadtxt(f"{d}/HUY_DTWG_ENTRY.TAB", usecols=(0, 3, 4, 5))
        desc = np.loadtxt(f"{d}/HUY_DTWG_DESCENT_POS.TAB", usecols=(0, 4, 5, 6))
        evel = np.loadtxt(f"{d}/HUY_DTWG_ENTRY_EME2000_VEL.TAB", usecols=(3, 4, 5))

        self.t_spk_end = sp.wnfetd(sp.spkcov(os.path.join(k, "spk/050214R_SCPSE_04336_05015.bsp"), PROBE), 0)[1]
        self.t_sep = sp.str2et(SEPARATION_UTC)
        self.t_end = sp.str2et(END_UTC)
        self.t_ei = entry[0, 0]                      # entry interface: first DTWG row
        self.t_b0 = self.t_ei - BLEND_S
        self.t_st = desc[0, 0]                       # first descent row
        self.t_land = desc[-1, 0]

        # stitched DTWG rows in IAU_TITAN body-fixed coordinates
        bf = lambda r: np.array(sp.latrec(R_REF + r[1], np.radians(-r[2]), np.radians(r[3])))
        e_by_t = {round(r[0], 3): bf(r) for r in entry}
        rows_t, rows_bf = [], []
        for r in entry:
            if r[0] < self.t_st:
                rows_t.append(r[0]); rows_bf.append(bf(r))
        for r in desc:
            p = bf(r)
            w = smooth((r[0] - self.t_st) / STITCH_S)
            pe = e_by_t.get(round(r[0], 3))
            if pe is not None and w < 1:
                p = (1 - w) * pe + w * p
            rows_t.append(r[0]); rows_bf.append(p)
        self.rows_t = np.array(rows_t)
        self.rows_bf = np.array(rows_bf)
        self.rows_alt = np.concatenate([entry[entry[:, 0] < self.t_st, 1], desc[:, 1]])
        # Titan-centred J2000 positions of the source rows, splined for velocity
        self.rows_rel = np.array([sp.pxform("IAU_TITAN", "J2000", t) @ p for t, p in zip(self.rows_t, self.rows_bf)])
        self.spline = CubicSpline(self.rows_t, self.rows_rel, bc_type="not-a-knot")
        self.land_bf = self.rows_bf[-1]

        # SPK -> DTWG correction, fixed at entry interface
        s_spk = self.spk_rel(self.t_ei)
        self.dp = self.rows_rel[0] - s_spk[:3]
        self.dv = evel[0] - s_spk[3:]
        self.raw_jump_km = float(np.linalg.norm(self.dp))
        self.raw_dv_kms = float(np.linalg.norm(self.dv))

    def titan(self, et):
        return np.array(sp.spkezr(str(TITAN), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0])

    def spk_rel(self, et):
        et = min(et, self.t_spk_end - 1e-3)
        return np.array(sp.spkezr(str(PROBE), et, "J2000", "NONE", str(TITAN))[0])

    def correction(self, et):
        """Cubic Hermite fade from 0 at t_b0 to (dp, dv) at entry interface."""
        T = self.t_ei - self.t_b0
        s = (et - self.t_b0) / T
        h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
        d01, d11 = (-6 * s**2 + 6 * s) / T, (3 * s**2 - 2 * s) / T
        return np.concatenate([h01 * self.dp + h11 * T * self.dv, d01 * self.dp + d11 * T * self.dv])

    def rel_state(self, et, blend=True):
        """Probe state relative to Titan, J2000."""
        if et < self.t_ei:
            s = self.spk_rel(et)
            if blend and et > self.t_b0:
                s = s + self.correction(et)
            return s
        if et <= self.t_land:
            return np.concatenate([self.spline(et), self.spline(et, 1)])
        xf = sp.sxform("IAU_TITAN", "J2000", et)
        return xf @ np.concatenate([self.land_bf, [0, 0, 0]])

    def state(self, et):
        return self.titan(et) + self.rel_state(et)

    def segment(self, et):
        if et < self.t_b0: return "coast"
        if et < self.t_ei: return "blend"
        if et < self.t_st + STITCH_S: return "entry"
        if et <= self.t_land: return "descent"
        return "surface"

    def tol(self, et, pos):
        if et >= self.t_ei:          # entry, descent and the landed point: 10 m
            return DESCENT_TOL
        c = np.array(sp.spkpos(str(CASSINI), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0])
        return min(TOL_CAP, max(TOL_FLOOR, ANGULAR_TOL * float(np.linalg.norm(pos - c))))


def sample(src, a, b, step0, min_step=0.5):
    """Adaptive Hermite sampling between a and b. In the DTWG span the error is checked at
    every source row inside the interval; elsewhere at the midpoint (as export_tracks.py does)."""
    grid = list(np.arange(a, b, step0)) + [b]
    out = [(grid[0], src.state(grid[0]))]
    for t1 in grid[1:]:
        stack = [(out[-1][0], out[-1][1], t1, src.state(t1))]
        while stack:
            ta, sa, tb, sb = stack.pop()
            tm = 0.5 * (ta + tb)
            sm = src.state(tm)
            err = np.linalg.norm(hermite(ta, sa, tb, sb, tm) - sm[:3])
            for tq in (ta + 0.25 * (tb - ta), ta + 0.75 * (tb - ta)):
                err = max(err, float(np.linalg.norm(hermite(ta, sa, tb, sb, tq) - src.state(tq)[:3])))
            if src.t_ei <= ta and tb <= src.t_land:
                m = (src.rows_t > ta) & (src.rows_t < tb)
                if m.any():
                    tt = src.rows_t[m]
                    truth = src.rows_rel[m] + np.array([src.titan(t)[:3] for t in tt])
                    err = max(err, float(np.max(np.linalg.norm(hermite(ta, sa, tb, sb, tt) - truth, axis=1))))
            if err > src.tol(tm, sm[:3]) and tb - ta > 2 * min_step:
                stack.append((tm, sm, tb, sb))
                stack.append((ta, sa, tm, sm))
            else:
                out.append((tb, sb))
    return out


def write_track(path, samples):
    t = np.array([s[0] for s in samples], dtype="<f8")
    st = np.array([s[1] for s in samples])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"CTRK" + struct.pack("<HHII", 1, 0, len(t), 0))
        fh.write(t.tobytes())
        fh.write(st[:, :3].astype("<f8").tobytes())
        fh.write(st[:, 3:].astype("<f4").tobytes())
    return len(t), os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    args = ap.parse_args()
    src = Source(args.root)
    out = os.path.join(args.root, "replay")
    y2005 = sp.str2et("2005-01-01T00:00:00")
    # breakpoints that are always samples
    bps = [src.t_sep, y2005, src.t_b0, src.t_ei, src.t_st, src.t_st + STITCH_S, src.t_land, src.t_end]
    pieces = {2004: [], 2005: []}
    steps = {src.t_sep: 3600.0, y2005: 3600.0, src.t_b0: 60.0, src.t_ei: 30.0,
             src.t_st: 10.0, src.t_st + STITCH_S: 60.0, src.t_land: 1800.0}
    for a, b in zip(bps[:-1], bps[1:]):
        year = 2004 if b <= y2005 else 2005
        seg = sample(src, a, b, steps[a])
        if pieces[year]:
            seg = seg[1:]          # shared breakpoint
        pieces[year] += seg
        print(f"{sp.et2utc(a, 'ISOC', 0)} -> {sp.et2utc(b, 'ISOC', 0)}  {src.segment(0.5 * (a + b)):8s} {len(seg):6d} samples", flush=True)

    chunks = []
    for year, samples in pieces.items():
        rel = f"tracks/huygens/{year}.bin"
        count, size = write_track(os.path.join(out, rel), samples)
        chunks.append({"year": year, "file": rel, "count": count, "bytes": size,
                       "coverage_et": [[samples[0][0], samples[-1][0]]]})
        print(f"{rel}: {count} samples, {size} bytes")
    manifest = {"HUYGENS": {
        "naif_id": PROBE, "chunks": chunks,
        "sources": {"coast": "NAIF 050214R_SCPSE_04336_05015.bsp (-150)",
                    "entry_descent": "ESA PSA HP-SSA-DTWG-6-TRAJECTORY-V2.0 (HUY_DTWG_ENTRY, HUY_DTWG_DESCENT_POS)",
                    "pck": "pck00011.tpc", "lsk": "naif0012.tls"},
        "events_et": {"separation": src.t_sep, "blend_start": src.t_b0, "entry_interface": src.t_ei,
                      "descent_table_start": src.t_st, "landing": src.t_land, "track_end": src.t_end},
        "landing_site": {"lat_deg": -10.5730225, "lon_w_deg": 192.3346498, "lon_e_deg": 360 - 192.3346498,
                         "radius_km": R_REF},
        "handover": {"raw_jump_km": round(src.raw_jump_km, 3), "raw_dv_km_s": round(src.raw_dv_kms, 5),
                     "blend_s": BLEND_S},
    }}
    with open(os.path.join(out, "manifest_huygens.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(json.dumps(manifest["HUYGENS"]["handover"]))


if __name__ == "__main__":
    main()
