#!/usr/bin/env python3
"""Every stage of one mosaic, saved from the pipeline's own calls, for the explainer animation (animate.py).

Nothing is re-implemented: each picture is what a repo function returned. Where a stage has no file of its own (the
colour steps inside obs_mosaic.so_far), the real function is wrapped so its return value is saved while so_far runs.

  python capture.py FRAME_ID OUT --cache DIR [--part raw,frames,chain,grow,variants] [--hero ID ...]

FRAME_ID: any frame of the mosaic pass (W1884003566_6: the Farewell to Saturn mosaic, 13 September 2017).
Run it in a checkout's root with the pipeline's usual environment (CASSINI_DATA, CASSINI_KERNELS, ...) and a private
cache, through the machine's job limiter. Parts:
  raw       every frame's archive codes (label_handler export, data_source.imread)
  frames    every frame alone through color_image.processed_frame (cleaned, calibrated, north up)
  chain     the hero frames through processed_frame with the pipeline's steps turned on one at a time
            (calibration.stepping), so each step's effect is a picture
  grow      obs_mosaic.so_far after each tile (the mosaic as it grows) and obs_mosaic.tile_map (the outlines)
  set       one pointing's colour frames (--set, red first) through processed_frame, with and without registration
  variants  the whole mosaic with alignment / blending / levelling off (calibration.stepping), and the finished one
            with the colour steps inside so_far saved as they return
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ARGV_CWD = os.getcwd()
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "web", "frames")]
os.chdir(ROOT)

import numpy as np   # noqa: E402
import cv2   # noqa: E402
from PIL import Image   # noqa: E402
import frame_server   # noqa: E402,F401  (first: it sets the paths the pipeline reads from)
import obs_mosaic as om   # noqa: E402
import calibration as cal   # noqa: E402
import color_image as ci   # noqa: E402
import label_handler as lh   # noqa: E402
import data_source as ds   # noqa: E402

# the single-frame steps in the order they are shown, each with the switches it turns on (calibration's order, then
# the repeat exposures merged, then the lens correction: geom alone on an unmerged short exposure clips its limb)
CHAIN = [("fill", ["fill"]), ("calibrate", ["calibrate"]), ("twohz", ["twohz", "twohzsky"]), ("dark", ["dark", "darksky"]),
         ("pairs", ["pairs"]), ("flat", ["flat"]), ("hotpix", ["hotpix"]), ("skysmooth", ["skysmooth"]), ("stack", ["stack", "hdr"]),
         ("geom", ["geom"])]
FRAME_STEPS = [s for _, group in CHAIN for s in group]
T0 = time.time()


def say(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def save(a, path):
    a = np.asarray(a)
    if a.dtype == np.uint8 and (a.ndim == 2 or a.shape[-1] in (3, 4)):
        Image.fromarray(a).save(path + ".png")
    else:
        np.save(path + ".npy", a)


def path_of(fid):
    return ("nac_data/" if fid[0] == "N" else "wac_data/") + fid + ".png"


def bgra(im):
    """processed_frame's picture is blue, green, red, alpha: as RGBA."""
    return cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA) if im.ndim == 3 and im.shape[2] == 4 else im


def part_raw(u, out):
    d = os.path.join(out, "raw"); os.makedirs(d, exist_ok=True)
    meta = {}
    for fr in u["frames"]:
        fid = fr[1]
        lbl = lh.label(path_of(fid), as_png=True); info = lbl.get_info()
        Image.fromarray(ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)).save(f"{d}/{fid}.png")
        meta[fid] = {k: str(info.get(k)) for k in ("FILTER_NAME", "EXPOSURE_DURATION", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID",
                                                   "IMAGE_TIME", "TARGET_NAME", "MISSING_LINES", "DATA_CONVERSION_TYPE")}
    json.dump(meta, open(f"{d}/meta.json", "w"), indent=1)
    say("raw", len(meta))


def part_frames(u, out):
    d = os.path.join(out, "frames"); os.makedirs(d, exist_ok=True)
    for fr in u["frames"]:
        fid = fr[1]
        if os.path.exists(f"{d}/{fid}.png"):
            continue
        im, _, rep = ci.processed_frame([path_of(fid)], hdr=True)
        Image.fromarray(bgra(im)).save(f"{d}/{fid}.png")
        say("frame", fid, fr[2], im.shape)


def part_chain(heroes, out):
    d = os.path.join(out, "chain"); os.makedirs(d, exist_ok=True)
    for fid in heroes:
        for old in os.listdir(d):   # (an earlier run's pictures of this frame, whose names follow the step order)
            if old.startswith(fid + "__"):
                os.remove(os.path.join(d, old))
        rows, on, last = [], [], None
        for name, group in [("as_taken", [])] + CHAIN:
            on += group
            off = [s for s in FRAME_STEPS if s not in on]
            with cal.stepping(off):
                im, _, rep = ci.processed_frame([path_of(fid)], hdr=True)
            im = bgra(im)
            change = None if last is None or last.shape != im.shape else float(np.abs(im[..., :3].astype(int) - last[..., :3]).mean())
            Image.fromarray(im).save(f"{d}/{fid}__{len(rows):02d}_{name}.png")
            rows.append({"step": name, "on": list(on), "change": change, "shape": list(im.shape),
                         "report": {k: v for k, v in rep.items() if isinstance(v, (int, float, str, bool, type(None)))}})
            last = im
            say("chain", fid, name, change)
        json.dump(rows, open(f"{d}/{fid}.json", "w"), indent=1)


