#!/usr/bin/env python3
"""A contact strip of every movie frame of one camera's observation, across all its passes in time order (an
observation whose TARGET_NAME changes is several passes, one per target), as the camera windows play them with Auto
center: each frame through the checkout's own obs_mosaic.movie_frame, centred (centre=True), once where SPICE puts it
(steady 0) and once stabilized (--smooth frames), labelled with its frame id, its pass's target and how far
stabilization moved it from SPICE. For the moon-transit stabilization report (Sam 2026-11-04).

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/mutual_strip.py --cache DIR --out strip.jpg OBSERVATION_ID N|W
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--smooth", type=int, default=12)
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("observation")
    ap.add_argument("cam", choices=("N", "W"))
    args = ap.parse_args()
    from PIL import Image, ImageDraw
    import calibration
    import obs_mosaic as om
    idx, _ = reel.load_index()
    inst = "ISSNA" if args.cam == "N" else "ISSWA"
    rows = idx[(idx["OBSERVATION_ID"] == args.observation) & (idx["INSTRUMENT_ID"] == inst)]
    passes = []
    for target in dict.fromkeys(rows["TARGET_NAME"]):
        passes += om.units(target, args.observation, args.cam)
    passes.sort(key=lambda u: u["frames"][0][3])
    cells, report = {0: [], args.smooth: []}, []
    with calibration.looking("balanced"):
        for u in passes:
            for n in range(len(u["frames"])):
                for steady in cells:
                    im, rep = om.movie_frame(u, n, args.cache, out=args.size, centre=True, steady=steady)
                    cells[steady].append((im, u, n, rep))
                    report.append({"pass": [str(v) for v in u["key"]], "n": n, "steady": steady,
                                   **{k: rep.get(k) for k in ("id", "centred", "stabilized", "steady", "held", "view")}})
                    print(rep.get("id"), steady, rep.get("stabilized"), flush=True)
    s, cols = args.size, args.cols
    n = len(cells[0])
    rows_n = -(-n // cols)
    sheet = Image.new("RGB", (cols * s, 2 * rows_n * (s + 16) + 40), (16, 16, 16))
    d = ImageDraw.Draw(sheet)
    for b, steady in enumerate(cells):
        top = b * rows_n * (s + 16) + 20 * (b + 1)
        d.text((4, top - 16), f"Auto center, {'stabilization off (SPICE only)' if not steady else f'stabilization on ({steady} frames)'}",
               fill=(255, 255, 255))
        for i, (im, u, k, rep) in enumerate(cells[steady]):
            x, y = (i % cols) * s, top + (i // cols) * (s + 16)
            if im is not None:
                sheet.paste(im.convert("RGB").resize((s, s)), (x, y))
            shift = (rep.get("stabilized") or {}).get("shift")
            label = f"{u['key'][0][:8]} {rep.get('id', '')[1:11]}" + (f" {shift[0]:+.0f},{shift[1]:+.0f}" if shift else "")
            d.text((x + 2, y + s + 2), label, fill=(220, 220, 140))
    sheet.save(args.out, quality=90)
    with open(os.path.splitext(args.out)[0] + ".json", "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
