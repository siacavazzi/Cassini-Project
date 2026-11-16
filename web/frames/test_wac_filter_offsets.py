#!/usr/bin/env python3
"""Checks that SPICE's offset between a colour set's channels (color_image.spice_offsets) carries the wide-angle
camera's filter offsets (color_image.WAC_FILTER_OFFSETS) and nothing for the narrow-angle camera or a filter the table
lacks: python web/frames/test_wac_filter_offsets.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import color_image as ci  # noqa: E402


class Lbl:
    def __init__(self, camera, filters, loc):
        self.info = {"INSTRUMENT_ID": camera, "FILTER_NAME": filters, "TARGET_NAME": "SATURN"}
        self._loc = loc

    def target_loc(self):
        return self._loc


def offsets(lbls, ref):
    keep = ci._spice_locs
    ci._spice_locs = lambda ls: [l._loc for l in ls]
    try:
        return ci.spice_offsets(lbls, ref)
    finally:
        ci._spice_locs = keep


def close(a, b):
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def test_wac_set_carries_the_filter_offsets():
    r, g, b = (Lbl("ISSWA", f, [10.0, 20.0, 1e6, 0.0]) for f in ('("CL1","RED")', '("CL1","GRN")', '("CL1","BL1")'))
    got = offsets([r, g, b], 1)
    red, blue = ci.WAC_FILTER_OFFSETS[("CL1", "RED")], ci.WAC_FILTER_OFFSETS[("CL1", "BL1")]
    assert close(got[1], (0.0, 0.0))
    assert close(got[0], red) and close(got[2], blue), got
    # the reference's own offset comes off every channel
    got = offsets([r, g, b], 0)
    assert close(got[1], (-red[0], -red[1])) and close(got[2], (blue[0] - red[0], blue[1] - red[1])), got


def test_spice_motion_still_counts():
    a, b = Lbl("ISSWA", "(CB2,CL2)", [0.0, 0.0, 1e6, 0.0]), Lbl("ISSWA", "(MT2,CL2)", [3.0, -4.0, 1e6, 0.0])
    got = offsets([a, b], 0)
    cb2, mt2 = ci.WAC_FILTER_OFFSETS[("CB2", "CL2")], ci.WAC_FILTER_OFFSETS[("MT2", "CL2")]
    assert close(got[1], (-3.0 + mt2[0] - cb2[0], 4.0 + mt2[1] - cb2[1])), got


def test_nac_and_unknown_filters_unchanged():
    n = [Lbl("ISSNA", f, [1.0, 2.0, 1e6, 0.0]) for f in ("(CL1,RED)", "(CL1,GRN)")]
    assert offsets(n, 1) == [(0.0, 0.0), (0.0, 0.0)]
    w = [Lbl("ISSWA", "(CL1,HAL)", [1.0, 2.0, 1e6, 0.0]), Lbl("ISSWA", "(CL1,GRN)", [1.0, 2.0, 1e6, 0.0])]
    assert offsets(w, 1) == [(0.0, 0.0), (0.0, 0.0)]
    # a frame SPICE can't place stays None
    w[0]._loc = None
    assert offsets(w, 1)[0] is None


def test_spice_sure_net_of_the_filters():
    import numpy as np
    import image_correction as ic
    a, b = Lbl("ISSWA", "(CL1,GRN)", [5.0, 5.0, 1e6, 0.0]), Lbl("ISSWA", "(CL1,BL1)", [5.3, 5.2, 1e6, 0.0])
    g = offsets([a, b], 0)[1]
    assert np.hypot(*g) > ic.SPICE_SURE and g.fixed == ci.WAC_FILTER_OFFSETS[("CL1", "BL1")]
    # SPICE says the frames moved 0.4 px: taken as it is, filters and all, as a 0.4 px offset was before
    blank = np.zeros((64, 64), np.float32)
    mask = np.ones((64, 64), bool)
    shift, how = ic.spice_shift(blank, blank, mask, mask, g)
    assert how == "SPICE" and shift == (float(g[0]), float(g[1])), (shift, how)
    # a bare 3.5 px offset is still checked on the frames (here: nothing to check on, so not taken)
    assert ic.spice_shift(blank, blank, mask, mask, (float(g[0]), float(g[1])))[0] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
