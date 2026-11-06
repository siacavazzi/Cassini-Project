"""Spot check 7, fix E: a small moon's centred view is placed on the moon the picture shows (color_image.find_small_body),
where SPICE's place is tens to hundreds of pixels off (Pan 2017-03-07 36 px, Atlas 2017-04-12 about 340 px).
Synthetic RGBA canvases. Run: python web/test_find_small_body.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import color_image  # noqa: E402

rng = np.random.default_rng(7)
H = 1400


def canvas(bodies=(), ring=False, edge=None):
    lum = rng.normal(8, 2, (H, H))
    yy, xx = np.mgrid[:H, :H]
    for x, y, r, lit in bodies:
        d = (yy - y) ** 2 + (xx - x) ** 2 < r * r
        if lit < 1:
            # a crescent: only the part of the disk right of x + (1 - 2 * lit) * r is lit
            d &= xx > x + (1 - 2 * lit) * r
        lum[d] = 220
    if ring:
        lum[(yy > 900) & (yy < 960)] = 150   # a ring strip across the frame
    for _ in range(300):                     # cosmic rays and stars
        lum[rng.integers(0, H), rng.integers(0, H)] = 255
    alpha = np.full((H, H), 255, np.uint8)
    alpha[:, :edge or 0] = 0
    im = np.clip(lum, 0, 255).astype(np.uint8)
    return np.dstack([im, im, im, alpha])


# SPICE 36 px off a gibbous moon of radius 95 px: found, within a pixel
f = color_image.find_small_body(canvas([(664, 736, 95, 1)]), 700, 700, 95)
assert f is not None and abs(f[0] - 664) < 1.5 and abs(f[1] - 736) < 1.5, f
# SPICE 340 px off a moon the frame's edge cuts: found (its centroid, on the moon)
f = color_image.find_small_body(canvas([(380, 700, 176, 1)], edge=300), 700, 700, 176)
assert f is not None and 300 < f[0] < 460, f
# a ring strip in the frame is not the moon
f = color_image.find_small_body(canvas([(650, 650, 60, 1)], ring=True), 700, 700, 60)
assert f is not None and abs(f[0] - 650) < 1.5 and abs(f[1] - 650) < 1.5, f
# a crescent near SPICE's place keeps SPICE's place (its lit centroid sits off its centre)
assert color_image.find_small_body(canvas([(700, 700, 100, 0.3)]), 690, 700, 100) is None
# nothing but sky and cosmic rays (Aegaeon in the G ring's radiation): SPICE's place
assert color_image.find_small_body(canvas(), 700, 700, 10) is None
# a body that fills the frame, or a speck: SPICE's place, as before
assert color_image.find_small_body(canvas([(700, 700, 400, 1)]), 700, 700, 400) is None
assert color_image.find_small_body(canvas([(700, 700, 9, 1)]), 650, 700, 9) is None
# a cosmic ray's track the size of a small disk is not the moon
im = canvas()
im[700:704, 400:520, :3] = 255
assert color_image.find_small_body(im, 700, 700, 30) is None
# review 11-05: a half-lit moon near SPICE's place keeps SPICE's place (its centroid sits 0.42 radius off its centre)
assert color_image.find_small_body(canvas([(700, 700, 80, 0.5)]), 700, 700, 80) is None
# another, bigger moon far from SPICE's place is not the body: nothing within reach, SPICE's place
assert color_image.find_small_body(canvas([(200, 200, 120, 1)]), 1000, 1100, 60) is None
# two moons within reach: the one nearer SPICE's place, not the bigger
f = color_image.find_small_body(canvas([(760, 700, 50, 1), (520, 520, 70, 1)]), 700, 700, 55)
assert f is not None and abs(f[0] - 760) < 1.5 and abs(f[1] - 700) < 1.5, f
print("ok")
