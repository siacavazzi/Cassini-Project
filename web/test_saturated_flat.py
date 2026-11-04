"""A frame the camera saturated all over (every pixel at the top of its 12 bit range or of the 8 bit table) is saturated
all over by calibration.saturated, also when it is asked about the frame's display picture: the display stretch has no
range to spread a flat frame over and draws it black, so the display picture marked none of it. 080EN PLMHINCL001's
82-220 s WAC frames near the Sun (W1597131507_1: 4095 DN everywhere) went into its mosaic as flat tiles in the flat
field's pattern (stacking.load_hdr asks with the display picture) instead of being left out (obs_mosaic.SATURATED_ALL).
Run: python web/test_saturated_flat.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402

ds.lut8 = lambda: True
TOP = int(np.argmax(cal.LUT >= 4095))   # the first 8-bit code the 12-bit table puts at 4095 DN


def check(conversion, top):
    info = {"DATA_CONVERSION_TYPE": conversion}
    flat = np.full((64, 64), top, np.uint8)
    shown = cal.display_stretch(flat, info)
    assert shown.max() == 0, "the display stretch draws a flat frame black"
    assert cal.saturated(flat, info).all(), conversion
    assert cal.saturated(flat, info, shown).all(), f"{conversion}: a flat saturated frame's display picture is saturated"
    # one pixel below the top: the rest stays saturated on the codes, the display picture marks its top pixels
    mixed = flat.copy()
    mixed[0, 0] = top - 40
    shown = cal.display_stretch(mixed, info)
    assert cal.saturated(mixed, info, shown).mean() > 0.99, conversion
    # a flat frame below the top is not saturated
    low = np.full((64, 64), top - 40, np.uint8)
    assert not cal.saturated(low, info, cal.display_stretch(low, info)).any(), conversion


check("12BIT", TOP)
check("TABLE", 255)
print("ok")
