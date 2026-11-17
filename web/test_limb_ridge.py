"""The limb match, where the outlines' correlation peak falls short, as a search for where the lit areas' outlines
differ least (image_correction.limb_shift, _outline_search): a round limb is found where it is; a near-straight one
(Titan's haze along the bottom of a frame, 200TI EUVFUV002's CB2/RED/BL1 set, gray after #491 when its correlation
peak fell from 0.21 to 0.17) is placed across itself and along it at SPICE's offset; two outlines running different
ways are not one limb moved; the place found does not hang on a few hundred changed pixels (W1640522624_1's peak fell
from 0.54 to 0.19 that way). Synthetic frames. Run: python web/test_limb_ridge.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import image_correction as ic  # noqa: E402

N = 1024
rng = np.random.default_rng(11)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
MASK = np.ones((N, N), bool)


def haze(dx, dy, band, tilt=0.0, specks=8):
    """A body far larger than the frame, its limb a gentle curve along the bottom with a soft haze over it (brighter
    in one band), noise, and a few stars and cosmic rays in the sky"""
    x, y = xx - dx, yy - dy
    r = np.hypot(x - 512, (y - 40200) + tilt * (x - 512))
    height = r - 39400                        # px above the limb (negative: on the disk)
    img = np.where(height < 0, 1.0, np.exp(-height / 45))
    img = 12 + (200 if band else 150) * img + rng.normal(0, 3.0, (N, N))
    for _ in range(specks):
        i, j = rng.integers(0, 600), rng.integers(0, N)
        img[i:i + 2, j:j + 3] = 250
    return cv2.cvtColor(np.clip(cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0), 0, 255).astype(np.uint8),
                        cv2.COLOR_GRAY2BGR)


checks = 0
# (the correlation peak, believed first where it reaches LIMB_RESPONSE, is set aside: the search decides)
believed = ic.LIMB_RESPONSE
ic.LIMB_RESPONSE = 2.0

# 1. the haze limb moved 7 px across (down) and 20 px along it: found across, SPICE's place along it
h1, h2 = haze(0, 0, 0), haze(20, 7, 1)
shift, how = ic.limb_shift(h1, h2, MASK, MASK, g=(18.0, 3.0))
assert shift is not None and "limb ridge" in how and "SPICE along it" in how, (how, shift)
assert abs(shift[1] - 7) < 1.0 and abs(shift[0] - 18) < 1.5, (how, shift)
print("haze limb:", how, [round(v, 1) for v in shift])
checks += 1

# 2. without SPICE (or SPICE far off): as taken along it
shift, how = ic.limb_shift(h1, h2, MASK, MASK)
assert shift is not None and "as taken along it" in how and abs(shift[0]) < 1.5 and abs(shift[1] - 7) < 1.0, (how, shift)
shift, how = ic.limb_shift(h1, h2, MASK, MASK, g=(300.0, 0.0))
assert shift is not None and "as taken along it" in how and abs(shift[0]) < 1.5, (how, shift)
checks += 2

# 3. a round limb (a whole disk in the frame) moved 6,-4: found where it is, SPICE not asked
disk = [cv2.cvtColor(np.clip(np.where(np.hypot(xx - 500 - dx, yy - 520 - dy) < 300, 180, 10) + rng.normal(0, 2, (N, N)), 0, 255)
                     .astype(np.uint8), cv2.COLOR_GRAY2BGR) for dx, dy in ((0, 0), (6, -4))]
shift, how = ic.limb_shift(disk[0], disk[1], MASK, MASK, g=(30.0, 10.0))
assert shift is not None and how.startswith("limb (") and np.hypot(shift[0] - 6, shift[1] + 4) < 0.6, (how, shift)
print("disk:", how, [round(v, 1) for v in shift])
checks += 1

# 4. two outlines running different ways (LIMB_TURN) are not one limb moved
assert ic.limb_shift(h1, haze(0, 7, 1, tilt=0.3), MASK, MASK)[0] is None
checks += 1

# 5. the same frame with its noise drawn again (a few hundred lit pixels along the outline change, as calibrating at full
# depth changed 200TI's and W1640522624_1's) leaves the place where it was
h3 = np.clip(h2.astype(np.float32) + rng.normal(0, 3.0, h2.shape[:2])[..., None], 0, 255).astype(np.uint8)
changed = int((ic._lit(h2, MASK) != ic._lit(h3, MASK)).sum())
a, _ = ic.limb_shift(h1, h2, MASK, MASK, g=(18.0, 3.0))
b, _ = ic.limb_shift(h1, h3, MASK, MASK, g=(18.0, 3.0))
assert changed > 100 and a is not None and b is not None and np.hypot(a[0] - b[0], a[1] - b[1]) < 0.6, (changed, a, b)
print(f"{changed} lit pixels changed: {[round(v, 2) for v in a]} -> {[round(v, 2) for v in b]}")
checks += 1

# 6. a straight edge with no SPICE moves only across it, also where its peak is believed
ic.LIMB_RESPONSE = believed
edge1 = cv2.cvtColor(np.where(xx < 500, 180, 10).astype(np.uint8), cv2.COLOR_GRAY2BGR)
edge2 = cv2.cvtColor(np.where(xx < 506, 120, 10).astype(np.uint8), cv2.COLOR_GRAY2BGR)
shift, how = ic.limb_shift(edge1, edge2, MASK, MASK)
assert shift is None or abs(shift[1]) < 1.0, (how, shift)
checks += 1
print(f"{checks} checks ok")
