"""Check calibration.enlarged: a summed frame's calibrated picture, which comes as blocks (each of the camera's pixels
repeated 2x2 or 4x4 to fill the 1024 px picture), is enlarged smoothly from the camera's own pixels (bicubic: Sam's taste
call 23, option C), and anything else is left as it is: a full size frame, and a summed frame at its own size (the
science TIFF's).
Run: python web/test_summed_enlarged.py"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calibration as cal  # noqa: E402

assert cal.SUMMED_ENLARGE == cv2.INTER_CUBIC
rng = np.random.default_rng(23)
for lines in (512, 256):
    s = 1024 // lines
    info = {"LINES": str(lines), "LINE_SAMPLES": str(lines)}
    # a smooth scene (a limb: a disk's edge crossing the frame) as the camera's pixels, drawn as blocks
    y, x = np.mgrid[0:lines, 0:lines].astype(np.float64)
    r = np.hypot(x - 0.3 * lines, y - 0.4 * lines)
    small = 0.2 / (1 + np.exp((r - 0.35 * lines) / 0.8)) + 0.001 * rng.standard_normal((lines, lines))
    blocks = np.repeat(np.repeat(small, s, 0), s, 1)
    out = cal.enlarged(blocks, info)
    assert out.shape == blocks.shape == (1024, 1024) and out.dtype == blocks.dtype
    # what it is: the camera's pixels enlarged bicubic, and the same from blocks that vary inside (a flat field's
    # pattern over them) as from their means
    assert np.array_equal(out, cv2.resize(small, (1024, 1024), interpolation=cv2.INTER_CUBIC))
    ripple = blocks * (1 + 0.01 * np.tile(np.array([[1.0, -1.0], [-1.0, 1.0]]), (512, 512)))
    assert np.allclose(cal.enlarged(ripple, info), out, rtol=0, atol=1e-12)
    # no stair steps: along the limb the blocks jump by a whole camera pixel's difference every s pixels and not at
    # all between; enlarged, no step between neighbours is more than a share of the largest block step
    step_blocks = np.abs(np.diff(blocks, axis=1)).max()
    step_out = np.abs(np.diff(out, axis=1)).max()
    assert step_out < 0.75 * step_blocks / (s / 2), (lines, step_out, step_blocks)
    # the picture's brightness is kept: each camera pixel's block mean within a small share of the limb's height,
    # and the overshoot past the scene's own range small (bicubic's: under a tenth of the limb's height)
    means = out.reshape(lines, s, lines, s).mean(axis=(1, 3))
    assert np.abs(means - small).max() < 0.05 * 0.2, np.abs(means - small).max()
    assert out.max() < small.max() + 0.02 and out.min() > small.min() - 0.02
    # a flat frame stays flat to the bit
    flat = np.full((1024, 1024), 0.125)
    assert np.array_equal(cal.enlarged(flat, info), flat)
    # left as they are: the frame at its own size (calibrate with no display image: the science TIFF), float32 kept
    native = small.astype(np.float32)
    assert cal.enlarged(native, info) is native
    assert cal.enlarged(blocks.astype(np.float32), info).dtype == np.float32
# a full size frame is never touched
full = rng.random((1024, 1024))
assert cal.enlarged(full, {"LINES": "1024", "LINE_SAMPLES": "1024"}) is full
assert cal.enlarged(full, {}) is full
print("summed frames enlarged smoothly from the camera's pixels (512 and 256 lines); full size and native size left: ok")
