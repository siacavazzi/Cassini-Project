"""CISSCAL's WAC geometric correction (geometric_correction.py, calibration.calibrate's "geom" step) against
cassimg__geomcorr.pro written out the slow way (the whole buffered array, its -1e38 margin and the blurred one, then
IDL's cubic interpolate one pixel at a time), on a positive image where CISSCAL's bad pixels and ours are the same; the
focal length table; a dot moved where the correction says; the masks moved with the pixels; and the WAC's centring
scale (bootleg_autonav.linear_ratio). Run: python web/test_geometric_correction.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import geometric_correction as gc  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

WAC = {"INSTRUMENT_ID": "ISSWA", "FILTER_NAME": '("CB3", "CL2")', "SHUTTER_STATE_ID": "ENABLED"}
NAC = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": '("CL1", "CL2")', "SHUTTER_STATE_ID": "ENABLED"}


def idl_cubic(a, x, y, c=-0.5):
    """IDL interpolate(a, x, y, cubic=c) at one point, a[line, sample], neighbours clamped to the edge."""
    def w(s):
        s = abs(s)
        if s <= 1:
            return (c + 2) * s ** 3 - (c + 3) * s ** 2 + 1
        if s < 2:
            return c * s ** 3 - 5 * c * s ** 2 + 8 * c * s - 4 * c
        return 0.0
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    total = 0.0
    for j in range(y0 - 1, y0 + 3):
        for i in range(x0 - 1, x0 + 3):
            total += w(x - i) * w(y - j) * float(a[min(max(j, 0), a.shape[0] - 1), min(max(i, 0), a.shape[1] - 1)])
    return total


def slow_geomcorr(in_image, f, points):
    """cassimg__geomcorr.pro's WAC branch, as written, at the output pixels points [(line, sample)]."""
    npix = in_image.shape[1]
    buffsize = 12. * npix / 1024.
    arrsize = int(npix + 2. * buffsize)
    xcen = 548. * arrsize / 1024.
    ycen = 508. * arrsize / 1024.
    f_default, k = 200.956, -0.000062
    b = int(buffsize)
    temp_image = np.full((arrsize, arrsize), -1.e38)
    temp_image[b:arrsize - b, b:arrsize - b] = in_image
    blur = np.full((arrsize, arrsize), np.nan)
    blur[b:arrsize - b, b:arrsize - b] = in_image
    width = b * 2 + 1
    h = width // 2
    padded = np.pad(blur, h, mode="edge")
    smoothed = np.empty_like(blur)
    for r in range(arrsize):
        for s in range(arrsize):
            win = padded[r:r + width, s:s + width]
            smoothed[r, s] = np.nanmean(win) if np.isfinite(win).any() else np.nan
    smoothed[b:arrsize - b, b:arrsize - b] = in_image
    out = []
    for line, sample in points:
        X, Y = sample + b, line + b                     # the IDL's array, before it is truncated
        Xmm = (X - xcen) * 0.012 * (1024. / npix)
        Ymm = (Y - ycen) * 0.012 * (1024. / npix)
        Rsq = Xmm ** 2 + Ymm ** 2
        Xo = (f / f_default) * Xmm / (1. + k * Rsq) / (0.012 * (1024. / npix)) + xcen
        Yo = (f / f_default) * Ymm / (1. + k * Rsq) / (0.012 * (1024. / npix)) + ycen
        bad = idl_cubic(temp_image, Xo, Yo) < 0
        out.append(0.0 if bad else idl_cubic(smoothed, Xo, Yo))
    return out


# focal lengths: the table, the default for a pair it has not, CISSCAL's filter names
assert gc.focal_length(WAC) == 201.22
assert gc.focal_length(dict(WAC, FILTER_NAME='("CL1", "GRN")')) == 200.71
assert gc.focal_length(dict(WAC, FILTER_NAME='("CL1", "MT1")')) == gc.F_DEFAULT
assert gc.wants(WAC) and not gc.wants(NAC) and not gc.wants(dict(WAC, SHUTTER_STATE_ID="DISABLED"))

# against the IDL written out, at 256 px (a SUM4 frame: the slow blur is quick there) and corners, edges, middle
rng = np.random.default_rng(3)
img = (rng.random((256, 256)) * 0.3 + 0.05).astype(np.float64)
img[100:140, 60:90] += 1.0      # a bright patch, so the cubic's overshoot is tried
pts = [(0, 0), (0, 255), (255, 0), (255, 255), (1, 1), (2, 128), (128, 0), (127, 137), (101, 61), (139, 89), (200, 250)]
for f in (200.71, 201.22, gc.F_DEFAULT):
    fast, _ = gc.geomcorr(img, f)
    slow = slow_geomcorr(img, f, pts)
    for (r, s), v in zip(pts, slow):
        assert abs(fast[r, s] - v) < 2e-5, (f, r, s, fast[r, s], v)
print("matches cassimg__geomcorr.pro at", len(pts), "pixels x 3 focal lengths")

