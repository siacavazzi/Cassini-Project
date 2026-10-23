"""
How far a displayed picture shows what it should hide: sky noise, 8-bit banding and scan lines, in output
levels, for a before/after pair of the same picture (PNG or JPG, same size). Used to check that the balanced
look never shows more of these than the classic one.

  python evidence/color_display/metrics.py BEFORE.png AFTER.png [more pairs ...]   -> one JSON line per pair

sky      pixels dark in both pictures (luminance under 12% of the before's 99.5th percentile, eroded 3 px)
body     pixels bright in both (over 25%), where the local gradient is gentle (a smooth slope)
noise    the sky's standard deviation after taking out a 9 px median, per channel, highest channel
banding  over the body's smooth slopes: the share of levels between its 5th and 95th percentile luminance
         that no pixel has (steps the stretch spread apart), and the mean step between used levels
scanline the ripple of row means after taking out a 31-row moving average (lines across the frame), over
         sky and body, in levels; also for columns
worse    the metrics where after exceeds before by more than 10% plus 0.3 levels (or 0.03 for banding gaps)
"""
import json
import sys

import cv2
import numpy as np


def load(path):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im.ndim == 2:
        im = np.dstack([im] * 3)
    alpha = im[..., 3] > 0 if im.shape[2] == 4 else np.ones(im.shape[:2], bool)
    return im[..., :3].astype(np.float32), alpha


def ripple(lum, mask, axis):
    vals = np.where(mask, lum, np.nan)
    with np.errstate(all="ignore"):
        means = np.nanmean(vals, axis=1 - axis)
    ok = ~np.isnan(means)
    if ok.sum() < 64:
        return None
    m = means[ok]
    smooth = np.convolve(np.pad(m, 15, mode="edge"), np.ones(31) / 31, mode="valid")
    return float(np.std(m - smooth))


def measure(im, sky, body, smooth):
    lum = im.mean(axis=2)
    out = {}
    if sky.sum() > 500:
        out["noise"] = max(float(np.std((im[..., c] - cv2.medianBlur(im[..., c].astype(np.uint8), 9))[sky])) for c in range(3))
    if smooth.sum() > 500:
        v = np.round(lum[smooth]).astype(int)
        lo, hi = np.percentile(v, 5), np.percentile(v, 95)
        used = np.unique(v[(v >= lo) & (v <= hi)])
        span = int(hi - lo) + 1
        out["banding_gaps"] = round(1 - len(used) / span, 3) if span > 4 else 0.0
        out["banding_step"] = round(float(np.diff(used).mean()), 2) if len(used) > 1 else 0.0
    for name, axis in (("scanline_rows", 0), ("scanline_cols", 1)):
        r = ripple(lum, sky | body, axis)
        if r is not None:
            out[name] = round(r, 3)
    return out


def pair(before_path, after_path):
    b, ab = load(before_path)
    a, aa = load(after_path)
    if a.shape != b.shape:
        a = cv2.resize(a, (b.shape[1], b.shape[0]), interpolation=cv2.INTER_AREA)
        aa = cv2.resize(aa.astype(np.uint8), (b.shape[1], b.shape[0])) > 0
    both = ab & aa
    lb, la = b.mean(axis=2), a.mean(axis=2)
    top_b, top_a = np.percentile(lb[both], 99.5), np.percentile(la[both], 99.5)
    kernel = np.ones((7, 7), np.uint8)
    sky = cv2.erode(((lb < 0.12 * top_b) & (la < 0.12 * top_a) & both).astype(np.uint8), kernel) > 0
    body = cv2.erode(((lb > 0.25 * top_b) & (la > 0.25 * top_a) & both).astype(np.uint8), kernel) > 0
    grad = np.hypot(cv2.Sobel(cv2.GaussianBlur(lb, (0, 0), 3), cv2.CV_32F, 1, 0), cv2.Sobel(cv2.GaussianBlur(lb, (0, 0), 3), cv2.CV_32F, 0, 1))
    smooth = body & (grad < np.percentile(grad[body], 40)) if body.sum() > 500 else body
    mb, ma = measure(b, sky, body, smooth), measure(a, sky, body, smooth)
    worse = []
    for k in mb:
        if k in ma:
            slack = 0.03 if k == "banding_gaps" else 0.3
            if ma[k] > mb[k] * 1.1 + slack:
                worse.append(k)
    return {"before": before_path, "after": after_path, "sky_px": int(sky.sum()), "body_px": int(body.sum()),
            "classic": mb, "balanced": ma, "worse": worse}


if __name__ == "__main__":
    args = sys.argv[1:]
    for b, a in zip(args[::2], args[1::2]):
        print(json.dumps(pair(b, a)))
