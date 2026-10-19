#!/usr/bin/env python3
"""
Check the Huygens track files against their sources.

  coast     random times vs SPK -150 (km, and microradians seen from Cassini)
  blend     random times vs the blended source, plus how far the blend moves off the raw SPK
  DTWG      every DTWG row (entry + descent) vs the track; also vs the unstitched tables
  surface   random times vs the landed body-fixed point
  handover  position and velocity continuity at entry interface, and in 1 s steps across it
  reader    a few points through tracks.js (Node) vs the Python Hermite

Usage: python tools/verify_huygens_track.py --root /Users/sam/Development/huygens-data
Writes replay/verify_huygens.json.
"""

import argparse
import json
import os
import subprocess

import numpy as np
import spiceypy as sp

from build_huygens_track import Source, R_REF


def load(path):
    b = open(path, "rb").read()
    assert b[:4] == b"CTRK"
    n = int(np.frombuffer(b[8:12], "<u4")[0])
    t = np.frombuffer(b, "<f8", n, 16)
    pos = np.frombuffer(b, "<f8", 3 * n, 16 + 8 * n).reshape(n, 3)
    vel = np.frombuffer(b, "<f4", 3 * n, 16 + 32 * n).reshape(n, 3).astype(float)
    return t, pos, vel


class Track:
    def __init__(self, files):
        parts = [load(f) for f in files]
        self.t = np.concatenate([p[0] for p in parts])
        self.pos = np.concatenate([p[1] for p in parts])
        self.vel = np.concatenate([p[2] for p in parts])
        keep = np.concatenate([[True], np.diff(self.t) > 0])     # shared year-boundary sample
        self.t, self.pos, self.vel = self.t[keep], self.pos[keep], self.vel[keep]

    def at(self, et, deriv=False):
        i = np.clip(np.searchsorted(self.t, et, side="right") - 1, 0, len(self.t) - 2)
        h = self.t[i + 1] - self.t[i]
        u = (et - self.t[i]) / h
        if deriv:
            c = [(6 * u**2 - 6 * u) / h, 3 * u**2 - 4 * u + 1, (-6 * u**2 + 6 * u) / h, 3 * u**2 - 2 * u]
        else:
            c = [2 * u**3 - 3 * u**2 + 1, (u**3 - 2 * u**2 + u) * h, -2 * u**3 + 3 * u**2, (u**3 - u**2) * h]
        c = [np.asarray(x)[..., None] for x in c]
        return c[0] * self.pos[i] + c[1] * self.vel[i] + c[2] * self.pos[i + 1] + c[3] * self.vel[i + 1]


