#!/usr/bin/env python3
"""Evidence for a single picture's own brightness scale (calibration.load_linear and tone: where its black and white
go): each frame through the checkout's own color path (color_image.load_aligned, one frame: repeat exposures stacked,
lost lines filled, calibrated, drawn), and through the same path with another checkout's calibration.py (--old, e.g.
main's), from the same I/F, so the two differ only in how the picture is drawn.

  export  IDS  each frame's raw (as the archive stores it, display stretched), its I/F as load_linear gets it (a
               16-bit PNG and its range, iof.json) and the picture as this checkout draws it, to work on elsewhere
  scan         --n random single frames from Image_index.csv: per frame the drawn picture's percentiles under --old
               and this checkout (scan.tsv), and a small old | new thumbnail of each
  grid    IDS  raw | old | new through the whole of load_aligned under each calibration.py, labeled, one JPEG per
               frame or color set (IDs joined by +, red first) and an index.html

  CASSINI_DATA=... CASSINI_CISSCAL=... python web/frames/tone_evidence.py scan --old /tmp/main_calibration.py --out DIR
"""
import argparse
import csv
import html
import importlib.util
import json
import multiprocessing
import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import data_source as ds  # noqa: E402

FOLDERS = {"N": "nac_data", "W": "wac_data"}
INFO_KEYS = ("PRODUCT_ID", "IMAGE_TIME", "INSTRUMENT_ID", "TARGET_NAME", "FILTER_NAME", "EXPOSURE_DURATION",
             "DATA_CONVERSION_TYPE", "GAIN_MODE_ID", "INSTRUMENT_MODE_ID", "OBSERVATION_ID", "MISSING_LINES")
_old = None


