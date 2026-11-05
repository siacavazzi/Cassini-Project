#!/usr/bin/env python3
"""Which other bodies SPICE puts in the frames of a pass besides its target (Sam 2026-11-04: movie stabilization
"locks on one moon and then changes" when two moons are in the frame, a moon transiting another). For every frame of
the observations asked (or every observation whose name matches --match), each body bootleg_autonav knows a radius of
(obs_mosaic.RADIUS) whose disk touches the frame, where SPICE puts it (full resolution pixels from the frame's
middle, the camera's own axes) and its radius in pixels, with the frame's TARGET_NAME and where the target is. One
JSON line per frame, so it shows which movie passes hold two bodies, which body is the bigger one in the frame, and
where the planners changed TARGET_NAME in the middle of an observation (206TE_MUTUALEVE001: Tethys, Helene,
Tethys), the two ways a movie centred on its pass's body can change bodies.

Loads each year's kernels once (bootleg_autonav.load_kernels), from the geometry cache's frame times (et) and camera.

  CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... python web/frames/bodies_probe.py --out bodies.jsonl \\
      [--match MUTUALEVE] [OBSERVATION_ID ...]
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--match", default="", help="every observation whose OBSERVATION_ID holds this")
    ap.add_argument("--margin", type=float, default=0.25, help="of a frame round it: bodies this far off still listed")
    ap.add_argument("observations", nargs="*")
    args = ap.parse_args()
    import spiceypy as sp
    import bootleg_autonav as ba
    import obs_mosaic as om
    idx, _ = reel.load_index()
    want = idx["OBSERVATION_ID"].astype(str)
    pick = want.isin(args.observations)
    if args.match:
        pick |= want.str.contains(args.match, regex=False)
    rows = idx[pick]
    db = sqlite3.connect(ba.GEOMETRY_CACHE)
    geo = {}
    ids = rows["id"].tolist()
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        q = f"SELECT frame, x, y, z, et, camera, target FROM target WHERE version = ? AND error IS NULL AND frame IN ({','.join('?' * len(part))})"
        for r in db.execute(q, (ba.GEOMETRY_VERSION, *part)):
            geo[r[0]] = r[1:]
    # kernels are loaded a calendar year at a time, as label_handler does
    by_year = {}
    for r in rows.itertuples(index=False):
        if r.id in geo:
            by_year.setdefault(datetime.datetime.fromtimestamp(r.seconds_1970, datetime.timezone.utc).year, []).append(r)
    bodies = sorted(om.RADIUS)
    half = ba.FULL_FRAME / 2 * (1 + 2 * args.margin)
    with open(args.out, "w") as out:
        for year in sorted(by_year):
            ba.unload_kernels()
            ba.load_kernels(year, year)
            scale = {}
            for r in by_year[year]:
                x, y, z, et, camera, target = geo[r.id]
                if camera not in scale:
                    scale[camera] = ba.pixel_scale(camera)
                cam = sp.pxform("J2000", camera, et)
                seen = []
                for b in bodies:
                    try:
                        pos, _ = sp.spkpos(b, et, "J2000", ba.ABCORR, "CASSINI")
                    except Exception:
                        continue
                    v = sp.mxv(cam, pos)
                    if v[2] <= 0:
                        continue
                    s, l = ba.project(v, scale[camera])
                    dist = sp.vnorm(pos)
                    rad = om.RADIUS[b] / dist * scale[camera]
                    dx, dy = s - ba.CCD_CENTER, l - ba.CCD_CENTER
                    if max(abs(dx), abs(dy)) - rad > half:
                        continue
                    seen.append({"body": b, "x": round(dx, 1), "y": round(dy, 1), "r": round(rad, 2), "km": round(dist)})
                seen.sort(key=lambda d: -d["r"])
                rec = {"id": r.id, "obs": r.OBSERVATION_ID, "cam": r.INSTRUMENT_ID, "target": r.TARGET_NAME,
                       "t": float(r.seconds_1970), "filter": f"{r.filter1}/{r.filter2}",
                       "target_at": [round(-x, 1), round(-y, 1)], "bodies": seen,
                       "others_on": [d["body"] for d in seen if d["body"] != r.TARGET_NAME
                                     and max(abs(d["x"]), abs(d["y"])) - d["r"] <= ba.FULL_FRAME / 2]}
                out.write(json.dumps(rec) + "\n")
            out.flush()
            print(year, len(by_year[year]), "frames", flush=True)


if __name__ == "__main__":
    main()
