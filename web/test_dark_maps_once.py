"""dark_current._parameters (the dark parameter maps and their FFTs, made once per camera, summing mode and hot pixel
list) against the form it replaced, copied here as it was at 5d600b5: the same maps and spectra to the bit, on
made-up maps (NaN, infinities, negatives, hot spots, hot pixel lists; both cameras; 1024, 512 and 256 lines) and on
the real ones when CASSINI_CISSCAL has them. And what the change is for: two threads asking at once make the maps
once, and making them takes under half the memory it took.
Run: python web/test_dark_maps_once.py"""
import glob
import os
import sys
import tempfile
import threading
import tracemalloc
import warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import dark_current as dc  # noqa: E402
import flat_field as ff  # noqa: E402

warnings.simplefilter("ignore")   # (the made-up maps' infinities overflow single precision, in both forms alike)
rng = np.random.default_rng(41)


def parameters_before(camera, lines, hot):
    path = os.path.join(ff.ROOT, "darkcurrent", f"{'nac' if camera == 'ISSNA' else 'wac'}_dark_parameters.full.cub")
    if not os.path.exists(path):
        return None
    full = np.nan_to_num(ff.read_cube(path).astype(np.float64))
    if camera == "ISSWA":
        full[0] = 0.0
    p = dc._sum_blocks(full, lines)
    if camera in dc.SMOOTH_MAP_CAMERAS:
        p = np.stack([cv2.medianBlur(band.astype(np.float32), 3) for band in p]).astype(np.float64)
    if hot:
        k = 1024 // lines
        curves = {(y, x): curve for y, x, curve in dc._hot_pixels(os.path.join(ff.ROOT, "darkcurrent", hot))}
        for (y, x), curve in curves.items():
            if camera == "ISSWA":
                curve = np.concatenate([[0.0], curve[1:]])
            p[:, y // k, x // k] += curve - full[:, y, x]
    spectra = np.fft.rfft(p, n=2 * lines, axis=1).astype(np.complex64)
    return p[0].astype(np.float32), spectra


def same(a, b):
    return all(x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes() for x, y in zip(a, b))


def both(camera, lines, hot):
    return parameters_before(camera, lines, hot), dc._parameters_made.__wrapped__(camera, lines, hot)


# made-up maps, read in place of the real ones
real_root, real_read, real_hot = ff.ROOT, ff.read_cube, dc._hot_pixels
with tempfile.TemporaryDirectory() as root:
    os.makedirs(os.path.join(root, "darkcurrent"))
    for name in ("nac", "wac"):
        open(os.path.join(root, "darkcurrent", f"{name}_dark_parameters.full.cub"), "w").close()
    try:
        ff.ROOT = root
        n = 0
        for k in range(4):
            cube = np.cumsum(rng.uniform(-5, 60, (8, 1024, 1024)), axis=0).astype(np.float32)
            cube[:, rng.random((1024, 1024)) < 0.002] *= 300          # hot spots
            cube[rng.random(cube.shape) < 0.0005] = np.nan            # what read_cube leaves of special pixels
            if k % 2:
                cube[3, 7, 9], cube[5, 600, 2] = np.inf, -np.inf
            listed = [(int(y), int(x), np.cumsum(rng.uniform(0, 900, 8)))
                      for y, x in rng.integers(0, 1024, (300, 2))] + [(5, 5, np.full(8, 3.0)), (5, 5, np.arange(8.0))]
            ff.read_cube = lambda path, cube=cube: cube.copy()
            dc._hot_pixels = lambda path, listed=listed: listed
            for camera in ("ISSNA", "ISSWA"):
                for lines in (1024, 512, 256):
                    for hot in ("", "made_up.tab"):
                        a, b = both(camera, lines, hot)
                        assert same(a, b), (k, camera, lines, hot)
                        assert b[0].shape == (lines, lines) and b[1].shape == (8, lines + 1, lines)
                        n += 1
        print(f"made-up maps: the same maps and spectra to the bit ({n} cases)")

        # two threads asking at once: the maps are made once, and both get the same ones
        reads, got = [], []
        cube = np.abs(cube)

        def read(path):
            reads.append(path)
            return cube.copy()
        ff.read_cube = read
        dc._parameters_made.cache_clear()
        start = threading.Barrier(2)

        def ask():
            start.wait()
            got.append(dc._parameters("ISSNA", 1024, ""))
        threads = [threading.Thread(target=ask) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(reads) == 1 and got[0][0] is got[1][0] and got[0][1] is got[1][1], len(reads)
        assert dc._parameters("ISSNA", 1024, "") is got[0] and len(reads) == 1
        # (cleared through the name the callers and the other tests know)
        assert dc._parameters.cache_info().currsize == 1
        dc._parameters.cache_clear()
        assert dc._parameters.cache_info().currsize == 0 and dc._parameters("ISSNA", 1024, "") is not got[0] and len(reads) == 2
        print("two threads at once: made once")

        # the memory making them takes (Python's and numpy's own allocations), against the old form's
        ff.read_cube = lambda path: cube.copy()
        peaks = []
        for make in (parameters_before, dc._parameters_made.__wrapped__):
            tracemalloc.start()
            make("ISSNA", 1024, "")
            peaks.append(tracemalloc.get_traced_memory()[1] / 1e6)
            tracemalloc.stop()
        assert peaks[1] < 0.5 * peaks[0], peaks
        print(f"memory to make the 1024 line maps: {peaks[0]:.0f} MB before, {peaks[1]:.0f} MB now")
    finally:
        ff.ROOT, ff.read_cube, dc._hot_pixels = real_root, real_read, real_hot
        dc._parameters_made.cache_clear()

# the real maps, where they are
if os.path.exists(os.path.join(ff.ROOT, "darkcurrent", "nac_dark_parameters.full.cub")):
    lists = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ff.ROOT, "darkcurrent", "WAC_hotpix*.tab")))
    n = 0
    for camera, hots in (("ISSNA", [""]), ("ISSWA", [""] + lists[:1] + lists[-1:])):
        for lines in (1024, 512, 256):
            for hot in hots:
                a, b = both(camera, lines, hot)
                assert same(a, b), (camera, lines, hot)
                n += 1
    print(f"the real maps: the same to the bit ({n} cases)")
else:
    print("the real maps are not here (CASSINI_CISSCAL): skipped")
print("ok")
