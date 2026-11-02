"""Colour filter matching (thread "Review color filter frame matching", 2026-11-02), the registration half; the set
rule's half is in test_sets_passes.py. Synthetic frames.
  2. a mosaic tile is searched only near SPICE's place (obs_mosaic._register, REGISTER_MAX), its border left out
  3. a set's three channels are matched with one another too, and a wrong match is caught (image_correction._loop)
  4. a channel is scaled and turned onto the reference about its target's centre (color_image.spice_warps)
  5. a star field is matched on its stars (image_correction.star_shift), hot pixels left out
Run: python web/test_set_matching.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, ".."), os.path.join(HERE, "frames")]
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import image_correction as ic  # noqa: E402

N = 1024
rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
CRATERS = [(420, 400, 30), (520, 560, 22), (380, 560, 26), (600, 420, 18), (470, 300, 15)]


def body(dx=0.0, dy=0.0, level=200, scale=1.0, cx=480.0, cy=470.0, r=300.0):
    """A cratered moon wholly inside the frame, centre (cx + dx, cy + dy), radius r * scale"""
    X, Y = (xx - cx - dx) / scale + cx, (yy - cy - dy) / scale + cy
    im = np.clip(r - np.hypot(X - cx, Y - cy), 0, 1) * level
    for a, b, rad in CRATERS:
        im = im * np.where(np.hypot(X - a, Y - b) < rad, 0.55, 1.0)
    im = im + rng.normal(0, 1.0, im.shape)
    return cv2.cvtColor(np.clip(im, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


ones = lambda: np.ones((N, N), bool)

# ---------- 3. the loop check ----------
ref, a, b = body(), body(4.0, -3.0, 150), body(-6.0, 2.5, 120)
true = {1: (4.0, -3.0), 2: (-6.0, 2.5)}
shifts, hows = [None, (4.0 + 38.0, -3.0 - 21.0), (-6.0, 2.5)], [None, "phase", "phase"]   # channel 1's match wrong
ic._loop([ref, a, b], [ones(), ones(), ones()], 0, shifts, hows, None)
assert np.hypot(shifts[1][0] - 4.0, shifts[1][1] + 3.0) < 0.5, shifts
assert "via the other channel" in hows[1], hows
# a channel that matched nothing lands through the other one
shifts, hows = [None, None, (-6.0, 2.5)], [None, "not aligned", "phase"]
ic._loop([ref, a, b], [ones(), ones(), ones()], 0, shifts, hows, None)
assert np.hypot(shifts[1][0] - 4.0, shifts[1][1] + 3.0) < 0.5, shifts
# a closed loop shares the error: the three agree, each within a tenth of a pixel of the truth
rep, found = [], []
ic.align_with_masks([ref.copy(), a.copy(), b.copy()], [ones(), ones(), ones()], 0, rep, found=found)
for i in (1, 2):
    assert np.hypot(found[i][0] - true[i][0], found[i][1] - true[i][1]) < 0.15, (i, found[i], rep)
print("3. loop check:", rep)

# ---------- 4. scale and turn ----------
import color_image  # noqa: E402
import bootleg_autonav as ba  # noqa: E402
C = ba.CCD_CENTER
# the reference at 10,000 km, the channel 17% further (the body smaller) and turned 2 degrees; target at (480, 470)
locs = [[C - 480, C - 470, 10000.0, 30.0], [C - 480, C - 470, 11700.0, 32.0]]
color_image._spice_locs = lambda lbls: locs
w = color_image.spice_warps([None, None], 0)
assert w[0] is None and w[1] is not None and abs(w[1][2] - 1.17) < 1e-6 and abs(w[1][3] - 2.0) < 1e-6, w
small = body(level=150, scale=1 / 1.17)
grown = color_image.warp_frame(small, w[1])
# grown back to the reference's size: the limb lines up (the radius in each, by the lit area)
lit = lambda im: np.sqrt((cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) > 60).sum() / np.pi)
assert abs(lit(grown) - lit(ref)) < 2.0, (lit(small), lit(grown), lit(ref))
# no change worth a pixel: none
locs[1] = [C - 480, C - 470, 10000.3, 30.0]
assert color_image.spice_warps([None, None], 0) == [None, None]
print("4. scale and turn: radius", round(lit(small), 1), "->", round(lit(grown), 1), "reference", round(lit(ref), 1))

# ---------- 5. stars ----------
stars = rng.uniform(40, 980, (35, 2))
hot = [tuple(v) for v in rng.integers(10, 1010, (60, 2))]


def field(dx, dy):
    im = rng.normal(10, 1.5, (N, N)).astype(np.float32)
    for x, y in stars:
        X, Y = x + dx, y + dy
        im += 120 * np.exp(-((xx - X) ** 2 + (yy - Y) ** 2) / (2 * 1.2 ** 2))
    for x, y in hot:   # the camera's hot pixels, where they are in every frame
        im[y, x] = 250
    return cv2.cvtColor(np.clip(im, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


f0, f1 = field(0, 0), field(12.6, -33.4)
s = ic.star_shift(f0, f1)
assert s is not None and np.hypot(s[0] - 12.6, s[1] + 33.4) < 0.3, s
rep, found = [], []
ic.align_with_masks([f0.copy(), f1.copy()], [ones(), ones()], 0, rep, found=found)
assert rep[1].startswith("stars") and np.hypot(found[1][0] - 12.6, found[1][1] + 33.4) < 0.3, rep
m = ic.star_shift(body(), body(3, 2))   # a moon: nothing, or the right answer from its own points
assert m is None or np.hypot(m[0] - 3, m[1] - 2) < 0.5, m
print("5. star field:", rep[1])

# ---------- 2. mosaic tiles: near SPICE only ----------
import obs_mosaic  # noqa: E402


def tile(dx, dy, level, black=False):
    im = (rng.normal(6, 2, (N, N)).clip(0, 255).astype(np.uint8)[..., None].repeat(3, 2) if black
          else body(dx, dy, level))
    rgba = np.dstack([cv2.cvtColor(im, cv2.COLOR_BGR2RGB), np.full((N, N), 255, np.uint8)])
    rgba[:, :40, 3] = 0   # the tile's edge: alpha ends here, a bright step against the black of the crop
    rgba[:, 40:44, :3] = 90
    return rgba


q = {"offset": [0.0, 0.0], "box": [-N / 2, -N / 2, N, N]}
t = {"offset": [0.0, 0.0], "box": [-N / 2, -N / 2, N, N]}
within = obs_mosaic.REGISTER_MAX * obs_mosaic.FRAME
for d in ((3.4, -2.2), (-7.0, 5.5)):
    shift, how = obs_mosaic._shift_onto(q, tile(0, 0, 200), q["offset"], t, tile(*d, 150), t["offset"], within=within)
    assert shift is not None and np.hypot(shift[0] - d[0], shift[1] - d[1]) < 0.3, (d, shift, how)
# a black tile whose edge sits 30 px from the reference's: the borders are not matched, and nothing moves past the cap
a_, b_ = tile(0, 0, 0, black=True), tile(0, 0, 0, black=True)
b_ = np.roll(b_, 30, axis=1)
shift, how = obs_mosaic._shift_onto(q, a_, q["offset"], t, b_, t["offset"], within=within)
assert shift is None or np.hypot(*shift) <= within, (shift, how)
print("2. tiles near SPICE:", how, shift)
print("ok")