def part_grow(u, cache, out):
    d = os.path.join(out, "grow"); os.makedirs(d, exist_ok=True)
    rows = []
    for n in range(len(u["frames"])):
        made = om.layout(u, n, cache)
        im, rep = om.so_far(u, n, cache, made) if made else (None, None)
        if im is not None:
            im.save(f"{d}/{n:03d}.png")
        rows.append({"n": n, "id": u["frames"][n][1], "filter": u["frames"][n][2], "t": u["frames"][n][3],
                     "name": made[5] if made else None, "report": rep})
        say("grow", n, made[5] if made else None)
    last = u["frames"][-1][1]
    json.dump(rows, open(f"{d}/grow.json", "w"), indent=1, default=str)
    json.dump(om.tile_map(last, cache), open(f"{d}/tile_map.json", "w"), indent=1, default=str)
    made = om.layout(u, len(u["frames"]) - 1, cache)
    p, tiles, rect = made[:3]
    keep = ("n", "id", "filter", "t", "offset", "spice_place", "native_offset", "box", "outline", "turn", "why", "lost", "stacked")
    json.dump({"rect": rect, "k": p.get("k"), "count": made[3], "used": made[4], "name": made[5], "plan": p,
               "tiles": [{k: t[k] for k in keep if k in t} for t in tiles]},
              open(f"{out}/layout.json", "w"), indent=1, default=str)


def part_set(ids, out):
    """one pointing's colour set through processed_frame: the filters laid over each other as taken, then registered"""
    d = os.path.join(out, "set"); os.makedirs(d, exist_ok=True)
    for name, off in (("unaligned", ["align"]), ("aligned", [])):
        with cal.stepping(off):
            im, _, rep = ci.processed_frame([path_of(i) for i in ids], hdr=True)
        Image.fromarray(bgra(im)).save(f"{d}/{name}.png")
        say("set", name, im.shape)
    json.dump({"ids": ids}, open(f"{d}/set.json", "w"))


TRACED = ("filter_mosaic", "colour_picture", "unmixed", "over_grey", "ring_white", "detail")


def traced(d):
    """om's colour steps wrapped so each one's return is saved as so_far calls it; returns the undo."""
    real, calls = {}, []

    def wrap(name):
        fn = getattr(om, name)

        def inner(*a, **kw):
            got = fn(*a, **kw)
            label = name + ("_" + str(a[2]).replace("/", "-") if name == "filter_mosaic" else "")
            calls.append(label)
            save(got, f"{d}/{len(calls):02d}_{label}")
            say("  traced", label, getattr(got, "shape", None))
            return got
        real[name] = fn
        setattr(om, name, inner)
    for name in TRACED:
        wrap(name)

    def undo():
        for name, fn in real.items():
            setattr(om, name, fn)
        json.dump(calls, open(f"{d}/calls.json", "w"))
    return undo


def part_variants(u, cache, out):
    d = os.path.join(out, "variants"); os.makedirs(d, exist_ok=True)
    n = len(u["frames"]) - 1
    report = {}
    for name, off in (("spice_only", ["panels", "surface", "blend", "level"]), ("aligned", ["blend", "level"]),
                      ("blended", ["level"]), ("final", [])):
        om._last_canvas.made = None
        undo = None
        if name == "final":
            os.makedirs(f"{d}/final_steps", exist_ok=True)
            undo = traced(f"{d}/final_steps")
        try:
            with cal.stepping(off):
                made = om.layout(u, n, cache)
                im, rep = om.so_far(u, n, cache, made, out=om.CANVAS)
        finally:
            if undo:
                undo()
        im.save(f"{d}/{name}.png")
        moved = {t["n"]: [t["offset"][0] - t["spice_place"][0], t["offset"][1] - t["spice_place"][1]] for t in made[1] if "spice_place" in t}
        report[name] = {"off": off, "layout": made[5], "size": list(im.size), "report": rep, "moved": moved}
        say("variant", name, made[5], im.size, len(moved), "tiles moved")
        json.dump(report, open(f"{d}/variants.json", "w"), indent=1, default=str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame"); ap.add_argument("out"); ap.add_argument("--cache", required=True)
    ap.add_argument("--part", default="raw,frames,chain,grow,variants"); ap.add_argument("--hero", nargs="*", default=[])
    ap.add_argument("--set", nargs="*", default=[], help="one pointing's colour frames, red first")
    a = ap.parse_args()
    out, cache = (os.path.join(ARGV_CWD, os.path.expanduser(v)) for v in (a.out, a.cache))
    os.makedirs(out, exist_ok=True)
    u, _ = om.unit_of(a.frame)
    say(u["key"], len(u["frames"]), "frames", u.get("kind"))
    json.dump({"key": u["key"], "kind": u.get("kind"), "frames": [list(f[1:4]) for f in u["frames"]],
               "commit": os.popen("git rev-parse HEAD").read().strip()}, open(f"{out}/unit.json", "w"), indent=1, default=str)
    parts = a.part.split(",")
    with cal.looking("balanced"):
        if "raw" in parts:
            part_raw(u, out)
        if "grow" in parts:
            part_grow(u, cache, out)
        if "variants" in parts:
            part_variants(u, cache, out)
        if "chain" in parts:
            part_chain(a.hero or [u["frames"][len(u["frames"]) // 2][1]], out)
        if "set" in parts and a.set:
            part_set(a.set, out)
        if "frames" in parts:
            part_frames(u, out)
    say("done")


if __name__ == "__main__":
    main()
