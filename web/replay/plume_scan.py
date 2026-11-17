#!/usr/bin/env python3
"""
The geometry of every picture that holds Enceladus, for finding the ones where its south polar plumes should show
(Sam 2026-11-16: "events where Enceladus's plumes are very visible" in the Moments list).

The plumes are fine ice grains: they scatter sunlight forward, so they are bright only when the Sun is nearly behind
Enceladus as Cassini sees it (high phase angle), and they show against black sky only where the column over the south
pole rises past the limb. For each frame this works out from SPICE (the mission kernels, loaded a year at a time as
bodies_probe does, at the geometry cache's frame time and camera):

  phase     Sun-Enceladus-Cassini angle (degrees)
  sublat    Cassini's latitude over Enceladus (degrees, south negative): near 0 puts the pole on the limb
  r_px      Enceladus' radius in full resolution pixels
  above_px  how far past the limb, in pixels, the column at PLUME_KM over the south pole stands (negative: in front of
            the disk, hidden against it)
  px, py    where that point of the column falls in the frame (full resolution pixels, 0 at the top left corner)
  in_frame  that point is inside the frame
  lit       Enceladus is out of Saturn's shadow (the column is in sunlight)
  on_saturn that point falls on Saturn's disk (a bright background, not black sky)
  near      the other bodies whose disks come within NEAR radii of Enceladus' centre in the picture

One JSON line per frame; plume_moments.py applies the rule to these and measures the pictures.

  CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... python web/replay/plume_scan.py --out plume_geometry.jsonl
"""
import argparse
import datetime
import json
import math
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "frames"))
import reel  # noqa: E402,F401  (puts the repo on the path)

RADIUS_KM = 252.1      # Enceladus' mean radius
PLUME_KM = 100.0
NEAR = 2.5             # another body whose disk comes within this many of Enceladus' radii of its centre is "near"       # the height over the south pole the column is judged at: the bright lower plume


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--years", default="2004-2017")
    args = ap.parse_args()
    import numpy as np
    import spiceypy as sp
    import bootleg_autonav as ba
    import obs_mosaic as om
    others = [b for b in om.RADIUS if b not in ("ENCELADUS", "JUPITER") and b not in om.CRUISE_RADIUS]
    y0, _, y1 = args.years.partition("-")
    years = range(int(y0), int(y1 or y0) + 1)
    idx, _ = reel.load_index()
    meta = {r.id: r for r in idx[["id", "OBSERVATION_ID", "INSTRUMENT_ID", "TARGET_NAME", "filter1", "filter2",
                                    "seconds_1970"]].itertuples(index=False)}
    db = sqlite3.connect(ba.GEOMETRY_CACHE)
    frames = {r[0] for r in db.execute("SELECT frame FROM bodies WHERE body = 'ENCELADUS' AND version = ?",
                                       (ba.GEOMETRY_VERSION,))}
    frames |= {r[0] for r in db.execute("SELECT frame FROM target WHERE target = 'ENCELADUS' AND version = ? "
                                        "AND error IS NULL", (ba.GEOMETRY_VERSION,))}
    geo = {}
    ids = sorted(frames)
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        q = f"SELECT frame, et, camera FROM target WHERE version = ? AND frame IN ({','.join('?' * len(part))})"
        for r in db.execute(q, (ba.GEOMETRY_VERSION, *part)):
            if r[1] is not None and r[2]:
                geo[r[0]] = (r[1], r[2])
    by_year = {}
    for f in ids:
        if f in geo and f in meta:
            y = datetime.datetime.fromtimestamp(meta[f].seconds_1970, datetime.timezone.utc).year
            if y in years:
                by_year.setdefault(y, []).append(f)
    print(f"{len(ids)} frames with Enceladus, {sum(map(len, by_year.values()))} with pointing in {args.years}", flush=True)
    with open(args.out, "w") as out:
        for year in sorted(by_year):
            ba.unload_kernels()
            ba.load_kernels(year, year)
            scale = {}
            n = 0
            for f in sorted(by_year[year], key=lambda f: geo[f][0]):
                et, camera = geo[f]
                if camera not in scale:
                    scale[camera] = ba.pixel_scale(camera)
                try:
                    pos, lt = sp.spkpos("ENCELADUS", et, "J2000", ba.ABCORR, "CASSINI")
                    sun, _ = sp.spkpos("SUN", et - lt, "J2000", ba.ABCORR, "ENCELADUS")
                    rot = sp.pxform("IAU_ENCELADUS", "J2000", et - lt)
                    cam = sp.pxform("J2000", camera, et)
                except Exception:
                    continue
                pos, sun = np.array(pos), np.array(sun)
                dist = float(np.linalg.norm(pos))
                to_sc = -pos / dist
                phase = math.degrees(math.acos(float(np.clip(np.dot(to_sc, sun / np.linalg.norm(sun)), -1, 1))))
                south = -np.array(rot)[:, 2]
                sublat = -math.degrees(math.asin(float(np.clip(np.dot(to_sc, south), -1, 1))))
                # how far off the line of sight through the centre the column point stands, past the limb
                off = (RADIUS_KM + PLUME_KM) * math.sqrt(max(0.0, 1 - float(np.dot(to_sc, south)) ** 2))
                km_px = dist / scale[camera]
                v = sp.mxv(cam, (pos + (RADIUS_KM + PLUME_KM) * south).tolist())
                if v[2] <= 0:
                    continue
                px, py = ba.project(v, scale[camera])
                c = sp.mxv(cam, pos.tolist())
                cx, cy = ba.project(c, scale[camera]) if c[2] > 0 else (float("nan"), float("nan"))
                try:
                    lit = not sp.occult("SATURN", "ELLIPSOID", "IAU_SATURN", "SUN", "POINT", " ", "LT", "ENCELADUS", et - lt)
                except Exception:
                    lit = None
                # other bodies near Enceladus in the picture: their disks or glow would be taken for a plume
                on_saturn, near = False, []
                er = RADIUS_KM / dist * scale[camera]
                for b in others:
                    try:
                        bp, _ = sp.spkpos(b, et, "J2000", ba.ABCORR, "CASSINI")
                    except Exception:
                        continue
                    bv = sp.mxv(cam, bp)
                    if bv[2] <= 0:
                        continue
                    bx, by = ba.project(bv, scale[camera])
                    br = om.RADIUS[b] / sp.vnorm(bp) * scale[camera]
                    if b == "SATURN" and math.hypot(px - bx, py - by) < br and sp.vnorm(bp) > dist:
                        on_saturn = True
                    if math.hypot(cx - bx, cy - by) - br < NEAR * er:
                        near.append(b)
                m = meta[f]
                out.write(json.dumps({
                    "id": f, "obs": m.OBSERVATION_ID, "cam": m.INSTRUMENT_ID[3], "target": m.TARGET_NAME,
                    "filter": f"{m.filter1}/{m.filter2}", "et": round(et, 2), "utc": sp.et2utc(et, "ISOC", 0),
                    "km": round(dist), "phase": round(phase, 2), "sublat": round(sublat, 2),
                    "r_px": round(RADIUS_KM / km_px, 2), "above_px": round((off - RADIUS_KM) / km_px, 2),
                    "px": round(px, 1), "py": round(py, 1), "cx": round(cx, 1), "cy": round(cy, 1),
                    "in_frame": bool(0 <= px < ba.FULL_FRAME and 0 <= py < ba.FULL_FRAME),
                    "lit": lit, "on_saturn": on_saturn, "near": near}) + "\n")
                n += 1
            out.flush()
            print(year, n, "frames", flush=True)


if __name__ == "__main__":
    main()