def old_module(path):
    spec = importlib.util.spec_from_file_location("calibration_old", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


"""
One frame through load_aligned with this checkout's calibration, and the same frame's I/F drawn by old (another
calibration module) when given: (label, I/F, new picture, old picture or None, valid mask, report)
"""
def draw(frame_id, old=None):
    seen = {}
    real = cal.load_linear

    def hook(labels, images=None, iofs=None):
        iofs = cal._calibrated(labels, images, iofs)
        seen.update(labels=labels, iofs=iofs)
        return real(labels, images, iofs)

    cal.load_linear = hook
    try:
        imgs, valid, lbl, report = color_image.load_aligned([f"{FOLDERS[frame_id[0]]}/{frame_id}.png"])
    finally:
        cal.load_linear = real
    new = imgs[0][..., 0] if imgs[0].ndim == 3 else imgs[0]
    iof = seen["iofs"][0] if seen.get("iofs") else None
    before = None
    if old is not None and iof is not None:
        linear = old.load_linear(seen["labels"], None, seen["iofs"])
        if linear is not None:
            before = old.tone(*linear)[0][..., 0]
    return lbl, iof, new, before, valid, report


def info_of(lbl):
    info = lbl.get_info()
    return {k: str(info.get(k, "")) for k in INFO_KEYS}


def stats(picture, valid):
    v = picture[valid] if valid is not None and valid.any() else picture.ravel()
    p = np.percentile(v, (1, 5, 10, 50, 90, 99))
    return {"p1": int(p[0]), "p5": int(p[1]), "p10": int(p[2]), "p50": int(p[3]), "p90": int(p[4]), "p99": int(p[5]),
            "white": round(float((v >= 250).mean()), 4), "black": round(float((v <= 5).mean()), 4)}


def export(ids, out):
    os.makedirs(out, exist_ok=True)
    for frame_id in ids:
        try:
            lbl, iof, new, _, valid, report = draw(frame_id)
        except Exception as e:
            print(f"{frame_id}: {e}")
            continue
        base = os.path.join(out, frame_id)
        cv2.imwrite(base + ".raw.png", lbl.resize_image())
        cv2.imwrite(base + ".new.png", new)
        cv2.imwrite(base + ".valid.png", valid.astype(np.uint8) * 255)
        meta = {"info": info_of(lbl), "report": report}
        if iof is not None:
            lo, hi = float(iof.min()), float(iof.max())
            q = np.round((iof - lo) / max(hi - lo, 1e-30) * 65535).astype(np.uint16)
            cv2.imwrite(base + ".iof.png", q)
            codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
            meta.update(lo=lo, hi=hi, saturated=round(float(cal.saturated(codes, lbl.get_info()).mean()), 4))
        with open(base + ".json", "w") as f:
            json.dump(meta, f, indent=1)
        print(frame_id, "ok" if iof is not None else "not calibrated")


def _init(old_path):
    global _old
    os.nice(19)
    _old = old_module(old_path)


def thumb(picture, valid, side=160):
    g = np.where(valid, picture, 128).astype(np.uint8) if valid is not None else picture
    return cv2.resize(g, (side, side), interpolation=cv2.INTER_AREA)


def _scan_one(args):
    frame_id, out = args
    try:
        lbl, iof, new, before, valid, report = draw(frame_id, _old)
    except Exception as e:
        return {"id": frame_id, "error": str(e)[:100]}
    row = {"id": frame_id, **{k.lower(): v for k, v in info_of(lbl).items() if k != "PRODUCT_ID"}}
    if iof is None or before is None:
        row["error"] = "not calibrated"
        return row
    sky = cal._sky([iof.astype(np.float32)])
    row.update(sky=round(float(sky.mean()), 3))
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    row.update(saturated=round(float(cal.saturated(codes, lbl.get_info()).mean()), 4))
    for name, picture in (("old", before), ("new", new)):
        row.update({f"{name}_{k}": v for k, v in stats(picture, valid).items()})
    row["changed"] = round(float(np.mean(np.abs(new.astype(np.int16) - before)[valid])) if valid.any() else 0, 2)
    cv2.imwrite(os.path.join(out, "thumbs", frame_id + ".jpg"),
                np.hstack([thumb(before, valid), thumb(new, valid)]), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return row


def scan(n, seed, old_path, out, workers):
    os.makedirs(os.path.join(out, "thumbs"), exist_ok=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Image_index.csv")) as f:
        ids = [os.path.basename(r["path"]).split(".")[0] for r in csv.DictReader(f)]
    ids = random.Random(seed).sample(sorted(set(ids)), n)
    rows = []
    with multiprocessing.Pool(workers, _init, (old_path,)) as pool:
        for i, row in enumerate(pool.imap_unordered(_scan_one, [(i, out) for i in ids], chunksize=4)):
            rows.append(row)
            if i % 200 == 0:
                print(f"{i}/{n}", flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(out, "scan.tsv"), "w") as f:
        w = csv.DictWriter(f, keys, delimiter="\t")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["id"]))


def label(picture, text):
    p = cv2.cvtColor(picture, cv2.COLOR_GRAY2BGR) if picture.ndim == 2 else picture.copy()
    cv2.putText(p, text, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(p, text, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 220, 255), 2, cv2.LINE_AA)
    return p


"""
A frame (ID) or a color set (IDs joined by +, red first) through the whole of load_aligned with module as its
calibration (main's calibration.py has no draw_saturated: it did not have that step): (BGR picture, valid, labels)
"""
def aligned(spec, module):
    keep = color_image.cal
    color_image.cal = module
    if not hasattr(module, "draw_saturated"):
        module.draw_saturated = lambda labels, channels, margin: 0.0
    try:
        ids = spec.split("+")
        imgs, valid, _, report = color_image.load_aligned([f"{FOLDERS[i[0]]}/{i}.png" for i in ids])
    finally:
        color_image.cal = keep
    chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
    if len(chans) == 2:
        chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
    picture = chans[0] if len(chans) == 1 else np.dstack(chans[::-1])
    return picture, valid, report


def flat(picture, valid, side):
    p = np.where(valid[..., None] if picture.ndim == 3 else valid, picture, 128).astype(np.uint8)
    return cv2.resize(p, (side, side), interpolation=cv2.INTER_AREA)


def grid(ids, old_path, out, side):
    os.makedirs(out, exist_ok=True)
    old = old_module(old_path)
    rows = []
    for spec in ids:
        try:
            before, valid_before, _ = aligned(spec, old)
            after, valid, report = aligned(spec, cal)
        except Exception as e:
            print(f"{spec}: {e}")
            continue
        lbls = [color_image.lh.label(f"{FOLDERS[i[0]]}/{i}.png", as_png=True) for i in spec.split("+")]
        raws = [lbl.resize_image() for lbl in lbls]
        raws = [r[..., 0] if r.ndim == 3 else r for r in raws]
        raw = raws[0] if len(raws) == 1 else np.dstack(raws[::-1]) if len(raws) == 3 else raws[0]
        cells = [label(cv2.resize(raw, (side, side), interpolation=cv2.INTER_AREA), "raw"),
                 label(flat(before, valid_before, side), "today"), label(flat(after, valid, side), "fixed")]
        name = spec.replace("+", "_")
        cv2.imwrite(os.path.join(out, name + ".jpg"), np.hstack(cells), [cv2.IMWRITE_JPEG_QUALITY, 88])
        info = info_of(lbls[0])
        filters = " ".join(info_of(lbl)["FILTER_NAME"] for lbl in lbls)
        rows.append((name, info["IMAGE_TIME"], info["TARGET_NAME"], filters, report.get("saturated")))
        print(spec, "ok")
    with open(os.path.join(out, "index.tsv"), "w") as f:
        f.write("file\ttime\ttarget\tfilters\tsaturated\n")
        for row in rows:
            f.write("\t".join([row[0] + ".jpg"] + [str(v if v is not None else "") for v in row[1:]]) + "\n")
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write("<!doctype html><meta charset=utf-8><title>Tone grid</title><body style='background:#777;font:14px sans-serif'>")
        for name, t, target, filters, _ in rows:
            f.write(f"<p>{html.escape(name)} {html.escape(t)} {html.escape(target)} {html.escape(filters)}<br>"
                    f"<img src='{name}.jpg' style='max-width:100%'></p>")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("export", "scan", "grid"))
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--out", required=True)
    ap.add_argument("--old", help="another checkout's calibration.py, drawn from the same I/F (scan, grid)")
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--side", type=int, default=512, help="grid: each picture's side, px")
    a = ap.parse_intermixed_args()
    if a.what == "export":
        export(a.ids, a.out)
    elif a.what == "scan":
        scan(a.n, a.seed, a.old, a.out, a.workers)
    else:
        grid(a.ids, a.old, a.out, a.side)


if __name__ == "__main__":
    main()
