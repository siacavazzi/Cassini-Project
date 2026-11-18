"""Sky smoothing leaves a lit body alone (calibration.SKY_LINE; pipeline audit finding 12). smooth_sky's
glow part took each line's median as the sky: on a line mostly across Saturn that is the body, so the limb, cloud
belts and ring edges were smoothed as faint glow over 16 px, a second darker limb about 10 px inside Saturn's
(N1469611288_1, lit pixels moved up to 6% of white). Now no lit pixel there moves over 2% of white, while the dark
sky is still smoothed; on a ring frame whose lines cross the rings (N1737251394_1) the lit rings moved go from 10% to
under 4% (the rest is faint ringlets near the sky's level, smoothed as glow as before). The faint sky beside the limb is not lifted either (the slope guard on every frame, 11-17). Fails on the code before it.
Real frames: needs the archive (CASSINI_DATA and the rest, as the frame server). Run: python web/test_sky_limb.py"""
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

for fid, most in (("N1469611288_1", 0.001), ("N1737251394_1", 0.04)):
    lbl = lh.label("nac_data/" + fid + ".png", as_png=True)
    info = lbl.get_info()
    png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    gray = cv2.cvtColor(lbl.resize_image(), cv2.COLOR_BGR2GRAY)
    with cal.stepping("skysmooth"):
        off = cal.calibrate(png, info, gray, smooth=True).astype(np.float32)
    on = cal.calibrate(png, info, gray, smooth=True).astype(np.float32)
    top = float(np.percentile(off, 99))
    lit = off > 0.5 * top
    moved = float((np.abs(on - off)[lit] / top > 0.02).mean())
    dark = off < np.percentile(off, 1) + 0.02 * top
    grain = lambda v: float((v - cv2.GaussianBlur(v, (0, 0), 3))[dark].std())
    print(fid, "lit pixels moved over 2%% of white: %.2f%%" % (100 * moved), " sky grain %.3g -> %.3g" % (grain(off), grain(on)))
    assert moved < most, moved
    # nor lifts the faint sky beside it (the slope guard, SKY_GLOW_MOVE, on every frame): the limb's soft edge spread
    # 16 px out lifted the sky 10 px past Saturn's limb from 0.04 to 0.11 of white, a grainy halo past a dark gap (Sam,
    # 11-17)
    faint = off < 0.2 * top
    lifted = float(np.percentile((on - off)[faint] / top, 99.99))
    print(fid, "faint sky lifted by the smoothing (99.99th percentile): %.3f of white" % lifted)
    if fid == "N1469611288_1":
        assert lifted < 0.02, lifted
    assert grain(on) < grain(off)
print("ok")
