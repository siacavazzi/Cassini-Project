#!/usr/bin/env python3
"""Checks that a 4x4-summed colour set's channel match, which snaps to whole camera pixels on the frames enlarged by
repeating pixels, is refined at the frames' own size (color_image.refine_summed): python web/frames/test_summed_native_match.py"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import color_image as ci  # noqa: E402
import image_correction as ic  # noqa: E402


class Lbl:
    def __init__(self, lines):
        self.info = {"LINES": lines}


def scene(seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)
    im = np.zeros((1024, 1024), np.float32)
    for _ in range(40):
        x, y, r = rng.uniform(150, 870), rng.uniform(150, 870), rng.uniform(20, 90)
        im += rng.uniform(40, 120) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r))
    im += 150 * ((xx - 512) ** 2 + (yy - 512) ** 2 < 300 ** 2)
    return cv2.GaussianBlur(im, (0, 0), 2)


def summed(im):
    small = cv2.resize(im, (256, 256), interpolation=cv2.INTER_AREA)
    big = cv2.resize(small, (1024, 1024), interpolation=cv2.INTER_AREA)   # as label.resize_image: repeated pixels
    return cv2.cvtColor(np.clip(big, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def test_refined_to_the_true_shift():
    base = scene()
    for true in ((2.0, 1.2), (2.1, -1.4), (0.5, 2.5), (1.0, -3.0)):
        moved = cv2.warpAffine(base, np.float32([[1, 0, true[0]], [0, 1, true[1]]]), (1024, 1024), flags=cv2.INTER_CUBIC)
        imgs = [summed(base), summed(moved)]
        masks = [np.ones((1024, 1024), bool)] * 2
        shifts, how = [], []
        ic.align_with_masks(list(imgs), [m.copy() for m in masks], 0, how, found=shifts)
        before = np.hypot(shifts[1][0] - true[0], shifts[1][1] - true[1])
        ci.refine_summed(imgs, [Lbl(256), Lbl(256)], 0, shifts, how)
        after = np.hypot(shifts[1][0] - true[0], shifts[1][1] - true[1])
        assert after < 1.0 and after < before, (true, before, after, how)
        print(f"  true {true}: on the blocks {before:.2f} px off, refined {after:.2f} px off ({how[1]})")


def test_full_frames_and_mixed_sets_untouched():
    imgs = [summed(scene()), summed(scene())]
    shifts, how = [None, (2.0, 0.0)], ["reference", "phase +2.0,+0.0"]
    ci.refine_summed(imgs, [Lbl(1024), Lbl(1024)], 0, shifts, how)
    assert shifts[1] == (2.0, 0.0)
    ci.refine_summed(imgs, [Lbl(256), Lbl(1024)], 0, shifts, how)
    assert shifts[1] == (2.0, 0.0)
    shifts, how = [None, (4.0, 0.0)], ["reference", "SPICE +4.0,+0.0"]
    ci.refine_summed(imgs, [Lbl(256), Lbl(256)], 0, shifts, how)
    assert shifts[1] == (4.0, 0.0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
