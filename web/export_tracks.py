#!/usr/bin/env python3
"""
Precompute the Cassini mission geometry for the browser replay.

Reads the per-year meta-kernels (cosp_1000/index/cas_YYYY*.tm) and writes:

  tracks/<body>/<year>.bin   position/velocity samples for cubic Hermite interpolation
  catalog/<year>.json        per-image geometry (time, target, range, phase, km/pixel)
  encounters.json            closest approaches to every body plus mission milestones
  manifest.json              bodies, radii, IAU rotation constants, chunk list, format notes

Only SPK, LSK and PCK kernels are needed (no CK), so the kernel set is about 1 GB.

Usage:
  python web/export_tracks.py --kernels <dir with mk/ spk/ lsk/ pck/> --out <output dir>

Track file layout (little endian, struct of arrays so every array is aligned):
  16-byte header: b"CTRK", uint16 version (1), uint16 flags (0), uint32 count, uint32 reserved
  float64 t[count]          ephemeris time, TDB seconds past J2000
  float64 pos[count*3]      km, J2000 frame, solar system barycentre origin
  float32 vel[count*3]      km/s, same frame
"""

import argparse
import glob
import json
import math
import os
import re
import struct

import numpy as np
import pandas as pd
import spiceypy as sp

CASSINI = -82
LAUNCH_UTC = "1997-10-15T09:26:08"  # approximate; tracks start where the SPK coverage starts

# name, NAIF id, smallest Hermite tolerance in km (used when Cassini is close)
BODIES = [
    ("SUN", 10, 50.0), ("MERCURY BARYCENTER", 1, 50.0), ("VENUS", 299, 5.0),
    ("VENUS BARYCENTER", 2, 5.0), ("EARTH", 399, 1.0), ("MOON", 301, 1.0),
    ("MARS BARYCENTER", 4, 20.0), ("JUPITER BARYCENTER", 5, 20.0), ("JUPITER", 599, 2.0),
    ("IO", 501, 1.0), ("EUROPA", 502, 1.0), ("GANYMEDE", 503, 1.0), ("CALLISTO", 504, 1.0),
    ("SATURN BARYCENTER", 6, 5.0), ("SATURN", 699, 0.1),
    ("MIMAS", 601, 0.05), ("ENCELADUS", 602, 0.05), ("TETHYS", 603, 0.05), ("DIONE", 604, 0.05),
    ("RHEA", 605, 0.05), ("TITAN", 606, 0.05), ("HYPERION", 607, 0.1), ("IAPETUS", 608, 0.1),
    ("PHOEBE", 609, 0.1), ("JANUS", 610, 0.05), ("EPIMETHEUS", 611, 0.05), ("HELENE", 612, 0.05),
    ("TELESTO", 613, 0.05), ("CALYPSO", 614, 0.05), ("ATLAS", 615, 0.05), ("PROMETHEUS", 616, 0.05),
    ("PANDORA", 617, 0.05), ("PAN", 618, 0.05), ("METHONE", 632, 0.05), ("PALLENE", 633, 0.05),
    ("POLYDEUCES", 634, 0.05), ("DAPHNIS", 635, 0.05), ("URANUS BARYCENTER", 7, 50.0),
    ("NEPTUNE BARYCENTER", 8, 50.0),
]

# bodies Cassini can fly close to; used for the adaptive step and the encounter search
NEAR_BODIES = [299, 399, 301, 599, 501, 502, 503, 504, 699, 601, 602, 603, 604, 605, 606, 607,
               608, 609, 610, 611, 612, 613, 614, 615, 616, 617, 618, 632, 633, 634, 635]

MILESTONES = [
    ("1997-10-15T09:26:08", "Launch from Cape Canaveral"),
    ("1998-04-26T13:44:00", "First Venus flyby"),
    ("1999-06-24T20:30:00", "Second Venus flyby"),
    ("1999-08-18T03:28:00", "Earth flyby"),
    ("2000-12-30T10:05:00", "Jupiter closest approach"),
    ("2004-06-11T19:33:00", "Phoebe flyby"),
    ("2004-07-01T02:48:00", "Saturn orbit insertion"),
    ("2004-12-25T02:00:00", "Huygens probe released"),
    ("2005-01-14T09:05:53", "Huygens enters Titan's atmosphere"),
    ("2005-01-14T11:38:11", "Huygens lands on Titan"),  # touchdown, ESA DTWG descent reconstruction
    ("2009-08-11T00:00:00", "Saturn equinox"),
    ("2017-04-26T09:00:00", "First Grand Finale dive between Saturn and its rings"),
    ("2017-09-15T10:31:00", "Final plunge into Saturn"),
]


