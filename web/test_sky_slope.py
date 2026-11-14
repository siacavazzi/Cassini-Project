"""Sky smoothing's slope guard (calibration.SKY_SLOPE_BODIES, SKY_GLOW_MOVE): a Titan crescent's terminator is not
pulled down to the edge of the glow smoothing. On the 2017-04-24 crescent's RED frame (ISS_271TI_CLOUD001,
N1871765587_1) the stored codes rise smoothly across the terminator, but smooth_sky drew the slope below them up to
its cutoff, so the calibrated I/F jumped from 0.028 to 0.041 within a few pixels, a hard dark line along the
terminator once the filters were put together (Sam, 11-14). With the guard it follows the codes; with it off (or on
a frame of another body) the smoothing is as before. Fails on the code before it (the jump).
Real frame: needs the archive (CASSINI_DATA and the rest, as the frame server). Run: python web/test_sky_slope.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import frame_server  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import label_handler as lh  # noqa: E402

if not os.environ.get("CASSINI_DATA"):
    print("skipped: no CASSINI_DATA")
    sys.exit(0)

lbl = lh.label("nac_data/N1871765587_1.png", as_png=True)
assert cal._value(lbl.get_info(), "TARGET_NAME") == "TITAN"


def column(**off):
    with cal.slope_guard(off.get("guard", True)):
        iof = cal._calibrated([lbl], [lbl.resize_image()])[0]
    return iof[806:834, 246].astype(np.float64)


guarded, before = column(), column(guard=False)
with cal.stepping("skysmooth"):
    raw = column()
steps = lambda v: np.diff(v[::2])
print("I/F x1000, every 2nd row across the terminator:\n guarded", (guarded[::2] * 1e3).round(1),
      "\n before ", (before[::2] * 1e3).round(1), "\n no smoothing", (raw[::2] * 1e3).round(1))
assert steps(before).max() > 0.008                        # the old smoothing's jump (0.028 -> 0.041)
assert steps(guarded).max() < 0.006                       # gone: the slope rises as the codes do
assert np.abs(guarded - raw).max() < 0.002                # ... about as calibrated without smoothing there
assert cal.slope_guarded([lbl]) and not cal.slope_guarded([lh.label("nac_data/N1872033073_1.png", as_png=True)])
print("ok")
