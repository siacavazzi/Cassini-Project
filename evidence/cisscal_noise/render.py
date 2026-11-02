# Before/after evidence for the "twohz" and "pairs" steps: each frame calibrated by the pipeline (calibration.calibrate)
# with both steps off and on (dark, flat and hot pixels off in both, so only these two steps differ), drawn on the
# pipeline's own single-picture scale (picture_scale + display), and a second pair stretched hard on the sky
# (its 1st..99th percentile) where the bands show. Run from the repo root with CASSINI_DATA set to a lean archive.
# usage: render.py OUTDIR ID ...
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
import calibration as cal  # noqa: E402
import cisscal_noise as cn  # noqa: E402
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)


def tag(img, text):
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    for color, width in (((0, 0, 0), 3), ((255, 255, 255), 1)):
        cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, width, cv2.LINE_AA)
    return img


for fid in sys.argv[2:]:
    path = f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.LBL"
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    with cal.stepping("dark,flat,hotpix,twohz,pairs"):
        before = cal.calibrate(codes, info)
    with cal.stepping("dark,flat,hotpix"):
        after = cal.calibrate(codes, info)
    blacks, white, _ = cal.picture_scale([after.astype(np.float32)])
    show = lambda x: cal.display(x.astype(np.float32), blacks[0], white, 2.2, cal.SHOULDER)  # noqa: E731
    sky = cal._sky([after.astype(np.float32)])
    vals = after[sky] if sky.mean() > 0.05 else after.ravel()
    lo, hi = np.percentile(vals, [1, 99])
    hard = lambda x: np.clip((x - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)  # noqa: E731
    got = cal.overclock_avg(info)
    hum = cn.two_hz(info, *got) if got is not None else None
    note = f"2 Hz {'p-p %.1f DN' % np.ptp(hum) if hum is not None else 'not applied'}"
    row1 = np.hstack([tag(show(before), f"{fid} before"), tag(show(after), f"after ({note})")])
    row2 = np.hstack([tag(hard(before), "sky stretched: before"), tag(hard(after), "sky stretched: after")])
    cv2.imwrite(os.path.join(out, f"{fid}_before_after.png"), np.vstack([row1, row2]))
    diff = np.abs(after - before) > 0
    print(fid, note, "pixels changed", int(diff.sum()))
