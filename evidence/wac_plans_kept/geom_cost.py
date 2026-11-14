import sys, time
sys.path.insert(0, ".")
import numpy as np, geometric_correction as gc
def t(f, n=3):
    best = 1e9
    for _ in range(n):
        t0 = time.perf_counter(); f(); best = min(best, time.perf_counter() - t0)
    return best * 1000
fs = sorted(set(gc.FOCAL_LENGTHS.values()) | {gc.F_DEFAULT})
print(len(fs), "focal lengths")
for npix in (1024, 512):
    f = fs[3]
    gc._map.cache_clear(); gc._plan.cache_clear()
    print(npix, "_map miss %.0f ms" % t(lambda: (gc._map.cache_clear(), gc._map(npix, f))))
    b, arrsize, X, Y = gc._map(npix, f)
    print(npix, "_keys(X) %.0f ms" % t(lambda: gc._keys(X)))
    bx, wx = gc._keys(X); by, wy = gc._keys(Y)
    w = (bx.astype(np.int32), [a.astype(np.float32) for a in wx], by.astype(np.int32), [a.astype(np.float32) for a in wy])
    margin = np.ones((arrsize, arrsize), np.float32); margin[b:arrsize - b, b:arrsize - b] = 0
    print(npix, "bad (_interpolate margin) %.0f ms" % t(lambda: gc._interpolate(margin, X, Y, w) > 1e-6))
    print(npix, "_plan miss %.0f ms" % t(lambda: (gc._plan.cache_clear(), gc._plan(npix, f))))
    img = np.random.rand(npix, npix).astype(np.float32)
    print(npix, "geomcorr hit %.0f ms" % t(lambda: gc.geomcorr(img, f)))
    m = np.random.rand(npix, npix) > 0.5
    info = {"INSTRUMENT_ID": "ISSWA", "FILTER_NAME": "(CL1,RED)"}
    print(npix, "correct_mask hit %.0f ms" % t(lambda: gc.correct_mask(m, info)))
    e = gc._plan(npix, f)
    print(npix, "plan entry MB %.1f" % ((e[2][0].nbytes + e[2][2].nbytes + sum(a.nbytes for a in e[2][1]) + sum(a.nbytes for a in e[2][3]) + e[3].nbytes) / 1e6),
          "map entry MB %.1f" % ((X.nbytes + Y.nbytes) / 1e6))
