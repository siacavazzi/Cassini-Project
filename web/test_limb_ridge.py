"""A near-straight limb matched across itself (image_correction._limb_ridge): Titan's haze along the bottom of a frame
correlates as a ridge whose peak sits round LIMB_RESPONSE (200TI EUVFUV002's CB2/RED/BL1 set: 0.21 on the display
copies, 0.17 at full depth, so the set went gray). Such an outline is pinned across itself by the lit areas' outlines
and placed along it at SPICE's offset; a round limb, two outlines running different ways, or a lit area that is not
one edge are not. Synthetic frames. Run: python web/test_limb_ridge.py"""
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
    r = np.hypot(x - 512, (y - 5200) + tilt * (x - 512))
    height = r - 4400                        # px above the limb (negative: on the disk)
    img = np.where(height < 0, 1.0, np.exp(-height / 45))
    img = 12 + (200 if band else 150) * img + rng.normal(0, 3.0, (N, N))
    for _ in range(specks):
        i, j = rng.integers(0, 600), rng.integers(0, N)
        img[i:i + 2, j:j + 3] = 250
    return cv2.cvtColor(np.clip(cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0), 0, 255).astype(np.uint8),
                        cv2.COLOR_GRAY2BGR)


checks = 0
low = ic.LIMB_RESPONSE
ic.LIMB_RESPONSE = 2.0   # (every peak too low to believe: the ridge rule decides)

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

# 3. a round limb (a whole disk in the frame) is not a ridge: the low peak still says no
r = np.hypot(xx - 500, yy - 520)
disk = [cv2.cvtColor(np.clip(np.where(np.hypot(xx - 500 - d, yy - 520) < 300, 180, 10) + rng.normal(0, 2, (N, N)), 0, 255)
                     .astype(np.uint8), cv2.COLOR_GRAY2BGR) for d in (0, 6)]
assert ic.limb_shift(disk[0], disk[1], MASK, MASK, g=(6.0, 0.0)) == (None, "not aligned")
checks += 1

# 4. two outlines running different ways (LIMB_TURN) are not one limb moved
assert ic.limb_shift(h1, haze(0, 7, 1, tilt=0.3), MASK, MASK)[0] is None
checks += 1

# 5. the believed peak is unchanged: a straight edge with no low-peak rule still moves only across it
ic.LIMB_RESPONSE = low
edge1 = cv2.cvtColor(np.where(xx < 500, 180, 10).astype(np.uint8), cv2.COLOR_GRAY2BGR)
edge2 = cv2.cvtColor(np.where(xx < 506, 120, 10).astype(np.uint8), cv2.COLOR_GRAY2BGR)
shift, how = ic.limb_shift(edge1, edge2, MASK, MASK)
assert shift is None or abs(shift[1]) < 1.0, (how, shift)
checks += 1
print(f"{checks} checks ok")
