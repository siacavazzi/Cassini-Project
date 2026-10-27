#!/usr/bin/env python3
"""Before/after evidence for image stabilization of movie passes (obs_mosaic.steady_places): each pass played as a
movie twice through the checkout's own movie_frame, before (steady 0: every tile where SPICE puts it) and after
(stabilized, smoothed over --smooth frames), side by side in one MP4 clip, how far the picture moves from one frame
to the next in each (track_steady_evidence.motion: phase correlation over the part both frames cover; the median and
the largest), how far stabilization moved the tiles from SPICE's places, and how long the pass's stabilization chain
took to work out (steady_chain: what a pass costs the first time, and what remaking pre-built movie frames adds).
Written with an index.html, for the live site's static folder. Needs ffmpeg.

  CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... \\
  python web/frames/stabilize_evidence.py --cache DIR --out OUT TARGET:OBSERVATION_ID:CAM[:pass] ...
"""
import argparse
import html
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)


from track_steady_evidence import motion  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=640, help="each side of the clip, px")
    ap.add_argument("--max", type=int, default=150, help="most frames per pass (from its start)")
    ap.add_argument("--fps", type=int, default=6)
    ap.add_argument("--smooth", type=int, default=12, help="stabilization smoothing, frames")
    ap.add_argument("passes", nargs="+")
    args = ap.parse_args()
    import numpy as np
    from PIL import Image, ImageDraw
    import calibration
    import time
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
            print(name, len(u["frames"]), "frames,", u.get("kind"), "track" if u.get("track") else "", flush=True)
            if u.get("track") or u.get("kind") == "mosaic_movie":
                print("  not a movie pass this stabilizes", flush=True)
                continue
            p = om.plan(u, args.cache)
            for j in range(len(u["frames"])):
                om.tile(u, j, args.cache, p["display_scale"])
            began = time.time()
            chain = om.steady_chain(u, args.cache, p)
            took = time.time() - began
            how = json.load(open(os.path.join(om.folder(u, args.cache), om.STEADY_FILE)))["how"]
            places = om.steady_places(u, args.cache, p, args.smooth)
            moves = [float(np.hypot(*np.subtract(places[j], om.tile(u, j, args.cache, p["display_scale"])["offset"])))
                     for j in places]
            print(f"  chain {took:.1f} s over {len(chain)} tiles; registered {sum(' to ' in h for h in how.values())}, "
                  f"held {sum(h.startswith('held') for h in how.values())}; moved from SPICE median "
                  f"{np.median(moves):.1f} px, largest {np.max(moves):.1f} px", flush=True)
            frames_dir = os.path.join(args.out, name + "_frames")
            os.makedirs(frames_dir, exist_ok=True)
            last, moved, colour = {}, {"before": [], "after": []}, {"before": 0, "after": 0}
            for j in range(n):
                sides = []
                for side, steady in (("before", 0), ("after", args.smooth)):
                    im, rep = om.movie_frame(u, j, args.cache, steady=steady)
                    pic = np.zeros((args.size, args.size, 4), np.uint8)
                    if im is not None:
                        im.thumbnail((args.size, args.size), Image.LANCZOS)
                        a = np.asarray(im)
                        pic[:a.shape[0], :a.shape[1]] = a
                        colour[side] += bool(rep.get("color"))
                        if side in last:
                            m = motion(last[side], pic)
                            if m is not None:
                                moved[side].append(m)
                        last[side] = pic
                    sides.append(pic)
                canvas = Image.new("RGB", (2 * args.size + 8, args.size + 28), (12, 12, 14))
                for i, (side, pic) in enumerate(zip(("Before: SPICE's places", f"After: stabilized ({args.smooth} frames)"), sides)):
                    canvas.paste(Image.fromarray(pic[..., :3]), (i * (args.size + 8), 28))
                    ImageDraw.Draw(canvas).text((i * (args.size + 8) + 6, 8), f"{side}  {j + 1}/{n}", fill=(220, 220, 220))
                canvas.save(os.path.join(frames_dir, f"{j:04d}.png"))
                if j % 20 == 0:
                    print(" ", j, flush=True)
            clip = f"{name}_before_after.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps), "-i",
                            os.path.join(frames_dir, "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", os.path.join(args.out, clip)], check=True)
            stats = {"chain_s": round(took, 1), "tiles": len(chain), "held": sum(h.startswith("held") for h in how.values()),
                     "moved_from_spice_px": {"median": round(float(np.median(moves)), 1), "max": round(float(np.max(moves)), 1)}}
            stats.update({side: {"median_px": round(float(np.median(v)), 1) if v else None,
                            "max_px": round(float(np.max(v)), 1) if v else None, "pairs": len(v), "colour_frames": colour[side]}
                     for side, v in moved.items()})
            print(" ", json.dumps(stats), flush=True)
            rows.append((name, n, clip, stats))
    json.dump({r[0]: r[3] for r in rows}, open(os.path.join(args.out, "motion.json"), "w"), indent=1)
    with open(os.path.join(args.out, "index.html"), "w") as fh:
        fh.write("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Movie stabilization</title>"
                 "<style>body{background:#0c0c0e;color:#ddd;font:14px -apple-system,sans-serif;margin:16px}video{max-width:100%}"
                 "</style><h1>Movie passes, stabilized</h1><p>Left: every frame where SPICE puts it (before). Right: every "
                 "frame registered to the one before it with the pipeline's filter alignment, SPICE's step as the starting "
                 "guess, and held to SPICE over the smoothing (after). Motion is how far the picture moves from one frame to "
                 "the next, in pixels of this clip.</p>")
        for name, n, clip, st in rows:
            fh.write(f"<h2>{html.escape(name)} · first {n} frames</h2><video src='{clip}' controls loop muted playsinline></video>"
                     f"<p>Frame-to-frame motion, median / largest: before {st['before']['median_px']} / {st['before']['max_px']} px, "
                     f"after {st['after']['median_px']} / {st['after']['max_px']} px. Frames in color: before "
                     f"{st['before']['colour_frames']}, after {st['after']['colour_frames']} of {n}. Stabilization moved the frames "
                     f"{st['moved_from_spice_px']['median']} px from SPICE's places (median, full-resolution px), at most "
                     f"{st['moved_from_spice_px']['max']}; working it out took {st['chain_s']} s over {st['tiles']} frames.</p>")


if __name__ == "__main__":
    main()
