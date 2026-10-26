"""Synthetic check that obs_mosaic._lit_crop (a tile's picture resized from its canvas's lit part and cut to its lit
pixels) gives the bytes and the place the tile had from PIL's resize of the whole canvas, cut to the lit rows and columns
of its alpha: canvases lit nowhere, at one pixel, everywhere, in a box, a disk, a turned frame, with holes, at an edge,
resized down, up and not at all.
Run: python web/test_lit_resize.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(8)


def canvas(n, kind):
    im = np.zeros((n, n, 4), np.uint8)
    if kind == "nothing":
        return im
    if kind == "pixel":
        y, x = rng.integers(0, n, 2)
        im[y, x] = rng.integers(1, 256, 4)
        return im
    if kind == "everywhere":
        im[:] = rng.integers(0, 256, (n, n, 4))
        im[..., 3] |= 1
        return im
    y0, x0 = rng.integers(0, n - 1, 2)
    if kind == "edge":
        y0 = 0 if rng.random() < .5 else y0
        x0 = 0 if rng.random() < .5 else x0
    hh, ww = rng.integers(1, n - y0 + 1), rng.integers(1, n - x0 + 1)
    if kind == "edge":
        hh, ww = n - y0, n - x0
    block = rng.integers(0, 256, (hh, ww, 4)).astype(np.uint8)
    yy, xx = np.mgrid[:hh, :ww]
    if kind == "disk":
        inside = (yy - hh / 2) ** 2 / max(hh / 2, 1) ** 2 + (xx - ww / 2) ** 2 / max(ww / 2, 1) ** 2 < 1
    elif kind == "holes":
        inside = rng.random((hh, ww)) < .7
    elif kind == "turned":
        u, v = (xx - ww / 2) * .88 - (yy - hh / 2) * .48, (xx - ww / 2) * .48 + (yy - hh / 2) * .88
        inside = (abs(u) < ww / 3) & (abs(v) < hh / 3)
    else:
        inside = np.ones((hh, ww), bool)
    # an unlit pixel of a canvas can still hold colour: premultiplied, it is 0 all the same
    block[..., 3] = np.where(inside, np.maximum(block[..., 3], 1), 0)
    im[y0:y0 + hh, x0:x0 + ww] = block
    return im


def whole(im, side):
    """The tile as it was made: PIL's resize of the whole canvas (none at its own size), cut to the rows and columns
    where its alpha is lit; (cut, top, left) or None"""
    small = np.asarray(Image.fromarray(im).resize((side, side), Image.LANCZOS)) if side != im.shape[0] else im
    rows, cols = np.flatnonzero(small[..., 3].any(1)), np.flatnonzero(small[..., 3].any(0))
    if not len(rows):
        return None
    a, b, c, d = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    return np.ascontiguousarray(small[a:b, c:d]), a, c


def same(im, side):
    want, got = whole(im, side), om._lit_crop(im, side)
    if want is None or got is None:
        return want is None and got is None
    return (got[0].dtype == want[0].dtype and got[0].shape == want[0].shape and np.array_equal(got[0], want[0])
            and (got[1], got[2]) == (want[1], want[2]))


checks = 0
for trial in range(320):
    n = int(rng.choice([5, 16, 37, 100, 211, 300]))
    kind = ("nothing", "pixel", "everywhere", "box", "disk", "holes", "turned", "edge")[trial % 8]
    im = canvas(n, kind)
    side = n if trial % 4 == 3 else max(1, round(n * rng.uniform(0.4, 1.6)))
    assert same(im, side), (n, kind, side)
    checks += 1
# a movie tile's canvas: 3072 px, the frame turned in its middle
im = np.zeros((3072, 3072, 4), np.uint8)
im[843:2228, 843:2228] = canvas(1385, "turned")[:, :, :]
for side in (3027, 3072, 3101):
    assert same(im, side), side
    checks += 1
print(f"{checks} checks ok")
