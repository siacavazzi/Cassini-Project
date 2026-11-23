"""calibration._mostly_sky: a frame that is sky all over round a speck is measured as sky (distant-moon stills drew a
gray banded panel when SKY_CUT of the 99.9th percentile left under 1000 pixels below the cut)."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
import calibration  # noqa: E402


def frame(seed=1, banding=0.4, disc=0.0):
    rng = np.random.default_rng(seed)
    level, noise = 2.0e-4, 1.0e-5
    iof = level + noise * rng.standard_normal((512, 512))
    iof += banding * noise * np.sin(np.arange(512) / 3.0)[None, :]   # column banding
    iof[250:254, 250:254] = 4.0e-3                                     # the speck
    if disc:
        yy, xx = np.mgrid[:512, :512]
        iof[(yy - 256) ** 2 + (xx - 256) ** 2 < disc * 512 * 512 / np.pi] = 2.0e-3
    return iof.astype(np.float32)


def test_speck_on_banded_sky_is_sky():
    sky = calibration._sky([frame()])
    assert sky.mean() > 0.95, sky.mean()
    assert not sky[251, 251]


def test_scale_measured_and_black_above_the_noise():
    iof = frame()
    levels, margin, white, measured = calibration._balanced_scale([iof])
    assert measured
    assert abs(levels[0] - 2.0e-4) < 2.0e-5
    black = levels[0] + margin
    assert (iof < black).mean() > 0.9


def test_body_filling_the_frame_is_not_sky():
    assert calibration._mostly_sky(frame(disc=0.3)) is None


def test_large_glow_is_not_flat():
    iof = frame()
    yy, xx = np.mgrid[:512, :512]
    iof += (3.0e-5 * np.exp(-((xx - 128) ** 2 + (yy - 256) ** 2) / (2 * 80.0 ** 2))).astype(np.float32)
    assert calibration._mostly_sky(iof) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
