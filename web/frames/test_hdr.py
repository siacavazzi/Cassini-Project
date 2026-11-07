#!/usr/bin/env python3
"""Checks the HDR recovery map (calibration.hdr_capture, tone, recovery_map, recover): the picture tone draws is the
same bytes with the capture open or not, and the drawn picture times the map gives tone's linear picture back:
python web/frames/test_hdr.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import calibration as cal  # noqa: E402


def channels(seed=0):
    """Three linear channels (white = 1) with a dark sky, a lit body, highlights past white and a saturated patch"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:128, 0:128].astype(np.float32)
    body = np.clip(1 - np.hypot(x - 64, y - 64) / 50, 0, 1) * 1.3
    base = 0.002 * rng.standard_normal((128, 128)).astype(np.float32) + body
    chans = [base * g for g in (1.0, 0.9, 0.75)]
    sat = np.zeros((128, 128), bool)
    sat[60:68, 60:68] = True
    return chans, [sat, sat, sat]


def test_same_picture():
    for seed in range(3):
        chans, sat = channels(seed)
        plain = cal.tone([c.copy() for c in chans], 0.01, saturated=sat)
        with cal.hdr_capture() as sink:
            kept = cal.tone([c.copy() for c in chans], 0.01, saturated=sat)
        assert len(sink) == 1 and sink[0].shape == (128, 128) and sink[0].dtype == np.uint8
        assert all(np.array_equal(a, b) for a, b in zip(plain, kept))


def test_no_capture_outside():
    chans, sat = channels()
    with cal.hdr_capture():
        pass
    assert cal.hdr_sink() is None
    cal.tone(chans, 0.01, saturated=sat)
    assert cal.hdr_sink() is None


def test_recover():
    chans, sat = channels()
    with cal.hdr_capture() as sink:
        drawn = cal.tone([c.copy() for c in chans], 0.01, saturated=sat)
    rgb = np.dstack([d[..., 0] for d in drawn])
    back = cal.recover(rgb, sink[-1]).max(axis=-1)
    shown = (rgb.max(axis=-1).astype(np.float32) / 255) ** cal.HDR_GAMMA
    lum = np.max(chans, axis=0)
    # highlights past the shoulder come back above white, within a code's step (5/255 stop) of tone's own linear values
    bright = (shown > 0.6) & ~sat[0]
    assert bright.sum() > 100
    assert back[bright].max() > 1.1 and shown[bright].max() <= 1.0
    lin = np.maximum(lum, 0)[bright]
    assert np.median(np.abs(np.log2(back[bright] / lin))) < 0.03
    # what the camera saturated: HDR_SATURATED (8x white) is past the map's top, so it comes back at its ceiling
    assert back[sat[0]].min() > 7.0
    # shadows and mid tones (under HDR_FROM of white): 0 stops, the HDR picture there is the SDR picture as drawn
    low = np.maximum(lum, 0) < cal.HDR_FROM[0]
    assert (sink[-1][low] == cal.HDR_ZERO).all()


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
