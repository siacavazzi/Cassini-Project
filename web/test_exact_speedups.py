"""The faster forms of the second optimization pass's steps against the forms they replaced (copied here as they were
at d0777e6), to the bit: label_handler.garbled_lines (rows found a row at a time, the steps' median from a histogram,
no second look when the first finds nothing), dark_current._dark (the 5 line median as minimum and maximum passes,
the inverse FFT along the transposed spectrum, the lift and saturation in place), image_correction's sort of a few
frames (agreeing_median) and its nearest valid row searches (fill_lines, line_fills), and calibration._floor without
the fine structure where it cannot count. Made-up inputs with ties, infinities, NaN, signed zeros and edges.
Run: python web/test_exact_speedups.py"""
import math
import os
import sys
import warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import calibration as cal  # noqa: E402
import dark_current as dc  # noqa: E402
import image_correction as ic  # noqa: E402
import label_handler as lh  # noqa: E402

warnings.simplefilter("ignore")
rng = np.random.default_rng(29)


def same(a, b):
    if isinstance(a, (tuple, list)):
        return isinstance(b, (tuple, list)) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return isinstance(b, float) and (math.isnan(a) and math.isnan(b) or a == b and math.copysign(1, a) == math.copysign(1, b))
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


# ---------- garbled_lines ----------
def garbled_before(img, mask):
    c = img.astype(np.float32)
    h, w = c.shape
    if h < 3:
        return np.zeros(c.shape, bool)
    good = mask.copy()
    limits = np.full(lh.GARBLE_FAR + 2, np.inf, np.float32)
    for d in range(1, min(lh.GARBLE_FAR, h - 1) + 1):
        steps = np.abs(c[d:] - c[:-d])[good[d:] & good[:-d]]
        noise = 1.4826 * float(np.median(steps)) / np.sqrt(2) if steps.size else 0.0
        limits[d] = lh.GARBLE_SIGMA * max(noise, 1.0)
    rows = np.arange(h)[:, None]
    out = np.zeros(c.shape, bool)
    cols = np.broadcast_to(np.arange(w), c.shape)

    def nearest(ok, step):
        if step < 0:
            first = np.maximum.accumulate(np.where(ok, rows, -1), axis=0)
            one = np.vstack([np.full((1, w), -1), first[:-1]])
            two = np.where(one >= 0, first[np.clip(one - 1, 0, h - 1), cols], -1)
            two[0] = -1
            return one, np.where(one >= 1, two, -1)
        first = np.minimum.accumulate(np.where(ok, rows, h)[::-1], axis=0)[::-1]
        one = np.vstack([first[1:], np.full((1, w), h)])
        two = np.where(one < h - 1, first[np.clip(one + 1, 0, h - 1), cols], h)
        return one, two

    for _ in range(2):
        ok = good & ~out
        (a1, a2), (b1, b2) = nearest(ok, -1), nearest(ok, 1)
        jump = np.zeros(c.shape, bool)
        for a, b in ((a1, b1), (a1, b2), (a2, b1)):
            have = (a >= 0) & (b < h)
            va, vb = c[np.clip(a, 0, h - 1), cols], c[np.clip(b, 0, h - 1), cols]
            limit = limits[np.clip(np.maximum(rows - a, b - rows), 1, lh.GARBLE_FAR + 1)]
            jump |= have & (np.minimum(np.abs(c - va), np.abs(c - vb)) - np.abs(va - vb) > limit)
        jump &= good
        share = cv2.blur(jump.astype(np.float32), (lh.GARBLE_RUN, 1), borderType=cv2.BORDER_CONSTANT)
        tail = np.cumsum(jump[:, ::-1], axis=1)[:, ::-1]
        left = np.cumsum(good[:, ::-1], axis=1)[:, ::-1]
        begin = np.clip(np.arange(w)[None, :] - lh.GARBLE_RUN // 2, 0, w - 1)
        starts = (share >= lh.GARBLE_SHARE) & (tail[:, begin[0]] >= lh.GARBLE_SHARE * np.maximum(left[:, begin[0]], lh.GARBLE_RUN))
        first = np.minimum.accumulate(np.where(jump, np.arange(w)[None, :], w)[:, ::-1], axis=1)[:, ::-1]
        at = np.maximum(np.argmax(starts, axis=1) - lh.GARBLE_RUN // 2, 0)
        start = np.where(starts.any(axis=1), first[np.arange(h), at], w)
        out |= np.arange(w)[None, :] >= start[:, None]
    return out & good


found = 0
for k in range(160):
    h, w = (int(rng.choice([3, 4, 9])), int(rng.choice([1, 2, 33, 64]))) if k % 8 == 0 else \
        (int(rng.choice([16, 64, 130, 256])), int(rng.choice([64, 65, 200, 256])))
    img = np.clip(rng.integers(0, 200) + rng.normal(0, rng.choice([0.0, 1, 10, 40]), (h, w)), 0, 255).astype(np.uint8)
    mask = np.ones((h, w), bool)
    if k % 4 == 1:
        for r in range(h):
            if rng.random() < 0.2:
                mask[r, rng.integers(0, w + 1):] = False
    elif k % 4 == 2:
        mask = rng.random((h, w)) < 0.9
    elif k % 4 == 3:
        mask[::2] = False
    for r in rng.choice(h, min(h, int(rng.integers(1, 6)) if k % 3 else 0), replace=False):
        x0 = int(rng.integers(0, w))
        img[r, x0:] = rng.integers(0, 256, w - x0)
    for pic in ([img] if k % 5 else [img, img.astype(np.float32) + 0.25, img.astype(np.uint16)]):
        a, b = garbled_before(pic, mask), lh.garbled_lines(pic, mask)
        assert same(a, b), (k, pic.dtype, h, w, int(a.sum()), int(b.sum()))
        found += int(a.any())
assert found > 50, found
print("garbled_lines the same,", found, "with garbled lines")


# ---------- the dark current ----------
def dark_before(constant, spectra, r):
    camera, lines, gain = r[0], r[1], r[2]
    t = np.array([dc.line_time(r, i + 1) for i in range(lines)])
    start = np.concatenate([[0.0], t[:-1]])
    end = start + np.maximum(t - start, 0.0)
    weights = dc._basis(end) - dc._basis(start)
    kernel = np.fft.rfft(weights, n=2 * lines, axis=0)
    summed = np.einsum("bfs,fb->fs", spectra, kernel.astype(np.complex64), optimize=True)
    dark = constant + np.fft.irfft(summed, n=2 * lines, axis=0)[:lines].astype(np.float32)
    med = dark.copy()
    med[2:-2] = np.median(np.stack([dark[k:lines - 4 + k] for k in range(5)]), axis=0)
    dark = np.where(med - dark > 10, med, dark)
    dn = dark / (dc.GAIN2[camera] / dc.GAIN_RATIOS[camera][gain])
    return np.where((dn >= dc.DN_SATURATION) | (dark >= dc.E_SATURATION[camera]), dc.DN_SATURATION, dn).astype(np.float32)


made = dc._parameters
try:
    for k in range(12):
        lines = (256, 512)[k % 2]
        p = np.cumsum(rng.uniform(0, 60, (8, lines, lines)), axis=0) - 20
        p[:, rng.random((lines, lines)) < 0.01] *= 400       # hot spots past the saturation
        p[:, :, rng.integers(0, lines)] = 0.0                # a column with no dark
        constant, spectra = p[0].astype(np.float32), np.fft.rfft(p, n=2 * lines, axis=1).astype(np.complex64)
        dc._parameters = lambda *a: (constant, spectra)
        comp = ("NotCompressed", "Lossless", "Lossy")[k % 3]
        r = (("ISSNA", "ISSWA")[k % 2], lines, (215, 95, 29, 12)[k % 4], comp, 1.0 if comp == "NotCompressed" else 2.7,
             ("12Bit", "8Bit")[k // 6], 1.4, (8, 16, 24, 32, 40, 48)[k % 6], k, k % 2, (k // 2) % 2,
             float((0, 5000, 46000, 1200000, 2000000, 300000)[k % 6]), "")
        a, b = dark_before(constant, spectra, r), dc._dark.__wrapped__(r)
        assert same(a, b) and b.flags["C_CONTIGUOUS"] and not b.flags.writeable, (k, r)
finally:
    dc._parameters = made
for k in range(300):
    x = rng.integers(0, 4, (5, 7, int(rng.integers(1, 9)))).astype(np.float32) * rng.choice([1.0, -0.5, 1e30])
    if k % 3 == 0:
        x[rng.random(x.shape) < 0.05] = rng.choice([np.inf, -np.inf, np.nan])
    a = np.median(x, axis=0)
    b = dc._median5(*x)
    assert np.array_equal(a, b, equal_nan=True) and a.dtype == b.dtype, k


def lift_before(dark):
    lines = len(dark)
    med = dark.copy()
    med[2:-2] = np.median(np.stack([dark[k:lines - 4 + k] for k in range(5)]), axis=0)
    return np.where(med - dark > 10, med, dark)


lifted = 0
for k in range(600):
    # spikes over a few levels with ties, zeros of one sign or both, infinities and NaN
    levels = [0.0, 12.0, 30.0, -15.0] + ([-0.0] if k % 3 == 0 else []) + ([np.inf, -np.inf] if k % 5 == 0 else []) + \
        ([np.nan] if k % 7 == 0 else [])
    dark = rng.choice(np.array(levels, np.float32), (int(rng.integers(5, 40)), int(rng.integers(1, 30))))
    if k % 2:
        dark += rng.normal(0, 8, dark.shape).astype(np.float32)
    a, b = lift_before(dark), dark.copy()
    dc._lift_spikes(b)
    assert same(a, b), k
    lifted += int((a != dark).any())
assert lifted > 100, lifted
print("dark current the same")


# ---------- a few frames sorted, and the nearest valid rows ----------
def agreeing_before(stack, agrees, count):
    ordered = np.sort(np.where(agrees, stack, np.inf), axis=0)
    low = np.take_along_axis(ordered, ((count - 1) // 2)[None], 0)[0]
    high = np.take_along_axis(ordered, (count // 2)[None], 0)[0]
    return (low + high) / 2


for k in range(400):
    n, h, w = int(rng.integers(1, 12)), int(rng.integers(1, 20)), int(rng.integers(1, 20))
    stack = (rng.integers(0, 5, (n, h, w)) * rng.choice([1.0, 0.25, 33.5])).astype(np.float32)
    if k % 4 == 0:
        stack[rng.random(stack.shape) < 0.1] = rng.choice([np.inf, -np.inf, np.nan])
    assert np.array_equal(np.sort(stack, axis=0), ic._sorted(stack), equal_nan=True), k
    agrees = rng.random((n, h, w)) < 0.7
    agrees[0] = True
    count = agrees.sum(axis=0)
    assert same(agreeing_before(stack, agrees, count), ic.agreeing_median(stack, agrees, count)), k
    on = rng.random((h, w)) < rng.choice([0.0, 0.2, 0.8, 1.0])
    rows = np.arange(h)[:, None]
    assert same(np.maximum.accumulate(np.where(on, rows, -1), axis=0), ic.rows_above(on)), k
    assert same(np.minimum.accumulate(np.where(on, rows, h)[::-1], axis=0)[::-1], ic.rows_below(on)), k
print("sorts and nearest rows the same")


# ---------- the floor black ----------
def floor_before(iofs, levels, sky=None):
    lum = iofs[0] - np.float32(levels[0]) if len(iofs) == 1 else \
        np.mean([iof - np.float32(level) for iof, level in zip(iofs, levels)], axis=0)
    floor, middle, glow = (float(v) for v in np.percentile(lum, (cal.FLOOR_PCT, 50, cal.GLOW_PCT)))
    black = cal.FLOOR_SHARE * max(floor, 0.0)
    dim = np.log(cal.GLOW_IOF[1] / max(middle, 1e-12)) / np.log(cal.GLOW_IOF[1] / cal.GLOW_IOF[0])
    smooth = (cal.GLOW_FINE[1] - cal.fine_structure(lum)) / (cal.GLOW_FINE[1] - cal.GLOW_FINE[0])
    return black + min(max(float(dim), 0.0), 1.0) * min(max(smooth, 0.0), 1.0) * max(glow - black, 0.0)


for k in range(300):
    lum = (10 ** rng.uniform(-5, 0) * (1 + rng.normal(0, rng.choice([0.0, 0.05, 0.5]), (40, 40)))).astype(np.float32)
    if k % 5 == 1:
        lum[rng.random(lum.shape) < 0.02] = rng.choice([np.nan, np.inf, -np.inf])
    if k % 5 == 2:
        lum[rng.random(lum.shape) < 0.5] = -0.0
    if k % 9 == 0:
        lum[:] = rng.choice([0.0, -0.0, 0.004999, 0.005, 0.0050001])
    if k % 11 == 0:
        # finite pixels near the float32 limit, whose blurs overflow: the full path (a NaN there before)
        lum = (rng.choice([1.0, -1.0], lum.shape) * rng.choice([1e29, 1e30, 1e37, 2e38, 3.4e38])).astype(np.float32)
        lum[:20] = np.abs(lum[:20])
    iofs = [lum * np.float32(rng.uniform(0.5, 2)) for _ in range(int(rng.choice([1, 3])))]
    levels = [float(rng.choice([0.0, -0.0, 1e-4])) for _ in iofs]
    assert same(floor_before(iofs, levels), cal._floor(iofs, levels)), k
print("floor black the same")
print("ok")
