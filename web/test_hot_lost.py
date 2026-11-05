"""Synthetic check of the hot pixel repair next to lost lines (dark_current.repair_hot's lost): a 2x2-summed frame
that lost every other line in downlink has its hot pixels put back to the median of the real pixels round them, not to
the lost lines' level (black dots in Rhea ISS_162RH_REGMAP001's mosaic once the fill step had filled only the lines);
without lost pixels, and where every pixel round one is lost, the repair is as before.
Run: python web/test_hot_lost.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import dark_current as dc

ok = True


def check(name, cond, detail=None):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail is not None else ""))


L = 512
hot = np.array([[101, 200, 1], [301, 50, 1], [11, 11, -1]], np.int16)   # (line, sample, +1 hot / -1 dead)
dc.hot_file = lambda *a, **k: None
dc.hot_map = lambda info: hot
info = {"LINES": str(L), "INSTRUMENT_ID": "ISSNA"}
dc._value = lambda info, key, default=None: info.get(key, default)

rng = np.random.default_rng(1)
native = rng.normal(500, 10, (L, L)).astype(np.float32)
native[101, 200] = 1500
native[301, 50] = 1500
native[11, 11] = 0
lost = np.zeros((L, L), bool)
lost[0::2] = True                      # every other line lost
native[lost] = -60                     # the lost lines' level after the bias came off


def up(a):
    return np.repeat(np.repeat(a, 2, 0), 2, 1).copy()


img = up(native)
n_old = dc.repair_hot(img.copy(), info)
plain = img.copy()
dc.repair_hot(plain, info)
img2 = img.copy()
n_new = dc.repair_hot(img2, info, lost=lost)
check("with lost: hot pixel put back to the real pixels round it", 470 < img2[202, 400] < 530, img2[202, 400])
check("with lost: the other hot pixel too", 470 < img2[602, 100] < 530, img2[602, 100])
check("as many repaired", n_new >= 2, (n_old, n_new))
check("lost lines left as they are (the fill step's)", np.all(img2[0:2, :] == -60))

clean = up(rng.normal(500, 10, (L, L)).astype(np.float32))
clean[200, 400:402] = clean[201, 400:402] = 1500
a, b = clean.copy(), clean.copy()
dc.repair_hot(a, info)
dc.repair_hot(b, info, lost=np.zeros((L, L), bool))
check("no lost pixels: the same repair as before", np.array_equal(a, b))

sky = up(np.full((L, L), -60, np.float32))
sky[202, 400:402] = sky[203, 400:402] = 900
gone = np.ones((L, L), bool)
gone[101, 200] = False
dc.repair_hot(sky, info, lost=gone)
check("every pixel round it lost: the plain median, as before", sky[202, 400] == -60, sky[202, 400])

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