# a dot where the correction takes output pixel (line, sample) from lands on that pixel
b, _, X, Y = gc._map(1024, 201.22)
for r, s in [(30, 30), (990, 1000), (508, 15), (15, 548), (900, 100)]:
    raw = np.zeros((1024, 1024), np.float32)
    raw[int(round(Y[r, s] - b)), int(round(X[r, s] - b))] = 1.0
    out = gc.correct(raw, WAC)
    peak = np.unravel_index(np.argmax(out), out.shape)
    assert abs(peak[0] - r) <= 1 and abs(peak[1] - s) <= 1, ((r, s), peak)
    # ... and a mask on that dot's pixel moves with it
    m = gc.correct_mask(raw > 0.5, WAC)
    assert m[r, s] or m[max(r - 1, 0):r + 2, max(s - 1, 0):s + 2].any(), (r, s)
# how far it moves: a few pixels at the corners, under a tenth of one near the optical centre
d = np.hypot(X - (np.arange(1024) + b)[None, :], Y - (np.arange(1024) + b)[:, None])
assert 3 < d[0, 0] < 6 and d[508, 548] < 0.2, (d[0, 0], d[508, 548])
print(f"corner moves {d[0, 0]:.2f} px (CB3/CL2), centre {d[508, 548]:.3f} px")

# the NAC, and the WAC with the step off, are left as they are
flat = np.ones((1024, 1024), np.float32)
assert gc.correct(flat, NAC) is flat or np.array_equal(gc.correct(flat, NAC), flat)
with cal.stepping(["geom"]):
    assert np.array_equal(gc.correct(flat, WAC), flat)
    assert ba.linear_ratio("CASSINI_ISS_WAC", 200.77 / 0.012) == 1.0
with cal.stepping(["calibrate"]):
    assert not gc.active(WAC)
# an even picture stays even inside, the edge the correction reached past is 0 and not valid
even = gc.correct(flat, WAC)
_, _, _, bad = gc._plan(1024, 201.22)
assert np.allclose(even[~bad], 1.0, atol=1e-5) and np.all(even[bad] == 0)
assert 0 < bad.sum() < 0.02 * bad.size and not bad[400:600, 400:600].any()
valid = gc.correct_mask(np.ones((1024, 1024), bool), WAC)
assert np.array_equal(valid, ~bad)

# what is kept: a WAC sequence of more filters than the plans kept (PLANS_KEEP) works a frame's plan out again, with
# the same weights and the edge mask kept from its first time; a mask's correction then asks for no plan at all
pairs = list({f: p for p, f in gc.FOCAL_LENGTHS.items()}.values())[:gc.PLANS_KEEP + 3]   # (each its own focal length)
assert len({gc.FOCAL_LENGTHS[p] for p in pairs}) == gc.PLANS_KEEP + 3
infos = [dict(WAC, FILTER_NAME=f'("{a}", "{b}")') for a, b in pairs]
small = (rng.random((256, 256)) > 0.2)
pic = rng.random((256, 256)).astype(np.float32)
gc._plan.cache_clear()
first = [(gc.correct_mask(small, i), gc.correct(pic, i), gc._plan(256, gc.focal_length(i))) for i in infos]
assert gc._plan.cache_info().currsize == gc.PLANS_KEEP and all((256, gc.focal_length(i)) in gc._edges for i in infos)
worked = gc._plan.cache_info().misses
masks = [gc.correct_mask(small, i) for i in infos]                    # (the plans of the first of them are gone)
assert gc._plan.cache_info().misses == worked, "a mask's correction worked a plan out"
assert all(np.array_equal(m, f[0]) for m, f in zip(masks, first))
for i, (_, out, plan) in zip(infos, first):
    again = gc._plan(256, gc.focal_length(i))
    assert again[3] is plan[3] and all(np.array_equal(a, b) for a, b in zip(again[2][1] + again[2][3], plan[2][1] + plan[2][3]))
    assert np.array_equal(gc.correct(pic, i), out) and not again[3].flags.writeable
print("plans worked out again are the same, and masks ask for none:", len(pairs), "filter pairs")

# centring: a WAC shift grows from SPICE's 200.77 mm to the corrected frames' 200.956 mm; NAC unchanged
r = ba.linear_ratio("CASSINI_ISS_WAC", 200.77 / 0.012)
assert abs(r - 200.956 / 200.77) < 1e-12, r
assert ba.linear_ratio("CASSINI_ISS_NAC", 2003.44 / 0.012) == 1.0


class L:
    pass


lab = L()
lab.info = WAC
lab.geometry = {"camera": "CASSINI_ISS_WAC", "scale": 200.77 / 0.012, "center": 511.5, "et": 0, "target": "X"}
x, y, z, a = ba.linearized(lab, [100.0, -50.0, 1e5, 10.0])
assert abs(x - 100 * r) < 1e-9 and abs(y + 50 * r) < 1e-9 and z == 1e5 and a == 10.0
assert abs(lab.geometry["scale"] - gc.LINEAR_SCALE) < 1e-9
print("ok")
