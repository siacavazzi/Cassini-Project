#!/usr/bin/env python3
"""
Export the Huygens descent profile, DISR frame catalog and frame images for the replay.

  replay/huygens_descent.json      column arrays at 2 s from the DTWG V2.0 entry and descent tables
  replay/catalog/huygens.json      column arrays, one entry per DISR imager frame, sorted by time
  replay/images/huygens/<id>.png   8-bit frames, consistent stretch per camera and phase
  replay/images/huygens_enh/<id>.png  same frames stretched per frame (for legibility only)
  replay/images/huygens/stretch.json  the stretch limits used

Images come from Karkoschka's processed set E (DISRSOFT_E_IMAGES_13NOV2005), falling back to
set G and then to the raw EDR TIFF. E values are raw DN x 8 at the frame's auto exposure, so
they are divided by 8 and by the exposure time (DN/ms) before the shared stretch; that way a
brighter or darker frame is really brighter or darker.

Usage: python tools/export_huygens_catalog.py --root /Users/sam/Development/huygens-data
"""

import argparse
import csv
import glob
import json
import math
import os
import re
import sys

import numpy as np
import spiceypy as sp
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from pgm import read_pgm  # noqa: E402

DISR = "raw/psa/DISR/HP-SSA-DISR-2-3-EDR-RDR-V1.3"
DTWG = "raw/psa/DTWG/HP-SSA-DTWG-6-TRAJECTORY-V2.0/DATA"
LANDING_UTC = "2005-01-14T11:38:10.769"
LANDING = {"lat_deg": -10.5730225, "lon_w_deg": 192.3346498}
P_LO, P_HI = 0.5, 99.5     # pooled percentiles for the shared stretch


def num(s):
    return float(s.split()[0]) if s and s.split() else None


