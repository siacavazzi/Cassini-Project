"""
Evidence images for the lean archive test.

  evidence/triplet_<n>.png   old dataset PNGs merged as RGB (each with its own stretch)
                             next to the new format calibrated to I/F with one white point
  evidence/dark_<n>.png      a dark crop, old vs new, both with a strong stretch
  evidence/sizes.png         bytes per frame for each format

Usage: python -I scripts/evidence.py <raw_test dir>
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from encode import calibration, parse_label, clean  # noqa: E402

LUT = calibration.LUT
GAMMA = 2.2


def info_of(root, fid):
    raw = parse_label(os.path.join(root, "img", fid + ".LBL"))
    return {k: clean(v) for k, v in raw.items()}


def new_dn(root, fid, info):
    codes = np.array(Image.open(os.path.join(root, "new", fid + ".png")))
    return LUT[codes] if info["DATA_CONVERSION_TYPE"] == "12BIT" else codes.astype(np.float64)


def iof_from_dn(dn, info):
    """calibration.calibrate with the unstretch step replaced by the decoded DN."""
    original = calibration.unstretch
    calibration.unstretch = lambda png, info, image=None: dn
    try:
        return calibration.calibrate(dn, info)
    finally:
        calibration.unstretch = original


def shared_stretch(iofs, sky_fraction=0.1, sky_percentile=98):
    """The black/white/gamma part of calibration.load_channels, on I/F arrays."""
    iofs = [i.astype(np.float32) for i in iofs]
    sky = np.ones(iofs[0].shape, dtype=bool)
    for iof in iofs:
        sky &= iof < 0.05 * np.percentile(iof, 99.9)
    blacks = [0.0] * len(iofs)
    if sky.mean() > sky_fraction:
        blacks = [np.percentile(iof[sky], sky_percentile) for iof in iofs]
    white = max(cv2.medianBlur(iof - b, 3).max() for iof, b in zip(iofs, blacks))
    return [np.clip((iof - b) / white, 0, 1) ** (1 / GAMMA) for iof, b in zip(iofs, blacks)], blacks, white


def label(img, text):
    img = img.copy()
    cv2.putText(img, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def to8(x):
    return (np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)


def main(root):
    seq = json.load(open(os.path.join(root, "sequence.json")))
    ids = [r["FILE_NAME"].replace(".IMG", "") for r in seq]
    order = {"RED": 0, "GRN": 1, "BL1": 2}
    triplets = []
    for i in range(0, len(ids) - 2, 3):
        group = ids[i:i + 3]
        infos = [info_of(root, f) for f in group]
        keys = [next(k for k in order if k in inf["FILTER_NAME"]) for inf in infos]
        if sorted(keys) == ["BL1", "GRN", "RED"]:
            triplets.append(sorted(zip(keys, group, infos), key=lambda t: order[t[0]]))
    out = os.path.join(root, "evidence")
    os.makedirs(out, exist_ok=True)
    notes = {"triplets": [], "old_pipeline_calibrates": 0, "frames": 0}

    for n, trip in enumerate(triplets):
        fids = [t[1] for t in trip]
        infos = [t[2] for t in trip]
        old = [np.array(Image.open(os.path.join(root, "old_png", f + ".png"))) for f in fids]
        for png, inf in zip(old, infos):
            notes["frames"] += 1
            if calibration.calibrate(png, inf) is not None:
                notes["old_pipeline_calibrates"] += 1
        old_rgb = np.dstack(old)  # R, G, B
        iofs = [iof_from_dn(new_dn(root, f, inf), inf) for f, inf in zip(fids, infos)]
        chans, blacks, white = shared_stretch(iofs)
        new_rgb = np.dstack([to8(c) for c in chans])
        # channel balance: median I/F of the brightest 5% of pixels, relative to green
        lit = iofs[1] > np.percentile(iofs[1], 95)
        balance = [float(np.median(i[lit]) / np.median(iofs[1][lit])) for i in iofs]
        old_balance = [float(np.median(o[lit]) / np.median(old[1][lit])) for o in old]
        notes["triplets"].append(dict(frames=fids, white_iof=float(white), blacks=[float(b) for b in blacks],
                                      new_rgb_ratio=balance, old_rgb_ratio=old_balance))
        pair = np.hstack([label(cv2.resize(old_rgb, (768, 768), interpolation=cv2.INTER_AREA), "dataset PNGs (per-frame stretch)"),
                          np.full((768, 8, 3), 255, np.uint8),
                          label(cv2.resize(new_rgb, (768, 768), interpolation=cv2.INTER_AREA), "new 8-bit LUT -> I/F, shared white")])
        Image.fromarray(pair).save(os.path.join(out, f"triplet_{n:02d}_{fids[0]}.png"), optimize=True)

        # dark crop: the 256x256 window with the lowest median green signal that still
        # has some structure (not pure sky), strongly stretched in both versions
        g = iofs[1]
        best = None
        for y in range(0, 1024 - 256 + 1, 64):
            for x in range(0, 1024 - 256 + 1, 64):
                w = g[y:y + 256, x:x + 256]
                med, spread = np.median(w), np.percentile(w, 95) - np.percentile(w, 5)
                if spread > 0.02 * np.percentile(g, 99) and (best is None or med < best[0]):
                    best = (med, y, x)
        _, y, x = best
        crop = (slice(y, y + 256), slice(x, x + 256))

        def strong(stack):
            stack = stack.astype(np.float64)
            lo, hi = np.percentile(stack, 1), np.percentile(stack, 99)
            return to8(np.clip((stack - lo) / max(hi - lo, 1e-12), 0, 1) ** 0.5)
        old_crop = strong(old_rgb[crop])
        new_crop = strong(np.dstack([i[crop] for i in iofs]))
        # nearest-neighbour upscale so the 8-bit levels stay visible
        up = lambda a: cv2.resize(a, (512, 512), interpolation=cv2.INTER_NEAREST)
        dark = np.hstack([label(up(old_crop), "old, stretched"), np.full((512, 8, 3), 255, np.uint8),
                          label(up(new_crop), "new, stretched")])
        Image.fromarray(dark).save(os.path.join(out, f"dark_{n:02d}_{fids[0]}_y{y}x{x}.png"), optimize=True)
        notes["triplets"][-1].update(dark_crop=[y, x],
                                     old_crop_levels=[int(len(np.unique(o[crop]))) for o in old],
                                     new_crop_levels=[int(len(np.unique(np.array(Image.open(os.path.join(root, "new", f + ".png")))[crop]))) for f in fids])
        print(n, fids, "balance new", np.round(balance, 3), "old", np.round(old_balance, 3), "crop", y, x, flush=True)

    json.dump(notes, open(os.path.join(root, "evidence_notes.json"), "w"), indent=1)
    sizes_chart(root, out)


def sizes_chart(root, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    m = json.load(open(os.path.join(root, "metrics.json")))
    n = len(m)
    rows = [
        ("Raw IMG + LBL (PDS)", sum(r["size_img"] + r["size_lbl"] for r in m)),
        ("16-bit PNG, raw DN (lossless)", sum(r["size_png16"] for r in m)),
        ("Current dataset PNG (stretched)", sum(r["size_old_png"] for r in m)),
        ("New: 8-bit LUT PNG + prefix.gz", sum(r["size_new_png"] + r["size_prefix_gz"] for r in m)),
    ]
    labels = [r[0] for r in rows]
    kb = [r[1] / n / 1000 for r in rows]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    colors = ["#9aa3ad"] * 3 + ["#2f6db5"]
    ax.barh(labels[::-1], kb[::-1], color=colors[::-1], height=0.55)
    for i, v in enumerate(kb[::-1]):
        ax.text(v + 15, i, f"{v:,.0f} KB", va="center", fontsize=9, color="#333")
    ax.set_xlabel(f"Mean size per frame (KB), {n} NAC 1024x1024 12BIT frames")
    ax.set_xlim(0, max(kb) * 1.18)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#e5e5e5")
    ax.set_axisbelow(True)
    ax.set_title("Archive size by format (ISS_123RI_PHOTDARK002_PRIME)", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "sizes.png"))


if __name__ == "__main__":
    main(sys.argv[1])
