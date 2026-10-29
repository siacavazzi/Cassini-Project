"""Small artifacts in single frames and movies (group I of the picture fix plan), on synthetic frames:
- stack_frames: a saturated star a fraction of a pixel off between repeats is not a change (no box of the reference
  alone round it), nor is a repeat's bleed down the star's column averaged in (no vertical spike), and where the reference lost a block a repeat's pixels count however much changed beside it
- fill_lines: a lost run is filled along the picture's slant, and left lost where a trial fill beside it misses
  (judged only where the trial had enough of the run to try on, and never on a run one of the frame's lines tall)
- label.garbled_lines: the garbage the decompressor writes after losing its place in a line is found, a thin feature
  lying along a line is not
- spikes: a movie frame's cosmic rays are found, a star (drifting) and a small moon (moving) are not
Run: python web/test_small_artifacts.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import image_correction as ic  # noqa: E402
import label_handler as lh  # noqa: E402

H = 400
yy, xx = np.mgrid[:H, :H].astype(np.float32)


def bgr(a):
    return cv2.cvtColor(np.clip(a + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


# ---------- stack_frames: no box round a saturated star ----------
rng = np.random.default_rng(1)
stars = [(rng.uniform(20, H - 20), rng.uniform(20, H - 20), 10 ** rng.uniform(1.5, 4)) for _ in range(60)]


def starfield(dx, dy, seed, sky):
    im = np.full((H, H), sky, np.float32)
    for y, x, b in stars:
        im += b * np.exp(-((xx - x - dx) ** 2 + (yy - y - dy) ** 2) / (2 * 1.3 ** 2))
    return bgr(im + np.random.default_rng(seed).normal(0, 2, (H, H)))


# the repeats' sky a few levels darker than the reference's (each frame's own stretch): a box of the reference alone
# shows as a brighter patch
out = ic.stack_frames([starfield(0, 0, 1, 22), starfield(0.6, -0.4, 2, 18), starfield(-0.5, 0.7, 3, 18)])[..., 0]
sky = cv2.dilate((out > 45).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
level = cv2.blur(out.astype(np.float32), (5, 5))[sky]
assert np.percentile(level, 99) - np.percentile(level, 1) < 1.6, np.percentile(level, [1, 99])
# repeats whose saturated star bled 12-15 rows up and down its column (the reference's didn't): no spike averaged
# into the stack
bled = [starfield(0, 0, 1, 22), starfield(0.6, -0.4, 2, 18), starfield(-0.5, 0.7, 3, 18)]
y, x, _ = max(stars, key=lambda s: s[2])
y, x = int(round(y)), int(round(x))
bled[1][max(y - 15, 0):y + 16, x:x + 2] = 255
bled[2][max(y - 12, 0):y + 13, x:x + 2] = 255
out = ic.stack_frames(bled)[..., 0].astype(float)
column = np.r_[out[max(y - 12, 0):max(y - 6, 0), x:x + 2].ravel(), out[y + 7:y + 13, x:x + 2].ravel()]
clean = ic.stack_frames(bled[:1] + [starfield(0.6, -0.4, 2, 18), starfield(-0.5, 0.7, 3, 18)])[..., 0].astype(float)
reference = np.r_[clean[max(y - 12, 0):max(y - 6, 0), x:x + 2].ravel(), clean[y + 7:y + 13, x:x + 2].ravel()]
assert np.abs(column - reference).max() < 12, np.abs(column - reference).max()   # 138 levels with #192's margin
print("no boxes round saturated stars ok")

# ---------- stack_frames: a repeat fills the whole block the reference lost ----------
scene = 60 + 900 * cv2.GaussianBlur(np.random.default_rng(9).uniform(0, 1, (H, H)).astype(np.float32), (0, 0), 3)
scene = 40 + 150 * (scene - scene.min()) / (scene.max() - scene.min())
ref, rep = bgr(scene), bgr(np.where(xx > 200, np.roll(scene, 3, axis=0), scene))   # the right half moved
lost = np.ones((H, H), bool)
lost[150:240] = False
ref[~lost] = 0
stacked, valid = ic.stack_frames([ref, rep], masks=[lost, np.ones((H, H), bool)])
assert valid[:, 2:-2].all(), (~valid[:, 2:-2]).sum()
print("block the reference lost filled to its edges ok")

# ---------- fill_lines: along the slant, or left lost ----------
for angle in (1.0, 1.2, 1.3):
    u = xx * np.cos(angle) + yy * np.sin(angle)
    rings = 110 + 70 * np.sin(u / 4.0) + 30 * np.sin(u / 11.0)
    img = bgr(rings + np.random.default_rng(2).normal(0, 2, (H, H)))[..., 0]
    m = np.ones((H, H), bool)
    m[120:126, 60:110] = False
    filled, mask = ic.fill_lines(img, m)
    assert mask.all()
    miss = np.abs(filled[~m].astype(float) - rings[~m]).mean()
    assert miss < 2.5, (angle, miss)   # straight down it was out by 9 to 11 levels
blocks = cv2.resize(np.random.default_rng(3).uniform(0, 255, (50, 50)).astype(np.float32), (H, H), interpolation=cv2.INTER_NEAREST)
filled, mask = ic.fill_lines(bgr(blocks)[..., 0], m)
assert not mask[120:126, 60:110].any()   # a trial fill beside it misses: left lost
# ... but a run one of the frame's own lines tall (a 256 line frame: 4 rows of the 1024 grid) is always filled
m4 = np.ones((H, H), bool)
m4[120:124, 60:110] = False
blocky = bgr(blocks)[..., 0]
assert not ic.fill_lines(blocky, m4)[1][120:124, 60:110].any()
assert ic.fill_lines(blocky, m4, fills=ic.line_fills(blocky, m4, line=4))[1].all()
smooth = 100 + 20 * np.sin(xx / 30)
filled, mask = ic.fill_lines(bgr(smooth + np.random.default_rng(4).normal(0, 3, (H, H)))[..., 0], m)
assert mask.all() and np.abs(filled[~m].astype(float) - smooth[~m]).mean() < 3
# the same fill on another picture of the frame (its I/F): fills=
fills = ic.line_fills(bgr(rings)[..., 0], m)
f2, m2 = ic.fill_lines((rings / 255).astype(np.float32), m, fills=fills)
assert m2.all() and np.abs(f2[~m] * 255 - rings[~m]).mean() < 2.5
# every other line lost (a frame's lost packets), from columns that differ line to line: the trial has valid rows
# beside only a few pixels at a run's start, where a ringlet lies along the lines, and they are too few to judge by
ground = 100 + 20 * np.sin(xx / 30) + np.where((xx >= 150) & (xx < 160), np.where(yy % 2 == 0, 15, -15), 0)
img = bgr(ground + np.random.default_rng(10).normal(0, 1, (H, H)))[..., 0]
m = np.ones((H, H), bool)
for y in range(100, 300, 2):
    m[y, 150 if y % 4 == 0 else 160:] = False
filled, mask = ic.fill_lines(img, m)
assert mask.all(), (~mask).sum()   # 12,250 of its 24,500 pixels were left lost (black lines in a colour set)
assert np.abs(filled[~m].astype(float) - ground[~m]).mean() < 3
print("fill_lines slant and trial ok")

# ---------- garbled_lines ----------
sky = bgr(40 + 50 * np.exp(-((yy - 300) / 40) ** 2) + np.random.default_rng(5).normal(0, 1, (H, H)))[..., 0]
garbled = sky.copy()
garbled[100, 150:] = 225                                     # constant garbage from x = 150
garbled[200, 0:] = np.random.default_rng(6).integers(0, 255, H)   # a whole line of noise
garbled[250, 80:], garbled[251, 80:] = 180, 30               # two garbled lines next to each other
garbled[300, 50:200] = 0                                     # (a thin dark feature lying along part of a line: not garbage)
found = lh.garbled_lines(garbled, np.ones((H, H), bool))
assert found[100, 160:].all() and not found[100, :120].any()
assert found[200, 30:].all() and found[250, 120:].all() and found[251, 120:].all()
assert not found[300].any() and found.any(axis=1).sum() == 4, np.nonzero(found.any(axis=1))[0]
assert not lh.garbled_lines(sky, np.ones((H, H), bool)).any()
# every other line lost across bands lying along the lines (rings): lines 2 and 4 apart differ by the bands, not by
# garbage (17,585 pixels found before)
bands = 110 + 40 * np.sin(2 * np.pi * (yy + 0.02 * xx) / 14)
bands = bgr(np.where(yy < 250, bands, 60) + np.random.default_rng(11).normal(0, 0.5, (H, H)))[..., 0]
m = np.ones((H, H), bool)
for y in range(20, 240, 2):
    m[y, 150 if y % 4 == 0 else 170:] = False
bands[~m] = 0
assert not lh.garbled_lines(bands, m).any(), np.nonzero(lh.garbled_lines(bands, m).any(axis=1))[0]
print("garbled lines ok")

# ---------- spikes ----------
spots = [(rng.uniform(20, H - 20), rng.uniform(20, H - 20), 10 ** rng.uniform(1.2, 2.3)) for _ in range(40)]


def stare(k, seed):
    r = np.random.default_rng(seed)
    im = np.full((H, H), 12, np.float32)
    for y, x, b in spots:
        im += b * np.exp(-((xx - x - 0.8 * k) ** 2 + (yy - y) ** 2) / (2 * 1.2 ** 2))
    im += 60 * np.exp(-((xx - 200 - 4 * k) ** 2 + (yy - 300 - 3 * k) ** 2) / (2 * 1.2 ** 2))   # a small moon
    im += r.normal(0, 2, (H, H))
    rays = []
    for _ in range(30):
        y, x = r.integers(5, H - 5, 2)
        n = r.integers(1, 5)
        im[y, x:x + n] += r.uniform(40, 200)
        rays.append((y, x))
    return bgr(im), rays


(a, _), (b, rays), (c, _) = stare(-1, 1), stare(0, 2), stare(1, 3)
found = ic.spikes(b, [a, c])
caught = sum(bool(found[y, x]) for y, x in rays)
assert caught >= 26, caught   # (a ray landing on a star, or by chance on a neighbour's own ray, is let be)
assert not any(found[int(round(y)), int(round(x))] for y, x, _ in spots) and not found[300, 200]
assert not ic.spikes(b, [None, None]).any()
print("spikes ok")
print("ok")
