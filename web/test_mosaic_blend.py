"""The blend step (mosaic.composite, Settings > Processing > Blend mosaic seams): two tiles made with mask.png's soft
edge, overlapping by less than two soft edges. With blend on the join is opaque and the same colour as both tiles
(before it was part transparent: a dark line down the seam and a notch where it meets the mosaic's edge), the mosaic's
outer edge runs on across the seam as along any tile's edge, a lost line's gap stays a gap, two tiles of different
brightness meet without a step; with blend off the picture is drawn as before, byte for byte. Synthetic frames.
Run: python web/test_mosaic_blend.py"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calibration  # noqa: E402
import mosaic  # noqa: E402

mask = np.asarray(Image.open(os.path.join(os.path.dirname(mosaic.__file__), "mask.png")).convert("L"))
TOP = 50


def tiles(overlap, tint=1.0):
    out = []
    for i, x0 in enumerate([0, 1024 - overlap]):
        f = np.zeros((1100, 2100, 4), np.uint8)
        f[TOP:TOP + 1024, x0:x0 + 1024, :3] = np.clip(np.array((230, 215, 160)) * (tint if i else 1), 0, 255)
        f[TOP:TOP + 1024, x0:x0 + 1024, 3] = mask
        f[600:604, x0 + 300:x0 + 700, 3] = 0   # a lost line's gap
        out.append(f)
    return out


def draw(frames, off=""):
    mosaic.feather_px = 128
    mosaic.reset()
    with calibration.stepping(off):
        return mosaic.composite(frames, np.ones((len(frames), 3)))


def legacy(frames):
    """composite as it was before the blend step."""
    mosaic.feather_px = 128
    h, w = frames[0].shape[:2]
    rgb = np.zeros((h, w, 3), np.float32)
    acc = np.zeros((h, w), np.float32)
    for f in frames:
        own = f[..., 3] * np.float32(1 / 255)
        a = mosaic.feather_alpha(f[..., 3]) * acc + own * (1 - acc)
        rgb += (f[..., :3].astype(np.float32) - rgb) * a[..., None]
        acc = a + acc * (1 - a)
    rgb /= np.maximum(acc, 1e-6)[..., None]
    return np.dstack([np.clip(rgb, 0, 255).round(), (acc * 255).round()]).astype(np.uint8)


for overlap in (40, 100, 200):
    frames = tiles(overlap)
    seam = 1024 - overlap // 2
    on, off = draw(frames), draw(frames, "blend")
    assert np.array_equal(off, legacy(frames)), overlap
    old_dip = 255 - int(off[560, seam - 60:seam + 60, 3].min())
    assert on[TOP + 100:TOP + 900, seam - 80:seam + 80, 3].min() == 255, overlap
    inside = on[TOP + 100:TOP + 900, 100:1900 - overlap]
    ok = inside[..., 3] == 255
    assert np.abs(inside[ok][:, :3].astype(int) - (230, 215, 160)).max() <= 1, overlap
    # the outer edge across the seam is the edge along a tile's middle (its outermost pixel a little fainter, where
    # both tiles' corners are: _support reads them as a little slanted)
    for r in range(TOP, TOP + 60):
        assert abs(int(on[r, seam, 3]) - int(on[r, 500, 3])) <= (4 if r == TOP else 3), (overlap, r, on[r, seam, 3], on[r, 500, 3])
    # a tile's own edges and corners are as they were, less the tile's outermost RIM pixels
    R = mosaic.RIM
    assert np.array_equal(on[TOP + R:TOP + 60, 500, 3], off[TOP + R:TOP + 60, 500, 3]), overlap
    assert not on[TOP:TOP + R, :, 3].any(), overlap
    # the first tile's own soft edge lies on the canvas's border: it ends there, less its rim
    assert not on[TOP + 300, :R, 3].any() and on[TOP + 300, R, 3] == off[TOP + 300, R, 3], overlap
    assert abs(int(on[TOP + R, R, 3]) - int(off[TOP + R, R, 3])) <= 2, overlap
    # the lost line's gap in the first tile, where the second does not cover, stays a gap
    assert on[601, 400, 3] == 0 and on[596, 400, 3] == 255, overlap
    print(f"overlap {overlap}: seam opaque (was down to {255 - old_dip}/255), outer edge unbroken")

# a tile the canvas's border cuts (its picture whole there) goes on past it: no edge, no rim there
cut = tiles(40)[0]
cut[:, :-100] = cut[:, 100:].copy()
on = draw([cut])
assert on[TOP + 300, 0, 3] == 255 and on[TOP + 300, 0, 0] == 230, on[TOP + 300, :4]
print("a tile the canvas cuts keeps its picture to the canvas's border; ok")

# tiles of different brightness: no step anywhere along a row across the seam (level off: each tile its own
# brightness away from the seam; level on: leveled to each other, both meeting halfway, the difference spread
# smoothly over the tiles and each back near its own brightness far from the seam)
on = draw(tiles(40, 1.1), "level")
row = on[560, 900:1100, 0].astype(int)
assert np.abs(np.diff(row)).max() <= 3 and row[0] == 230 and row[-1] == 253, row
on = draw(tiles(40, 1.1))
row = on[560, 100:1950, 0].astype(int)
assert np.abs(np.diff(row)).max() <= 1, row
assert abs(int(on[560, 1100, 0]) - int(on[560, 900, 0])) <= 6 and 238 <= on[560, 1000, 0] <= 244, row
assert row[0] < 236 and row[-1] > 247, row
print("tiles of different brightness meet without a step, and leveled to each other; ok")

# tiles made as obs_mosaic's are: turned north up (linear, on colour and alpha apart, so the edge mixes with the black
# round it), then resized (Lanczos) to twice their size: no dark line or specks where their edges fall inside the
# mosaic, nor along its outer edge
import cv2  # noqa: E402
frames = []
for i, x0 in enumerate((0, 1300)):
    t = np.zeros((1448, 1448, 4), np.uint8)
    t[212:1236, 212:1236, :3] = (230, 215, 160)
    t[212:1236, 212:1236, 3] = mask
    t = cv2.warpAffine(t, cv2.getRotationMatrix2D((724, 724), 20, 1.0), (1448, 1448), flags=cv2.INTER_LINEAR)
    t = t[150:1300, 150:1300]
    t = np.asarray(Image.fromarray(t).resize((2300, 2300), Image.LANCZOS))
    f = np.zeros((2400, 3700, 4), np.uint8)
    f[50:2350, x0:x0 + 2300] = t
    frames.append(f)
on = draw(frames)
solid = on[..., 3] == 255
assert on[..., 0][solid].min() >= 228, on[..., 0][solid].min()
edge = (on[..., 3] > 60) & ~solid
assert on[..., 0][edge].min() >= 200, np.sort(on[..., 0][edge])[:10]
print("tiles' dark, specked edges never drawn; ok")

# what is dark in the picture itself near a tile's edge is not its rim (mosaic._rim): the sky beside a bright ring
# that crosses the edge, straight or slanted (Saturn's rings, 2013, were left out in wedges); a rim of a pixel of
# black and four at half brightness all along the edge is found
mosaic.feather_px = 128
yy, xx = np.mgrid[0:1024, 0:1024]
for slant in (0, 0.5, 2.0):
    f = np.zeros((1100, 1100, 4), np.uint8)
    picture = np.full((1024, 1024), 12, np.uint8)
    picture[(xx >= 400 + yy * slant) & (xx < 560 + yy * slant)] = 200
    f[40:1064, 40:1064, :3] = picture[..., None]
    f[40:1064, 40:1064, 3] = mask
    dist = mosaic._inside((f[..., 3] > 0).astype(np.uint8), np.zeros(f.shape[:2], bool))
    rim = mosaic._rim(mosaic._colors(f), dist > 0, dist)
    assert rim is None or (rim & (dist > 1.5)).sum() < 20, (slant, (rim & (dist > 1.5)).sum())
good = (f[..., 3] >= 40).astype(np.uint8)
d = cv2.distanceTransform(np.pad(good, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
f[..., :3] = 150
f[(d > 0) & (d <= 1), :3] = 0
f[(d > 1) & (d <= 5), :3] = 75
dist = mosaic._inside((f[..., 3] > 0).astype(np.uint8), np.zeros(f.shape[:2], bool))
rim = mosaic._rim(mosaic._colors(f), dist > 0, dist)
assert rim is not None and rim[(good > 0) & (d <= 5)].all(), rim[(good > 0) & (d <= 5)].mean()
# and drawn where nothing is below it, the rim has the colour of the picture next to it, not its own dark one (a
# tile drawn over it later would show a faint line of it in its bands of detail)
on = draw([f])
assert on[..., 0][on[..., 3] > 0].min() >= 145, on[..., 0][on[..., 3] > 0].min()
print("a ring's dark sky at a tile's edge is picture, a dark rim is not, and is never drawn dark; ok")

# where tiles do not quite meet (two tiles 36 px apart under a third that spans both), the gap between them keeps a
# soft edge, as the mosaic's outer edge does
frames = []
for x0, y0 in ((0, 0), (1000, 0), (-30, 1000), (1030, 1000)):
    f = np.zeros((2100, 2100, 4), np.uint8)
    xa, ya = max(x0, 0), y0
    f[ya:ya + 1024, xa:x0 + 1024, :3] = (230, 215, 160)
    f[ya:ya + 1024, xa:x0 + 1024, 3] = mask[:, xa - x0:]
    frames.append(f)
on = draw(frames)
row = on[1600, 900:1012, 3].astype(int)
assert row[0] == 255 and row[-1] == 0 and np.all(np.diff(row) <= 0) and (row > 0).sum() - (row == 255).sum() > 30, row
print("a gap between tiles keeps a soft edge; ok")

# a mosaic grown a tile at a time over the picture so far (obs_mosaic.draw_over: the part of the picture round the
# tile, composed with the tile as a picture drawn so far, under=0), the same place drawn again and again as a mosaic
# movie's is: the picture's outer edge round it, a neighbour's, stays as it was drawn, never eaten into a few pixels
# with every tile drawn near it (its first pixels may settle by a level or three onto the soft edge's own profile,
# then stay)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic  # noqa: E402
pic = draw(tiles(40))
first = pic.copy()
t = tiles(40)[1]
ys, xs = np.nonzero(t[..., 3])
part = t[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
with calibration.stepping(""):
    for i in range(12):
        last = pic.copy()
        obs_mosaic.draw_over(pic, lambda: part, int(xs.min()), int(ys.min()), part.shape[1], part.shape[0], 1.0,
                             match=False)
grown = np.abs(pic[..., 3].astype(int) - first[..., 3])
assert grown.max() <= 3, (grown.max(), np.argwhere(grown > 3)[:5])
assert np.abs(pic[..., 3].astype(int) - last[..., 3]).max() <= 1
print("a picture grown over and over keeps its outer edge; ok")

# a tile drawn again over a picture's outer edge (a mosaic movie's lap redrawing its bottom row), a little brighter
# than it: the picture changes over across the tile's edge there as it does inside, not in a step (the picture's
# weight was 0 near its edge, so the tile took over at once)
pic = draw(tiles(40)[:1] + [tiles(140)[1]])
t = tiles(40)[0][TOP:TOP + 1024, :1024].copy()
t[..., :3] = (t[..., :3] * 1.04).astype(np.uint8)
with calibration.stepping(""):
    obs_mosaic.draw_over(pic, lambda: t, 0, TOP, 1024, 1024, 1.0, match=False)
for r in (TOP + 1000, TOP + 1012):
    assert pic[r, 1000, 3] > 0 and np.abs(np.diff(pic[r, 900:1100, 0].astype(int))).max() <= 2, (r, pic[r, 900:1100:10, 0])
print("a tile drawn again over a picture's outer edge changes over smoothly there; ok")

# the same two tiles in three filters, each with its own noise, the second a little brighter in all: the seam's cut
# runs along the middle of the overlap in every filter (where the two barely differ it ran wherever the noise led it,
# and a colour mosaic's filters were cut tens of pixels apart: coloured stripes)
cuts, seam_cut = [], mosaic._seam_cut


def caught(a, has, below, color, under):
    seam, cut = seam_cut(a, has, below, color, under)
    rows = range(200, 800)   # (away from the tiles' corners, where the overlap's middle bends)
    cuts.append((np.array([np.argmax(seam[r] > 0.5) for r in rows]), np.array([np.argmax(a[r] >= 0.5) for r in rows])))
    return seam, cut


mosaic._seam_cut = caught
try:
    for seed in (1, 2, 3):
        noisy = tiles(200, 1.15)
        for f in noisy:
            f[..., :3] = np.clip(f[..., :3] * 0.3 + np.random.default_rng(seed).normal(0, 2, f.shape[:2])[..., None], 0, 255)
        draw(noisy, "level")
finally:
    mosaic._seam_cut = seam_cut
assert len(cuts) == 3 and all(np.abs(c - mid).max() <= 3 for c, mid in cuts), [np.abs(c - mid).max() for c, mid in cuts]
assert all(np.abs(c - cuts[0][0]).max() <= 2 for c, _ in cuts), [np.abs(c - cuts[0][0]).max() for c, _ in cuts]
print("where the tiles barely differ, every filter's seam is cut along the overlap's middle; ok")

# a mosaic grown a tile at a time over a first lap that is darker than the laps after it (a mosaic movie's place
# seen again later, brighter than the gains' limit lets a tile be matched to): with the level step the picture
# brightens with the later laps as with blend alone (leveled to the picture so far on the whole, it stayed at the
# first lap's level: Saturn's movie of 2013 drawn whole came out 25% darker)
import seam_synth  # noqa: E402
rng = np.random.default_rng(0)
ground = np.full((900, 900), 150, np.float32) + cv2.GaussianBlur(rng.normal(0, 6, (900, 900)).astype(np.float32), (0, 0), 3)
laps = [[np.clip(f.astype(np.float32) * np.array([0.7 if lap == 0 else 1.0] * 3 + [1]), 0, 255).astype(np.uint8)
         for f, _ in seam_synth.tiles(ground, side=340, grid=(2, 2), overlap=(30, 60), seed=lap % 3, slope=0.05)]
        for lap in range(6)]
level = {}
for off in ("level", ""):
    with calibration.stepping(off):
        pic = seam_synth.compose(laps[0], off=off).copy()
        for lap in laps[1:]:
            for f in lap:
                ys, xs = np.nonzero(f[..., 3])
                part = f[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                obs_mosaic.draw_over(pic, lambda: part, int(xs.min()), int(ys.min()), part.shape[1], part.shape[0], 0.5)
    inner = cv2.erode((pic[..., 3] == 255).astype(np.uint8), np.ones((61, 61), np.uint8)) > 0
    level[off] = float(np.median(pic[..., 0][inner]))
assert level[""] > 0.96 * level["level"] and level["level"] > 120, level
print(f"a grown picture follows later, brighter laps with the level step too ({level[''] :.0f} vs {level['level']:.0f}); ok")

# a mosaic movie's laps over a disc that gets smaller by 10 px a lap: an older lap's limb does not show past the
# newest one along the mosaic's edge, where the newest lap's tiles come in near their own edges (the picture drawn
# so far weighed in there, and Saturn's limb of 2013 showed twice, with a bright sliver between)
yy, xx = np.mgrid[0:1100, 0:1100].astype(np.float32)
r = np.hypot(xx - 640, yy - 560)
texture = cv2.GaussianBlur(rng.normal(0, 8, (1100, 1100)).astype(np.float32), (0, 0), 2)
radii = [360 - 10 * lap for lap in range(5)]
laps = [[f for f, _ in seam_synth.tiles(3 + (165 + texture) * np.clip((R - r) / 2 + 0.5, 0, 1), side=420, grid=(2, 2),
                                        overlap=(30, 60), seed=lap % 3 + 1, noise=1.0, gain=0.03, slope=0.03,
                                        falloff=0.05, pointing=1.0)]
        for lap, R in enumerate(radii)]
newest = np.any([f[..., 3] >= 250 for f in laps[-1]], axis=0)
twice = {}
for off in ("blend,level", "level"):
    with calibration.stepping(off):
        pic = seam_synth.compose(laps[0], off=off).copy()
        for lap in laps[1:]:
            for f in lap:
                ys, xs = np.nonzero(f[..., 3])
                part = f[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                obs_mosaic.draw_over(pic, lambda: part, int(xs.min()), int(ys.min()), part.shape[1], part.shape[0], 0.5)
    sky = (pic[..., 3] == 255) & newest & (r > radii[-1] + 4) & (r < radii[0] + 6)
    twice[off] = float(np.mean(pic[..., 0][sky] > 30))
assert twice["level"] <= 0.7 * twice["blend,level"], twice
print(f"an older lap's limb does not show past the newest ({twice['level']:.1%} of the sky past it lit, "
      f"{twice['blend,level']:.1%} before); ok")

# a tile with a lost line (a row of alpha 0) turned 20 degrees onto the canvas, nothing else there: along the line
# its alpha is 0 at a pixel here and there among low alpha, and those pixels were drawn as holes (black dots in a
# colour mosaic, where the colour is only where every filter has picture: Enceladus, 2005)
t = np.zeros((420, 420, 4), np.float32)
t[..., :3] = 150
t[..., 3] = cv2.resize(mask, (420, 420), interpolation=cv2.INTER_AREA)
t[200, :, 3] = 0
turn = cv2.getRotationMatrix2D((210, 210), 20, 1.0)
turn[:, 2] += 190
f = np.clip(cv2.warpAffine(t, turn, (800, 800), flags=cv2.INTER_LINEAR) + 0.5, 0, 255).astype(np.uint8)
off_line = cv2.warpAffine(np.pad(np.ones((340, 340), np.float32), 40), turn, (800, 800)) > 0.99
assert (f[..., 3][off_line] == 0).any()   # (the holes are there to be drawn)
on = draw([f])
assert on[..., 3][off_line].min() == 255 and on[..., 0][off_line].min() >= 148, (on[..., 3][off_line].min(), on[..., 0][off_line].min())
print("a turned tile's lost line has no holes; ok")

# a tile drawn over a picture whose bottom band is darker (an older lap there, along the mosaic's edge, as a movie
# brightens lap by lap), its bottom edge 8 px above the picture's: with the level step it is not leveled down to that
# band where none of the picture is left past its edge (it was, and every lap of Saturn's 2013 movie was leveled
# down to the one before along the bottom edge: a band 20% dark); its sides still meet the band where it goes on past
# them, so it is leveled a little toward it there
pic = np.zeros((1400, 1400, 4), np.uint8)
pic[100:1300, 100:1300, :3] = 180
pic[1180:1300, 100:1300, :3] = 135
pic[100:1300, 100:1300, 3] = cv2.resize(mask, (1200, 1200), interpolation=cv2.INTER_AREA)
t = np.zeros((600, 600, 4), np.uint8)
t[..., :3] = 180
t[..., 3] = cv2.resize(mask, (600, 600), interpolation=cv2.INTER_AREA)
bottom = {}
for off in ("level", ""):
    p = pic.copy()
    with calibration.stepping(off):
        obs_mosaic.draw_over(p, lambda: t, 400, 692, 600, 600, 1.0)
    bottom[off] = float(np.median(p[1232:1272, 600:800, 0]))
assert bottom[""] >= bottom["level"] - 12, bottom
print(f"a tile is not leveled down to an older band along the mosaic's edge ({bottom[''] :.0f} vs {bottom['level']:.0f}); ok")