def stats(err):
    err = np.asarray(err)
    return {"n": int(err.size), "max": float(err.max()), "median": float(np.median(err)), "p99": float(np.percentile(err, 99))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    args = ap.parse_args()
    root = args.root
    src = Source(root)
    tr = Track([os.path.join(root, f"replay/tracks/huygens/{y}.bin") for y in (2004, 2005)])
    rng = np.random.default_rng(1)
    res = {"samples": int(len(tr.t)), "start_utc": sp.et2utc(tr.t[0], "ISOC", 3), "end_utc": sp.et2utc(tr.t[-1], "ISOC", 3)}

    # coast vs SPK
    ts = rng.uniform(src.t_sep, src.t_b0, 3000)
    e_km, e_urad, ratio, far = [], [], [], []
    for t in ts:
        truth = src.titan(t)[:3] + src.spk_rel(t)[:3]
        d = np.linalg.norm(tr.at(t) - truth)
        cas = np.array(sp.spkpos("-82", t, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0])
        rng_km = np.linalg.norm(truth - cas)
        e_km.append(d); ratio.append(d / src.tol(t, truth))
        if rng_km > 2000:          # beyond the 10 m floor (5 urad x 2000 km = 10 m)
            e_urad.append(1e6 * d / rng_km)
    res["coast_vs_spk_km"] = stats(e_km)
    res["coast_err_over_budget"] = stats(ratio)
    res["coast_vs_spk_urad_from_cassini_beyond_2000km"] = stats(e_urad)

    # blend vs blended source, and offset from raw SPK
    ts = np.linspace(src.t_b0, src.t_ei, 601)
    res["blend_vs_source_km"] = stats([np.linalg.norm(tr.at(t) - src.state(t)[:3]) for t in ts])
    res["blend_off_raw_spk_km"] = stats([np.linalg.norm(tr.at(t) - src.titan(t)[:3] - src.spk_rel(t)[:3]) for t in ts])

    # every DTWG source row (stitched) vs track
    tit = np.array([src.titan(t)[:3] for t in src.rows_t])
    res["dtwg_rows_vs_track_m"] = stats(1000 * np.linalg.norm(tr.at(src.rows_t) - (src.rows_rel + tit), axis=1))
    # altitude, lat, lon as recovered from the track, vs the DTWG tables as published
    d = os.path.join(root, "raw/psa/DTWG/HP-SSA-DTWG-6-TRAJECTORY-V2.0/DATA")
    desc = np.loadtxt(f"{d}/HUY_DTWG_DESCENT_POS.TAB", usecols=(0, 4, 5, 6))
    entry = np.loadtxt(f"{d}/HUY_DTWG_ENTRY.TAB", usecols=(0, 3, 4, 5))
    for name, tab in (("descent_table", desc[desc[:, 0] >= src.t_st + 60]), ("entry_table", entry[entry[:, 0] < src.t_st])):
        p = tr.at(tab[:, 0])
        da, dh = [], []
        for t, q, r in zip(tab[:, 0], p, tab):
            bf = sp.pxform("J2000", "IAU_TITAN", t) @ (q - src.titan(t)[:3])
            rad, lon, lat = sp.reclat(bf)
            da.append(1000 * abs(rad - R_REF - r[1]))
            truth = np.array(sp.latrec(R_REF + r[1], np.radians(-r[2]), np.radians(r[3])))
            dh.append(1000 * np.linalg.norm(bf - truth))
        res[f"{name}_alt_err_m"] = stats(da)
        res[f"{name}_pos_err_m"] = stats(dh)
    # entry vs descent tables where they overlap (what the 60 s stitch absorbs)
    eb = {round(r[0], 3): r for r in entry}
    ov = [np.linalg.norm(np.array(sp.latrec(R_REF + r[1], np.radians(-r[2]), np.radians(r[3])))
                         - np.array(sp.latrec(R_REF + eb[round(r[0], 3)][1], np.radians(-eb[round(r[0], 3)][2]), np.radians(eb[round(r[0], 3)][3]))))
          for r in desc if round(r[0], 3) in eb]
    res["entry_vs_descent_overlap_km"] = stats(ov)
    res["entry_vs_descent_at_stitch_km"] = float(ov[0])

    # surface vs landed point
    ts = np.concatenate([rng.uniform(src.t_land, src.t_land + 600, 500), rng.uniform(src.t_land + 1, src.t_end, 2000)])
    res["surface_vs_landed_point_m"] = stats([1000 * np.linalg.norm(tr.at(t) - src.state(t)[:3]) for t in ts])
    lp = [sp.reclat(sp.pxform("J2000", "IAU_TITAN", t) @ (tr.at(t) - src.titan(t)[:3])) for t in ts[:5]]
    res["surface_latlon_check"] = [[round(np.degrees(l[2]), 5), round((-np.degrees(l[1])) % 360, 5)] for l in lp]

    # handover continuity
    tE = src.t_ei
    p_lo, p_hi = tr.at(tE - 1e-3), tr.at(tE + 1e-3)
    v_lo, v_hi = tr.at(tE - 1e-3, True), tr.at(tE + 1e-3, True)
    truth = src.rows_rel[0] + src.titan(tE)[:3]
    ts = np.arange(src.t_b0 - 300, tE + 300, 1.0)
    p = tr.at(ts)
    v = tr.at(ts, True)
    rel_v = v - np.array([src.titan(t)[3:] for t in ts])
    acc = np.linalg.norm(np.diff(rel_v, axis=0), axis=1)   # km/s per s
    inb = (ts[1:] > src.t_b0) & (ts[1:] <= tE)
    spk_acc = np.linalg.norm(np.diff(np.array([src.spk_rel(t)[3:] for t in ts]), axis=0), axis=1)
    raw = np.array([src.titan(t)[:3] + (src.spk_rel(t)[:3] if t < tE else src.spline(t)) for t in ts])
    res["handover"] = {
        "raw_jump_km": src.raw_jump_km, "raw_dv_km_s": src.raw_dv_kms,
        "track_vs_dtwg_at_entry_m": float(1000 * np.linalg.norm(tr.at(tE) - truth)),
        "position_step_across_entry_m": float(1000 * np.linalg.norm(p_hi - p_lo - 0.5 * (v_lo + v_hi) * 2e-3)),
        "velocity_step_across_entry_m_s": float(1000 * np.linalg.norm(v_hi - v_lo)),
        "max_1s_step_km_blended": float(np.max(np.linalg.norm(np.diff(p, axis=0), axis=1))),
        "max_1s_step_km_raw": float(np.max(np.linalg.norm(np.diff(raw, axis=0), axis=1))),
        "max_accel_m_s2_in_blend": float(1000 * acc[inb].max()),
        "max_accel_m_s2_raw_spk_in_blend": float(1000 * spk_acc[inb].max()),
        "speed_km_s_at_entry": float(np.linalg.norm(rel_v[np.searchsorted(ts, tE)])),
    }

    # tracks.js reader through Node
    ets = [float(x) for x in rng.uniform(src.t_sep, src.t_end, 6)] + [src.t_ei, src.t_land]
    js = []
    for y in (2004, 2005):
        f = os.path.join(root, f"replay/tracks/huygens/{y}.bin")
        mine = [e for e in ets if (e < sp.str2et("2005-01-01")) == (y == 2004)]
        out = subprocess.run(["node", os.path.join(root, "tools/test_tracks.mjs"), f] + [repr(e) for e in mine],
                             capture_output=True, text=True, check=True).stdout
        for row in json.loads(out):
            js.append(1000 * float(np.linalg.norm(np.array(row["pos"]) - tr.at(row["et"]))))
    res["tracks_js_vs_python_m"] = stats(js)

    with open(os.path.join(root, "replay/verify_huygens.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
