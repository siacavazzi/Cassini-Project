#!/usr/bin/env python3
"""
How much a camera window's picture loses to lossy WebP: real frames from the archive, each made the way
frame_server.encode makes it (longest side shrunk to the size with LANCZOS), then saved at several WebP qualities
and compared with the same shrunk picture saved losslessly. Prints bytes and errors per setting, writes
results.csv, summary.json and, for the frames with the most detail, 100% crops side by side (lossless, each
quality, and the difference x8).

  CASSINI_DATA=/Volumes/LaCie/cassini_lut8.zip python web/frames/webp_quality.py --out ~/Documents/webp-quality --n 80
"""
import argparse
import csv
import io
import json
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_server  # noqa: E402

QUALITIES = (80, 90, 95)
SIZES = (512, 1024)


def shrink(im, size):
    im = im.copy()
    if max(im.size) > size:
        im.thumbnail((size, size), Image.LANCZOS)
    return im


def webp(im, **kw):
    buf = io.BytesIO()
    im.save(buf, "WEBP", method=4, **kw)
    data = buf.getvalue()
    return data, np.asarray(Image.open(io.BytesIO(data)).convert("L"), dtype=np.float64)


def psnr(a, b):
    mse = np.mean((a - b) ** 2)
    return 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=80)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    import reel
    idx, _ = reel.load_index()
    random.seed(7)
    ids = random.sample(idx["id"].tolist(), args.n)
    rows, crops = [], []
    for fid in ids:
        try:
            src = Image.open(io.BytesIO(frame_server.archive_png(fid)))
        except Exception as e:
            print(fid, "unreadable", e)
            continue
        src = src.convert("L") if src.mode in ("L", "I", "I;16", "P", "1") else src.convert("RGB")
        if src.mode != "L":
            continue
        for size in SIZES:
            im = shrink(src, size)
            lossless, ref = webp(im, lossless=True, quality=80)
            ref_arr = np.asarray(im, dtype=np.float64)
            # where the body is: pixels clearly above the sky, which carry the detail the eye looks at
            lit = ref_arr > max(20, np.percentile(ref_arr, 50) + 10)
            row = {"id": fid, "size": size, "native": max(src.size), "lit_frac": round(float(lit.mean()), 3), "lossless_bytes": len(lossless)}
            for q in QUALITIES:
                data, got = webp(im, quality=q)
                err = np.abs(got - ref_arr)
                row[f"q{q}_bytes"] = len(data)
                row[f"q{q}_psnr"] = round(psnr(got, ref_arr), 2)
                row[f"q{q}_psnr_lit"] = round(psnr(got[lit], ref_arr[lit]), 2) if lit.sum() > 500 else None
                row[f"q{q}_p99_err"] = float(np.percentile(err, 99))
                row[f"q{q}_max_err"] = float(err.max())
            rows.append(row)
            if size == 1024 and max(src.size) >= 1024:
                crops.append((float(np.std(ref_arr[lit])) * lit.mean() if lit.any() else 0, fid, im))
        print(fid, "done", flush=True)
    with open(os.path.join(args.out, "results.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = {}
    for size in SIZES:
        rs = [r for r in rows if r["size"] == size]
        s = {"frames": len(rs), "lossless_kb_mean": round(np.mean([r["lossless_bytes"] for r in rs]) / 1e3, 1)}
        for q in QUALITIES:
            lit = [r[f"q{q}_psnr_lit"] for r in rs if r[f"q{q}_psnr_lit"] is not None]
            s[f"q{q}"] = {"kb_mean": round(np.mean([r[f"q{q}_bytes"] for r in rs]) / 1e3, 1),
                          "psnr_median": round(float(np.median([r[f"q{q}_psnr"] for r in rs])), 1),
                          "psnr_lit_median": round(float(np.median(lit)), 1) if lit else None,
                          "psnr_lit_worst": round(float(min(lit)), 1) if lit else None,
                          "p99_err_median": float(np.median([r[f"q{q}_p99_err"] for r in rs]))}
        summary[size] = s
    with open(os.path.join(args.out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))
    # 100% crops of the most detailed frames: 320 px around the busiest part, lossless | q80 | q90 | q95 | |q80 - lossless| x8
    for _, fid, im in sorted(crops, key=lambda c: -c[0])[:6]:
        a = np.asarray(im, dtype=np.float64)
        best, at = -1, (0, 0)
        for y in range(0, a.shape[0] - 320, 64):
            for x in range(0, a.shape[1] - 320, 64):
                v = a[y:y + 320, x:x + 320].std()
                if v > best:
                    best, at = v, (x, y)
        box = (at[0], at[1], at[0] + 320, at[1] + 320)
        panels = [("lossless", im.crop(box))]
        for q in QUALITIES:
            panels.append((f"WebP q{q}", Image.open(io.BytesIO(webp(im, quality=q)[0])).convert("L").crop(box)))
        diff = np.clip(np.abs(np.asarray(panels[1][1], dtype=np.float64) - np.asarray(panels[0][1], dtype=np.float64)) * 8, 0, 255)
        panels.append(("q80 error x8", Image.fromarray(diff.astype(np.uint8))))
        sheet = Image.new("L", (len(panels) * 330 + 10, 360), 40)
        d = ImageDraw.Draw(sheet)
        for k, (label, p) in enumerate(panels):
            sheet.paste(p, (10 + k * 330, 30))
            d.text((10 + k * 330, 8), label, fill=230)
        d.text((10, 350 - 2), fid, fill=160)
        sheet.save(os.path.join(args.out, f"crop_{fid}.png"))


if __name__ == "__main__":
    main()
