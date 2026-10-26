#!/usr/bin/env python3
"""Before/after evidence for feature tracks (pictures program phase 5, obs_mosaic._judge's track): each pass drawn
as it played before, its whole mosaic (so_far over every tile), next to frames of it played as a movie (movie_frame,
steadied on the pass's one scale), both through the checkout's own obs_mosaic, nothing re-implemented. Written as
JPEG with an index.html, for the live site's static folder.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/track_evidence.py --cache DIR --out OUT TARGET:OBSERVATION_ID:CAM[:pass] ...
"""
import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=3, help="movie frames shown per pass")
    ap.add_argument("passes", nargs="+")
    args = ap.parse_args()
    import calibration
    import obs_mosaic as om
    os.makedirs(args.out, exist_ok=True)
    rows = []
    with calibration.looking("balanced"):
        for spec in args.passes:
            target, obs, cam, *k = spec.split(":")
            us = om.units(target, obs, cam)
            u = us[int(k[0])] if k else max(us, key=lambda v: len(v["frames"]))
            name = "_".join(map(str, u["key"]))
            n = len(u["frames"])
            print(name, n, "tiles, now", u["kind"], "track" if u.get("track") else "", flush=True)
            shots = []
            im, _ = om.so_far(u, n - 1, args.cache)
            if im is not None:
                im.convert("RGB").save(os.path.join(args.out, f"{name}_before.jpg"), quality=90)
                shots.append((f"{name}_before.jpg", f"Before: the whole pass as a mosaic ({n} tiles)"))
            for j in sorted({round(i * (n - 1) / max(1, args.frames - 1)) for i in range(args.frames)}):
                im, rep = om.movie_frame(u, j, args.cache)
                if im is None:
                    continue
                im.convert("RGB").save(os.path.join(args.out, f"{name}_after_{j}.jpg"), quality=90)
                shots.append((f"{name}_after_{j}.jpg", f"After: frame {j + 1} of {n} played as a movie, {rep.get('id', '')}"
                              + (f", color {' '.join(rep['color'])}" if rep.get("color") else "")))
                print(" ", j, "done", flush=True)
            rows.append((name, u["kind"], shots))
    with open(os.path.join(args.out, "index.html"), "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Feature tracks</title>"
                 "<style>body{background:#0c0c0e;color:#ddd;font:14px -apple-system,sans-serif;margin:16px}figure{display:inline-block;"
                 "margin:0 12px 12px 0;vertical-align:top}img{max-width:min(46vw,640px);display:block}figcaption{max-width:min(46vw,640px)}</style>"
                 "<h1>Feature tracks play as movies (phase 5, PR #124)</h1>")
        for name, kind, shots in rows:
            fh.write(f"<h2>{html.escape(name)} · now {html.escape(str(kind))}</h2>")
            for f, cap in shots:
                fh.write(f"<figure><a href='{f}'><img src='{f}' loading=lazy></a><figcaption>{html.escape(cap)}</figcaption></figure>")


if __name__ == "__main__":
    main()
