#!/usr/bin/env python3
"""Auto center's rule (obs_mosaic.centre_half) before and after the body had to be on a frame and the square had to
keep CENTRE_KEEP of the frames: for every pass the windows play as a movie, the share of each frame's area outside
the movie's view (movie_rect) and the frames wholly outside it, under the old rule and the new; and for every pass,
whether the camera windows' single pictures (centre_view) flip between centred, north up and as they are. Each
frame is its own outline from the geometry cache (frames_seen: turned north up by its own angle), and the
footprint the frames' outlines with MOVIE_MARGIN round them, as movie_footprint measures it on the tiles. Needs the
index and the geometry cache (CASSINI_GEOMETRY_CACHE), as units does; reads only, no pictures.
Run: python web/frames/centred_passes.py --out centred-passes.tsv [--ids flipped-ids.txt] [--targets SATURN,...]"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_mosaic as om  # noqa: E402
import reel  # noqa: E402

LOST = 0.05   # a pass losing more than this share of its frames (mean over them) counts as cut


def old_half(fp, radius):
    """centre_half before this change: the body's centre in the footprint's box, the view capped at MOVIE_FIT."""
    x0, y0, x1, y1 = fp
    side = om.MOVIE_FIT * om.FRAME
    around = max(om.FRAME, 2 * radius * (1 + om.CENTRE_MARGIN))
    if radius > 0 and around <= side and x0 <= 0 <= x1 and y0 <= 0 <= y1:
        return min(side, max(around, 2 * max(-x0, x1, -y0, y1))) / 2
    return None


def lost(u, seen, half):
    """(mean share of the frames outside the movie's view, frames wholly outside it), the view centred on the body
    with half side half, or movie_rect's footprint view when half is None."""
    n = om.SEEN_GRID ** 2
    pts = seen[1].reshape(-1, n, 2)
    lo, hi = pts.min((0, 1)), pts.max((0, 1))
    m = om.MOVIE_MARGIN * om.FRAME
    fp = (lo[0] - m, lo[1] - m, hi[0] + m, hi[1] + m)
    out = []
    for p in pts:
        if half:
            x, y, w, h = -half, -half, 2 * half, 2 * half
        else:
            x, y, w, h = om.movie_rect(fp, {"offset": p.mean(0)})
        inside = (p[:, 0] >= x) & (p[:, 0] <= x + w) & (p[:, 1] >= y) & (p[:, 1] <= y + h)
        out.append(1 - inside.mean())
    out = np.array(out)
    return float(out.mean()), int((out >= 1).sum()), fp


def still(u, seen, radius, rule):
    """centre_view's decision for the pass's single pictures under rule (old or new): centre, north or plain."""
    fp = om._box(u, u["z"])
    if not fp or not radius:
        half = None
    else:
        half = old_half(fp, radius) if rule == "old" else om.centre_half(fp, radius, seen)
    if half:
        return "centre"
    boxes = [(-x * fz / u["z"] - om.HALF, -y * fz / u["z"] - om.HALF, -x * fz / u["z"] + om.HALF, -y * fz / u["z"] + om.HALF)
             for *_, x, y, fz in u["frames"] if fz]
    on = sum(om._on_disk(b, radius) for b in boxes) if radius else 0
    return "north" if boxes and on * 2 > len(boxes) else "plain"


def sweep(targets=None):
    idx, _ = reel.load_index()
    rows = []
    for (target, obs, inst) in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices:
        if not isinstance(obs, str) or inst not in ("ISSNA", "ISSWA") or targets and target not in targets:
            continue
        cam = "N" if inst == "ISSNA" else "W"
        for u in om.units(target, obs, cam):
            if not u["frames"] or not u.get("z"):
                continue
            seen = om.frames_seen(u["frames"], u["z"])
            if seen is None:
                continue
            radius = om.RADIUS.get(target, 0) / (u["z"] * om.IFOV[cam])
            movie = u.get("kind") == "movie" or (u.get("movie") and not u["mosaic"])
            row = {"pass": "_".join(map(str, u["key"])), "first": u["frames"][0][1], "t": u["frames"][0][3],
                   "frames": len(u["frames"]), "movie": bool(movie), "track": bool(u.get("track")),
                   "on": bool(seen[0]), "still_old": still(u, seen, radius, "old"), "still_new": still(u, seen, radius, "new"),
                   "ids": [fr[1] for fr in u["frames"]]}
            if movie and not u.get("track"):
                _, _, fp = lost(u, seen, None)
                h_old = old_half(fp, radius)
                h_new = om.centre_half(fp, radius, seen)
                # the share of the frames a view centred on the body would keep (centre_half's third test)
                around = max(om.FRAME, 2 * radius * (1 + om.CENTRE_MARGIN))
                half = min(om.MOVIE_FIT * om.FRAME, max(around, 2 * max(-fp[0], fp[2], -fp[1], fp[3]))) / 2
                row.update(centred_old=bool(h_old), centred_new=bool(h_new), kept=round(om.kept_share(seen, half), 4))
                row["lost_old"], row["off_old"], _ = lost(u, seen, h_old)
                row["lost_new"], row["off_new"], _ = lost(u, seen, h_new)
            rows.append(row)
        with om._lock:
            om._units.clear()
            om._seen.clear()
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="write one line per movie pass here (TSV)")
    ap.add_argument("--ids", help="write the frame ids of the passes whose single pictures flip here (prebuild --only)")
    ap.add_argument("--targets", help="only these targets, comma separated")
    ap.add_argument("--show", default="EG130PHAS001,228EN_PLUME001,201RI_SPOKEMOV009,RPX120PH001",
                    help="observations to print in full (comma separated, matched inside the pass name)")
    a = ap.parse_args()
    rows = sweep(set(a.targets.split(",")) if a.targets else None)
    movies = [r for r in rows if "lost_old" in r]
    for rule in ("old", "new"):
        c = [r for r in movies if r[f"centred_{rule}"]]
        print(f"{rule}: {len(c)} of {len(movies)} movie passes centred; "
              f"{sum(r[f'lost_{rule}'] > LOST for r in movies)} lose more than {LOST:.0%} "
              f"({sum(r[f'lost_{rule}'] > LOST for r in c)} of them centred), "
              f"{sum(r[f'lost_{rule}'] > 0.2 for r in movies)} more than 20%, "
              f"{sum(r[f'off_{rule}'] > 0 for r in movies)} with frames wholly outside the view "
              f"({sum(r[f'off_{rule}'] > 0 for r in c)} of them centred; {sum(r[f'off_{rule}'] for r in movies)} frames)")
    flips = collections.Counter((r["centred_old"], r["centred_new"]) for r in movies)
    print("movie passes centred old -> new:", {f"{o}->{n}": k for (o, n), k in sorted(flips.items())})
    st = collections.Counter((r["still_old"], r["still_new"]) for r in rows if r["still_old"] != r["still_new"])
    print(f"single pictures: {sum(st.values())} of {len(rows)} passes flip "
          f"({sum(r['frames'] for r in rows if r['still_old'] != r['still_new'])} frames):",
          {f"{o}->{n}": k for (o, n), k in st.most_common()})
    for want in a.show.split(","):
        for r in movies:
            if want and want in r["pass"]:
                print(" ", {k: v for k, v in r.items() if k != "ids"})
    if a.out:
        keys = ["pass", "first", "t", "frames", "on", "kept", "centred_old", "centred_new", "lost_old", "lost_new",
                "off_old", "off_new", "still_old", "still_new"]
        with open(a.out, "w") as f:
            f.write("\t".join(keys) + "\n")
            for r in movies:
                f.write("\t".join(str(round(r[k], 4) if isinstance(r[k], float) else r[k]) for k in keys) + "\n")
        print("movie passes in", a.out)
    if a.ids:
        with open(a.ids, "w") as f:
            for r in rows:
                if r["still_old"] != r["still_new"]:
                    f.writelines(i + "\n" for i in r["ids"])
        print("ids in", a.ids)
