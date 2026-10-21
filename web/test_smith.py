"""Synthetic check of export_attitude.smith(): AACS pointing 50 deg off inside a window, c-smithed anchors
on every third image. Run: python web/test_smith.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from export_attitude import smith, qmul, qconj, qangle, CAM_TO_BODY, SMITH_REACH
def rot(axis, deg):
    a = np.radians(deg) / 2; ax = np.array(axis, float) / np.linalg.norm(axis)
    return np.r_[np.cos(a), np.sin(a) * ax]
rng = np.random.default_rng(1)
truth = lambda t: qmul(rot([0, 0, 1], t / 600.0), rot([1, 0.3, 0], 20))   # slow turn
D = rot([0.2, 1, 0], 50)                                                   # AACS error inside the window
bad = lambda t: 1e5 <= t <= 1.4e5
rc = lambda t: qmul(qconj(D), truth(t)) if bad(t) else truth(t)
ets = np.arange(0, 3e5, 900.0) + 7
cams = ["N" if i % 2 else "W" for i in range(len(ets))]
smithed = np.array([i % 3 == 0 for i in range(len(ets))])
cam_of = lambda q, c: qmul(qconj(CAM_TO_BODY[c]), q)
img_q = np.array([cam_of(truth(t) if s else rc(t), c) for t, s, c in zip(ets, smithed, cams)])
bg_t = np.arange(0, 3e5, 600.0)
bg_q = np.array([rc(t) for t in bg_t])
ni, nb, ang = smith(img_q, cams, ets, smithed, rc, bg_t, bg_q, 0.5)
err_bg = [qangle(q, truth(t)) for q, t in zip(nb, bg_t)]
err_img = [qangle(qmul(CAM_TO_BODY[c], q), truth(t)) for q, t, c in zip(ni, ets, cams)]
before = [qangle(q, truth(t)) for q, t in zip(bg_q, bg_t)]
print("before max", max(before), "after bg max", max(err_bg), "img max", max(err_img), "anchors", len(ang), sum(a > .5 for a in ang))
# window edges: within one anchor spacing of the window ends the correction ramps; elsewhere exact
inner = [e for e, t in zip(err_bg, bg_t) if 1.03e5 <= t <= 1.37e5 or t < 0.97e5 or t > 1.43e5]
assert max(inner) < 1e-3, max(inner)
untouched = [e for e, t in zip(err_bg, bg_t) if t < 1e5 - SMITH_REACH or t > 1.4e5 + SMITH_REACH]
assert max(untouched) < 1e-4
print("ok")
# --refine samples inside a c-smithed window already carry the smithed attitude: they must not be offset again
bg_t2 = np.sort(np.r_[bg_t, ets[smithed] + 0.1])
in_win = np.isin(bg_t2, ets[smithed] + 0.1)
bg_q2 = np.array([truth(t) if w else rc(t) for t, w in zip(bg_t2, in_win)])
_, nb2, _ = smith(img_q, cams, ets, smithed, rc, bg_t2, bg_q2, 0.5, in_win)
err2 = [qangle(q, truth(t)) for q, t in zip(nb2, bg_t2)]
assert max(e for e, w in zip(err2, in_win) if w) < 1e-6
assert max(e for e, t in zip(err2, bg_t2) if 1.03e5 <= t <= 1.37e5) < 1e-3
print("ok (refined samples inside windows kept)")
