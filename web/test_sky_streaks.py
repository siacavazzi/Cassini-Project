"""
A cosmic ray's track in one channel of a color set's sky (Mimas 2005, N1492222777_1 and its set: blue, green and red
dashes) is 2 to 6 pixels wide, so the 3x3 median of calibration._clean_spikes takes it for sky and it stays.
calibration._clean_streaks takes it off; a star (in every channel) and the body stay as they were.
Run: PYTHONPATH=. python web/test_sky_streaks.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2
import numpy as np

import calibration as cal


def scene():
    rng = np.random.default_rng(3)
    n = 256
    yy, xx = np.mgrid[:n, :n]
    body = (yy - 60) ** 2 + (xx - 60) ** 2 < 40 ** 2
    chans = []
    for i in range(3):
        c = rng.normal(0.002, 0.001, (n, n)).astype(np.float32)
        c[body] += 0.6 + 0.05 * np.sin(xx[body] / 3.0) + 0.01 * i   # cratered texture
        c[180:183, 60:63] += 0.5                                      # a star, in every channel
        chans.append(c)
    track = np.zeros((n, n), np.uint8)
    cv2.line(track, (120, 150), (200, 200), 1, 4)                     # a 4 px cosmic ray track, blue only
    chans[2][track > 0] += 0.3
    sky = np.logical_and.reduce([c < 0.05 * np.percentile(c, 99.9) for c in chans])
    return chans, sky, track > 0, body


def main():
    chans, sky, track, body = scene()
    spikes = cal._clean_spikes([c.copy() for c in chans], sky)
    assert spikes[2][track].mean() > 0.1, "the 3x3 cleaner alone leaves the track (what this test is about)"
    out = cal._clean_streaks(spikes, sky)
    left = float(out[2][track].mean())
    print("track before %.3f after %.4f" % (spikes[2][track].mean(), left))
    assert left < 0.01, left
    for i in range(3):
        assert out[i][180:183, 60:63].min() > 0.4, "the star is in every channel and stays"
        assert np.array_equal(out[i][body], spikes[i][body]), "the body is not sky"
    # a thin haze just off the limb, in one filter only, is left
    chans, sky, track, body = scene()
    yy, xx = np.mgrid[:256, :256]
    haze = (np.hypot(yy - 60, xx - 60) > 41) & (np.hypot(yy - 60, xx - 60) < 44)
    chans[2][haze] += 0.1
    sky = np.logical_and.reduce([c < 0.05 * np.percentile(c, 99.9) for c in chans])
    out = cal._clean_streaks(cal._clean_spikes([c.copy() for c in chans], sky), sky)
    print("haze %.3f" % out[2][haze].mean())
    assert out[2][haze].mean() > 0.08, out[2][haze].mean()
    print("ok")


if __name__ == "__main__":
    main()
