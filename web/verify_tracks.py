#!/usr/bin/env python3
"""
Check exported tracks against SPICE and draw overview plots.

  python web/verify_tracks.py --kernels <kernel dir> --data <export dir> --plots <dir>

For random times in every chunk it interpolates the track exactly as tracks.js does and
compares with spkezr. Errors are reported in km and as the angle seen from Cassini.
"""

import argparse
import glob
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import spiceypy as sp

from export_tracks import CASSINI, furnish_year, hermite


def read_track(path):
    raw = open(path, "rb").read()
    n = int.from_bytes(raw[8:12], "little")
    t = np.frombuffer(raw, "<f8", n, 16)
    pos = np.frombuffer(raw, "<f8", 3 * n, 16 + 8 * n).reshape(n, 3)
    vel = np.frombuffer(raw, "<f4", 3 * n, 16 + 32 * n).reshape(n, 3).astype(float)
    return t, pos, vel


def interp(track, et):
    t, pos, vel = track
    i = max(0, min(np.searchsorted(t, et, "right") - 1, len(t) - 2))
    s0 = np.concatenate([pos[i], vel[i]])
    s1 = np.concatenate([pos[i + 1], vel[i + 1]])
    return hermite(t[i], s0, t[i + 1], s1, et)


def ssb(body, et):
    return np.array(sp.spkpos(str(body), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")[0])


def saturn_equator_frame():
    ra, dec = np.radians(40.589), np.radians(83.537)  # Saturn pole, pck00010
    z = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    x = np.cross([0, 0, 1], z); x /= np.linalg.norm(x)
    return np.array([x, np.cross(z, x), z])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernels", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--plots", required=True)
    ap.add_argument("--samples", type=int, default=300)
    args = ap.parse_args()
    os.makedirs(args.plots, exist_ok=True)
    man = json.load(open(os.path.join(args.data, "manifest.json")))
    mks = {int(re.search(r"cas_(\d{4})", m).group(1)): m for m in glob.glob(f"{args.kernels}/mk/*.tm")}
    rng = np.random.default_rng(1)

    rows = []
    years = sorted({c["year"] for b in man["bodies"].values() for c in b["chunks"]})
    for year in years:
        furnish_year(args.kernels, mks[year])
        for name, body in man["bodies"].items():
            chunk = next((c for c in body["chunks"] if c["year"] == year), None)
            if not chunk:
                continue
            track = read_track(os.path.join(args.data, chunk["file"]))
            for a, b in chunk["coverage_et"]:
                for et in rng.uniform(a, b, args.samples // len(chunk["coverage_et"])):
                    try:
                        truth = ssb(body["naif_id"], et)
                        cas = ssb(CASSINI, et)
                    except Exception:
                        continue
                    err = np.linalg.norm(interp(track, et) - truth)
                    dist = max(np.linalg.norm(truth - cas), 1.0)
                    rows.append((year, name, err, err / dist if name != "CASSINI" else np.nan))
        print(f"checked {year}", flush=True)

    errs = np.array([r[2] for r in rows])
    ang = np.array([r[3] for r in rows if not np.isnan(r[3])])
    report = {"checks": len(rows), "median_err_km": float(np.median(errs)),
              "p99_err_km": float(np.percentile(errs, 99)), "max_err_km": float(errs.max()),
              "median_angle_urad": float(np.median(ang) * 1e6), "p99_angle_urad": float(np.percentile(ang, 99) * 1e6),
              "max_angle_urad": float(ang.max() * 1e6)}
    per_body = {}
    for _, name, e, a in rows:
        per_body.setdefault(name, []).append(e)
    report["max_err_km_by_body"] = {k: round(float(max(v)), 3) for k, v in per_body.items()}
    json.dump(report, open(os.path.join(args.plots, "verification.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))

    # 1. error histogram
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    ax[0].hist(np.log10(errs + 1e-6), bins=80, color="#4a7bd0")
    ax[0].set_xlabel("log10 position error (km)"); ax[0].set_ylabel("random checks")
    ax[0].set_title(f"Interpolated track vs SPICE: median {report['median_err_km']*1000:.1f} m, max {report['max_err_km']:.2f} km")
    ax[1].hist(np.log10(ang * 1e6 + 1e-6), bins=80, color="#d07a4a")
    ax[1].axvline(np.log10(6.0), color="k", ls="--"); ax[1].text(np.log10(6.0), ax[1].get_ylim()[1] * 0.9, " 1 NAC pixel")
    ax[1].set_xlabel("log10 angular error seen from Cassini (microradians)")
    ax[1].set_title("Body position error as Cassini would see it")
    fig.tight_layout(); fig.savefig(os.path.join(args.plots, "track_error.png"), dpi=120)

    def full(name):
        ts, ps = [], []
        for c in sorted(man["bodies"][name]["chunks"], key=lambda c: c["year"]):
            t, p, _ = read_track(os.path.join(args.data, c["file"]))
            ts.append(t); ps.append(p)
        return np.concatenate(ts), np.concatenate(ps)

    # 2. cruise, heliocentric
    tc, pc = full("CASSINI"); ts_, psun = full("SUN")
    sun_at = lambda t: np.array([np.interp(t, ts_, psun[:, k]) for k in range(3)]).T
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="black"); ax.set_facecolor("black")
    soi = sp.str2et("2004-07-01T02:48")
    m = tc < soi
    rel = (pc[m] - sun_at(tc[m])) / 1.496e8
    for nm, col in [("VENUS BARYCENTER", "#ff6fae"), ("EARTH", "#5aa0ff"), ("JUPITER BARYCENTER", "#ff9a3c"), ("SATURN BARYCENTER", "#e6d8a8")]:
        tb, pb = full(nm); mb = tb < soi
        r = (pb[mb] - sun_at(tb[mb])) / 1.496e8
        ax.plot(r[:, 0], r[:, 1], color=col, lw=0.6, alpha=0.6, label=nm.replace(" BARYCENTER", "").title())
    ax.plot(rel[:, 0], rel[:, 1], color="white", lw=1.2, label="Cassini")
    ax.plot(0, 0, "o", color="yellow")
    ax.set_aspect("equal"); ax.legend(facecolor="black", labelcolor="white", loc="lower left")
    ax.set_title("Cruise 1997 to 2004 from the exported tracks (AU, J2000)", color="white")
    ax.tick_params(colors="gray")
    fig.savefig(os.path.join(args.plots, "cruise.png"), dpi=120, facecolor="black")

    # 3. Saturn tour in Saturn's equatorial frame
    tsat, psat = full("SATURN")
    R = saturn_equator_frame()
    m = tc > soi
    sat_at = np.array([np.interp(tc[m], tsat, psat[:, k]) for k in range(3)]).T
    rel = (pc[m] - sat_at) @ R.T / 60268.0
    fig, ax = plt.subplots(1, 2, figsize=(16, 8), facecolor="black")
    years = (tc[m] - soi) / (365.25 * 86400)
    for a, (i, j, ttl) in zip(ax, [(0, 1, "Looking down on Saturn's equator"), (0, 2, "Side view (ring plane horizontal)")]):
        a.set_facecolor("black")
        a.scatter(rel[:, i], rel[:, j], c=years, cmap="plasma", s=0.15, lw=0)
        a.add_patch(plt.Circle((0, 0), 1, color="#e6d8a8"))
        a.set_aspect("equal"); a.set_xlim(-60, 60); a.set_ylim(-60, 60)
        a.set_title(ttl, color="white"); a.tick_params(colors="gray")
        a.set_xlabel("Saturn radii", color="gray")
    fig.suptitle("Every Saturn orbit, 2004 to 2017, coloured by year (yellow is the Grand Finale). Flat lines in the side view are equatorial orbits seen edge-on", color="white")
    fig.savefig(os.path.join(args.plots, "saturn_tour.png"), dpi=120, facecolor="black")

    # 4. Huygens week: Cassini and Titan around Saturn
    a, b = sp.str2et("2005-01-10"), sp.str2et("2005-01-18")
    tt, pt = full("TITAN")
    sel = (tc > a) & (tc < b); selt = (tt > a) & (tt < b)
    sat_c = np.array([np.interp(tc[sel], tsat, psat[:, k]) for k in range(3)]).T
    sat_t = np.array([np.interp(tt[selt], tsat, psat[:, k]) for k in range(3)]).T
    rc = (pc[sel] - sat_c) @ R.T / 60268.0
    rt = (pt[selt] - sat_t) @ R.T / 60268.0
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="black"); ax.set_facecolor("black")
    ax.plot(rc[:, 0], rc[:, 1], ".", ms=2, color="white", label=f"Cassini ({sel.sum()} samples)")
    ax.plot(rt[:, 0], rt[:, 1], ".", ms=2, color="#e0a040", label=f"Titan ({selt.sum()} samples)")
    ax.add_patch(plt.Circle((0, 0), 1, color="#e6d8a8"))
    ax.set_aspect("equal"); ax.legend(facecolor="black", labelcolor="white")
    ax.set_title("Huygens landing week, Jan 10 to 18 2005: raw samples (denser near flybys)", color="white")
    ax.tick_params(colors="gray")
    fig.savefig(os.path.join(args.plots, "huygens_week.png"), dpi=120, facecolor="black")


if __name__ == "__main__":
    main()
