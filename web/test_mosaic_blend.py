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
    # the outer edge across the seam is the edge along a tile's middle
    for r in range(TOP, TOP + 60):
        assert abs(int(on[r, seam, 3]) - int(on[r, 500, 3])) <= 3, (overlap, r, on[r, seam, 3], on[r, 500, 3])
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
