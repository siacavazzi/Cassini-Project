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
# pixels lost in downlink (a line's end that never came: zeros in the camera frame) are bridged before the frame is
# enlarged, so they do not bleed into the rows beside them
for lines in (512, 256):
    s = 1024 // lines
    info = {"LINES": str(lines), "LINE_SAMPLES": str(lines)}
    y, x = np.mgrid[0:lines, 0:lines].astype(np.float64)
    whole = 0.1 + 0.05 * np.sin(x / 9.0) * np.cos(y / 13.0)
    lost = np.zeros((lines, lines), bool)
    lost[100:102, 40:] = True            # two lines' ends
    lost[:, [0, -1]] = True              # a summed frame's first and last column (label.valid_mask)
    lost[lines - 1, 10:20] = True        # at the frame's bottom: only pixels above to take
    hit = np.where(lost, 0.0, whole)
    clean = cal.enlarged(np.repeat(np.repeat(whole, s, 0), s, 1), info)
    blocks = np.repeat(np.repeat(hit, s, 0), s, 1)
    bled = cal.enlarged(blocks, info)
    got = cal.enlarged(blocks, info, lost)
    beside = np.zeros((1024, 1024), bool)          # the three camera rows on each side of the lost lines, kept columns
    beside[97 * s:100 * s, 45 * s:-3 * s] = beside[102 * s:105 * s, 45 * s:-3 * s] = True
    assert np.abs(bled - clean)[beside].max() > 0.005          # as it was without the mask: the zeros bleed
    assert np.abs(got - clean)[beside].max() < 2e-4, np.abs(got - clean)[beside].max()
    # and what was lost reads as its neighbours do, not as zeros (the picture's own fill takes it from there)
    inside = np.zeros((1024, 1024), bool)
    inside[100 * s:102 * s, 45 * s:-3 * s] = True
    assert np.abs(got - clean)[inside].max() < 0.01 and got[inside].min() > 0.04
    assert got[-1, 12 * s:18 * s].min() > 0.04
    # a mask of another size, or none lost: as without one
    assert np.array_equal(cal.enlarged(blocks, info, np.zeros((7, 7), bool)), bled)
    assert np.array_equal(cal.enlarged(blocks, info, np.zeros((lines, lines), bool)), bled)
# what the camera saturated, and the camera pixels the enlargement would mix it into, stay as they were (blocks)
for lines in (512, 256):
    s = 1024 // lines
    info = {"LINES": str(lines), "LINE_SAMPLES": str(lines)}
    y, x = np.mgrid[0:lines, 0:lines].astype(np.float64)
    scene = 0.1 + 0.05 * np.sin(x / 9.0) * np.cos(y / 13.0)
    blown = np.hypot(x - 120, y - 90) < 14
    scene[blown] = 1.0                       # a blown-out patch at the top of the range
    blocks = np.repeat(np.repeat(scene, s, 0), s, 1)
    plain = cal.enlarged(blocks, info)
    got = cal.enlarged(blocks, info, None, blown)
    reach = cv2.dilate(blown.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0     # the patch and 2 camera pixels round it
    big = np.repeat(np.repeat(reach, s, 0), s, 1)
    assert np.array_equal(got[big], blocks[big])                       # as it was: no part of the clipped value moved
    assert np.abs(plain - blocks)[big & ~np.repeat(np.repeat(blown, s, 0), s, 1)].max() > 0.05   # without: it does
    far = ~np.repeat(np.repeat(cv2.dilate(blown.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0, s, 0), s, 1)
    assert np.array_equal(got[far], plain[far])                        # beyond 4 camera pixels: the enlarged picture
    assert np.abs(got - plain)[~big].max() < 0.02                      # and a smooth join between
    assert cal.enlarged(blocks, info, None, np.zeros((lines, lines), bool)) is not None
    assert np.array_equal(cal.enlarged(blocks, info, None, np.zeros((lines, lines), bool)), plain)
assert cal.clipped_codes(np.zeros((4, 4, 3), np.uint8), {}) is None
v = np.arange(20.0).reshape(5, 4)
gone = np.zeros((5, 4), bool); gone[1:3, 0] = True; gone[0, 1] = True; gone[:, 3] = True
out = cal.bridged(v, gone)
assert out[1, 0] == v[0, 0] + (v[3, 0] - v[0, 0]) / 3 and out[2, 0] == v[0, 0] + 2 * (v[3, 0] - v[0, 0]) / 3   # in proportion
assert out[0, 1] == v[1, 1] and np.all(out[:, 3] == np.median(v[~gone])) and np.array_equal(out[~gone], v[~gone])
# a full size frame is never touched
full = rng.random((1024, 1024))
assert cal.enlarged(full, {"LINES": "1024", "LINE_SAMPLES": "1024"}) is full
assert cal.enlarged(full, {}) is full
print("summed frames enlarged smoothly from the camera's pixels (512 and 256 lines); full size and native size left: ok")
