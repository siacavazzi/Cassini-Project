#!/usr/bin/env python3
"""Before/after movie frames for fix plan group D (2026-10-29), drawn by the repo's own movie maker
(obs_mosaic.movie_frame, as the windows' movie pictures are) from the code at CASSINI_REPO into a cache of its own.

  render:  CASSINI_REPO=<checkout> CASSINI_DATA=... CASSINI_KERNELS=... CASSINI_GEOMETRY_CACHE=... CASSINI_CISSCAL=... \\
           python clips.py render --cache <scratch cache> --out <dir>/<tag> --exposure 0|8 [--only NAME ...]
  compose: python clips.py compose --before <dir>/before --after <dir>/after --out <web folder>

render writes <out>/<pass name>/<n>.png (512 px) and frames.json (each frame's id, filter, time and report);
compose puts the two side by side, labelled, as an MP4 per pass (ffmpeg), a contact sheet PNG of the frames the
fix changes most, and an index.html."""
import argparse
import json
import os
import sys

# (name, observation, camera, a frame in the pass or None for its longest movie pass, why)
PASSES = [
    ("pallene-pumping", "ISS_139PL_PALENCLOS001_PIE", "PALLENE", "N", "N1665944384_1",
     "Brightness pumping in a faint pass (exposure normalization on by default)"),
    ("rings-strobe", "ISS_213RI_EG150PHAS001_VIMS", "SATURN", "W", "W1805641731_1",
     "Exposure strobe: every second frame shorter and black"),
    ("rings-partial", "ISS_137RI_BMOVIE003_PRIME", "SATURN", "N", "N1662236009_2",
     "Partial downlinks (_2 frames that lost most of their lines) held"),
    ("jupiter-black", "ISS_C23JU_18ATM2X2A013_PRIME", "JUPITER", "W", None, "Black CL1/CL2 frames in a lit Jupiter pass"),
    ("jupiter-white", "ISS_C23JU_6ATM2X2A043_PRIME", "JUPITER", "W", None, "Jupiter small in the frame, clipped white"),
    ("titan-nearwhite", "ISS_00ATI_HIRES002_VIMS", "TITAN", "N", "N1477496427_2",
     "Titan N1477496427_2 (the known near-white case) with exposure normalization on"),
]
MAX_FRAMES = 140


