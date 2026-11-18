#!/usr/bin/env python3
"""Checks web/frames/studio_look.py, the Cassini Studio look the movie export puts on its pictures:
python web/frames/test_studio_look.py"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import studio_look as L  # noqa: E402


def picture():
    y, x = np.mgrid[0:64, 0:64]
    return Image.fromarray(np.dstack([x * 4, y * 4, (x + y) * 2]).astype(np.uint8), "RGB")


def test_rest():
    # nothing to do: no look at all, and the frame keys alone (a picture's crop) are not a film's
    assert L.parse("") is None and L.parse("cr:0.1_0.1_0.5_0.5,q:1,fi:none") is None
    im = picture()
    assert L.apply(im, None) is im


def test_parse_encode():
    p = L.parse("ex:0.3,ct:20,sa:500,fi:warm,st:80,bogus:1,wa:x")
    assert p["exposure"] == 0.3 and p["contrast"] == 20 and p["saturation"] == 100 and p["filter"] == "warm" and p["strength"] == 80
    assert L.parse(L.encode(p)) == p
    assert L.encode(p) == "ex:0.3,ct:20,sa:100,fi:warm,st:80"


def test_effective():
    # a filter moves the sliders by its own amounts at its strength, clamped (studio.html effective)
    e = L.effective(L.parse("fi:noir,st:50,ct:90"))
    assert e["saturation"] == -50 and e["contrast"] == 100 and e["black"] == 3


def test_pixels():
    im = picture()
    a = np.asarray(im, np.float32) / 255
    # exposure +1 EV doubles, clipped
    out = np.asarray(L.apply(im, L.parse("ex:1")), np.float32) / 255
    assert np.abs(out - np.clip(a * 2, 0, 1)).max() <= 1 / 255
    # saturation -100 is the luminance in every channel
    out = np.asarray(L.apply(im, L.parse("sa:-100")), np.int16)
    assert np.abs(out[..., 0] - out[..., 1]).max() <= 1 and np.abs(out[..., 1] - out[..., 2]).max() <= 1
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    assert np.abs(out[..., 0] / 255 - lum).max() <= 1 / 255
    # black and white levels stretch [bk, wt] to [0, 1]
    out = np.asarray(L.apply(im, L.parse("bk:20,wt:80")), np.float32) / 255
    assert np.abs(out - np.clip((a - 0.2) / 0.6, 0, 1)).max() <= 1 / 255
    # warmth adds red and takes blue
    out = np.asarray(L.apply(im, L.parse("wa:50")), np.float32)
    assert out[..., 0].mean() > np.asarray(im)[..., 0].mean() and out[..., 2].mean() < np.asarray(im)[..., 2].mean()


def test_denoise():
    # off at rest; on, grain in a flat area is smoothed while a strong edge keeps its step and its place
    assert L.parse("dn:0") is None
    rng = np.random.default_rng(1)
    a = np.zeros((48, 48, 3), np.float32)
    a[:, 24:] = 0.6
    a = np.clip(a + 0.2 + rng.normal(0, 0.02, a.shape), 0, 1)
    im = Image.fromarray(np.round(a * 255).astype(np.uint8), "RGB")
    out = np.asarray(L.apply(im, L.parse("dn:60")), np.float32) / 255
    assert out[:, 3:20].std() < a[:, 3:20].std() / 3
    assert abs((out[:, 27:].mean() - out[:, :21].mean()) - (a[:, 27:].mean() - a[:, :21].mean())) < 0.01
    assert out[:, 22].mean() < 0.3 and out[:, 25].mean() > 0.7
    # denoise with sharpness sharpens the smoothed picture, and links keep both
    assert L.encode(L.parse("sh:20,dn:40")) == "dn:40,sh:20" and L.override("sh:10,dn:30") == "dn:30,sh:10"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
