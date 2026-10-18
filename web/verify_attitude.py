#!/usr/bin/env python3
"""
Check the exported attitude, interpolated by tracks.js exactly as the browser does, against SPICE.

  python web/verify_attitude.py --zip /Volumes/LaCie/cassiniprojectJAN05.zip \
      --data <replay_data> --catalog <replay_data>/catalog --tmp /Volumes/LaCie/verify_tmp

For each finished year it picks a few random weeks, extracts only the CKs covering them, and
compares attitudeAt() (run through node web/test_attitude.mjs) with pxform J2000 -> CASSINI_SC_COORD
at random times and at image times. Errors are the rotation angle between the two attitudes.
Also checks the fixed camera -> body rotations hard-coded in tracks.js against the frames kernel.
"""

import argparse
import datetime
import gzip
import json
import os
import re
import shutil
import subprocess
import zipfile

import numpy as np
import spiceypy as sp

from export_attitude import FRAMES, PREFIX, kernels_for_year

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400.0


def angle_deg(q1, q2):
    d = abs(float(np.dot(q1, q2))) / (np.linalg.norm(q1) * np.linalg.norm(q2))
    return np.degrees(2 * np.arccos(min(1.0, d)))


def kernel_span(name):
    """ET span from a CK name like 05022_05058py_as_flown.bc, or None if it has no date range."""
    m = re.search(r"(?<!\d)(\d{2})(\d{3})_(\d{2})(\d{3})(?!\d)", os.path.basename(name))
    if not m:
        return None
    def et(yy, ddd):
        y = int(yy) + (1900 if int(yy) >= 90 else 2000)
        d = datetime.date(y, 1, 1) + datetime.timedelta(int(ddd) - 1)
        return sp.str2et(d.isoformat())
    return et(m[1], m[2]) - DAY, et(m[3], m[4]) + 2 * DAY


def load_catalog(path):
    if os.path.exists(path):
        return json.load(open(path))
    return json.load(gzip.open(path + ".gz"))


def js_quats(bin_path, cat_path, ets):
    if not os.path.exists(cat_path):
        cat_path += ".gz"
    out = subprocess.run(["node", os.path.join(HERE, "test_attitude.mjs"), bin_path, cat_path],
                         input=json.dumps([float(e) for e in ets]), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check_year(z, members, year, args, rng):
    bin_path = os.path.join(args.data, "attitude", f"{year}.bin")
    raw = open(bin_path, "rb").read()
    n_img, n_bg = np.frombuffer(raw, "<u4", 2, 8)
    bg_t = np.frombuffer(raw, "<f8", n_bg, 16 + 16 * n_img)
    cat = load_catalog(os.path.join(args.catalog, f"{year}.json"))
    img_et = np.array(cat["et"], dtype=float)

    centres = rng.choice(bg_t, size=min(args.weeks, len(bg_t)), replace=False)
    windows = [(c - 3.5 * DAY, c + 3.5 * DAY) for c in centres]

    tmp = os.path.join(args.tmp, str(year))
    os.makedirs(tmp, exist_ok=True)
    sp.kclear()
    kernels = kernels_for_year(z, year)
    for k in [k for k in kernels if k.startswith("lsk/")]:
        sp.furnsh(extract(z, members, k, tmp))
    loaded = 0
    for k in kernels:
        if k.startswith("lsk/"):
            continue
        if k.split("/")[0] in ("ck", "iss_ck"):
            span = kernel_span(k)
            if span is None:
                if z.getinfo(PREFIX + "data/" + k).file_size > 20e6:
                    continue  # big instrument-articulation CKs; they do not move the spacecraft body
            elif not any(span[0] < b and a < span[1] for a, b in windows):
                continue
        path = extract(z, members, k, tmp)
        if path:
            sp.furnsh(path)
            loaded += 1

    # random times inside the chosen weeks, and image times inside them
    rand = np.sort(np.concatenate([rng.uniform(a, b, args.samples // len(windows)) for a, b in windows]))
    in_win = np.zeros(len(img_et), bool)
    for a, b in windows:
        in_win |= (img_et > a) & (img_et < b)
    imgs = img_et[in_win]
    imgs = np.sort(rng.choice(imgs, size=min(args.samples, len(imgs)), replace=False)) if len(imgs) else imgs

    result = {}
    for label, ets in (("random", rand), ("image", imgs)):
        js = js_quats(bin_path, os.path.join(args.catalog, f"{year}.json"), ets)
        errs, no_js, no_spice = [], 0, 0
        for et, q in zip(ets, js):
            try:
                truth = sp.m2q(sp.pxform("J2000", "CASSINI_SC_COORD", et))
            except Exception:
                no_spice += 1
                continue
            if q is None:
                no_js += 1
                continue
            errs.append(angle_deg(np.array(q), truth))
        result[label] = (np.array(errs), no_js, no_spice)
    sp.kclear()
    shutil.rmtree(tmp, ignore_errors=True)
    return loaded, result


def extract(z, members, k, tmp):
    src = PREFIX + "data/" + k
    if src not in members:
        return None
    dst = os.path.join(tmp, os.path.basename(k))
    if not os.path.exists(dst):
        with z.open(src) as fin, open(dst, "wb") as fout:
            shutil.copyfileobj(fin, fout, 1 << 24)
    return dst


def check_frames(z, members, year, tmp):
    """Compare tracks.js CAM_TO_BODY with the frames kernel of that year."""
    text = open(os.path.join(HERE, "tracks.js")).read()
    sp.kclear()
    os.makedirs(tmp, exist_ok=True)
    for k in kernels_for_year(z, year):
        if k.split("/")[0] in ("fk", "lsk"):
            sp.furnsh(extract(z, members, k, tmp))
    for cam, frame in FRAMES.items():
        js = np.array([float(v) for v in re.search(rf"{cam}: \[([^\]]+)\]", text)[1].split(",")])
        fk = sp.m2q(sp.pxform(frame, "CASSINI_SC_COORD", 0.0))
        print(f"  {frame} -> CASSINI_SC_COORD: tracks.js vs FK differ by {angle_deg(js, fk) * 3600:.2f} arcsec")
    sp.kclear()


def stats(errs):
    if not len(errs):
        return "no samples"
    p = np.percentile(errs, [50, 90, 99])
    return (f"n={len(errs)}  median {p[0]:.4f}°  90% {p[1]:.4f}°  99% {p[2]:.4f}°  max {errs.max():.4f}°")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--years", help="e.g. 1999-2012; default every year with an attitude file")
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    z = zipfile.ZipFile(args.zip)
    members = set(z.namelist())

    have = sorted(int(f[:4]) for f in os.listdir(os.path.join(args.data, "attitude")) if re.fullmatch(r"\d{4}\.bin", f))
    if args.years:
        y0, y1 = (int(x) for x in args.years.split("-"))
        have = [y for y in have if y0 <= y <= y1]

    check_frames(z, members, have[-1], os.path.join(args.tmp, "fk"))
    all_err = {"random": [], "image": []}
    for year in have:
        loaded, result = check_year(z, members, year, args, rng)
        print(f"{year} ({loaded} kernels)", flush=True)
        for label, (errs, no_js, no_spice) in result.items():
            all_err[label].append(errs)
            print(f"  {label:6s} {stats(errs)}  (outside export coverage {no_js}, no CK data {no_spice})", flush=True)
    print("all years")
    for label, errs in all_err.items():
        print(f"  {label:6s} {stats(np.concatenate(errs))}")
    shutil.rmtree(os.path.join(args.tmp, "fk"), ignore_errors=True)


if __name__ == "__main__":
    main()