def render(args):
    repo = os.environ["CASSINI_REPO"]
    sys.path[:0] = [os.path.join(repo, "web", "frames"), repo]
    import numpy as np  # noqa: F401
    import calibration
    import obs_mosaic as om
    import reel
    idx, _ = reel.load_index()
    for name, obs, target, cam, fid, why in PASSES:
        if args.only and name not in args.only:
            continue
        if fid and fid not in set(idx["id"]):
            print(f"{name}: {fid} not in the index"); continue
        if fid:
            row = idx[idx["id"] == fid].iloc[0]
            obs, target = row["OBSERVATION_ID"], row["TARGET_NAME"]
        us = om.units(target, obs, cam)
        if fid:
            found = om.unit_of(fid)
            if not found:
                print(f"{name}: {fid} in no pass"); continue
            u = found[0]
        else:
            movies = [v for v in us if v.get("kind") == "movie" or (v.get("movie") and not v["mosaic"])]
            if not movies:
                print(f"{name}: no movie pass in {obs} {cam}"); continue
            u = max(movies, key=lambda v: len(v["frames"]))
        out = os.path.join(args.out, name)
        os.makedirs(out, exist_ok=True)
        frames = []
        n0 = 0
        if fid and len(u["frames"]) > MAX_FRAMES:
            n0 = max(0, min(om.unit_of(fid)[1] - MAX_FRAMES // 2, len(u["frames"]) - MAX_FRAMES))
        with calibration.looking("balanced"):
            for n in range(n0, min(len(u["frames"]), n0 + MAX_FRAMES)):
                path = os.path.join(out, f"{n}.png")
                im, rep = om.movie_frame(u, n, args.cache, colour=True, centre=True, exposure=args.exposure)
                fr = u["frames"][n]
                frames.append({"n": n, "id": fr[1], "filter": fr[2], "t": fr[3], "report": rep})
                if im is not None:
                    im.thumbnail((512, 512))
                    im.save(path)
                print(f"{name} {n} {fr[1]} {'drawn' if im is not None else rep.get('why')}", flush=True)
        json.dump({"name": name, "why": why, "key": [str(k) for k in u["key"]], "frames": frames}, open(os.path.join(out, "frames.json"), "w"))


def compose(args):
    import subprocess
    import numpy as np
    from PIL import Image, ImageDraw
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for name, *_ in PASSES:
        b, a = os.path.join(args.before, name), os.path.join(args.after, name)
        if not (os.path.exists(os.path.join(b, "frames.json")) and os.path.exists(os.path.join(a, "frames.json"))):
            continue
        fb, fa = json.load(open(os.path.join(b, "frames.json"))), json.load(open(os.path.join(a, "frames.json")))
        work = os.path.join(args.out, name)
        os.makedirs(work, exist_ok=True)
        changed = []
        for k, (x, y) in enumerate(zip(fb["frames"], fa["frames"])):
            pics = []
            for d, f in ((b, x), (a, y)):
                p = os.path.join(d, f"{f['n']}.png")
                pics.append(Image.open(p).convert("RGB") if os.path.exists(p) else Image.new("RGB", (512, 512)))
            W, H = max(p.width for p in pics), max(p.height for p in pics)
            sheet = Image.new("RGB", (2 * W + 8, H + 28), (24, 24, 24))
            for i, p in enumerate(pics):
                sheet.paste(p, (i * (W + 8) + (W - p.width) // 2, 28 + (H - p.height) // 2))
            g = ImageDraw.Draw(sheet)
            rep = y["report"]
            note = f"  held: {rep['held']}" if rep.get("held") else ""
            g.text((6, 7), f"before (main, as live)   {x['id']} {x['filter']}", fill=(220, 220, 220))
            g.text((W + 14, 7), f"after (group D){note}", fill=(255, 210, 120) if note else (220, 220, 220))
            sheet.save(os.path.join(work, f"{k:04d}.png"))
            diff = float(np.abs(np.asarray(pics[0].resize((W, H)), float) - np.asarray(pics[1].resize((W, H)), float)).mean())
            changed.append((diff, k))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "4", "-i", os.path.join(work, "%04d.png"),
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20",
                        os.path.join(args.out, f"{name}.mp4")], check=True)
        # the 6 frames the fix changes most, in time order, as one still
        top = sorted(k for _, k in sorted(changed, reverse=True)[:6])
        tiles = [Image.open(os.path.join(work, f"{k:04d}.png")) for k in top]
        if tiles:
            still = Image.new("RGB", (tiles[0].width, sum(t.height for t in tiles)), (0, 0, 0))
            yy = 0
            for t in tiles:
                still.paste(t, (0, yy)); yy += t.height
            still.save(os.path.join(args.out, f"{name}_still.png"))
        rows.append((name, fb.get("why", ""), fb["key"], len(changed), sum(1 for f in fa["frames"] if f["report"].get("held"))))
    html = ["<!doctype html><meta charset=utf-8><title>Movie frames, group D</title>",
            "<style>body{background:#111;color:#ddd;font:14px system-ui;margin:16px}video,img{max-width:100%}h2{font-weight:500}</style>",
            "<h1>Movie frames: brightness, black and partial frames (group D)</h1>",
            "<p>Left: main as live today (Exposure normalization off). Right: this PR (Exposure normalization on at 8, "
            "partial frames held, the small-body white). Drawn by obs_mosaic.movie_frame from the archive.</p>"]
    for name, why, key, count, held in rows:
        html += [f"<h2>{why}</h2><p>{' '.join(key)}: {count} frames, {held} held</p>",
                 f"<video src='{name}.mp4' controls loop muted></video>", f"<p><img src='{name}_still.png'></p>"]
    open(os.path.join(args.out, "index.html"), "w").write("\n".join(html))
    print(f"{len(rows)} passes composed into {args.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("render", "compose"))
    ap.add_argument("--cache")
    ap.add_argument("--out", required=True)
    ap.add_argument("--exposure", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--before")
    ap.add_argument("--after")
    a = ap.parse_args()
    render(a) if a.what == "render" else compose(a)
