"""Wild alignment fits (fix plan PR 3): a colour set's star, edge or centroid fit far from SPICE's offset is rejected
(image_correction._plausible, FIT_REACH), stars are matched only on a black sky (star_shift, STAR_DARK), a tiny SPICE
offset is taken as it is (spice_shift, SPICE_SURE), and a set with a channel nothing places is drawn grey from the
reference (color_image.unaligned, grey_from), never in colours that sit apart. Synthetic frames.
Run: python web/test_wild_fits.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import image_correction as ic  # noqa: E402

rng = np.random.default_rng(7)
N = 1024
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
ones = lambda: np.ones((N, N), bool)  # noqa: E731
bgr = lambda a: cv2.cvtColor(np.clip(a, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)  # noqa: E731


def rings(dx, dy, band, seed):
    """A frame filled by rings (Grand Finale, N1877994287_1): ringlets across the whole frame, each filter seeing them
    with its own contrast, and sharp specks of ring texture that star_points takes for stars"""
    r = (xx - dx) * 0.8 + (yy - dy) * 0.6
    a = 120 + 40 * np.sin(r / 7.0) + 25 * np.sin(r / 2.3 + band) + 15 * np.sin(r / 31.0)
    g = np.random.default_rng(seed)
    for x, y in g.integers(20, N - 20, (120, 2)):
        a += 60 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 2.0)
    return bgr(a + g.normal(0, 2, a.shape))


def disk(dx, dy, seed, r0=700):
    """Titan close up (N1881184559_1): a lit disk over most of the frame, its haze smooth, its noise speckled"""
    d = np.hypot(xx - 300 - dx, yy - 900 - dy)
    a = np.where(d < r0, 200 - 0.08 * d, 2.0)
    g = np.random.default_rng(seed)
    for x, y in g.integers(20, N - 20, (60, 2)):
        a += 40 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.5)
    return bgr(a + g.normal(0, 1.5, a.shape))


# ---------- stars only on a black sky ----------
a, b = rings(0, 0, 0, 1), rings(3, 1, 1, 1)   # the same specks in both: they vote for a false (0, 0) or worse
assert ic.lit_share(a) > ic.STAR_DARK
assert ic.star_shift(a, b) is None
assert ic.star_shift(disk(0, 0, 2), disk(2, 1, 2)) is None
stars = [tuple(v) for v in rng.integers(30, N - 30, (90, 2))]


def field(dx, dy):
    im = rng.normal(10, 1.5, (N, N)).astype(np.float32)
    for x, y in stars:
        im += 120 * np.exp(-((xx - x - dx) ** 2 + (yy - y - dy) ** 2) / (2 * 1.2 ** 2))
    return bgr(im)


f0, f1 = field(0, 0), field(12.6, -33.4)
assert ic.lit_share(f0) < ic.STAR_DARK
s = ic.star_shift(f0, f1)
assert s is not None and np.hypot(s[0] - 12.6, s[1] + 33.4) < 0.3, s
print("stars: ring frame", round(ic.lit_share(a), 2), "refused; star field", round(ic.lit_share(f0), 4), "kept")

# ---------- a fit far from SPICE is rejected ----------
assert ic._plausible((32.0, -91.9), "stars", (1.0, -2.0), []) == (None, "stars")
rej = []
assert ic._plausible((5.0, 3.0), "edges", (1.0, -2.0), rej) == ((5.0, 3.0), "edges") and not rej
assert ic._plausible((98.0, 0.0), "stars", None, rej) == ((98.0, 0.0), "stars") and not rej   # no SPICE: as before
ic._plausible((98.0, 0.0), "stars", (0.5, 0.5), rej)
assert rej == ["stars +98.0,+0.0"], rej

# a star field whose star fit is 98 px from where SPICE puts the frame: rejected, SPICE stands (the stars matched
# themselves, the target moved as SPICE says), and the report says what was rejected. Phase correlation is held off
# here (on the real frames it fails: different filters, a disk filling the frame)
f2 = field(98.0, 0.0)
find_shift = ic.find_shift
ic.find_shift = lambda *a, **k: None
rep, found = [], []
ic.align_with_masks([f0.copy(), f2.copy()], [ones(), ones()], 0, rep, found=found, guess=[None, (1.5, 0.0)])
assert rep[1].startswith("SPICE") or rep[1].startswith("not aligned"), rep
assert "(stars +98.0," in rep[1] and "rejected)" in rep[1], rep
print("98 px star fit:", rep[1])
# without SPICE the star fit stands, as before
rep = []
ic.align_with_masks([f0.copy(), f2.copy()], [ones(), ones()], 0, rep)
assert rep[1].startswith("stars +98.0"), rep
ic.find_shift = find_shift

# ---------- weak phase and edge peaks that agree near SPICE are believed (a colour set's channels only) ----------
def fake(values):
    seq = list(values)
    return lambda a, b, max_shift=100, min_response=0.3: None if min_response >= ic.GUESS_RESPONSE else seq.pop(0)


centroid = ic.centroid_shift
ic.centroid_shift = lambda *a, **k: None
ic.find_shift = fake([(9.7, 5.8), (9.2, 7.8)])
got = ic.guided_shift(f0, f0, (-27.6, 168.8), weak=True)
assert got[1] == "phase and edges near SPICE" and np.hypot(got[0][0] + 18.15, got[0][1] - 175.6) < 0.01, got
ic.find_shift = fake([(9.7, 5.8), (2.0, -4.0)])          # they disagree: nothing
assert ic.guided_shift(f0, f0, (-27.6, 168.8), weak=True) == (None, "not aligned")
ic.find_shift = fake([(9.7, 5.8), (9.2, 7.8)])          # a mosaic's tiles (no weak): as before
assert ic.guided_shift(f0, f0, (-27.6, 168.8), window=8) == (None, "not aligned")
ic.find_shift, ic.centroid_shift = find_shift, centroid
print("weak peaks agreeing near SPICE:", got)

# ---------- a tiny SPICE offset is taken as it is ----------
blank = bgr(rng.normal(20, 2, (N, N)))
assert ic.spice_shift(a, blank, ones(), ones(), (0.5, -1.0)) == ((0.5, -1.0), "SPICE")
assert ic.spice_shift(a, blank, ones(), ones(), (40.0, -50.0)) == (None, "not aligned")

# ---------- not aligned: grey from the reference ----------
assert color_image.unaligned(["reference", "phase +1.0,+0.0", "not aligned"])
assert color_image.unaligned(["failed", "failed"])
assert not color_image.unaligned(["reference", "SPICE +0.5,-1.0"])
assert not color_image.unaligned(["off", "off", "off"])
assert not color_image.unaligned(["not aligned"])   # one frame is no set
chans = [np.full((4, 4), v, np.float32) for v in (0.2, 0.5, 0.9)]
grey = color_image.grey_from(chans, 1)
assert all(np.array_equal(c, chans[1]) for c in grey) and grey[0] is not chans[1]
# region (PR 5's moving bodies): only those pixels
region = np.zeros((4, 4), bool)
region[0, 0] = True
part = color_image.grey_from(chans, 1, region)
assert part[0][0, 0] == 0.5 and part[0][1, 1] == np.float32(0.2) and part[2][0, 0] == 0.5
drawn = [np.full((4, 4, 3), v, np.uint8) for v in (10, 50, 90)]
part = color_image.grey_from(drawn, 2, region)
assert part[0][0, 0].tolist() == [90] * 3 and part[0][1, 1].tolist() == [10] * 3 and part[0].dtype == np.uint8
# the linear path: calibration.tone of the greyed channels (no mix) is neutral, whatever the set's mix was
lin = [np.clip(rng.normal(0.3, 0.1, (64, 64)), 0, 1).astype(np.float32) * k for k in (1.0, 0.7, 1.4)]
mix = np.eye(3) * [1.3, 1.0, 0.6]
args = color_image._greyed(lin, (lin, 0.01, mix), 1, ["reference", "not aligned", "phase +0.1,+0.0"])
assert args[2] is None
out = cal.tone(*args)
assert np.array_equal(out[0], out[1]) and np.array_equal(out[1], out[2])
args = color_image._greyed(lin, (lin, 0.01, mix), 1, ["phase +0.2,+0.0", "reference", "phase +0.1,+0.0"])
assert args[0] is lin and args[2] is mix
print("not aligned: grey from the reference")
print("ok")
