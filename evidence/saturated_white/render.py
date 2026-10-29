# Before/after evidence for saturated pixels drawn white in mosaics and movies (stacking.load_hdr's clipped, drawn
# white by calibration.load_channels on a pass's shared scale): the finished mosaic of each mosaic pass below, and
# movie frames of the movie passes, made by the pipeline (obs_mosaic: every tile through color_image.processed_frame),
# with the frame server's environment (CASSINI_DATA, CASSINI_KERNELS, CASSINI_GEOMETRY_CACHE, CASSINI_CISSCAL).
# Run it once in a checkout of the code before and once in one of the code after, each with its own scratch cache
# (never the served one), then --compose puts the two side by side; --probe (either checkout) prints, for every frame
# below, how much of it the camera saturated (raw codes at the top) and how much stays clipped once its exposures are
# merged, so a blown subject can be told apart from a white point that is too low (calibration, not this change):
#   python evidence/saturated_white/render.py --cache CACHE_BEFORE --out OUT --tag before
#   python evidence/saturated_white/render.py --cache CACHE_AFTER --out OUT --tag after
#   python evidence/saturated_white/render.py --out OUT --compose
#   python evidence/saturated_white/render.py --out OUT --probe
import argparse
import json
import os
import sys
import time

REPO = os.getcwd()
sys.path.insert(0, os.path.join(REPO, "web", "frames"))
sys.path.insert(0, REPO)

# (name, a frame of the pass, or an observation id to look up, kind) from the round-2 spot check
PASSES = [("enceladus_250EN_ENCELSPOL001", "N1858933183_1", "mosaic"),
          ("sun_212SA_STORMW010_W", "W1803106757_1", "mosaic"),
          ("00CIA_DUSTSEAR001", "ISS_00CIA_DUSTSEAR001", "mosaic"),
          ("saturn_2004_spokes_W", "W1479406901_1", "movie"),
          ("rhea_N1547735221", "N1547735221_1", "movie"),
          ("dione_N1549197117", "N1549197117_1", "movie"),
          ("saturn_ring_N1833759933", "N1833759933_1", "movie"),
          ("enceladus_N1746104469", "N1746104469_1", "movie")]
MOVIE_FRAMES = 4   # frames of each movie pass drawn, spread over it

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--cache")
ap.add_argument("--tag")
ap.add_argument("--compose", action="store_true")
ap.add_argument("--probe", action="store_true")
ap.add_argument("--only", default="", help="comma separated names")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
todo = [p for p in PASSES if not a.only or p[0] in a.only.split(",")]


def unit(om, ref):
    if "_" in ref and not ref.startswith("ISS_"):
        found = om.unit_of(ref)
        return found[0] if found else None
    idx, rows = om._observations()
    for (target, obs, inst), _ in rows.items():
        if obs.startswith(ref):
            us = om.units(target, obs, "N" if inst == "ISSNA" else "W")
            if us:
                return max(us, key=lambda u: len(u["frames"]))
    return None


if a.probe:
    import numpy as np
    import calibration as cal
    import stacking
    import obs_mosaic as om
    rows = []
    for name, ref, kind in todo:
        u = unit(om, ref)
        if u is None:
            print(name, "no pass", flush=True)
            continue
        frames = u["frames"]
        pick = frames if kind == "mosaic" else [frames[int(i * (len(frames) - 1) / (MOVIE_FRAMES - 1))] for i in range(MOVIE_FRAMES)]
        for path, fid, f, *_ in pick:
            lbl = stacking.lh.label(path, as_png=True)
            got = stacking.load_hdr(path, u.get("repeat_gap", 120), clipped=True)
            raw = cal.saturated_of(lbl, got[1].shape) if got[1] is not None else None
            row = {"pass": name, "id": fid, "filter": f, "exposure": lbl.get_info().get("EXPOSURE_DURATION"),
                   "merged": got[2], "raw_saturated": None if raw is None else round(float(raw.mean()), 4),
                   "clipped": None if got[3] is None else round(float(got[3].mean()), 4)}
            if got[1] is not None:
                row["iof_p50_p99_max"] = [round(float(v), 4) for v in np.percentile(got[1], (50, 99, 100))]
            rows.append(row)
            print(json.dumps(row), flush=True)
    with open(os.path.join(a.out, "probe.json"), "w") as fh:
        json.dump(rows, fh, indent=1)
elif not a.compose:
    import obs_mosaic as om
    for name, ref, kind in todo:
        t0 = time.time()
        u = unit(om, ref)
        if u is None:
            print(name, "no pass", flush=True)
            continue
        info = {"pass": list(u["key"]), "kind": u.get("kind"), "tiles": len(u["frames"])}
        if kind == "mosaic":
            for n in range(len(u["frames"])):
                om.tile(u, n, a.cache)
            last = u["frames"][-1][1]
            made = om.mosaic_webp(last, "full", a.cache, fmt="png", ahead=0, force=True)
            if made is None or made[0] is None:
                print(name, "no mosaic", flush=True)
                continue
            with open(os.path.join(a.out, f"{name}_{a.tag}.png"), "wb") as fh:
                fh.write(made[0])
            info.update(last=last, behind=made[1].get("behind"))
        else:
            from PIL import Image
            frames = u["frames"]
            picks = sorted({int(i * (len(frames) - 1) / (MOVIE_FRAMES - 1)) for i in range(MOVIE_FRAMES)})
            pics = []
            for n in picks:
                image, rep = om.movie_frame(u, n, a.cache)
                if image is not None:
                    pics.append(image.convert("RGB"))
            if not pics:
                print(name, "no movie frames", flush=True)
                continue
            strip = Image.new("RGB", (sum(p.width for p in pics) + 8 * (len(pics) - 1), max(p.height for p in pics)))
            x = 0
            for p in pics:
                strip.paste(p, (x, 0))
                x += p.width + 8
            strip.save(os.path.join(a.out, f"{name}_{a.tag}.png"))
            info.update(frames=[frames[n][1] for n in picks])
        info["seconds"] = round(time.time() - t0)
        with open(os.path.join(a.out, f"{name}_{a.tag}.json"), "w") as fh:
            json.dump(info, fh)
        print(name, a.tag, info, flush=True)
else:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default()
    for name, _, _ in todo:
        pics = [os.path.join(a.out, f"{name}_{t}.png") for t in ("before", "after")]
        if not all(os.path.exists(p) for p in pics):
            continue
        ims = [Image.open(p).convert("RGB") for p in pics]
        infos = [json.load(open(p[:-4] + ".json")) for p in pics]
        vertical = ims[0].width > 1.5 * ims[0].height   # movie strips go one above the other
        if vertical:
            sheet = Image.new("RGB", (max(i.width for i in ims), sum(i.height + 28 for i in ims) + 16), "black")
        else:
            sheet = Image.new("RGB", (sum(i.width for i in ims) + 16, max(i.height for i in ims) + 28), "black")
        x = y = 0
        for im, info, t in zip(ims, infos, ("before", "after")):
            ImageDraw.Draw(sheet).text((x + 8, y + 8), f"{t}: {name}, {info['tiles']} frames", fill="white", font=font)
            sheet.paste(im, (x, y + 28))
            if vertical:
                y += im.height + 28 + 16
            else:
                x += im.width + 16
        sheet.save(os.path.join(a.out, f"{name}_before_after.png"))
        print("wrote", f"{name}_before_after.png")
