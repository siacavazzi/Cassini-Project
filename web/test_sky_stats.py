"""Check that calibration._median_percentiles (a sky's median and percentiles from two partitions of one working array)
gives the values np.median and np.percentile give each on its own, to the bit and of the same type: on made-up skies of
1 pixel to a million, float32 and float64, with ties, a constant, infinities, only +0 or only -0 zeros, and the cases
it hands back to numpy (a NaN, both signs of zero, empty); that it only reorders the working array; and that
sky_levels, with and without the floor, gives what the separate calls give. Run: python web/test_sky_stats.py"""
import math
import os
import struct
import sys
import warnings
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402

warnings.simplefilter("ignore")
rng = np.random.default_rng(7)


def bits(x):
    if isinstance(x, (list, tuple)):
        return [bits(v) for v in x]
    if isinstance(x, (np.ndarray, np.generic)):
        return type(x).__name__, x.dtype.str, x.tobytes()
    return type(x).__name__, struct.pack("<d", x)


def call(f, *a):
    try:
        return bits(f(*a))
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def separate(v, pcts):
    return np.median(v), [np.percentile(v, p) for p in pcts]


def multiset(v):
    return np.sort(v.view(np.uint64 if v.dtype.itemsize == 8 else np.uint32)).tobytes()


def sky(n, kind, dtype):
    v = rng.normal(0.002, 0.0005, n)
    if kind == "ties":
        v = np.round(v * 2000) / 2000
    elif kind == "constant":
        v[:] = 0.004
    elif kind == "inf":
        v[rng.random(n) < 0.05] = np.inf
        v[rng.random(n) < 0.05] = -np.inf
    elif kind == "+0":
        v[rng.random(n) < 0.3] = 0.0
    elif kind == "-0":
        v[rng.random(n) < 0.3] = -0.0
    elif kind == "zeros":
        v[:] = 0.0
        v[rng.random(n) < 0.5] = -0.0
    elif kind == "nan":
        v[rng.random(n) < 0.01] = np.nan
        v[0] = np.nan
    elif kind == "steps":
        v = np.round(v * 255) / 255           # 8-bit-like, many ties and zeros of one sign
        v[v == 0] = 0.0
    return v.astype(dtype)


checks = handed = 0
PCTS = [(20,), (20, 98), (20, 5), (20, 99.9), (20, 20), (0, 100), (98, 20)]
KINDS = ["normal", "ties", "constant", "inf", "+0", "-0", "steps", "zeros", "nan"]
for n in [1, 2, 3, 4, 5, 10, 101, 1000, 4096, 65537, 1_000_000]:
    for kind in KINDS:
        for dtype in (np.float32, np.float64):
            v = sky(n, kind, dtype)
            mixed = np.signbit(v[v == 0])
            handed += bool(np.isnan(v).any() or (mixed.any() and not mixed.all()))
            for pcts in PCTS if n < 65537 else PCTS[:2]:
                w = v.copy()
                got, want = call(cal._median_percentiles, w, pcts), call(separate, v, pcts)
                assert got == want, (n, kind, dtype, pcts, got, want)
                assert multiset(w) == multiset(v), (n, kind, dtype, pcts)
                checks += 1
# empty: the median is nan (numpy warns) and a percentile of nothing raises, as each call on its own
for dtype in (np.float32, np.float64):
    for pcts in PCTS[:2]:
        got, want = call(cal._median_percentiles, np.zeros(0, dtype), pcts), call(separate, np.zeros(0, dtype), pcts)
        assert got == want and isinstance(got, str), (dtype, pcts, got, want)
        checks += 1


# sky_levels as it was, each statistic from its own call
def levels_separate(images, masks, floor_pct=None):
    levels, noises, floors = [], [], []
    for ims, ms in zip(images, masks):
        v = np.concatenate([im[m] for im, m in zip(ims, ms)])
        steps = np.concatenate([np.abs(np.diff(im, axis=1))[m[:, 1:] & m[:, :-1]] for im, m in zip(ims, ms)])
        noise = 1.4826 * float(np.median(steps)) / math.sqrt(2) if steps.size else 0.0
        median = np.median(v)
        levels.append(min(float(median), float(np.percentile(v, 20)) + 0.84 * noise))
        noises.append(noise)
        if floor_pct is not None:
            floors.append(float(np.percentile(v, floor_pct) - median))
    margin = cal.NOISE_MARGIN * math.sqrt(sum(n * n for n in noises) / len(noises))
    if floor_pct is not None:
        margin = max(margin, max(floors))
    return levels, margin


for t in range(120):
    side = int(rng.choice([1, 2, 8, 64, 300]))
    channels, pictures = (1, 3)[t % 2], 1 + t % 3
    images = [[sky(side * side, KINDS[(t + c + p) % len(KINDS)], np.float32).reshape(side, side) + np.float32(0.01 * c)
               for p in range(pictures)] for c in range(channels)]
    masks = [[rng.random((side, side)) < rng.uniform(0.3, 1) for p in range(pictures)] for c in range(channels)]
    for floor_pct in (None, 98, 99.5):
        got = call(cal.sky_levels, images, masks, floor_pct)
        want = call(levels_separate, images, masks, floor_pct)
        assert got == want, (t, side, floor_pct, got, want)
        checks += 1
print(f"{checks} checks ok ({handed} of the made-up skies handed back to numpy)")
