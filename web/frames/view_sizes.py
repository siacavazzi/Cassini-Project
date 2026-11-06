#!/usr/bin/env python3
"""How big Auto center draws each movie pass (obs_mosaic.centre_half / fitted_half), before and after the view was
fitted to what the frames show (2026-11-03): for every pass the windows play as a movie and centre on its body, the
view's side before (the whole footprint, MOVIE_MARGIN round the frames turned north up) and after, in frames, the
body's disk across the view, and the share of the frames' area the new view leaves out. Each frame is its own outline
from the geometry cache (frames_seen), as centred_passes.py measures it. Needs the index and the geometry cache
(CASSINI_GEOMETRY_CACHE); reads only, no pictures.
Run: python web/frames/view_sizes.py --out view-sizes.tsv [--targets HYPERION,...]"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import centred_passes  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reel  # noqa: E402


def sweep(targets=None):
    idx, _ = reel.load_index()
    rows = []
    for (target, obs, inst) in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices:
        if not isinstance(obs, str) or inst not in ("ISSNA", "ISSWA") or targets and target not in targets:
            continue
        cam = "N" if inst == "ISSNA" else "W"
        for u in om.units(target, obs, cam):
            movie = u.get("kind") == "movie" or (u.get("movie") and not u["mosaic"])
            if not (movie and u["frames"] and u.get("z")) or u.get("track"):
                continue
            seen = om.frames_seen(u["frames"], u["z"])
            if seen is None:
                continue
            radius = om.RADIUS.get(target, 0) / (u["z"] * om.IFOV[cam])
            # movie_footprint: the tiles with MOVIE_MARGIN round them and the plan's footprint (HALF round each frame)
            _, _, fp = centred_passes.lost(u, seen, None)
            g = om._box(u, u["z"])
            fp = (min(fp[0], g[0]), min(fp[1], g[1]), max(fp[2], g[2]), max(fp[3], g[3]))
            new = om.centre_half(fp, radius, seen)
            if not new:
                continue
            around = max(om.FRAME, 2 * radius * (1 + om.CENTRE_MARGIN))
            old = min(om.MOVIE_FIT * om.FRAME, max(around, 2 * max(-fp[0], fp[2], -fp[1], fp[3]))) / 2
            rows.append({"pass": "_".join(map(str, u["key"])), "first": u["frames"][0][1], "t": u["frames"][0][3],
                         "cam": cam, "frames": len(u["frames"]), "old_side": round(2 * old / om.FRAME, 3),
                         "new_side": round(2 * new / om.FRAME, 3), "disk_old": round(radius / old, 3),
                         "disk_new": round(radius / new, 3), "lost_new": round(1 - om.kept_share(seen, new), 4)})
        with om._lock:
            om._units.clear()
            om._seen.clear()
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="write one line per centred movie pass here (TSV)")
    ap.add_argument("--targets", help="only these targets, comma separated")
    a = ap.parse_args()
    rows = sweep(set(a.targets.split(",")) if a.targets else None)
    for cam in ("N", "W"):
        c = [r for r in rows if r["cam"] == cam]
        if not c:
            continue
        old, new = np.array([r["old_side"] for r in c]), np.array([r["new_side"] for r in c])
        print(f"{cam}AC: {len(c)} centred movie passes; view side in frames, median {np.median(old):.2f} -> "
              f"{np.median(new):.2f} (10%-90%: {np.percentile(old, 10):.2f}-{np.percentile(old, 90):.2f} -> "
              f"{np.percentile(new, 10):.2f}-{np.percentile(new, 90):.2f}); the body drawn "
              f"{np.median(old / new):.2f}x bigger (median), {sum(new < old * 0.99)} passes change; "
              f"frames' area left out, median {np.median([r['lost_new'] for r in c]):.1%}, "
              f"most {max(r['lost_new'] for r in c):.1%}")
    if a.out:
        keys = list(rows[0]) if rows else []
        with open(a.out, "w") as f:
            f.write("\t".join(keys) + "\n")
            for r in rows:
                f.write("\t".join(str(r[k]) for k in keys) + "\n")
        print("centred movie passes in", a.out)
