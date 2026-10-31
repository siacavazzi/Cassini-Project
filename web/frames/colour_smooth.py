#!/usr/bin/env python3
"""
Color smoothing: a run of color pictures that mostly share one palette, with now and then a picture of another set of
filters (the WAC Saturn stares of 2005-07: MT3/CB2/MT2 four pointings in five, MT3/MT2/BL1 at the fifth, peach and
blue among green), has each picture's colors moved toward the palette of the pictures round it, so the odd one
bridges the gap instead of flashing. Brightness is left alone (that is exposure smoothing's) and so is the picture's
data: only the balance between its three channels moves.

It works on the finished pictures a window shows, so it runs on the viewer's computer (docs/compute-on-viewer.md):
the page's port is web/cassini-os/src/colour-smooth.html (window.cassiniColourSmooth), line for line, and
web/test_colour_smooth.py runs both on the same pictures. The server keeps no variant.

  st = palette(rgba)                      # the picture's palette: 6 numbers, or None (too little of it lit)
  want = wanted(stats, i, SPAN)           # the palette of the pictures round picture i (a median, so the odd one out
                                          # never sets it)
  out = smoothed(rgba, st, want, 1.0)     # the picture with its palette moved toward want (strength 0..1)

A palette is each channel's mean and spread of its log brightness less the pixel's mean log brightness (its color
apart from its brightness), over the lit pixels of a grid of at most GRID x GRID samples. A picture is moved by
shifting each channel's mean and scaling its spread toward the wanted ones, each pixel's mean log brightness kept, so
black stays black and a bright pixel stays as bright.
"""
import math

import numpy as np

GRID = 128        # the palette is measured on at most GRID x GRID samples of the picture (every step-th pixel)
LIT = 24          # a sample counts when the mean of its three channels is at least this (of 255): the body, not the sky
TOP = 250         # ... and none of its channels is at or above this (blown pixels have no color)
FEW = 200         # a picture with fewer lit samples has no palette (a speck, a night side): left as it is
SHIFT = 0.5       # the furthest a channel's mean moves (log brightness, about x1.65)
SPREAD = 3.0      # the furthest a channel's spread is scaled, either way
SPAN = 4          # a picture's palette is wanted from the pictures this many either side of it (9 in all)
DARK = 24         # below this mean of its channels a pixel is moved in part (none at 0): the sky's noise keeps its color


def step_of(w, h):
    return max(1, -(-max(w, h) // GRID))


def palette(rgba):
    """The picture's palette (RGBA uint8, h x w x 4): [mean R, mean G, mean B, spread R, spread G, spread B] of each
    channel's log brightness less the pixel's mean, over its lit samples, or None when fewer than FEW are lit."""
    h, w = rgba.shape[:2]
    s = step_of(w, h)
    a = rgba[::s, ::s].reshape(-1, 4).astype(np.int64)
    keep = (a[:, 3] > 0) & (a[:, 0] + a[:, 1] + a[:, 2] >= 3 * LIT) & (a[:, :3].max(axis=1) < TOP)
    a = a[keep]
    # (a grey picture, every lit sample the same in its three channels, has no palette: it is no color picture)
    if len(a) < FEW or ((a[:, 0] == a[:, 1]) & (a[:, 1] == a[:, 2])).all():
        return None
    sums, squares = [0.0] * 3, [0.0] * 3
    for r, g, b, _ in a.tolist():
        lr, lg, lb = math.log(r or 1), math.log(g or 1), math.log(b or 1)
        y = (lr + lg + lb) / 3
        for k, l in enumerate((lr, lg, lb)):
            c = l - y
            sums[k] += c
            squares[k] += c * c
    n = len(a)
    mu = [v / n for v in sums]
    sd = [math.sqrt(max(squares[k] / n - mu[k] * mu[k], 0.0)) for k in range(3)]
    return mu + sd


def median(v):
    v = sorted(v)
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def wanted(stats, i, span):
    """The palette picture i is moved toward: each number's median over the pictures from i - span to i + span that
    have a palette (stats: palettes in the order the pictures play, None for one without). None when picture i has
    none."""
    if stats[i] is None:
        return None
    near = [st for st in stats[max(0, i - span):i + span + 1] if st is not None]
    return [median([st[k] for st in near]) for k in range(6)]


def moves(own, want, strength):
    """What smoothed does to every pixel: per channel (the shift of its mean, the scale of its spread), strength of
    the way from own to want, within SHIFT and SPREAD."""
    out = []
    for k in range(3):
        d = max(-SHIFT, min(SHIFT, strength * (want[k] - own[k])))
        r = (want[3 + k] / own[3 + k]) ** strength if own[3 + k] > 1e-6 and want[3 + k] > 1e-6 else 1.0
        out.append((d, max(1 / SPREAD, min(SPREAD, r))))
    return out


def smoothed(rgba, own, want, strength):
    """rgba (uint8, h x w x 4) with its palette own moved strength (0..1) of the way to want; the same array when
    there is nothing to move."""
    if own is None or want is None or strength <= 0:
        return rgba
    mv = moves(own, want, strength)
    if all(abs(d) < 1e-9 and abs(r - 1) < 1e-9 for d, r in mv):
        return rgba
    v = rgba[..., :3].astype(np.float64)
    l = np.log(np.maximum(v, 1))
    y = l.mean(axis=2, keepdims=True)
    c = l - y
    mu = np.array(own[:3])
    d = np.array([m[0] for m in mv])
    r = np.array([m[1] for m in mv])
    c2 = mu + d + (c - mu) * r
    c2 = c2 - c2.mean(axis=2, keepdims=True)
    # (dark pixels moved in part: the sky's noise is no color to correct)
    wgt = np.minimum(v.sum(axis=2, keepdims=True) / (3 * DARK), 1.0)
    out = np.exp(y + c + (c2 - c) * wgt)
    out = np.where(v.max(axis=2, keepdims=True) > 0, np.clip(np.floor(out + 0.5), 0, 255), v)
    return np.dstack([out.astype(np.uint8), rgba[..., 3]])
