"""obs_mosaic.ring_places (ring registration's fit of every tile to the pass's reference ring profile) against the
form it replaced, copied below as it was at 58502ad: the same answers and the same reference, to the last digit, with
each tile's profiles kept from one round for the next, kept only in part, or not kept at all (RING_PROFILES_MB), and
with a reference too thin to match anything answered without a search. Made-up tiles: a ring pattern seen through
radius grids of their own, each put a few pixels off; tiles with rings at other radii; tiles fixed beforehand; a
reference given (later tiles fitted to it alone); fewer tiles than a fit needs.
Run: python web/test_ring_fit_once.py"""
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reproject as rp  # noqa: E402

BEFORE = '''
def ring_places_before(u, tiles, picture, fixed=None, ref=None):
    fixed = fixed or {}
    rings = _ring_geometry(u)
    if rings is None:
        return {}, None
    reach = int(round(RING_SEARCH * FRAME))
    data = {}
    for t in tiles:
        if "offset" not in t or ref is not None and t["n"] in fixed:
            continue
        im = picture(t["n"])
        got = _tile_ring_samples(u, t, im, rings, reach) if im is not None else None
        if got is not None:
            data[t["n"]] = got
    if ref is None and len(data) < RING_FIT_MIN:
        return {}, None
    moves = {n: tuple(fixed[n][:2]) if n in fixed else (0, 0) for n in data}
    # each tile's samples binned by radius at every place tried, ~2,200 a tile (the coarse grid of RING_FIT_STEP, the
    # fine one, the parabola, RING_FIT_ROUNDS times): the bin of every point of its radius grid is worked out once
    # (_ring_bins) and a place tried only reads its samples' bins there, where it worked the bins out again from the
    # radii each time (half of a ring pass's time, 2026-11-16). The same bins, sums and counts: _ring_profile's.
    # (the radius grid itself, 9.5 MB a tile, is let go for its bins' 2.4)
    data = {n: (v,) + _ring_bins(radius) + (sy.astype(np.int64) * radius.shape[1] + sx, radius.shape[1])
            for n, (v, radius, on, sy, sx) in data.items()}

    def prof(n, d):
        v, bins, nb, at, width = data[n]
        dx, dy = int(round(d[0])), int(round(d[1]))
        # (never past the margin the samples were taken with, reach: there the flat index would read another row's
        # bins without a word, where the 2-D index it replaces raised or wrapped)
        assert abs(dx) <= reach and abs(dy) <= reach, (n, dx, dy, reach)
        b = bins.take(at + (dy * width + dx))
        return np.bincount(b, weights=v, minlength=nb + 1)[:nb], np.bincount(b, minlength=nb + 1)[:nb]

    out = {}
    given = ref is not None
    for _ in range(1 if given else RING_FIT_ROUNDS):
        if not given:
            details = []
            for n in data:
                tot, cnt = prof(n, moves[n])
                dd = _ring_detail(tot, cnt)
                dd[cnt < 3] = np.nan
                details.append(dd)
            ref = np.nanmedian(np.vstack(details), axis=0)
        new = dict(moves)
        for n in data:
            if n in fixed:
                continue
            score = lambda d: _profile_ncc(*prof(n, d), ref)
            before = score((0, 0))
            best, at = -2.0, (0, 0)
            for dy in range(-reach, reach + 1, RING_FIT_STEP):
                for dx in range(-reach, reach + 1, RING_FIT_STEP):
                    sc = score((dx, dy))
                    if sc > best:
                        best, at = sc, (dx, dy)
            for dy in range(at[1] - RING_FIT_STEP + 1, at[1] + RING_FIT_STEP):
                for dx in range(at[0] - RING_FIT_STEP + 1, at[0] + RING_FIT_STEP):
                    if abs(dx) <= reach and abs(dy) <= reach:
                        sc = score((dx, dy))
                        if sc > best:
                            best, at = sc, (dx, dy)
            ok = best >= RING_FIT_NCC and (math.hypot(*at) <= 0.5 or best >= before + RING_FIT_GAIN) \
                and max(abs(at[0]), abs(at[1])) < reach
            new[n] = at if ok else (0, 0)
            # (to a tenth of a pixel: a parabola through the best and its neighbours, each way)
            fine = list(at)
            if ok:
                for axis in (0, 1):
                    lo_, hi_ = list(at), list(at)
                    lo_[axis] -= 1
                    hi_[axis] += 1
                    a_, c_ = score(tuple(lo_)), score(tuple(hi_))
                    if a_ - 2 * best + c_ < 0:
                        fine[axis] = round(at[axis] + 0.5 * (a_ - c_) / (a_ - 2 * best + c_), 1)
            out[n] = {"move": fine if ok else [0, 0], "ncc": [round(before, 3), round(best, 3)], "found": list(at), "ok": bool(ok)}
        moves = new
    return out, ref
'''

rng = np.random.default_rng(58)
REACH = int(round(om.RING_SEARCH * om.FRAME))
SIDE = 96


def pattern(radius):
    """a made-up ring system: ringlets and gaps at several widths"""
    r = (radius - rp.RING_INNER) / 1000.0
    return 80 + 40 * np.sin(r * 2.1) + 25 * np.sin(r * 5.3 + 1.0) + 15 * (np.sin(r * 0.37) > 0.3)


