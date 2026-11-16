"""Lossy frames' compression blocks smoothed in full from 10 to 1 (calibration.LOSSY_RATIO). At 10.7 to 1 deblock ran
at a third of its strength (full only from 20), leaving 103RI TDIFN45HP001's dim rings (W1613182176_1) in 8 px blocks a
few codes apart, the darkest under the picture's black: ragged dark patches. Measured as the jump across the 8 px
block edges against the jump between pixels inside the blocks, over the frame's dim third (0.61 before, 0.53 now).
Fails on the code before it.
Real frame: needs the archive (CASSINI_DATA and the rest, as the frame server). Run: python web/test_deblock_ratio.py"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import frame_server  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402
import label_handler as lh  # noqa: E402

if not os.environ.get("CASSINI_DATA"):
    print("skipped: no CASSINI_DATA")
    sys.exit(0)

lbl = lh.label("wac_data/W1613182176_1.png", as_png=True)
info = lbl.get_info()
assert 10 < float(cal._value(info, "INST_CMPRS_RATIO")) < 11
png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
v = cal.calibrate(png, info, cv2.cvtColor(lbl.resize_image(), cv2.COLOR_BGR2GRAY), smooth=True).astype(np.float32)
dim = v < np.percentile(v, 30)
dx = np.abs(np.diff(v, axis=1))
edges, inside = dx[:, 7::8], np.delete(dx, np.s_[7::8], axis=1)
ratio = edges[dim[:, 7::8][:, :edges.shape[1]]].mean() / inside[np.delete(dim[:, :-1], np.s_[7::8], axis=1)].mean()
print("block edge jump / inside jump on the dim rings: %.2f" % ratio)
assert ratio < 0.57, ratio
print("ok")
