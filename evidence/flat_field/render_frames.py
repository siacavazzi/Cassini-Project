# Before/after evidence for the flat field step: each frame calibrated by the pipeline (stacking.load_hdr, the path
# mosaics, movies and reels take: repeats merged, calibration.calibrate) with the "flat" step off and on, drawn on one
# stretch, beside its high-pass (the frame over its 20 px blur, +-4%) where rings and columns stand out, plus a 3x crop
# round the ground-calibration dust ring (sample 887, line 388). Run from the repo root with CASSINI_DATA and
# CASSINI_CISSCAL set.
# usage: render_frames.py OUTDIR ID[:name] ...
import os
import sys
import numpy as np
import cv2
sys.path.insert(0, os.getcwd())
import calibration as cal  # noqa: E402
import flat_field as ff  # noqa: E402
import stacking  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)


def load(fid):
    path = f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.png"
    lbl, iof, n = stacking.load_hdr(path, 120)
    return lbl, np.asarray(iof, np.float64), n


def label(img, text):
    img = img.copy()
    cv2.putText(img, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
    return img


for arg in sys.argv[2:]:
    fid, _, name = arg.partition(":")
    name = name or fid
    with cal.stepping("flat"):
        lbl, before, n = load(fid)
    _, after, _ = load(fid)
    info = lbl.get_info()
    lit = after > np.percentile(after, 40)
    lo, hi = np.percentile(after[lit], [0.5, 99.8])
    lo = min(lo, np.percentile(after, 2))

    def show(x):
        return np.clip((x - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)

    def high(x):
        hp = x / np.maximum(cv2.GaussianBlur(x, (0, 0), 20), 1e-12)
        return np.clip((hp - 0.96) / 0.08 * 255, 0, 255).astype(np.uint8)

    size = 512
    scale = before.shape[0] / 1024
    cx, cy = int(887 * scale), int(388 * scale)
    r = int(64 * scale)

    def crop(x):
        c = x[max(cy - r, 0):cy + r, max(cx - r, 0):cx + r]
        return cv2.resize(c, (size // 2, size // 2), interpolation=cv2.INTER_NEAREST)

    rows = []
    for tag, x in (("before (no flat field)", before), ("after (flat field)", after)):
        s, h = show(x), high(x)
        rows.append(np.hstack([label(cv2.resize(s, (size, size), interpolation=cv2.INTER_AREA), tag),
                               label(cv2.resize(h, (size, size), interpolation=cv2.INTER_AREA), "high-pass +-4%"),
                               np.vstack([label(crop(s), "ring 887,388"), crop(h)])]))
    sheet = np.vstack(rows)
    title = (f"{fid}  {info.get('IMAGE_TIME', '')[:17]}  {info.get('FILTER_NAME', '')}  "
             f"{info.get('INSTRUMENT_MODE_ID', '')}  {n} frame(s)  flat {ff.flat_name(info)}  "
             f"dust {ff.dust_name(info) if info.get('INSTRUMENT_ID') == 'ISSNA' else '-'}")
    bar = np.full((36, sheet.shape[1]), 32, np.uint8)
    cv2.putText(bar, title.replace('"', ""), (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out, f"{name}_before_after.png"), np.vstack([bar, sheet]))
    # how even the lit part is, before and after: the high-pass spread (lower is flatter)
    for tag, x in (("before", before), ("after", after)):
        hp = x / np.maximum(cv2.GaussianBlur(x, (0, 0), 20), 1e-12)
        inner = lit & (cv2.erode(lit.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0)
        print(f"{name} {tag}: high-pass std over the lit disk {np.std(hp[inner]) * 100:.2f}%")
