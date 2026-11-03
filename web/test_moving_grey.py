"""Grey where a moving body can't register (fix plan PR 5): after a colour set is aligned on its target, what moved
between the filters (a second moon's copies, a moon over the rings, Saturn's limb behind a moon: Mimas 126MI's magenta
square) is drawn grey from the reference frame (color_image.moved_region, grey_plan, grey_from, neutral), while a
colour of the surface (a methane band: Saturn dark where the rings are bright), a tint of the whole picture, stars and
cosmic rays keep their colour. Synthetic frames.
Run: python web/test_moving_grey.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import calibration as cal  # noqa: E402
import color_image as ci  # noqa: E402

N = 1024
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
rng = np.random.default_rng(5)


def disk(cx, cy, r, soft=2.0):
    return np.clip((r - np.hypot(xx - cx, yy - cy)) / soft + 0.5, 0, 1).astype(np.float32)


def noisy(a, s=0.002):
    return (a + rng.normal(0, s, a.shape)).astype(np.float32)


def at(region, x, y):
    return float(region[int(y), int(x)])


# ---------- a second moon whose copies sit apart (Enceladus 2015) ----------
moon = disk(512, 512, 160)
chans = [noisy(0.9 * moon + 0.6 * disk(200 + 40 * j, 800, 14)) for j in range(3)]
region = ci.moved_region(chans, 1, None)
assert region is not None and not isinstance(region, str)
for j in range(3):
    assert at(region, 200 + 40 * j, 800) == 1.0, j      # every copy
assert at(region, 512, 512) == 0.0 and at(region, 512, 380) == 0.0   # the target, aligned, keeps its colour
assert at(region, 900, 100) == 0.0                                     # the sky far off
grey = ci.grey_from(chans, 1, region)
assert all(abs(grey[j][800, 200 + 40 * k] - grey[1][800, 200 + 40 * k]) < 1e-6 for j in range(3) for k in range(3))
print("second moon's copies: grey,", round(float(region.mean()), 4), "of the picture")

# ---------- Saturn's limb behind a moon, in one filter only (Mimas 126MI, N1644787450_1) ----------
saturn = np.full((N, N), 0.45, np.float32)
limb = np.clip((620 - xx) / 40 + 0.5, 0, 1)     # the green frame's limb: Saturn left of it, sky right
mimas = disk(470, 540, 440)
g = [0.6, 0.45, 0.42]
chans = [noisy(np.maximum(mimas, g[j] * (limb if j == 1 else 1) * saturn / 0.45)) for j in range(3)]
region = ci.moved_region(chans, 2, None)
assert region is not None and not isinstance(region, str)
assert at(region, 1000, 40) == 1.0 and at(region, 1000, 1000) == 1.0 and at(region, 640, 20) == 1.0
assert at(region, 470, 540) == 0.0 and at(region, 60, 40) == 0.0     # Mimas and Saturn's other side keep their colour
plan = ci.grey_plan(["phase +0.8,-0.3", "phase +5.0,+0.2", "reference"], chans, 2)
assert plan[0] == "moved" and plan[1] is not None
print("Saturn's limb in one filter: grey,", round(float(region.mean()), 4), "of the picture")

# ---------- colours of the surface stay ----------
rings = ((np.abs((yy - 512) - 0.3 * (xx - 512)) < 60) & (np.hypot(xx - 512, yy - 512) > 260)).astype(np.float32)
planet = disk(512, 512, 250)
# a methane band: Saturn 25 times fainter than in the continuum, its rings as bright, every edge where it was
chans = [noisy(0.8 * planet * (1 - rings) + 0.9 * rings), noisy(0.03 * planet * (1 - rings) + 0.9 * rings),
         noisy(0.7 * planet * (1 - rings) + 0.8 * rings)]
assert ci.moved_region(chans, 0, None, ["CB2", "MT2", "CB3"]) is None
assert ci.moved_region(chans, 1, None, ["CB2", "MT2", "CB3"]) is None     # the methane band the reference
assert ci.other_layer("MT3") and ci.other_layer("CL1/UV3") and ci.other_layer("IR2/MT2")
assert not ci.other_layer("RED") and not ci.other_layer("CB3") and not ci.other_layer("CL1/CL2")
# a body twice as red as the rest of the picture
chans = [noisy(0.8 * planet + 0.5 * rings), noisy(0.4 * planet + 0.5 * rings), noisy(0.35 * planet + 0.5 * rings)]
assert ci.moved_region(chans, 1, None) is None
# the whole picture tinted (the channels on one scale, a filter brighter)
assert ci.moved_region([c * k for c, k in zip(chans, (1.0, 1.6, 0.5))], 1, None) is None
# a star field that moved a little (stars, cosmic rays: no bodies)
stars = rng.integers(20, N - 20, (60, 2))
field = lambda dx: noisy(sum(disk(x + dx, y, 1.2, 0.7) for x, y in stars) + 0.9 * planet)  # noqa: E731
ray = field(0)
ray[300:302, 100:400] += 1.0                                   # a cosmic ray in one frame
assert ci.moved_region([ray, field(0), field(3)], 1, None) is None
# a small crescent over a sky glow tinted in one filter (N1358114660_1's set, Mini): the glow is no body
crescent = disk(512, 380, 40) * (1 - disk(512, 350, 45))
glow = np.clip(1 - np.hypot(xx - 512, yy - 512) / 700, 0, 1) * 0.03
chans = [noisy(crescent + glow), noisy(crescent + glow * 0.1), noisy(crescent + glow * 0.08)]
assert ci.moved_region(chans, 1, None) is None
print("methane band, red body, tint, stars, cosmic ray, a crescent's tinted glow: colour kept")

# ---------- moved over most of the picture: the whole set grey ----------
band = lambda dy: noisy(((np.abs((yy - 512 - dy) - 0.3 * (xx - 512)) % 160) < 50).astype(np.float32) * 0.8)  # noqa
assert ci.moved_region([band(0), band(60), band(120)], 1, None) == "whole"
moved = [band(0), band(60), band(120)]
assert ci.grey_plan(["phase +0.1,+0.0", "reference", "phase +0.2,+0.1"], moved, 1) == ("moved", None)
print("rings moved across the whole picture: the whole set grey")

# ---------- drawn channels (a mosaic's or movie's 8-bit path) and the plan's other answers ----------
draw = lambda a: cv2.cvtColor(np.clip(a * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)  # noqa: E731
chans = [draw(0.9 * moon + 0.6 * disk(200 + 40 * j, 800, 14)) for j in range(3)]
region = ci.moved_region(chans, 1, None)
assert region is not None and at(region, 200, 800) == 1.0 and at(region, 512, 512) == 0.0
out = ci.grey_from(chans, 1, region)
assert out[0].dtype == np.uint8 and out[0][800, 200].tolist() == chans[1][800, 200].tolist()
assert ci.grey_plan(["off", "off", "off"], chans, 1) == (None, None)            # the viewer's own choice
assert ci.grey_plan(["reference", "not aligned", "phase +0.1,+0.0"], chans, 0) == ("not aligned", None)
assert ci.grey_plan(["reference"], chans[:1], 0) == (None, None)
assert ci.moved_region([c * 0 for c in chans], 1, None) is None                # a black frame
print("drawn channels and the plan's answers")

# ---------- a soft region and the false color mix: neutral where grey, untouched elsewhere ----------
soft = np.zeros((8, 8), np.float32)
soft[:, 4:] = 1.0
soft[:, 3] = 0.5
drawn = [np.full((8, 8, 3), v, np.uint8) for v in (40, 120, 200)]
part = ci.grey_from(drawn, 1, soft)
assert part[0][0, 0].tolist() == [40] * 3 and part[0][0, 6].tolist() == [120] * 3 and part[0][0, 3].tolist() == [80] * 3
n = ci.neutral(drawn, soft)
assert n[0][0, 0].tolist() == [40] * 3 and n[2][0, 0].tolist() == [200] * 3
assert all(n[j][0, 6].tolist() == [120] * 3 for j in range(3))
lin = [np.clip(rng.normal(0.3, 0.1, (64, 64)), 0, 1).astype(np.float32) * k for k in (1.0, 0.7, 1.4)]
reg = np.zeros((64, 64), np.float32)
reg[:, 32:] = 1.0
mix = np.diag(np.asarray([1.0, 1.5, 3.0], np.float32)).view(cal.FalseMix)
mix.tint = None
args = ci._greyed(lin, (lin, 0.01, mix), 1, ["phase +0.2,+0.0", "reference", "phase +0.1,+0.0"], "moved", reg)
assert args[2] is mix and np.array_equal(args[0][0][:, 40:], lin[1][:, 40:])
assert np.array_equal(args[0][0][:, :10], lin[0][:, :10])
out = ci.neutral(cal.tone(*args), reg)
assert np.array_equal(out[0][:, 40:], out[2][:, 40:])          # grey where it moved, whatever the mix's gains
assert not np.array_equal(out[0][:, :10], out[2][:, :10])      # colour elsewhere
sat = ci._saturated_masks([np.ones((64, 64), np.float32)] * 3, reg)
assert not sat[0][:, 40:].any() and sat[0][:, :10].all()       # no saturated fill where grey
print("soft region, false color mix, saturated fill")
print("ok")
