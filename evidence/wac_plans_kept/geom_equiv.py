"""geometric_correction old (OLD checkout) against new (NEW checkout): every focal length at 1024, 512 and 256 px, in an
order that makes both caches turn over, comparing dtype, shape and bytes of geomcorr's picture and edge mask, correct
and correct_mask (valid masks and saturated masks, outside False and True), and timing both.  geom_equiv.py OLD NEW"""
import importlib.util, random, sys, time
import numpy as np

def load(path, name):
    sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(name, path + "/geometric_correction.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sys.path.pop(0)
    return m
old, new = load(sys.argv[1], "gc_old"), load(sys.argv[2], "gc_new")
sys.path.insert(0, sys.argv[1])   # (calibration, which both ask whether the step is on)
pairs = list(old.FOCAL_LENGTHS) + [("CL1", "UV3")]   # (the last: no row in the table, F_DEFAULT)
rng = np.random.default_rng(5)
frames = {n: (rng.normal(0.02, 0.05, (n, n)).astype(np.float32), rng.random((n, n)) > 0.1, rng.random((n, n)).astype(np.float64)) for n in (1024, 512, 256)}
calls = [(n, p) for n in (1024, 512, 256) for p in pairs] * 3
random.Random(3).shuffle(calls)
# and the real pattern: a WAC sequence cycling 9 filters, a mask then the picture of each frame
calls += [(1024, pairs[k % 9]) for k in range(90)]
same = diff = 0
t_old = t_new = 0.0
def eq(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
for n, (f1, f2) in calls:
    info = {"INSTRUMENT_ID": "ISSWA", "FILTER_NAME": f"({f1},{f2})", "SHUTTER_STATE_ID": "ENABLED"}
    img, mask, img64 = frames[n]
    out = []
    for m in (old, new):
        t0 = time.perf_counter()
        r = [m.correct_mask(mask, info), m.correct(img, info), m.correct(img64, info), m.correct_mask(img > 0.1, info),
             m.correct_mask(mask, info, outside=True), *m.geomcorr(img, m.focal_length(info))]
        dt = time.perf_counter() - t0
        if m is old: t_old += dt
        else: t_new += dt
        out.append(r)
    for a, b in zip(*out):
        if eq(a, b): same += 1
        else: diff += 1; print("DIFFER", n, f1, f2)
print(f"{len(calls)} frames ({len(pairs)} filter pairs x 3 sizes x 3 in random order, then 90 frames cycling 9 filters): "
      f"{same} outputs the same to the byte, {diff} differ; old {t_old:.1f} s, new {t_new:.1f} s")
print("new caches:", new._plan.cache_info(), new._map.cache_info(), len(new._edges), "edge masks kept",
      f"({sum(v.nbytes for v in new._edges.values()) / 1e6:.0f} MB)")
print("old caches:", old._plan.cache_info(), old._map.cache_info())