def furnish_year(kdir, mk_path):
    sp.kclear()
    text = open(mk_path).read()
    for k in re.findall(r"\$KERNELS/(\S+?)'", text):
        if k.split("/")[0] in ("spk", "lsk", "pck"):
            sp.furnsh(os.path.join(kdir, k))


def state(body, et):
    s, _ = sp.spkezr(str(body), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")
    return np.array(s)


def hermite(t0, s0, t1, s1, t):
    h = t1 - t0
    u = (t - t0) / h
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    return h00 * s0[:3] + h10 * h * s0[3:] + h01 * s1[:3] + h11 * h * s1[3:]


# Error budget as an angle seen from Cassini: 5 microradians is about one narrow-angle camera pixel
ANGULAR_TOL = 5e-6


def body_tol(pos, et, floor):
    """Tolerance for a body: tight when Cassini is close, loose when it is far away."""
    try:
        c, _ = sp.spkpos(str(CASSINI), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")
        return min(200.0, max(floor, ANGULAR_TOL * float(np.linalg.norm(pos - np.array(c)))))
    except Exception:
        return floor


def nearest_distance(pos, et, near_ids):
    best = math.inf
    for b in near_ids:
        try:
            p, _ = sp.spkpos(str(b), et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")
        except Exception:
            continue
        best = min(best, float(np.linalg.norm(pos - np.array(p))))
    return best


def sample_adaptive(body, a, b, tol_fn, step0, min_step):
    """Bisect from a coarse grid until the Hermite midpoint error is under tolerance."""
    grid = list(np.arange(a, b, step0)) + [b]
    out = [(grid[0], state(body, grid[0]))]
    for t1 in grid[1:]:
        stack = [(out[-1][0], out[-1][1], t1, state(body, t1))]
        while stack:
            ta, sa, tb, sb = stack.pop()
            tm = 0.5 * (ta + tb)
            sm = state(body, tm)
            err = np.linalg.norm(hermite(ta, sa, tb, sb, tm) - sm[:3])
            if err > tol_fn(sm[:3], tm) and tb - ta > 2 * min_step:
                stack.append((tm, sm, tb, sb))
                stack.append((ta, sa, tm, sm))
            else:
                out.append((tb, sb))
    return out


def coverage(body, files):
    win = sp.cell_double(200000)
    for f in files:
        try:
            sp.spkcov(f, body, win)
        except Exception:
            pass
    return [sp.wnfetd(win, i) for i in range(sp.wncard(win))]


def write_track(path, samples):
    t = np.array([s[0] for s in samples], dtype="<f8")
    st = np.array([s[1] for s in samples])
    pos = st[:, :3].astype("<f8")
    vel = st[:, 3:].astype("<f4")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"CTRK" + struct.pack("<HHII", 1, 0, len(t), 0))
        fh.write(t.tobytes())
        fh.write(pos.tobytes())
        fh.write(vel.tobytes())
    return len(t), os.path.getsize(path)


def slug(name):
    return name.lower().replace(" ", "_")


def rotation_constants(body):
    out = {}
    for key in ("POLE_RA", "POLE_DEC", "PM", "NUT_PREC_RA", "NUT_PREC_DEC", "NUT_PREC_PM", "RADII"):
        try:
            n = sp.bodvcd(body, key, 100)[0]
            out[key] = list(sp.bodvcd(body, key, n)[1])
        except Exception:
            pass
    bary = body // 100 if body > 10 else None
    if bary and "NUT_PREC_RA" in out:
        try:
            n = sp.bodvcd(bary, "NUT_PREC_ANGLES", 100)[0]
            out["NUT_PREC_ANGLES"] = list(sp.bodvcd(bary, "NUT_PREC_ANGLES", n)[1])
        except Exception:
            pass
    return out


def export_tracks(kdir, out, years):
    manifest_bodies = {}
    mks = {int(re.search(r"cas_(\d{4})", m).group(1)): m for m in glob.glob(f"{kdir}/mk/*.tm")}
    for year in years:
        if year not in mks:
            continue
        furnish_year(kdir, mks[year])
        files = [sp.kdata(i, "SPK")[0] for i in range(sp.ktotal("SPK"))]
        y0 = sp.str2et(f"{year}-01-01T00:00:00")
        y1 = sp.str2et(f"{year + 1}-01-01T00:00:00")

        # Cassini: tighter tolerance near bodies, measured as distance to the nearest one
        near = [b for b in NEAR_BODIES if (b >= 600) == (year >= 2004)]
        cas_tol = lambda p, et: min(50.0, max(0.01, ANGULAR_TOL * nearest_distance(p, et, near)))
        jobs = [("CASSINI", CASSINI, cas_tol, 3600.0 if year >= 2004 else 6 * 3600.0, 5.0)]
        for name, nid, tol in BODIES:
            jobs.append((name, nid, (lambda p, et, tol=tol: body_tol(p, et, tol)), 6 * 3600.0, 60.0))

        for name, nid, tol_fn, step0, min_step in jobs:
            samples = []
            intervals = []
            for a, b in coverage(nid, files):
                a, b = max(a, y0), min(b, y1)
                if b - a < 2 * min_step:
                    continue
                try:
                    samples += sample_adaptive(nid, a, b, tol_fn, step0, min_step)
                    intervals.append([a, b])
                except Exception as exc:
                    print(f"  skip {name} {year}: {str(exc).splitlines()[0][:80]}")
            if not samples:
                continue
            rel = f"tracks/{slug(name)}/{year}.bin"
            count, size = write_track(os.path.join(out, rel), samples)
            entry = manifest_bodies.setdefault(name, {"naif_id": nid, "chunks": []})
            entry["chunks"].append({"year": year, "file": rel, "count": count, "bytes": size,
                                    "coverage_et": intervals})
            print(f"{year} {name:20s} {count:7d} samples {size / 1024:8.1f} KB", flush=True)

        if year == 2005:  # constants are the same every year; take them from one PCK load
            for name, nid, _ in BODIES:
                if name in manifest_bodies:
                    manifest_bodies[name]["iau_rotation"] = rotation_constants(nid)
    return manifest_bodies


def export_catalog(kdir, out, index_csv, years):
    df = pd.read_csv(index_csv, low_memory=False)
    df = df[df.year.notna()]
    mks = {int(re.search(r"cas_(\d{4})", m).group(1)): m for m in glob.glob(f"{kdir}/mk/*.tm")}
    ifov = {"ISSNA": 5.9907e-6, "ISSWA": 5.9907e-5}
    summary = {}
    for year in years:
        # stable, with the path as tie-break, so frames taken at the same instant keep one order on every machine
        sub = df[df.year == year].sort_values(["seconds_1970", "path"], kind="mergesort")
        if not len(sub) or year not in mks:
            continue
        furnish_year(kdir, mks[year])
        cols = {k: [] for k in ("id", "et", "cam", "f1", "f2", "target", "obs", "range_km",
                                "phase_deg", "km_per_px", "missing_lines")}
        for r in sub.itertuples():
            et = sp.str2et(r.IMAGE_MID_TIME)
            rng = ph = res = None
            try:
                p, _ = sp.spkpos(r.TARGET_NAME, et, "J2000", "LT+S", "CASSINI")
                s, _ = sp.spkpos("SUN", et, "J2000", "LT+S", r.TARGET_NAME)
                rng = float(np.linalg.norm(p))
                ph = math.degrees(sp.vsep(-np.array(p), s))
                res = rng * ifov.get(r.INSTRUMENT_ID, np.nan)
            except Exception:
                pass
            cols["id"].append(os.path.splitext(os.path.basename(r.path))[0])
            cols["et"].append(round(et, 3))
            cols["cam"].append("N" if r.INSTRUMENT_ID == "ISSNA" else "W")
            cols["f1"].append(r.filter1)
            cols["f2"].append(r.filter2)
            cols["target"].append(r.TARGET_NAME)
            cols["obs"].append(r.OBSERVATION_ID)
            cols["range_km"].append(None if rng is None else round(rng, 1))
            cols["phase_deg"].append(None if ph is None else round(ph, 2))
            cols["km_per_px"].append(None if res is None else round(res, 4))
            ml = pd.to_numeric(r.MISSING_LINES, errors="coerce")
            cols["missing_lines"].append(0 if pd.isna(ml) else int(ml))
        rel = f"catalog/{year}.json"
        os.makedirs(os.path.join(out, "catalog"), exist_ok=True)
        with open(os.path.join(out, rel), "w") as fh:
            # NaN is not valid JSON (browsers reject it); write null instead
            clean = {k: [None if isinstance(v, float) and not math.isfinite(v) else v for v in vals] for k, vals in cols.items()}
            json.dump(clean, fh, separators=(",", ":"), allow_nan=False)
        summary[year] = {"file": rel, "images": len(sub)}
        print(f"catalog {year}: {len(sub)} images", flush=True)
    return summary


def export_encounters(kdir, out, years, highlights_csv=None):
    mks = {int(re.search(r"cas_(\d{4})", m).group(1)): m for m in glob.glob(f"{kdir}/mk/*.tm")}
    found = []
    for year in years:
        if year not in mks:
            continue
        furnish_year(kdir, mks[year])
        files = [sp.kdata(i, "SPK")[0] for i in range(sp.ktotal("SPK"))]
        y0 = sp.str2et(f"{year}-01-01T00:00:00")
        y1 = sp.str2et(f"{year + 1}-01-01T00:00:00")
        cas = [(max(a, y0), min(b, y1)) for a, b in coverage(CASSINI, files)]
        for nid in NEAR_BODIES:
            name = sp.bodc2n(nid)
            radius = float(np.mean(sp.bodvcd(nid, "RADII", 3)[1]))
            limit = 300 * radius if nid % 100 == 99 else max(50000.0, 300 * radius)
            for a, b in cas:
                if b <= a:
                    continue
                ts = np.arange(a, b, 600.0)
                try:
                    d = np.array([np.linalg.norm(sp.spkpos(str(nid), t, "J2000", "NONE", "CASSINI")[0])
                                  for t in ts])
                except Exception:
                    continue
                for i in range(1, len(d) - 1):
                    if d[i] <= d[i - 1] and d[i] < d[i + 1] and d[i] < limit:
                        lo, hi = ts[i - 1], ts[i + 1]
                        f = lambda t: np.linalg.norm(sp.spkpos(str(nid), t, "J2000", "NONE", "CASSINI")[0])
                        for _ in range(60):  # golden section to sub-second
                            m1 = hi - 0.618 * (hi - lo)
                            m2 = lo + 0.618 * (hi - lo)
                            if f(m1) < f(m2):
                                hi = m2
                            else:
                                lo = m1
                        t = 0.5 * (lo + hi)
                        st, _ = sp.spkezr(str(nid), t, "J2000", "NONE", "CASSINI")
                        found.append({"kind": "flyby", "body": name, "et": round(t, 2),
                                      "utc": sp.et2utc(t, "ISOC", 0),
                                      "distance_km": round(f(t), 1),
                                      "altitude_km": round(f(t) - radius, 1),
                                      "speed_km_s": round(float(np.linalg.norm(st[3:])), 3)})
        print(f"encounters {year}: {len(found)} so far", flush=True)

    # Saturn periapses are flybys too: keep them, the browser can filter by body
    sp.kclear()
    sp.furnsh(f"{kdir}/lsk/naif0012.tls")
    for utc, label in MILESTONES:
        found.append({"kind": "milestone", "label": label, "et": round(sp.str2et(utc), 2), "utc": utc})

    if highlights_csv and os.path.exists(highlights_csv):
        h = pd.read_csv(highlights_csv, parse_dates=["start", "end"])
        for f in found:
            if f["kind"] != "flyby":
                continue
            t = pd.Timestamp(f["utc"])
            m = h[(h.target == f["body"]) & (h.start <= t + pd.Timedelta("1D")) & (h.end >= t - pd.Timedelta("1D"))]
            if len(m):
                best = m.sort_values("score", ascending=False).iloc[0]
                f["photo_score"] = round(float(best.score), 1)
                f["frames"] = int(best.frames)
                f["rgb_sets"] = int(best.rgb_sets)
    found.sort(key=lambda f: f["et"])
    with open(os.path.join(out, "encounters.json"), "w") as fh:
        json.dump(found, fh, indent=0)
    return len(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", default=os.path.join(os.path.dirname(__file__), "..", "Image_index.csv"))
    ap.add_argument("--highlights", default=None, help="encounters_ranked.csv from the highlight scoring")
    ap.add_argument("--years", default="1997-2017")
    ap.add_argument("--skip", default="", help="comma list of steps to skip: tracks,catalog,encounters")
    args = ap.parse_args()
    y0, y1 = (int(x) for x in args.years.split("-"))
    years = list(range(y0, y1 + 1))
    skip = set(filter(None, args.skip.split(",")))
    os.makedirs(args.out, exist_ok=True)

    manifest = {"format_version": 1,
                "frame": "J2000", "origin": "SOLAR SYSTEM BARYCENTER", "time": "TDB seconds past J2000",
                "track_layout": "16-byte header (CTRK, u16 version, u16 flags, u32 count, u32 reserved), "
                                "f64 t[count], f64 pos[3*count] km, f32 vel[3*count] km/s; "
                                "interpolate with cubic Hermite between neighbouring samples",
                "notes": "Positions are geometric (no light time). Bodies are absent from years their SPK does not cover."}
    path = os.path.join(args.out, "manifest.json")

    def save():  # after every step, merged with an earlier run, so a crash keeps finished work
        merged = json.load(open(path)) if os.path.exists(path) else {}
        merged.update(manifest)
        with open(path, "w") as fh:
            json.dump(merged, fh, indent=1)

    if "tracks" not in skip:
        manifest["bodies"] = export_tracks(args.kernels, args.out, years)
        save()
    if "catalog" not in skip:
        manifest["catalog"] = export_catalog(args.kernels, args.out, args.index, years)
        save()
    if "encounters" not in skip:
        manifest["encounters"] = {"file": "encounters.json",
                                  "count": export_encounters(args.kernels, args.out, years, args.highlights)}
        save()


if __name__ == "__main__":
    main()
