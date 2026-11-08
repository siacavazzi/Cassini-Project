#!/usr/bin/env python3
"""Checks that the movie frames' outline search (obs_mosaic._outline_shift's _shift_cost) gives, to the bit, the
differences the cv2.warpAffine it replaced gave, and that one thread at a time makes a movie picture (_making):
python web/frames/test_outline_shift.py"""
import os
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_mosaic  # noqa: E402


def warped(x, y, dx, dy, m):
    """The cost as it was: y moved by warpAffine (INTER_LINEAR, border 0), the mean absolute difference over m."""
    moved = cv2.warpAffine(y, np.float32([[1, 0, -dx], [0, 1, -dy]]), y.shape[::-1], flags=cv2.INTER_LINEAR)
    return float(np.abs(x - moved)[m].mean())


def blurred_disk(shape, cx, cy, r, seed):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    a = ((xx - cx) ** 2 + (yy - cy) ** 2 < r * r).astype(np.float32)
    a = cv2.GaussianBlur(a, (0, 0), 3) + np.random.default_rng(seed).random(shape, dtype=np.float32) * 0.05
    return a


def test_shift_cost_matches_warp():
    shape = (160, 210)
    x, y = blurred_disk(shape, 100, 80, 50, 1), blurred_disk(shape, 112, 71, 50, 2)
    masks = {"inner": cv2.erode((x > 0.1).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0,
             "edges": np.pad(np.ones((150, 200), bool), 5),           # reaches the picture's edges
             "corner": np.zeros(shape, bool), "all": np.ones(shape, bool)}
    masks["corner"][:20, -30:] = True                                 # a box off the middle
    for name, m in masks.items():
        cost = obs_mosaic._shift_cost(x, y, m)
        for dx in range(-30, 31, 3):
            for dy in range(-25, 26, 5):
                assert cost(dx, dy) == warped(x, y, dx, dy, m), (name, dx, dy)
    # moved right off the picture: all 0 under the mask, as warpAffine gave
    m = masks["all"]
    assert obs_mosaic._shift_cost(x, y, m)(500, 0) == warped(x, y, 500, 0, m)
    # nothing under the mask: the mean of nothing, NaN, as before
    assert np.isnan(obs_mosaic._shift_cost(x, y, np.zeros(shape, bool))(0, 0))


def test_outline_shift_same_move():
    """The whole search on two offset disks: the move the warpAffine search found, found again."""
    def old(im1, im2, both, reach, step=4):
        def lit(im):
            v = cv2.GaussianBlur(im.astype(np.float32), (0, 0), 2)
            t, _ = cv2.threshold(np.clip(v[both], 0, 255).astype(np.uint8).reshape(-1, 1), 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return cv2.GaussianBlur((v > t).astype(np.float32), (0, 0), 3)
        a, b = lit(im1), lit(im2)
        inner = cv2.erode(both.astype(np.uint8), np.ones((15, 15), np.uint8), borderValue=0) > 0
        small = lambda q: cv2.resize(q, (q.shape[1] // step, q.shape[0] // step), interpolation=cv2.INTER_AREA)
        sa, sb, sm = small(a), small(b), small(inner.astype(np.float32)) > 0.99
        r = int(reach // step)
        best = min((warped(sa, sb, dx, dy, sm), dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1))
        best = min((warped(a, b, best[1] * step + dx, best[2] * step + dy, inner), best[1] * step + dx, best[2] * step + dy)
                   for dx in range(-step, step + 1) for dy in range(-step, step + 1))
        if best[0] > obs_mosaic.TINT_OUTLINE_GAIN * warped(a, b, 0, 0, inner):
            return None
        return float(best[1]), float(best[2])
    shape = (256, 256)
    for k, (ox, oy) in enumerate(((9, -6), (0, 0), (-17, 13), (3, 22))):
        g = (blurred_disk(shape, 128, 128, 70, k) * 200).astype(np.uint8)
        c = (blurred_disk(shape, 128 + ox, 128 + oy, 70, k + 10) * 160).astype(np.uint8)
        both = np.ones(shape, bool)
        both[:, :8] = False
        assert obs_mosaic._outline_shift(g, c, both, 0.04 * 1024) == old(g, c, both, 0.04 * 1024), (ox, oy)


def test_making_one_at_a_time():
    """Two threads asking for one picture: the second waits for the first, and another picture is not held up."""
    inside, most, other = [0], [0], []
    lock = threading.Lock()

    def ask(path, hold):
        with obs_mosaic._making(path):
            with lock:
                inside[0] += 1
                most[0] = max(most[0], inside[0])
            time.sleep(hold)
            with lock:
                inside[0] -= 1
    ts = [threading.Thread(target=ask, args=("a.webp", 0.2)) for _ in range(3)]
    for t in ts:
        t.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    with obs_mosaic._making("b.webp"):
        other.append(time.monotonic() - t0)
    for t in ts:
        t.join()
    assert most[0] == 1, most
    assert other[0] < 0.1, other
    assert not obs_mosaic._making_now


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
