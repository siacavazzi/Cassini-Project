#!/usr/bin/env python3
"""
How bright the sky over Enceladus' south pole is in each picture plume_scan.py found, against the sky the same distance
off the other sides: the check that a picture whose geometry says "plumes should show" really shows them.

For a frame of radius R (pixels) it takes the frame as archived (the 8-bit picture in CASSINI_DATA, before any
stretch) and, around where SPICE puts Enceladus' centre:
  south  the pixels 1.15 R to 1.8 R from the centre within 20 degrees of the direction of the column over the pole
  others the same band in the three directions 90, 180 and 270 degrees round from it
  plume  median(south) minus the dimmest median(others): the column's light over the sky's
  snr    plume over the sky's scatter (median absolute deviation of the dimmest other band)
  rel    plume over the disk's bright end (99th percentile inside R, less the sky): how strong it is beside the moon
  sat    the share of the south band at the picture's top value (saturated)

  CASSINI_DATA=... python web/replay/plume_measure.py plume_geometry.jsonl --out plume_measured.jsonl [--jobs N]
"""
import argparse
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "frames"))

MIN_R_PX = 8          # smaller than this and the bands hold too few pixels to judge (and the plume is a smudge)
BAND = (1.15, 1.8)
LIMB_R_PX = 40
HALF_ANGLE = 20.0

_paths = None


def paths():
    global _paths
    if _paths is None:
        import pandas as pd
        idx = pd.read_csv(os.path.join(HERE, "..", "..", "Image_index.csv"), usecols=["path"], low_memory=False)
        _paths = {p.rsplit("/", 1)[-1].replace(".png", ""): p for p in idx["path"].dropna().tolist()}
    return _paths


def measure(row):
    import numpy as np
    import cv2
    import data_source as ds
    out = dict(row)
    path = paths().get(row["id"])
    if not path:
        out["error"] = "not in the index"
        return out
    try:
        img = ds.imread(path, cv2.IMREAD_GRAYSCALE)
    except Exception as e:
        out["error"] = str(e)[:100]
        return out
    if img is None:
        out["error"] = "unreadable"
        return out
    import obs_mosaic as om
    img = img.astype(np.float32)
    k = img.shape[0] / 1024.0
    cx, cy, px, py, r = row["cx"] * k, row["cy"] * k, row["px"] * k, row["py"] * k, row["r_px"] * k
    if not (r >= MIN_R_PX * k) or not math.isfinite(cx):
        out["error"] = "too small"
        return out
    # rows and columns of one value are lines the camera did not send (or a readout window): no data
    valid = ~(img.std(axis=1) == 0)[:, None] & ~(img.std(axis=0) == 0)[None, :]
    # SPICE's place, moved onto the limb in the picture (the pipeline's own search, obs_mosaic._limb_centre)
    try:
        f = min(1.0, LIMB_R_PX / r)   # searched on a picture shrunk to a radius of LIMB_R_PX: the same answer, sooner
        small = img if f == 1.0 else cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        moved = om._limb_centre(small, (cx * f, cy * f), r * f)
        moved = moved and (moved[0] / f, moved[1] / f)
    except Exception:
        moved = None
    if moved:
        cx, cy, px, py = cx + moved[0], cy + moved[1], px + moved[0], py + moved[1]
        out["moved"] = [round(moved[0] / k, 1), round(moved[1] / k, 1)]
    ang0 = math.atan2(py - cy, px - cx)
    reach = int(r * BAND[1]) + 2
    x0, x1 = max(0, int(cx) - reach), min(img.shape[1], int(cx) + reach + 1)
    y0, y1 = max(0, int(cy) - reach), min(img.shape[0], int(cy) + reach + 1)
    if x0 >= x1 or y0 >= y1:
        out["error"] = "off the frame"
        return out
    yy, xx = np.mgrid[y0:y1, x0:x1]
    rho = np.hypot(xx - cx, yy - cy) / r
    rel_ang = (np.degrees(np.arctan2(yy - cy, xx - cx) - ang0) + 540) % 360 - 180
    sub = img[y0:y1, x0:x1]
    band = (rho >= BAND[0]) & (rho <= BAND[1]) & valid[y0:y1, x0:x1]

    def sector(at):
        m = band & (np.abs((rel_ang - at + 540) % 360 - 180) <= HALF_ANGLE)
        return sub[m]

    south = sector(0)
    others = [s for s in (sector(90), sector(180), sector(-90)) if s.size >= 10]
    disk = sub[(rho < 1) & valid[y0:y1, x0:x1]]
    if south.size < 10 or not others or disk.size < 10:
        out["error"] = "bands off the frame"
        return out
    meds = [float(np.median(s)) for s in others]
    dim = others[int(np.argmin(meds))]
    bg = min(meds)
    noise = float(np.median(np.abs(dim - np.median(dim)))) * 1.4826 + 1.0
    s = float(np.median(south))
    # a jet fills a few degrees of the band: its brighter tenth, over the brighter tenth of the dimmest other side
    hi = float(np.percentile(south, 90)) - min(float(np.percentile(o, 90)) for o in others)
    top = float(np.percentile(disk, 99))
    # where SPICE puts the disk holds the lit part of the picture round it (no pointing miss, no other body)
    near = sub[rho < 3]
    bright = near > 0.5 * float(near.max())
    rr = rho[rho < 3]
    on_disk = float((bright & (rr < 1.1)).sum()) / max(1, int(bright.sum()))
    out.update({"south": round(s, 2), "sky": round(bg, 2), "plume": round(s - bg, 2), "snr": round((s - bg) / noise, 2),
                "jet": round(hi / noise, 2), "rel": round((s - bg) / max(1.0, top - bg), 3), "disk99": round(top, 1),
                "sat": round(float(np.mean(south >= 255)), 3), "disk_sat": round(float(np.mean(disk >= 255)), 3),
                "on_disk": round(on_disk, 3), "cover": round(float(valid.mean()), 3)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("geometry")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--min-phase", type=float, default=140)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.geometry)]
    rows = [r for r in rows if r["phase"] >= a.min_phase and r["above_px"] > 0 and r["in_frame"] and r["lit"] is not False]
    print(len(rows), "frames to measure", flush=True)
    with open(a.out, "w") as f, ProcessPoolExecutor(a.jobs) as pool:
        for n, r in enumerate(pool.map(measure, rows, chunksize=16)):
            f.write(json.dumps(r) + "\n")
            if n % 500 == 0:
                print(n, flush=True)


if __name__ == "__main__":
    main()
