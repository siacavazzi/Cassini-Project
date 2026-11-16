#!/usr/bin/env python3
"""Speed-ups that must give the same numbers to the bit as the code they replace (2026-11-16): each is checked here
against the old way, written out.
- calibration.saturated_code: each saturated patch's median from the saturated pixels alone, not from a sort of the
  whole frame;
- obs_mosaic.hdr_map: the tile's alpha as _place drew it (moved by a part of a pixel), not the tile moved again;
- obs_mosaic._brightest: the brightest of three channels, a plane at a time;
- obs_mosaic._ring_profile / ring_places: a tile's ring bins worked out once, not at every place tried.
Run: python web/test_pass_speedups.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage  # noqa: E402
import calibration as cal  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(11)


def same(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


# ---------- saturated_code: as with the whole frame's medians ----------
def saturated_code_before(iof, full, draw):
    """calibration.saturated_code as it was: ndimage.median over the whole frame."""
    full = np.asarray(full, bool)
    iof = np.asarray(iof, np.float32)
    count, labels = cv2.connectedComponents(full.astype(np.uint8), connectivity=8)
    side = 2 * cal.SAT_RING + 1
    ring = cv2.dilate(full.astype(np.uint8), np.ones((side, side), np.uint8)).astype(bool) & ~full
    near = cv2.dilate(labels.astype(np.float32), np.ones((side, side), np.uint8))
    index = np.arange(1, count)
    level = np.zeros(count, np.float32)
    smooth = np.zeros(count, np.float32)
    if count > 1:
        level[1:] = ndimage.median(iof, labels, index)
        near = near.astype(np.int32)
        on = ring & (near > 0)
        if on.any():
            v, k = iof[on], near[on]
            round_it = ndimage.labeled_comprehension(v, k, index, lambda q: np.percentile(q, cal.SAT_RING_PCT), np.float32, 0.0)
            close = ndimage.mean((v >= cal.SAT_NEAR * level[k]).astype(np.float32), k, index)
            smooth[1:] = np.clip((np.nan_to_num(close) - cal.SAT_SMOOTH[0]) / (cal.SAT_SMOOTH[1] - cal.SAT_SMOOTH[0]), 0, 1)
            level[1:] = np.maximum(level[1:], np.minimum(round_it, cal.SAT_RING_MOST * level[1:]))
    codes = draw(level[None, :]).astype(np.float32)[0]
    w = np.clip((codes - cal.SAT_WHITE[0]) / float(cal.SAT_WHITE[1] - cal.SAT_WHITE[0]), 0, 1)
    codes = codes + (255 - codes) * (w * w * (3 - 2 * w))
    codes = 255 - (255 - codes) * smooth
    return (codes[labels[full]] + 0.5).astype(np.uint8)[:, None]


draw = lambda v: np.clip(v * 4000, 0, 255)      # (I/F -> display codes, as load_channels' display(...)[..., 0])
for trial in range(60):
    h = int(rng.choice([48, 128, 256]))
    iof = rng.normal(0.02, 0.01, (h, h)).astype(np.float32)
    if trial % 3 == 0:
        iof[rng.random((h, h)) < 0.05] = 0.0        # equal values, zeros
    if trial % 5 == 0:
        iof.flat[rng.integers(0, h * h, 4)] = -0.0
    full = rng.random((h, h)) < rng.choice([0.002, 0.02, 0.3, 0.95])
    if trial % 7 == 0:
        full = cv2.dilate(full.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0     # patches, not lone pixels
    if trial == 0:
        full[:] = True
    if not full.any():
        continue
    assert same(cal.saturated_code(iof, full, draw), saturated_code_before(iof, full, draw)), trial
print("saturated_code: the same codes as with the whole frame's medians")

# ---------- _brightest ----------
for shape in ((7, 5, 4), (300, 211, 4), (64, 64, 3)):
    a = rng.integers(0, 256, shape, dtype=np.uint8)
    assert same(om._brightest(a), a[..., :3].max(axis=2))
print("_brightest: max(axis=2) of the colour channels")

# ---------- a tile's alpha moved by a part of a pixel is the same whatever its shade ----------
for trial in range(40):
    h, w = int(rng.integers(20, 200)), int(rng.integers(20, 200))
    part = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
    part[..., 3] = np.where(rng.random((h, w)) < 0.2, 0, rng.choice([255, 255, 255, 128, 3], (h, w)))
    part[:3] = 0
    shaded = om._shade(part, {"gain": float(rng.choice([0.4, 0.75, 1.3, 2.0])), "gamma": float(rng.choice([1.5, 2.2, 3.0]))})
    assert same(shaded[..., 3], part[..., 3]) and not same(shaded, part)
    fx, fy = (float(v) for v in rng.uniform(-0.5, 0.5, 2))
    assert same(om._subpixel(shaded, fx, fy)[..., 3], om._subpixel(part, fx, fy)[..., 3]), trial

# ---------- hdr_map: with the alpha _place drew, as with the tile moved again ----------
with tempfile.TemporaryDirectory() as tmp:
    cache = os.path.join(tmp, "cache")
    u = {"key": ("TESTBODY", "ISS_TEST_MAP", "N", 0), "frames": []}
    scale = {"white": 1.0, "blacks": {}, "gamma": 2.2}
    there = om._tiles(u, cache, scale)
    os.makedirs(there)
    tiles = []
    for n in range(4):
        h, w = int(rng.integers(120, 300)), int(rng.integers(120, 300))
        pic = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
        yy, xx = np.mgrid[0:h, 0:w]
        pic[..., 3] = np.where(np.hypot(xx - w / 2, yy - h / 2) < 0.48 * min(h, w), 255, 0)
        Image.fromarray(pic).save(os.path.join(there, f"{n}.png"))
        Image.fromarray(rng.integers(0, 256, (h, w), dtype=np.uint8), "L").save(
            os.path.join(there, f"{n}.hdr.webp"), "WEBP", lossless=True)
        tiles.append({"n": n, "filter": "RED" if n % 2 else "GRN", "box": [-w / 2, -h / 2, w, h],
                      "offset": [float(rng.uniform(-90, 90)), float(rng.uniform(-90, 90))],
                      **({"gain": 0.7, "gamma": 2.2} if n == 1 else {}), **({"turn": 0.4} if n == 3 else {})})
    rect, W, H = (-256.0, -256.0, 512.0, 512.0), 400, 400
    for k in (400 / 512, 0.5, 1.0):
        drew = []
        token = om._hdr_drawn.set(drew)
        try:
            for t in tiles:
                om._place(u, t, rect, k, W, H, cache, scale)
        finally:
            om._hdr_drawn.reset(token)
        assert any(d[7] is not None for d in drew) or k in (0.5, 1.0)
        assert drew[3][7] is None                                  # (a turned tile: its alpha worked out as before)
        with_alpha = om.hdr_map(drew, W, H)
        without = om.hdr_map([d[:7] for d in drew], W, H)          # (as before: the tile moved again for its alpha)
        assert with_alpha is not None and same(with_alpha, without), k
print("hdr_map: the same map from the alpha _place drew")

# ---------- a tile's ring bins worked out once: _ring_profile's sums and counts at every place tried ----------
import reproject as rp  # noqa: E402

for trial in range(12):
    h, w, reach = int(rng.integers(40, 130)), int(rng.integers(40, 130)), int(rng.choice([4, 16, 32]))
    gy, gx = np.mgrid[0:h + 2 * reach + 1, 0:w + 2 * reach + 1]
    # (radii across and past the rings both ways, with points SPICE has no radius for)
    radius = rp.RING_INNER - 9000 + (gx * 311.7 + gy * 173.3 + rng.normal(0, 40, gx.shape)) * (rp.RING_OUTER - rp.RING_INNER) / (300 * (w + h))
    radius[rng.random(radius.shape) < 0.02] = np.nan
    radius[rng.random(radius.shape) < 0.01] = np.inf
    sy, sx = np.mgrid[reach:reach + h:om.RING_STEP, reach:reach + w:om.RING_STEP]
    keep = rng.random(sy.size) < 0.8
    sy, sx = sy.ravel()[keep], sx.ravel()[keep]
    v = rng.uniform(0, 255, sy.size).astype(np.float32)
    with np.errstate(invalid="ignore"):
        bins, nb = om._ring_bins(radius)
        at, width = sy.astype(np.int64) * radius.shape[1] + sx, radius.shape[1]
        for dy, dx in [(0, 0), (-reach, -reach), (reach, reach), (reach, -reach)] + \
                [tuple(int(q) for q in rng.integers(-reach, reach + 1, 2)) for _ in range(20)]:
            want = om._ring_profile(v, radius[sy + dy, sx + dx])
            b = bins.take(at + (dy * width + dx))
            got = np.bincount(b, weights=v, minlength=nb + 1)[:nb], np.bincount(b, minlength=nb + 1)[:nb]
            assert same(got[0], want[0]) and same(got[1], want[1]), (trial, dy, dx)
print("ring fit: the same radial profile from bins worked out once")
print("ok")