def make_tiles(count, r0, km_px, spread, off=6.0, at=None):
    """count tiles: each a (SIDE + 2 REACH) px radius grid (a plane wave of radius across the tile, its own direction
    and start), its picture the pattern seen up to off px away from where the grid says"""
    tiles = {}
    for n in range(count):
        ang = rng.uniform(0, math.pi)
        yy, xx = np.mgrid[0:SIDE + 2 * REACH, 0:SIDE + 2 * REACH].astype(np.float64)
        start = (at if at is not None else r0 + spread * n)
        radius = start + km_px * (xx * math.cos(ang) + yy * math.sin(ang))
        dx, dy = rng.uniform(-off, off, 2)
        seen = pattern(start + km_px * ((xx + dx) * math.cos(ang) + (yy + dy) * math.sin(ang)))
        sy, sx = np.mgrid[REACH:REACH + SIDE:om.RING_STEP, REACH:REACH + SIDE:om.RING_STEP]
        sy, sx = sy.ravel(), sx.ravel()
        v = (seen[sy, sx] + rng.normal(0, 2, sy.size)).astype(np.float32)
        on = np.ones(radius.shape, bool)
        tiles[n] = (v, radius, on, sy, sx)
    return tiles


def same(a, b):
    (oa, ra), (ob, rb) = a, b
    if (ra is None) != (rb is None):
        return False
    if ra is not None and not (ra.shape == rb.shape and ra.tobytes() == rb.tobytes()):
        return False
    return oa == ob and repr(oa) == repr(ob)


def run(tiles, **kw):
    om._ring_geometry = lambda u: object()
    om._tile_ring_samples = lambda u, t, im, rings, reach: (tuple(x.copy() for x in tiles[t["n"]])
                                                            if t["n"] in tiles else None)
    ns = dict(vars(om))
    exec(BEFORE, ns)
    listed = [{"n": n, "offset": [0.0, 0.0]} for n in sorted(tiles)] + [{"n": 999}]
    want = ns["ring_places_before"]({}, listed, lambda n: True, **kw)
    got = {}
    for mb in (192, 0, 1):
        om.RING_PROFILES_MB = mb
        got[mb] = om.ring_places({}, listed, lambda n: True, **kw)
        assert same(want, got[mb]), (mb, kw.keys())
    return want


geometry, samples, mb = om._ring_geometry, om._tile_ring_samples, om.RING_PROFILES_MB
try:
    # a pass whose tiles share their radii: most are fitted
    tiles = make_tiles(9, 90000.0, 40.0, 900.0)
    out, ref = run(tiles)
    assert sum(v["ok"] for v in out.values()) >= 5 and np.count_nonzero(~np.isnan(ref)) >= 30, out
    moved = sum(v["ok"] and any(v["move"]) for v in out.values())
    print(f"a pass of 9 tiles: {sum(v['ok'] for v in out.values())} fitted, {moved} moved; "
          "the same answers and reference")
    # some fixed beforehand (kept moves), and later tiles fitted to a reference given
    fixed = {0: [2.0, -1.0, 0.9, True, True], 3: [0, 0, -1.0, False, True]}
    out2, ref2 = run(tiles, fixed=fixed)
    assert set(out2) == set(tiles) - set(fixed)
    out3, ref3 = run(make_tiles(4, 90500.0, 40.0, 700.0), ref=ref, fixed={1: [1.0, 1.0, 0.8, True, True]})
    assert ref3 is ref and 1 not in out3 and len(out3) == 3
    print("tiles fixed beforehand, a reference given: the same")
    # a scan across the rings: every tile at other radii (few bins shared), and coarse tiles (many bins a tile)
    out4, _ = run(make_tiles(8, 80000.0, 30.0, 6000.0))
    out5, _ = run(make_tiles(7, 76000.0, 400.0, 3000.0, off=3.0))
    print(f"a scan across the rings ({sum(v['ok'] for v in out4.values())} of 8 fitted), coarse tiles "
          f"({sum(v['ok'] for v in out5.values())} of 7): the same")
    # a scan along one radius: a reference under 30 bins, nothing can match; answered without a search
    thin = make_tiles(7, 0.0, 5.0, 0.0, at=100000.0)
    out6, ref6 = run(thin)
    assert np.count_nonzero(~np.isnan(ref6)) < 30, np.count_nonzero(~np.isnan(ref6))
    nothing = {"move": [0, 0], "ncc": [-1.0, -1.0], "found": [-REACH, -REACH], "ok": False}
    assert all(v == nothing for v in out6.values())
    calls = []
    real = om._profile_ncc
    om._profile_ncc = lambda *a: calls.append(1) or real(*a)
    try:
        om.ring_places({}, [{"n": n, "offset": [0.0, 0.0]} for n in sorted(thin)], lambda n: True)
    finally:
        om._profile_ncc = real
    assert not calls, len(calls)
    print(f"a reference of {np.count_nonzero(~np.isnan(ref6))} bins: no match for any tile, as the search answered, "
          "without one")
    # fewer ring tiles than a fit needs
    assert run(make_tiles(om.RING_FIT_MIN - 1, 90000.0, 40.0, 900.0)) == ({}, None)
    # a round's profiles are read back in the next: the samples are binned about half as often
    binned = []
    count = np.bincount
    om.RING_PROFILES_MB = 192
    om._ring_geometry = lambda u: object()
    om._tile_ring_samples = lambda u, t, im, rings, reach: tuple(x.copy() for x in tiles[t["n"]])
    listed = [{"n": n, "offset": [0.0, 0.0]} for n in sorted(tiles)]
    for mbs in (0, 192):
        om.RING_PROFILES_MB = mbs
        n0 = [0]

        def counting(*a, **k):
            n0[0] += 1
            return count(*a, **k)
        np.bincount = counting
        try:
            om.ring_places({}, listed, lambda n: True)
        finally:
            np.bincount = count
        binned.append(n0[0])
    assert binned[1] < 0.56 * binned[0], binned
    print(f"bincount calls for that pass: {binned[0]} making every profile again, {binned[1]} reading a round's back")
finally:
    om._ring_geometry, om._tile_ring_samples, om.RING_PROFILES_MB = geometry, samples, mb
print("ok")
