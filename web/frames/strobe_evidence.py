#!/usr/bin/env python3
"""Before/after evidence for movie strobing, pumping and panel flicker (web/test_movie_strobe.py): each pass, named by
one of its frames, drawn frame by frame as the windows play it by default (movies: movie_frame at 512 px, colour,
Auto center, exposure normalization 8; mosaic movies: rolling_webp, one lap), once with the code before and once with
the code after, each into its own cache; then the two side by side.

    # from each worktree (--code: that worktree's obs_mosaic), into its own cache and folder
    python web/frames/strobe_evidence.py draw --code WT_BEFORE --cache C1 --out out/before IDS...
    python web/frames/strobe_evidence.py draw --code WT_AFTER --cache C2 --out out/after IDS...
    # side by side: MP4 per pass, a sheet of its frames, and how much the picture jumps frame to frame
    python web/frames/strobe_evidence.py compare out/before out/after out/compare

Run draw with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE), from the
worktree root (Image_index.csv). Never point --cache at the served cache. compare needs ffmpeg.
"""
import io
import json
import math
import os
import subprocess
import sys

if "--code" in sys.argv:
    sys.path.insert(0, os.path.join(os.path.abspath(os.path.expanduser(sys.argv[sys.argv.index("--code") + 1])), "web", "frames"))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SIZE = 512


def draw(args):
    import obs_mosaic as om
    from PIL import Image
    for fid in args.ids:
        found = om.unit_of(fid)
        if not found:
            print(fid, "in no pass")
            continue
        u, _ = found
        kind = om.kind_of(fid).get("kind")
        there = os.path.join(args.out, fid)
        os.makedirs(there, exist_ok=True)
        rows = []
        for n, fr in enumerate(u["frames"][:args.max]):
            rep = {}
            try:
                if kind == "mosaic_movie":
                    data, rep = om.rolling_webp(fr[1], SIZE, args.cache, 1, wait=True)
                    im = Image.open(io.BytesIO(data)).convert("RGBA") if data else None
                else:
                    im, rep = om.movie_frame(u, n, args.cache, 0, True, SIZE, True, 0, om.EXPOSURE_SMOOTH)
            except Exception as e:
                im, rep = None, {"error": repr(e)[:200]}
            if im is not None:
                im.save(os.path.join(there, f"{n:04d}.png"))
            rows.append({"n": n, "id": fr[1], "filter": fr[2], "held": rep.get("held"), "gain": (rep.get("exposure") or {}).get("gain"),
                         "error": rep.get("error"), "drawn": im is not None})
            print(fid, n, rows[-1])
        with open(os.path.join(there, "frames.json"), "w") as fh:
            json.dump({"kind": kind, "key": list(u["key"]), "frames": rows}, fh)


def level(path):
    """The mean linear brightness of the picture's lit pixels (alpha), and the share of it that is lit."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64)
    lit = a[..., 3] > 0
    if not lit.any():
        return 0.0, 0.0
    v = (a[..., :3].mean(axis=2)[lit] / 255) ** 2.2
    return float(v.mean()), float(lit.mean())


def jumps(series):
    """|log| steps of brightness from frame to frame, per cent: (median, largest, how many over 25%)."""
    steps = [abs(math.log(max(b, 1e-4) / max(a, 1e-4))) * 100 for a, b in zip(series, series[1:])]
    if not steps:
        return 0, 0, 0
    steps.sort()
    return round(steps[len(steps) // 2], 1), round(steps[-1], 1), sum(s > 25 for s in steps)


def compare(before, after, out):
    from PIL import Image, ImageDraw
    os.makedirs(out, exist_ok=True)
    summary = []
    for fid in sorted(os.listdir(after)):
        a_dir, b_dir = os.path.join(before, fid), os.path.join(after, fid)
        if not os.path.isdir(a_dir) or not os.path.isdir(b_dir):
            continue
        meta = json.load(open(os.path.join(b_dir, "frames.json")))
        frames_dir = os.path.join(out, fid)
        os.makedirs(frames_dir, exist_ok=True)
        lv = {"before": [], "after": []}
        k = 0
        for row in meta["frames"]:
            name = f"{row['n']:04d}.png"
            pics = []
            for side, d in (("before", a_dir), ("after", b_dir)):
                p = os.path.join(d, name)
                if os.path.exists(p):
                    lv[side].append(level(p)[0])
                    pics.append(Image.open(p).convert("RGBA"))
                else:
                    pics.append(None)
            if all(q is None for q in pics):
                continue
            canvas = Image.new("RGB", (2 * SIZE, SIZE + 28), (8, 8, 10))
            d = ImageDraw.Draw(canvas)
            for i, (q, side) in enumerate(zip(pics, ("before", "after"))):
                if q is not None:
                    bg = Image.new("RGB", q.size, (0, 0, 0))
                    bg.paste(q, mask=q.split()[3])
                    canvas.paste(bg, (i * SIZE + (SIZE - q.width) // 2, 28 + (SIZE - q.height) // 2))
                d.text((i * SIZE + 8, 8), f"{side.upper()}  #{row['n']} {row['id']} {row['filter']}"
                       + (f"  held {row['held']}" if side == "after" and row.get("held") else ""), fill=(230, 230, 230))
            canvas.save(os.path.join(frames_dir, f"{k:04d}.png"))
            k += 1
        mp4 = os.path.join(out, f"{fid}_before_after.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "4", "-i", os.path.join(frames_dir, "%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4], check=False)
        row = {"pass": fid, "key": meta["key"], "kind": meta["kind"], "frames": k,
               "before": jumps(lv["before"]), "after": jumps(lv["after"]),
               "held_after": [r["n"] for r in meta["frames"] if r.get("held")]}
        summary.append(row)
        print(json.dumps(row))
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--code")
    d.add_argument("--cache", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--max", type=int, default=60)
    d.add_argument("ids", nargs="+")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("out")
    args = ap.parse_args()
    if args.cmd == "draw":
        draw(args)
    else:
        compare(args.before, args.after, args.out)


if __name__ == "__main__":
    main()
