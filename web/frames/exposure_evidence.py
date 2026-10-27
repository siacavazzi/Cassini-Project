#!/usr/bin/env python3
"""Before/after evidence for exposure normalization of movie passes (obs_mosaic.exposure_gains): each pass played as
a movie twice through the checkout's own movie_frame, both stabilized the same way (--steady), before with each frame
as the pass's display scale draws it (exposure 0) and after with its exposure evened out over --smooth frames, side by
side in one MP4 clip; how much the picture's brightness jumps from one frame to the next in each (the mean linear
brightness of the lit picture, |log| of the ratio, as a percentage: median and largest); the gains given; and how long
the pass's brightness chain took to work out (exposure_chain: what it adds to a pass the first time and to a remake).
Written with an index.html, for the live site's static folder. Needs ffmpeg.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/exposure_evidence.py --cache DIR --out OUT TARGET:OBSERVATION_ID:CAM[:pass] ...
"""
import argparse
import html
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=640, help="each side of the clip, px")
    ap.add_argument("--max", type=int, default=150, help="most frames per pass (from its start)")
    ap.add_argument("--fps", type=int, default=6)
    ap.add_argument("--smooth", type=int, default=8, help="exposure smoothing, frames")
    ap.add_argument("--steady", type=int, default=12, help="stabilization smoothing on both sides, frames (0: SPICE's)")
    ap.add_argument("passes", nargs="+")
    args = ap.parse_args()
    import numpy as np
    from PIL import Image, ImageDraw
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
            n = min(len(u["frames"]), args.max)
            print(name, len(u["frames"]), "frames,", u.get("kind"), flush=True)
            if u.get("kind") == "mosaic_movie":
                print("  a mosaic movie: not played as movie frames", flush=True)
                continue
            p = om.plan(u, args.cache)
            gamma = p["display_scale"].get("gamma", 2.2)
            for j in range(len(u["frames"])):
                om.tile(u, j, args.cache, p["display_scale"])
            began = time.time()
            om.exposure_chain(u, args.cache, p)
            took = time.time() - began
            gains = om.exposure_gains(u, args.cache, p, args.smooth)
            g = list(gains.values()) or [1.0]
            print(f"  chain {took:.1f} s over {len(gains)} tiles; gains {min(g):.2f}..{max(g):.2f}, "
                  f"{sum(abs(x - 1) > 0.05 for x in g)} frames changed by more than 5%", flush=True)
            frames_dir = os.path.join(args.out, name + "_frames")
            os.makedirs(frames_dir, exist_ok=True)
            last, jumps = {}, {"before": [], "after": []}
            for j in range(n):
                sides = []
                for side, exposure in (("before", 0), ("after", args.smooth)):
                    im, rep = om.movie_frame(u, j, args.cache, steady=om.steady_of(u, args.steady), exposure=exposure)
                    pic = np.zeros((args.size, args.size, 4), np.uint8)
                    if im is not None:
                        im.thumbnail((args.size, args.size), Image.LANCZOS)
                        a = np.asarray(im)
                        pic[:a.shape[0], :a.shape[1]] = a
                        lit = calibration.decode(a[..., :3].max(axis=2)[a[..., 3] > 0] / 255, gamma)
                        b = float(lit.mean()) if lit.size else 0.0
                        if side in last and last[side] > 0 and b > 0:
                            jumps[side].append(abs(np.log(b / last[side])) * 100)
                        last[side] = b
                    sides.append(pic)
                canvas = Image.new("RGB", (2 * args.size + 8, args.size + 28), (12, 12, 14))
                for i, (side, pic) in enumerate(zip(("Before: one scale for the pass",
                                                     f"After: exposure evened out ({args.smooth} frames)"), sides)):
                    canvas.paste(Image.fromarray(pic[..., :3]), (i * (args.size + 8), 28))
                    ImageDraw.Draw(canvas).text((i * (args.size + 8) + 6, 8), f"{side}  {j + 1}/{n}", fill=(220, 220, 220))
                canvas.save(os.path.join(frames_dir, f"{j:04d}.png"))
                if j % 20 == 0:
                    print(" ", j, flush=True)
            clip = f"{name}_exposure_before_after.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps), "-i",
                            os.path.join(frames_dir, "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", os.path.join(args.out, clip)], check=True)
            stats = {"chain_s": round(took, 1), "tiles": len(gains), "gain_min": round(min(g), 3), "gain_max": round(max(g), 3),
                     "changed_over_5pct": sum(abs(x - 1) > 0.05 for x in g)}
            stats.update({side: {"median_pct": round(float(np.median(v)), 1) if v else None,
                                 "max_pct": round(float(np.max(v)), 1) if v else None, "pairs": len(v)}
                          for side, v in jumps.items()})
            print(" ", json.dumps(stats), flush=True)
            rows.append((name, n, clip, stats))
    json.dump({r[0]: r[3] for r in rows}, open(os.path.join(args.out, "exposure.json"), "w"), indent=1)
    with open(os.path.join(args.out, "index.html"), "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Movie exposure</title>"
                 "<style>body{background:#0c0c0e;color:#ddd;font:14px -apple-system,sans-serif;margin:16px}video{max-width:100%}"
                 "</style><h1>Movie passes, exposure evened out</h1><p>Left: every frame on the pass's one brightness scale "
                 "(before). Right: each frame's brightness measured against the frame of its filter before it, single flashes "
                 "brought to their neighbours and jumps spread over the smoothing (after). Both stabilized the same way. "
                 "Jump is how much the picture's brightness changes from one frame to the next.</p>")
        for name, n, clip, st in rows:
            fh.write(f"<h2>{html.escape(name)} · first {n} frames</h2><video src='{clip}' controls loop muted playsinline></video>"
                     f"<p>Brightness jump between frames, median / largest: before {st['before']['median_pct']}% / "
                     f"{st['before']['max_pct']}%, after {st['after']['median_pct']}% / {st['after']['max_pct']}%. Gains "
                     f"{st['gain_min']} to {st['gain_max']}; {st['changed_over_5pct']} of {st['tiles']} frames changed by more "
                     f"than 5%. Working it out took {st['chain_s']} s.</p>")


if __name__ == "__main__":
    main()
