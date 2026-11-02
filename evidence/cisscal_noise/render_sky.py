# Before/after evidence for the "twohzsky" step: each frame calibrated by the pipeline (calibration.calibrate) with the
# 2 Hz noise measured from the overclocked pixels only (twohzsky off, CISSCAL's default) and from the frame's own sky
# (on), dark, flat and hot pixel repair off in both; and with no 2 Hz step at all. Drawn on the pipeline's own
# single-picture scale (picture_scale + display) and stretched hard on the sky (its 1st..99th percentile).
# usage (repo root, CASSINI_DATA = a lean archive): render_sky.py OUTDIR ID ...
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)


def tag(img, text):
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    for color, width in (((0, 0, 0), 3), ((255, 255, 255), 1)):
        cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, width, cv2.LINE_AA)
    return img


def bands(x):
    """line to line spread of each line's middle 80% mean, after a 31-line running mean is taken off (the bands)"""
    m = np.sort(x, axis=1)[:, 100:-100].mean(axis=1)
    return float(np.std(m - np.convolve(m, np.ones(31) / 31, mode="same"))[None][0])


for fid in sys.argv[2:]:
    path = f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.LBL"
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    with cal.stepping("dark,flat,hotpix,twohz"):
        none = cal.calibrate(codes, info)
    with cal.stepping("dark,flat,hotpix,twohzsky"):
        before = cal.calibrate(codes, info)
    with cal.stepping("dark,flat,hotpix"):
        after = cal.calibrate(codes, info)
    blacks, white, _ = cal.picture_scale([after.astype(np.float32)])
    show = lambda x: cal.display(x.astype(np.float32), blacks[0], white, 2.2, cal.SHOULDER)  # noqa: E731
    sky = cal._sky([after.astype(np.float32)])
    vals = after[sky] if sky.mean() > 0.05 else after.ravel()
    lo, hi = np.percentile(vals, [1, 99])
    hard = lambda x: np.clip((x - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)  # noqa: E731
    used = "sky" if not np.array_equal(before, after) else "overclocks (no dark sky)"
    b0, b1, b2 = (bands(x) / (hi - lo) * 100 for x in (none, before, after))
    row1 = np.hstack([tag(show(none), f"{fid} no 2 Hz step"), tag(show(before), "overclocks (CISSCAL default)"),
                      tag(show(after), f"after: {used}")])
    row2 = np.hstack([tag(hard(none), f"sky stretched, bands {b0:.1f}"), tag(hard(before), f"bands {b1:.1f}"),
                      tag(hard(after), f"bands {b2:.1f}")])
    cv2.imwrite(os.path.join(out, f"{fid}_sky_bands.jpg"), np.vstack([row1, row2]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(fid, info.get("DATA_CONVERSION_TYPE"), info.get("GAIN_MODE_ID"), "| method", used,
          "| bands (percent of the sky stretch): none %.2f, overclocks %.2f, after %.2f" % (b0, b1, b2))
