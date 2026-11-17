"""Colour-set channels whose only shared detail runs one way (image_correction.ridge_shift), and blank pairs wholly on
their target's disk (_flat's filled): Saturn's cloud tops through CB2 and MT2 crossed by one ring edge are pinned across
the edge and placed by SPICE along it, where nothing can fringe; a second ring edge close by (two ridges) or detail in
both channels along the edge leaves the channel not aligned; a featureless pair is the body's even colour only when SPICE
puts both frames on the disk. Synthetic frames. Run: python web/test_ridge_align.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import image_correction as ic  # noqa: E402

N = 1024
rng = np.random.default_rng(8)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
MASK = np.ones((N, N), bool)
BLOBS = [(rng.uniform(0, N), rng.uniform(0, N), rng.uniform(15, 60), rng.uniform(-0.05, 0.05)) for _ in range(60)]


def clouds(dx, dy, band, lines=(300.0,), texture=None):
    """A frame-filling cloud deck, a gentle glow across it, and ring edges running along x at rows lines (moved by
    dx, dy): band 0 shows faint cloud blobs, band 1 none (a methane band); texture adds detail along x to band 1"""
    img = 0.55 + 0.1 * (yy / N) + (0.05 * xx / N if band else 0.0)
    if band == 0:
        img = img + sum(a * np.exp(-((xx - x - dx) ** 2 + (yy - y - dy) ** 2) / s ** 2) for x, y, s, a in BLOBS)
    if texture is not None:
        img = img + 0.08 * np.sin((xx - dx) / texture) * np.exp(-((yy - 700 - dy) / 120) ** 2)
    for row in lines:
        img = img - 0.35 * np.exp(-((yy - row - dy) / 3.0) ** 2)
    img = img + np.random.default_rng(int(abs(dx) * 7 + abs(dy) * 13 + band + len(lines))).normal(0, 0.004, img.shape)
    return cv2.cvtColor(np.clip(img * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


# MT2 moved 15,-6 from CB2; SPICE says 13,-1 (off by 5 px across the edge, 2 along it)
ref, moved = clouds(0, 0, 0), clouds(15, -6, 1)
shift, how = ic.ridge_shift(ref, moved, MASK, MASK, (13.0, -1.0))
assert shift is not None and "ridge" in how, how
assert abs(shift[1] + 6) < 0.5, shift              # pinned across the edge
assert abs(shift[0] - 13.0) < 0.5, shift           # SPICE's along it (the clouds of MT2 are flat that way)
print("ridge:", how, [round(v, 2) for v in shift])
shift2, how2 = ic._match(ref, moved, (13.0, -1.0), MASK, MASK)
assert shift2 is not None and abs(shift2[1] + 6) < 1.0, (how2, shift2)
print("cascade:", how2)

# eight evenly spaced ringlets 12 px apart: a ridge every 12 px, none surely the one: not aligned
GAPS = tuple(300.0 + 12 * k for k in range(8))
ref3, moved3 = clouds(0, 0, 0, GAPS), clouds(15, -6, 1, GAPS)
assert ic.ridge_shift(ref3, moved3, MASK, MASK, (13.0, -1.0))[0] is None
# detail along the edge in both channels (the reference's clouds, a wave in the other): SPICE's error along it would show
moved4 = clouds(15, -6, 1, texture=6.0)
got4 = ic.ridge_shift(ref, moved4, MASK, MASK, (13.0, -1.0))
assert got4[0] is None or abs(got4[0][0] - 15) < 1.0, got4   # (the wave may pin it both ways: then it is a peak, not a ridge)
print("ringlets / detail both ways: not a ridge")

# a featureless pair (a 3-level spread): gray unless SPICE puts both frames wholly on the target's disk
flat1 = cv2.cvtColor(np.round(221 + 3 * xx / N).astype(np.uint8), cv2.COLOR_GRAY2BGR)
flat2 = cv2.cvtColor(np.round(242 + 3 * yy / N).astype(np.uint8), cv2.COLOR_GRAY2BGR)
assert not ic._flat(flat1, flat2, MASK, MASK)
assert ic._flat(flat1, flat2, MASK, MASK, filled=True)
shift5, how5 = ic._match(flat1, flat2, (4800.0, 3700.0), MASK, MASK, filled=True)
assert shift5 is not None and np.hypot(*shift5) < 1.0, (shift5, how5)
print("blank on the disk:", how5)

# ... and only a lit one counts as on the disk (color_image._lit_well): a blank pair on the night side, or on sky that
# SPICE puts on the disk, is dark noise whose color is the filters' noise ratio stretched: it stays gray
import color_image as ci  # noqa: E402
haze = 1.4 + rng.normal(0, 0.005, (N, N)).astype(np.float32)
night = 0.002 + rng.normal(0, 0.003, (N, N)).astype(np.float32)
assert ci._lit_well(haze) and not ci._lit_well(night)
assert not ci._lit_well(np.zeros((N, N), np.float32))
print("night-side blank pair: not lit, stays gray")

# in a set of three the channel the ridge places must itself be flat along the ridge (placed_flat): here the reference
# (clouds faint, flat along the edge) is flat but the channel placed has a wave along the edge, so it is not placed
ref6, moved6 = clouds(0, 0, 1), clouds(15, -6, 0, texture=8.0)
pair = ic.ridge_shift(ref6, moved6, MASK, MASK, (13.0, -1.0))
three = ic.ridge_shift(ref6, moved6, MASK, MASK, (13.0, -1.0), placed_flat=True)
assert pair[0] is not None and three[0] is None, (pair, three)
print("set of three, placed channel not flat along the ridge:", pair[1][:40], "->", three[1])
print("ok")
