"""Synthetic mosaics with a known truth, for measuring how well mosaic.compose hides its seams (seam_bench,
test_mosaic_blend). A real picture of a body (or any grey picture) is the truth; a pass is cut from it the way the
pipeline makes one: tiles of a frame each, turned (north up) and placed by obs_mosaic._window, each with mask.png's
soft edge and the dark rim turning and resizing leave, each with what really differs from tile to tile in a pass
(a gain the calibration leaves, a brightness gradient across the frame from the lighting and the haze, a little
fall-off to the corners, noise, a pixel or two of pointing error). The tiles are composed by obs_mosaic._compose,
as a pass's filter mosaic is, and the result is measured against the truth (measure).

Run: python web/frames/seam_synth.py TRUTH.png OUTDIR  (a page of crops and the numbers for every step setting)"""
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import calibration  # noqa: E402
import mosaic  # noqa: E402

MASK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mask.png")


def tiles(truth, side=512, grid=(3, 3), overlap=(16, 60), angle=20.0, gain=0.08, slope=0.12, falloff=0.08,
          noise=1.5, pointing=1.5, seed=1, order="rows"):
    """The canvas frames of a pass cut from truth (float32 grey levels 0-255, its middle the pass's middle):
    [(RGBA canvas uint8, the tile's place as a 2x3 affine from tile pixels to canvas pixels)], in the order taken.
    side = a tile's size on the canvas; grid = tiles across, down; overlap = (least, most) canvas pixels two
    neighbours share, drawn per seam; angle = how far the frames are turned on the canvas (north up); gain = the
    largest gain error, slope = the largest brightness change from the frame's middle to its edge, falloff = how
    much darker its corners are, noise = levels, pointing = the largest placement error (canvas pixels)."""
    rng = np.random.default_rng(seed)
    H, W = truth.shape
    mask = cv2.resize(np.asarray(Image.open(MASK).convert("L")), (side, side), interpolation=cv2.INTER_AREA)
    nx, ny = grid
    gaps_x = [side - rng.uniform(*overlap) for _ in range(nx - 1)]
    gaps_y = [side - rng.uniform(*overlap) for _ in range(ny - 1)]
    xs = np.concatenate([[0], np.cumsum(gaps_x)])
    ys = np.concatenate([[0], np.cumsum(gaps_y)])
    xs -= xs[-1] / 2
    ys -= ys[-1] / 2
    t = math.radians(angle)
    R = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    v, u = np.mgrid[0:side, 0:side].astype(np.float32)
    u, v = (u - side / 2) / (side / 2), (v - side / 2) / (side / 2)
    places = [(i, j) for j in range(ny) for i in range(nx)]
    if order == "snake":
        places = [(i if j % 2 == 0 else nx - 1 - i, j) for j in range(ny) for i in range(nx)]
    out = []
    for i, j in places:
        centre = np.array([W / 2, H / 2]) + R @ np.array([xs[i], ys[j]])
        # tile pixel (x, y) -> canvas: centre + R (x - side/2, y - side/2)
        A = np.hstack([R, (centre - R @ np.array([side / 2, side / 2]))[:, None]]).astype(np.float32)
        err = rng.uniform(-pointing, pointing, 2)
        A_seen = A.copy()
        A_seen[:, 2] += err   # the camera looked a little off where SPICE says
        grey = cv2.warpAffine(truth, A_seen, (side, side), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
        phi = rng.uniform(0, 2 * math.pi)
        field = (1 + rng.uniform(-gain, gain)) * (1 + rng.uniform(-slope, slope) * (math.cos(phi) * u + math.sin(phi) * v)) \
            * (1 - rng.uniform(0, falloff) * (u * u + v * v) / 2)
        grey = grey * field + rng.normal(0, noise, grey.shape)
        rgba = np.dstack([np.clip(grey, 0, 255)] * 3 + [mask.astype(np.float32)]).astype(np.float32)
        # placed on the canvas as obs_mosaic draws a tile: turned and resized, so its outermost pixels mix with the
        # black around it, as a real tile's do
        canvas = cv2.warpAffine(rgba, A, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out.append((np.clip(canvas + 0.5, 0, 255).astype(np.uint8), A))
    return out


def compose(frames, k=0.5, off=""):
    """frames composed as a pass's filter mosaic is (obs_mosaic._compose: calibrated, none pinned, the soft edge
    at this canvas scale), with the steps off turned off."""
    import obs_mosaic
    with calibration.stepping(off):
        return obs_mosaic._compose([(f, None, None, None) for f in frames], k, pin=None)


def grown(frames, k=0.5, start=4, off=""):
    """frames composed as a pass's filter mosaic past GROW_FROM tiles is, and a mosaic movie's picture: the first
    start drawn whole (compose), then each next one drawn over the picture so far (obs_mosaic.draw_over, as _over)."""
    import obs_mosaic
    rgba = compose(frames[:start], k, off).copy()
    with calibration.stepping(off):
        for f in frames[start:]:
            ys, xs = np.nonzero(f[..., 3])
            top, left = int(ys.min()), int(xs.min())
            part = f[top:ys.max() + 1, left:xs.max() + 1]
            obs_mosaic.draw_over(rgba, lambda: part, left, top, part.shape[1], part.shape[0], k)
    return rgba


def footprints(frames):
    """Each frame's picture on the canvas (bool)."""
    return [f[..., 3] > 0 for f in frames]


def measure(out, truth, frames, band=4, sigma=4.0):
    """How well out (RGBA, as seen over black) shows truth inside the tiles, as numbers (per cent):
    seam: the brightness step across the tiles' edges inside the mosaic, p50 and p95 over the edges (out's error
    against truth, log, smoothed by sigma, its change over band pixels each side of the edge); flat: the same over
    the tiles' insides, for scale; level: the median of out's error against truth (how far the whole mosaic's
    brightness moved); spread: how much that error changes over the mosaic (its p95 less its p5: a slow gradient
    leveling left); detail: the strength of the fine detail where tiles overlap, against inside one tile, out's over
    truth's (100 = as sharp, less = blurred where two tiles mix)."""
    union = np.sum([f for f in footprints(frames)], axis=0)
    seen = out[..., 0].astype(np.float32) * (out[..., 3].astype(np.float32) / 255)
    # not near the limb or the terminator, where a pixel of pointing is a big change, nor in the sky
    t = cv2.GaussianBlur(truth.astype(np.float32), (0, 0), 2)
    ty, tx = np.gradient(np.log(np.maximum(t, 1)))
    calm = cv2.erode((np.hypot(tx, ty) < 0.02).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    inside = cv2.erode((union > 0).astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
    lit = inside & (truth > 30) & calm
    err = np.where(lit, np.log(np.maximum(seen, 1)) - np.log(np.maximum(truth, 1)), 0).astype(np.float32)
    w = cv2.GaussianBlur(lit.astype(np.float32), (0, 0), sigma)
    e = cv2.GaussianBlur(err, (0, 0), sigma) / np.maximum(w, 1e-3)
    gy, gx = np.gradient(e)
    grad = np.hypot(gx, gy) * (2 * band)   # change over 2 band pixels across an edge
    inner = cv2.erode(lit.astype(np.uint8), np.ones((2 * band + 9, 2 * band + 9), np.uint8)) > 0
    edges = np.zeros_like(lit)
    for f in footprints(frames):
        f8 = f.astype(np.uint8)
        edges |= (cv2.dilate(f8, np.ones((3, 3), np.uint8)) - cv2.erode(f8, np.ones((3, 3), np.uint8))) > 0
    near = cv2.dilate(edges.astype(np.uint8), np.ones((2 * band + 1, 2 * band + 1), np.uint8)) > 0
    seam = near & inner
    flat = inner & ~(cv2.dilate(edges.astype(np.uint8), np.ones((81, 81), np.uint8)) > 0)
    hp = lambda a: a - cv2.GaussianBlur(a, (0, 0), 1.5)
    d_out, d_tru = hp(seen), hp(truth.astype(np.float32))
    over = (union >= 2) & lit
    one = (union == 1) & lit
    # the fine detail's strength (its RMS) where tiles overlap over where one tile is, out's against truth's: two
    # tiles mixed where their detail is not in quite the same place blur it (and ghost it)
    rms = lambda d, m: float(np.sqrt(np.mean(d[m] ** 2)))
    kept = lambda m: rms(d_out, m) / max(rms(d_tru, m), 1e-6)
    pct = lambda m, q: float(np.percentile(grad[m], q) * 100) if m.any() else float("nan")
    return {"seam50": pct(seam, 50), "seam95": pct(seam, 95), "flat50": pct(flat, 50), "flat95": pct(flat, 95),
            "level": float(np.median(err[lit]) * 100),
            "spread": float((np.percentile(e[inner], 95) - np.percentile(e[inner], 5)) * 100),
            "detail": kept(over) / max(kept(one), 1e-6) * 100 if over.any() and one.any() else float("nan")}


def truth_from(path, size=1600):
    """A grey truth picture from path, size px across, with the label at the top of an evidence picture cut off."""
    im = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    im = im[int(im.shape[0] * 0.06):]
    s = size / max(im.shape)
    return cv2.resize(im, (round(im.shape[1] * s), round(im.shape[0] * s)), interpolation=cv2.INTER_AREA)


SETTINGS = [("before (blend and level off)", "blend,level"), ("blend", "level"), ("blend + level", "")]


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    truth = truth_from(src)
    rows = []
    for name, kw in (("calm", {}), ("titan-like", {"slope": 0.25, "gain": 0.12, "falloff": 0.15}),
                     ("misregistered", {"pointing": 4.0})):
        frames = [f for f, _ in tiles(truth, **kw)]
        for label, off in SETTINGS:
            for how, draw in (("whole", compose), ("grown", grown)):
                out = draw(frames, off=off)
                m = measure(out, truth, frames)
                rows.append((name, label, how, m))
                Image.fromarray(out).save(os.path.join(outdir, f"{name}-{how}-{off.replace(',', '_') or 'all'}.png"))
                print(f"{name:14s} {label:30s} {how:6s} " + "  ".join(f"{k} {v:6.2f}" for k, v in m.items()))


if __name__ == "__main__":
    main()
