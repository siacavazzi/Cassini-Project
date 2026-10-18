#!/usr/bin/env python3
"""
Export Cassini's pointing for the browser replay. Needs the CK kernels, so it runs where the
full archive is (the LaCie zip), one year at a time to keep disk use small.

  python web/export_attitude.py --zip /Volumes/LaCie/cassiniprojectJAN05.zip \
      --catalog <replay_data>/catalog --out <replay_data> --tmp /Volumes/LaCie/attitude_tmp

Writes attitude/<year>.bin:
  16-byte header: b"CATT", uint16 version (1), uint16 flags (0), uint32 n_images, uint32 n_background
  float32 image_q[4*n_images]   camera pointing at each image's mid-time, in catalog/<year>.json order
  float64 bg_t[n_background]    ephemeris time of each background sample (every 10 minutes)
  float32 bg_q[4*n_background]  spacecraft body attitude (CASSINI_SC_COORD) at those times
Quaternions are SPICE style (w, x, y, z) for the rotation J2000 -> frame; NaN where the CK has no data.
"""

import argparse
import gzip
import json
import os
import re
import shutil
import struct
import zipfile

import numpy as np
import spiceypy as sp

FRAMES = {"N": "CASSINI_ISS_NAC", "W": "CASSINI_ISS_WAC"}
PREFIX = "cassini/cosp_1000/"


def kernels_for_year(z, year):
    names = [n for n in z.namelist() if re.match(rf"{PREFIX}index/cas_{year}(_iss)?_v\d+\.tm$", n)]
    if not names:
        return []
    text = z.read(sorted(names)[-1]).decode()
    keep = ("lsk", "sclk", "fk", "pck", "ck", "iss_ck")
    return [k for k in re.findall(r"\$KERNELS/(\S+?)'", text) if k.split("/")[0] in keep]


def quat(frame, et):
    try:
        return sp.m2q(sp.pxform("J2000", frame, et))
    except Exception:
        return [np.nan] * 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--years", default="1997-2017")
    args = ap.parse_args()
    y0, y1 = (int(x) for x in args.years.split("-"))
    z = zipfile.ZipFile(args.zip)
    members = set(z.namelist())
    os.makedirs(os.path.join(args.out, "attitude"), exist_ok=True)

    for year in range(y0, y1 + 1):
        path = os.path.join(args.out, "attitude", f"{year}.bin")
        if os.path.exists(path):
            continue
        kernels = kernels_for_year(z, year)
        if not kernels:
            continue
        tmp = os.path.join(args.tmp, str(year))
        os.makedirs(tmp, exist_ok=True)
        sp.kclear()
        for k in kernels:
            src = PREFIX + "data/" + k
            if src not in members:
                print(f"  missing {k}")
                continue
            dst = os.path.join(tmp, os.path.basename(k))
            if not os.path.exists(dst):
                with z.open(src) as fin, open(dst, "wb") as fout:
                    shutil.copyfileobj(fin, fout, 1 << 24)
            sp.furnsh(dst)

        cat_path = os.path.join(args.catalog, f"{year}.json")
        if os.path.exists(cat_path):
            cat = json.load(open(cat_path))
        elif os.path.exists(cat_path + ".gz"):
            cat = json.load(gzip.open(cat_path + ".gz"))
        else:
            cat = {"et": [], "cam": []}
        img_q = np.array([quat(FRAMES[c], et) for et, c in zip(cat["et"], cat["cam"])], dtype="<f4").reshape(-1, 4)

        a = sp.str2et(f"{year}-01-01T00:00:00")
        b = sp.str2et(f"{year + 1}-01-01T00:00:00")
        bg_t = np.arange(a, b, 600.0)
        bg_q = np.array([quat("CASSINI_SC_COORD", t) for t in bg_t], dtype="<f4")
        ok = ~np.isnan(bg_q[:, 0])
        bg_t, bg_q = bg_t[ok].astype("<f8"), bg_q[ok]

        with open(path, "wb") as fh:
            fh.write(b"CATT" + struct.pack("<HHII", 1, 0, len(img_q), len(bg_t)))
            fh.write(img_q.tobytes())
            fh.write(bg_t.tobytes())
            fh.write(bg_q.tobytes())
        good = int((~np.isnan(img_q[:, 0])).sum()) if len(img_q) else 0
        print(f"{year}: {good}/{len(img_q)} images pointed, {len(bg_t)} background samples, "
              f"{os.path.getsize(path) / 1e6:.1f} MB", flush=True)
        sp.kclear()
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
