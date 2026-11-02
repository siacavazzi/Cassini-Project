# Before/after evidence for the dark current step following CISSCAL 4.1 (dark_current.py): each frame calibrated by
# the pipeline (calibration.calibrate) with the dark step as it was (OLD, a copy of main's dark_current.py) and as it
# is now, flat field and hot pixel repair off in both so only the dark differs; drawn on the pipeline's own
# single-picture scale (picture_scale + display), a second pair stretched hard on the sky (its 1st..99th percentile),
# and the dark each took out, line by line. Run from the repo root with CASSINI_DATA and CASSINI_CISSCAL set.
# usage: render.py OLD_DARK_CURRENT_PY OUTDIR ID ...
import importlib.util
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
import calibration as cal  # noqa: E402
import dark_current as new  # noqa: E402
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402

spec = importlib.util.spec_from_file_location("dark_current_old", sys.argv[1])
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
out = sys.argv[2]
os.makedirs(out, exist_ok=True)


def tag(img, text):
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    for color, width in (((0, 0, 0), 3), ((255, 255, 255), 1)):
        cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, width, cv2.LINE_AA)
    return img


def plot(a, b, size):
    """the mean dark of each line, old (gray) and new (white), on one scale"""
    img = np.zeros((size // 3, size, 3), np.uint8)
    top = max(1e-6, float(max(np.nanmax(a), np.nanmax(b)) if a is not None else np.nanmax(b)))
    for curve, color in ((a, (128, 128, 128)), (b, (255, 255, 255))):
        if curve is None:
            continue
        y = (img.shape[0] - 40) * (1 - curve / top) + 35
        x = np.linspace(0, size - 1, len(curve))
        cv2.polylines(img, [np.stack([x, y], 1).astype(np.int32)], False, color, 2)
    return img


for fid in sys.argv[3:]:
    path = f"{'nac_data' if fid[0] == 'N' else 'wac_data'}/{fid}.LBL"
    lbl = lh.label(path, as_png=True)
    info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    with cal.stepping("flat,hotpix"):
        after = cal.calibrate(codes, info)
        cal.dc = old
        try:
            before = cal.calibrate(codes, info)
        finally:
            cal.dc = new
    blacks, white, _ = cal.picture_scale([after.astype(np.float32)])
    show = lambda x: cal.display(x.astype(np.float32), blacks[0], white, 2.2, cal.SHOULDER)  # noqa: E731
    sky = cal._sky([after.astype(np.float32)])
    vals = after[sky] if sky.mean() > 0.05 else after.ravel()
    lo, hi = np.percentile(vals, [1, 99])
    hard = lambda x: np.clip((x - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)  # noqa: E731
    d_old, d_new = old.dark_dn(info), new.dark_dn(info)
    m_old = None if d_old is None else d_old.mean(axis=1)
    m_new = None if d_new is None else d_new.mean(axis=1)
    note_old = "no dark" if d_old is None else f"dark {np.median(d_old):.1f} DN"
    note_new = "no dark" if d_new is None else f"dark {np.median(d_new):.1f} DN"
    size = before.shape[1]
    row1 = np.hstack([tag(show(before), f"{fid} before ({note_old})"), tag(show(after), f"after ({note_new})")])
    row2 = np.hstack([tag(hard(before), "sky stretched: before"), tag(hard(after), "sky stretched: after")])
    row3 = tag(cv2.resize(plot(m_old, m_new, size), (2 * size, 2 * size // 3)),
               "dark per line, top to bottom of the frame: before gray, after white")
    cv2.imwrite(os.path.join(out, f"{fid}_dark_before_after.png"), np.vstack([row1, row2, row3]))
    r = new.readout(info)
    print(fid, info.get("INSTRUMENT_MODE_ID"), info.get("INST_CMPRS_TYPE"), info.get("INSTRUMENT_DATA_RATE"),
          info.get("EXPOSURE_DURATION"), "|", note_old, "->", note_new,
          "| max change %.1f DN" % (np.nanmax(np.abs((d_new if d_new is not None else 0) - (d_old if d_old is not None else 0)))))
