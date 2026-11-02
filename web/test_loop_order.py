"""The loop check's match between a set's two other channels is tried both ways round (image_correction._loop), so a
channel that matched nothing on its own lands through the other one whatever order the set's frames come in (Dione
c34, N1855916434_1 UV3 + N1855916451_1 GRN + N1855916468_1 IR1: drawn grey in one order, aligned in the other).
A stand-in _match that finds IR1 against UV3 but not UV3 against IR1. Run: python web/test_loop_order.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import image_correction as ic  # noqa: E402

TRUE = {"UV3": (-1.5, 0.2), "GRN": (0.0, 0.0), "IR1": (0.9, -0.1)}   # where each channel is, against GRN


def one_way(im1, im2, g, m1, m2, within=None):
    if (im1, im2) == ("IR1", "UV3"):          # only this way round finds it, as on the real frames
        return (TRUE["UV3"][0] - TRUE["IR1"][0], TRUE["UV3"][1] - TRUE["IR1"][1]), "phase near SPICE"
    if (im1, im2) == ("UV3", "IR1"):
        return None, "not aligned"
    raise AssertionError((im1, im2))


ic._match = one_way
for order in (("IR1", "GRN", "UV3"), ("UV3", "GRN", "IR1")):
    shifts = [TRUE[b] if b == "IR1" else None for b in order]
    hows = ["phase" if b == "IR1" else None for b in order]
    ic._loop(list(order), [None] * 3, 1, shifts, hows, None)
    got = dict(zip(order, shifts))
    print(order, got["UV3"], hows[order.index("UV3")])
    assert got["UV3"] is not None and np.allclose(got["UV3"], TRUE["UV3"]), order
    assert "via the other channel" in hows[order.index("UV3")]
print("ok")
