"""Synthetic check that label.translate with draw=False (processed_frame's first call: where SPICE puts the frame,
not drawn) sets the placement translate sets when it draws, and returns the shape of the canvas it draws on: full and
summed frames, with and without the border, shifted on and off the canvas, turned, and not a number.
Run: python web/test_place_only.py"""
import contextlib
import io
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import frame_server as fs  # noqa: E402

lh = fs.color_image.lh
rng = np.random.default_rng(4)


def label(image):
    lbl = object.__new__(lh.label)
    lbl.info = {"SPACECRAFT_CLOCK_START_COUNT": "1500000000.000"}
    return lbl.set_color(image)


checks = 0
for trial in range(80):
    side = int(rng.choice([256, 512, 1024]))
    image = rng.integers(0, 256, (side, side, 4), dtype=np.uint8)
    x, y = rng.uniform(-1500, 1500, 2) if trial % 4 else rng.uniform(-4000, 4000, 2)
    angle = rng.uniform(-180, 180)
    if trial % 10 == 0:
        x = float("nan")
    elif trial % 10 == 1:
        angle = float("nan")
    for border in (True, False):
        with contextlib.redirect_stdout(io.StringIO()):
            drawn = label(image)
            img = drawn.translate("png", x, y, angle, border)
            placed = label(image)
            shape = placed.translate("png", x, y, angle, border, draw=False)
        assert shape == img.shape, (trial, border, shape, img.shape)
        assert placed.placement.dtype == drawn.placement.dtype, (trial, border)
        assert np.array_equal(placed.placement, drawn.placement, equal_nan=True), (trial, border)
        checks += 1
print(f"{checks} checks ok")
