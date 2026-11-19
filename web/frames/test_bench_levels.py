"""levels.measure on made-up pictures: black sky, the same sky lifted to gray with column stripes (the Full level's
veil), and a picture too little covered to judge.  python web/frames/test_bench_levels.py (or pytest)"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import image_bench  # noqa: E402

image_bench.checks_module()
from bench_checks import levels  # noqa: E402


def _pic(sky, stripes=0.0, seed=0):
    rng = np.random.default_rng(seed)
    lum = np.full((256, 256), float(sky)) + rng.normal(0, 1.0, (256, 256))
    lum += stripes * rng.normal(0, 1.0, 256)[None, :]
    lum[96:160, 96:160] = 220.0                       # a lit body
    lum = np.clip(lum, 0, 255).astype(np.uint8)
    return np.dstack([lum, lum, lum, np.full(lum.shape, 255, np.uint8)])


def test_black_and_banding():
    proc, full = levels.measure(_pic(2)), levels.measure(_pic(150, stripes=4.0))
    assert 100 * (proc["dark"] - full["dark"]) > levels.full_black.fn.__defaults__[0]
    assert full["band"] - proc["band"] > levels.full_banding.fn.__defaults__[0]


def test_same_picture_passes():
    a, b = levels.measure(_pic(3, seed=1)), levels.measure(_pic(3, seed=2))
    assert abs(a["dark"] - b["dark"]) < 0.02 and abs(a["band"] - b["band"]) < 0.5


def test_too_little_covered():
    p = _pic(2)
    p[..., 3] = 0
    p[:10, :10, 3] = 255
    assert levels.measure(p) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
