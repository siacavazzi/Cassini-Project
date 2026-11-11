#!/usr/bin/env python3
"""Checks the two causes of the regression-2017 build's failed items (2026-11-09): python web/frames/test_build_failures.py
(the pointing check needs CASSINI_KERNELS and is skipped without it)."""
import contextlib
import io
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import color_image  # noqa: E402


def test_sliver_tile():
    """A tile whose picture is a 5-row sliver between blank rows (5105 valid pixels, none 3 px inside the picture's
    edge) has no moon on it, and no crash: the chains and movies of JUPITER_ISS_C23JU_6ATM1X1337_PRIME_N_0/_W_0,
    JUPITER_ISS_C23JU_18ATM2X2A013_PRIME_W_6 and ENCELADUS_ISS_286EN_PLUME001_PIE_N_0 stopped on such a tile with an
    IndexError from an empty percentile."""
    rng = np.random.default_rng(1)
    im = np.zeros((30, 1021, 4), np.uint8)
    im[10:15, :, :3] = rng.integers(20, 200, (5, 1021, 1))
    im[10:15, :, 3] = 255
    assert color_image.find_small_body(im, 535, -395, 28.1) is None


def test_small_body_still_found():
    """A lit disk on a full tile is still found where it is."""
    side, r = 400, 20
    y, x = np.mgrid[0:side, 0:side]
    im = np.zeros((side, side, 4), np.uint8)
    im[..., 3] = 255
    im[(x - 230) ** 2 + (y - 170) ** 2 < r * r, :3] = 200
    got = color_image.find_small_body(im, 225, 175, r)
    assert got is not None and abs(got[0] - 230) < 1.5 and abs(got[1] - 170) < 1.5, got


def test_pointing_through_exposure():
    """W1354495588_1 (5 ms): its middle is 0.9 ms before its C-smithed pointing segment, where the reconstructed CK
    turns the camera 91 degrees from Jupiter; placed from the pointing during its exposure, Jupiter sits where it does
    on the frames of the same set (W1354495540_1, W1354495753_1: shifts about -25, -47 px)."""
    if not os.environ.get("CASSINI_KERNELS"):
        print("  (skipped: no CASSINI_KERNELS)")
        return
    import bootleg_autonav as ba
    with contextlib.redirect_stdout(io.StringIO()):
        ba.unload_kernels()
        ba.load_kernels(2000, 2000)
    info = {"path": "W1354495588_1.png", "IMAGE_MID_TIME": "2000-338T00:35:07.258", "TARGET_NAME": "JUPITER",
            "INSTRUMENT_NAME": "WIDE ANGLE CAMERA", "EXPOSURE_DURATION": "5.000000"}
    with contextlib.redirect_stdout(io.StringIO()):
        x, y, z, angle = ba.find_target(types.SimpleNamespace(info=info), False, "graphs")
    assert abs(x + 22) < 5 and abs(y + 47) < 5 and abs(angle + 14.02) < 0.1, (x, y, angle)
    # without its exposure (the cache's fill), only the rounding of the middle is looked past, which here is enough
    del info["EXPOSURE_DURATION"]
    with contextlib.redirect_stdout(io.StringIO()):
        assert abs(ba.find_target(types.SimpleNamespace(info=info), False, "graphs")[0] + 22) < 5
    # a frame pointed away all through its exposure still fails
    info = {"path": "x.png", "IMAGE_MID_TIME": "2000-338T00:35:05.000", "TARGET_NAME": "JUPITER",
            "INSTRUMENT_NAME": "WIDE ANGLE CAMERA", "EXPOSURE_DURATION": "5.000000"}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ba.find_target(types.SimpleNamespace(info=info), False, "graphs")
        raise AssertionError("placed a frame pointed away")
    except ValueError as e:
        assert "behind the camera" in str(e), e

if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
