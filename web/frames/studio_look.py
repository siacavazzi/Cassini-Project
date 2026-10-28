#!/usr/bin/env python3
"""
A Cassini Studio look applied to a finished picture, as the studio's WebGL pass draws it
(web/cassini-os/src/studio.html, FS and renderer().draw): the movie editor's look on every picture of an exported film.

The look is the color part of a studio recipe (the same short string the studio puts in links and gallery items,
e.g. "ex:0.3,ct:20,sa:15,fi:warm,st:80"): exposure, contrast, black and white levels, midtones, saturation, warmth,
tint, sharpness, sepia tone, and a filter at a strength, which moves those sliders by its own amounts. The frame keys
(turns, flips, straighten, crop, trim) are not a film's and are ignored here. Like the studio, this works on the
picture the pipeline made; nothing here touches the pipeline.

Every number below is the shader's (a picture drawn here and by the page's WebGL pass differ by a level or two of
255 at most: the shader's float precision; test_studio_look.py checks the arithmetic).

  look = studio_look.parse("ex:0.3,ct:20,fi:warm")
  im = studio_look.apply(im, look)          # PIL RGB in, PIL RGB out (the same image when the look does nothing)
"""
import numpy as np
from PIL import Image

# the studio's sliders: key, short key, range, rest (studio.html ADJ, TONE, DEF)
ADJ = {"exposure": ("ex", -2, 2, 0), "contrast": ("ct", -100, 100, 0), "black": ("bk", 0, 60, 0),
       "white": ("wt", 40, 100, 100), "midtones": ("md", -100, 100, 0), "saturation": ("sa", -100, 100, 0),
       "warmth": ("wa", -100, 100, 0), "tint": ("ti", -100, 100, 0), "sharpness": ("sh", 0, 100, 0),
       "tone": ("to", 0, 100, 0)}
# the studio's filters (studio.html FILTERS): their own amounts, at the recipe's strength
FILTERS = {"none": {}, "vivid": {"saturation": 35, "contrast": 15}, "mono": {"saturation": -100},
           "noir": {"saturation": -100, "contrast": 45, "black": 6}, "warm": {"warmth": 35, "saturation": 8},
           "cool": {"warmth": -30, "tint": -5}, "sepia": {"saturation": -100, "tone": 80}}
SHORT = {v[0]: k for k, v in ADJ.items()}
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def clamp(v, a, b):
    return max(a, min(b, v))


def parse(s):
    """The look of a studio recipe string (studio.html decode), or None when it changes nothing."""
    p = {k: v[3] for k, v in ADJ.items()}
    p.update(filter="none", strength=100.0)
    for kv in str(s or "").split(","):
        k, _, v = kv.partition(":")
        try:
            if k in SHORT:
                lo, hi = ADJ[SHORT[k]][1:3]
                p[SHORT[k]] = clamp(float(v), lo, hi)
            elif k == "fi" and v in FILTERS:
                p["filter"] = v
            elif k == "st":
                p["strength"] = clamp(float(v), 0, 100)
        except ValueError:
            continue
    return None if effective(p) == effective(None) else p


def effective(p):
    """The sliders drawn: the recipe's plus its filter's amounts at its strength (studio.html effective)."""
    if p is None:
        return {k: v[3] for k, v in ADJ.items()}
    f = FILTERS.get(p.get("filter"), {})
    return {k: clamp(p[k] + f.get(k, 0) * p["strength"] / 100, v[1], v[2]) for k, v in ADJ.items()}


def encode(p):
    """The short string of a look (only what is not at rest), the way the studio writes it."""
    if not p:
        return ""
    out = [f"{ADJ[k][0]}:{+round(p[k], 4):g}" for k in ADJ if p[k] != ADJ[k][3]]
    if p.get("filter", "none") != "none":
        out.append(f"fi:{p['filter']}")
    if p.get("strength", 100) != 100:
        out.append(f"st:{+round(p['strength'], 4):g}")
    return ",".join(out)


def apply(im, p, ev=0.0):
    """Picture im (PIL) with look p drawn over it, as the studio's shader draws it, RGB. ev: exposure added to the
    look's (the movie editor's exposure level for the picture), the sum within the exposure slider's range."""
    if not p and not ev:
        return im
    if ev:
        p = dict(p or effective(None), filter=(p or {}).get("filter", "none"), strength=(p or {}).get("strength", 100.0))
        p["exposure"] = p["exposure"] + ev
    e = effective(p)
    c = np.asarray(im.convert("RGB"), np.float32) / 255
    sharp = e["sharpness"] / 100 * 2.5
    if sharp > 0:
        # the four neighbours, the edge repeated (the texture clamps to its edge)
        q = np.pad(c, ((1, 1), (1, 1), (0, 0)), mode="edge")
        b = (q[1:-1, 2:] + q[1:-1, :-2] + q[2:, 1:-1] + q[:-2, 1:-1]) * 0.25
        c = c + (c - b) * sharp
    blk, wht = e["black"] / 100, e["white"] / 100
    c = np.maximum((c - blk) / max(wht - blk, 0.004), 0) * 2 ** e["exposure"]
    c = np.power(c, 2 ** (-e["midtones"] / 100))
    con = 1 + e["contrast"] / 100 * (1.2 if e["contrast"] > 0 else 0.9)
    c = (c - 0.5) * con + 0.5
    warm, tint = e["warmth"] / 100, e["tint"] / 100
    c = c * np.array([1 + warm * 0.22, 1 - warm * 0.03 - tint * 0.16, 1 - warm * 0.26], np.float32) * (1 + tint * 0.06)
    lum = (np.clip(c, 0, 1) @ LUMA)[..., None]
    c = lum + (c - lum) * (1 + e["saturation"] / 100)
    tone = e["tone"] / 100
    if tone:
        c = c + (lum * np.array([1.07, 0.86, 0.62], np.float32) + np.array([0.03, 0.02, 0], np.float32) - c) * tone
    return Image.fromarray(np.round(np.clip(c, 0, 1) * 255).astype(np.uint8), "RGB")