def descent_profile(root):
    d = os.path.join(root, DTWG)
    entry = np.loadtxt(f"{d}/HUY_DTWG_ENTRY.TAB", usecols=(0, 3, 4, 5))
    desc = np.loadtxt(f"{d}/HUY_DTWG_DESCENT_POS.TAB", usecols=(0, 3, 4, 5, 6))
    t_st = desc[0, 0]
    rows = [(r[0], None, r[1], r[2], r[3]) for r in entry if r[0] < t_st]
    rows += [(r[0], r[1], r[2], r[3], r[4]) for r in desc]
    out, last = [], -1e9
    for i, r in enumerate(rows):
        if r[0] - last >= 2.0 - 1e-6 or i == len(rows) - 1:
            out.append(r); last = r[0]
    cols = {"et": [round(r[0], 3) for r in out],
            "utc": [sp.et2utc(r[0], "ISOC", 3) for r in out],
            "alt_km": [round(r[2], 4) for r in out],
            "lat_deg": [round(r[4], 6) for r in out],
            "lon_w_deg": [round(r[3], 6) for r in out],
            "pressure_hpa": [None if r[1] is None else round(r[1], 4) for r in out]}
    meta = {"source": "ESA PSA HP-SSA-DTWG-6-TRAJECTORY-V2.0: HUY_DTWG_ENTRY before "
                      f"{sp.et2utc(t_st, 'ISOC', 3)} (no pressure), HUY_DTWG_DESCENT_POS after",
            "alt_ref": "altitude above a 2575 km sphere", "lat": "planetocentric", "lon": "west longitude",
            "time": "et is TDB seconds past J2000", "step_s": 2.0, "count": len(out),
            "landing_site": {**LANDING, "lon_e_deg": round(360 - LANDING["lon_w_deg"], 7),
                             "utc": LANDING_UTC, "et": round(sp.str2et(LANDING_UTC), 3)},
            "parachute_t0_utc": "2005-01-14T09:10:21"}
    return {**meta, **cols}, desc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    args = ap.parse_args()
    root = args.root
    sp.furnsh(os.path.join(root, "raw/spice/lsk/naif0012.tls"))
    out = os.path.join(root, "replay")
    os.makedirs(os.path.join(out, "catalog"), exist_ok=True)

    prof, desc = descent_profile(root)
    with open(os.path.join(out, "huygens_descent.json"), "w") as fh:
        json.dump(prof, fh, separators=(",", ":"))
    print(f"huygens_descent.json: {prof['count']} rows")

    labels = list(csv.DictReader(open(os.path.join(root, "derived/imager_index.csv"))))
    pdir = os.path.join(root, DISR, "EXTRAS/PROCESSED_IMAGES")
    sets = {}
    for key, d in (("E", "DISRSOFT_E_IMAGES_13NOV2005"), ("G", "DISRSOFT_G_IMAGES_13NOV2005")):
        sets[key] = {int(re.search(r"V_(\d{5})", f).group(1)): f for f in glob.glob(f"{pdir}/{d}/PGM/*.PGM")}
    t_land = sp.str2et(LANDING_UTC)

    frames = []
    for r in labels:
        seq = int(r["SEQUENCE_NUMBER"])
        t0, t1 = sp.str2et(r["START_TIME"]), sp.str2et(r["STOP_TIME"])
        et = 0.5 * (t0 + t1)
        exp = num(r["EXPOSURE_DURATION"]) or 0.0
        flags = []
        if r["START_TIME"].startswith("2005-01-14T19:10:21"):
            flags.append("bad_time")
        if exp == 0:
            flags.append("zero_exposure")
        if r["IMAGE_ID"] in ("UHH", "LHH"):
            flags.append("half_frame")
        if seq in sets["E"]:
            a, src = read_pgm(sets["E"][seq])[0] / 8.0, "E"
        elif seq in sets["G"]:
            a, src = read_pgm(sets["G"][seq])[0], "G"
            flags.append("g_fallback")
        else:
            tif = glob.glob(os.path.join(root, DISR, f"DATA/IMAGER/TIFF_FORMAT/*/TIFIMG_{seq:04d}_*.TIF"))[0]
            a, src = np.array(Image.open(tif)).astype(float), "EDR"
            flags.append("edr_fallback")
        surface = et > t_land      # the two bad_time frames (mission time 36000 s) are surface frames too
        if float((a >= a.max()).mean()) > 0.5:
            flags.append("saturated")
        frames.append({"seq": seq, "et": et, "cam": r["IMAGE_ID"], "phase": "surface" if surface else "descent",
                       "label": r, "exp": exp, "flags": flags, "src": src, "a": a})

    # shared stretch per camera and phase, on DN/ms; half-frames use the HRI limits (they are HRI halves)
    stretch = {}
    for cam in ("SLI", "MRI", "HRI"):
        for phase in ("descent", "surface"):
            vals = [f["a"].ravel() / f["exp"] for f in frames if f["cam"] == cam and f["phase"] == phase
                    and f["exp"] > 0 and f["src"] == "E" and "saturated" not in f["flags"]]
            v = np.concatenate(vals)
            v = v[v > 0]
            stretch[f"{cam}/{phase}"] = [float(np.percentile(v, P_LO)), float(np.percentile(v, P_HI))]

    img_dir = os.path.join(out, "images/huygens")
    enh_dir = os.path.join(out, "images/huygens_enh")
    os.makedirs(img_dir, exist_ok=True); os.makedirs(enh_dir, exist_ok=True)
    for f in frames:
        f["id"] = f"DISR_{f['seq']:04d}"
        a = f["a"]
        cam = "HRI" if f["cam"] in ("UHH", "LHH") else f["cam"]
        if f["exp"] > 0 and f["src"] == "E":
            lo, hi = stretch[f"{cam}/{f['phase']}"]
            v = a / f["exp"]
            f["stretch"] = "shared"
        else:   # dark frames and raw fallbacks: no exposure to normalise by, stretch the frame itself
            lo, hi = np.percentile(a, [P_LO, P_HI])
            v = a
            f["stretch"] = "per_frame"
            f["flags"].append("per_frame_stretch")
        img = (np.clip((v - lo) / max(hi - lo, 1e-9), 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(img).save(os.path.join(img_dir, f["id"] + ".png"), optimize=True)
        lo2, hi2 = np.percentile(a, [P_LO, P_HI])
        enh = (np.clip((a - lo2) / max(hi2 - lo2, 1e-9), 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(enh).save(os.path.join(enh_dir, f["id"] + ".png"), optimize=True)
        f["h"], f["w"] = a.shape

    frames.sort(key=lambda f: f["et"])
    # position along the DTWG profile (landed point after touchdown)
    lat = np.interp([f["et"] for f in frames], desc[:, 0], desc[:, 4])
    lon = np.interp([f["et"] for f in frames], desc[:, 0], desc[:, 3])
    alt_dtwg = np.interp([f["et"] for f in frames], desc[:, 0], desc[:, 2])
    keys = ("id", "et", "utc", "cam", "phase", "alt_km", "lat_deg", "lon_w_deg", "az_sun_deg", "az_north_deg",
            "tilt_deg", "exposure_ms", "mean_dn_ms", "w", "h", "file", "file_enh", "src", "flags")
    cols = {k: [] for k in keys}
    alt_diff = []
    for f, la, lo, ad in zip(frames, lat, lon, alt_dtwg):
        r = f["label"]
        alt = num(r["SPACECRAFT_ALTITUDE_START"])
        if f["phase"] == "descent":
            alt_diff.append(abs(alt - ad))
        bad = "bad_time" in f["flags"]
        row = {"id": f["id"], "et": None if bad else round(f["et"], 3),
               "utc": None if bad else sp.et2utc(f["et"], "ISOC", 3), "cam": f["cam"], "phase": f["phase"],
               "alt_km": alt, "lat_deg": round(float(la), 6), "lon_w_deg": round(float(lo), 6),
               "az_sun_deg": num(r["AZIMUTH_START"]), "az_north_deg": num(r["AZIMUTH_NORTH_START"]),
               "tilt_deg": num(r["EW_TILT_ANGLE_START"]), "exposure_ms": f["exp"], "w": int(f["w"]), "h": int(f["h"]),
               "mean_dn_ms": round(float(f["a"].mean() / f["exp"]), 3) if f["exp"] > 0 and f["src"] == "E" else None,
               "file": f"images/huygens/{f['id']}.png", "file_enh": f"images/huygens_enh/{f['id']}.png",
               "src": f["src"], "flags": f["flags"]}
        for k in keys:
            cols[k].append(row[k])
    cols = {k: [None if isinstance(v, float) and not math.isfinite(v) else v for v in vals] for k, vals in cols.items()}
    meta = {"count": len(frames), "time": "et is TDB seconds past J2000 at mid-exposure; null for bad_time frames",
            "alt_km": "label SPACECRAFT_ALTITUDE_START (DTWG June 2011 reconstruction)",
            "lat_lon": "DTWG V2.0 descent table interpolated at et (planetocentric, west longitude); landing site on the surface",
            "az_sun_deg": "CCW from the Sun, seen from nadir", "az_north_deg": "CW from North, seen from nadir",
            "tilt_deg": "east-west tilt, positive = parachute east of probe",
            "mean_dn_ms": "mean of set E DN/8 divided by exposure ms (relative scene brightness, same camera)",
            "file": "shared stretch per camera and phase (brightness comparable between frames)",
            "file_enh": "stretched per frame (0.5-99.5 percentile) for legibility",
            "cams": {"SLI": "side-looking 45-96 deg from nadir", "MRI": "medium res 16-45 deg",
                     "HRI": "high res 6-21 deg", "UHH/LHH": "upper/lower half HRI frames"},
            "flags": {"bad_time": "label time is a placeholder (19:10:21); et/utc null",
                      "zero_exposure": "manual zero-exposure (dark) frame",
                      "half_frame": "UHH/LHH half frame",
                      "saturated": "more than half the pixels at the frame's maximum (mostly HRI on the surface, lamp glare)", "per_frame_stretch": "image stretched on its own",
                      "g_fallback": "processed set G used", "edr_fallback": "raw EDR TIFF used (no processed version)"}}
    with open(os.path.join(out, "catalog/huygens.json"), "w") as fh:
        json.dump({**meta, **cols}, fh, separators=(",", ":"), allow_nan=False)
    with open(os.path.join(img_dir, "stretch.json"), "w") as fh:
        json.dump({"units": "DN/ms (set E DN / 8 / exposure ms)", "percentiles": [P_LO, P_HI],
                   "limits": stretch}, fh, indent=1)
    print(f"catalog: {len(frames)} frames; srcs", {s: sum(f['src'] == s for f in frames) for s in ('E', 'G', 'EDR')})
    print("flags", {k: sum(k in f['flags'] for f in frames) for k in meta['flags']})
    print("label alt vs DTWG interp (descent) km: max %.4f median %.4f" % (max(alt_diff), float(np.median(alt_diff))))
    print("stretch", json.dumps(stretch))


if __name__ == "__main__":
    main()
