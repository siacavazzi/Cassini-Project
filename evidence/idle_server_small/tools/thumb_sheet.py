#!/usr/bin/env python3
"""thumb_sheet.py OUT.png SPEC.json

A sheet of Highlights thumbnails at their own size (256 px, no enlargement), on the dark background the page shows
them on. SPEC: {"title": ..., "subtitle": ..., "rows": [{"heading": ..., "cells": [{"label": ..., "path": file or
null, "note": ...}, ...]}, ...]}. A cell with no path is drawn as an empty frame with its note (a thumbnail that was
never made)."""
import json, sys
from PIL import Image, ImageDraw, ImageFont

out, spec = sys.argv[1], json.load(open(sys.argv[2]))
BG, TILE, INK, INK2, LINE = (17, 17, 16), (0, 0, 0), (240, 239, 236), (195, 194, 183), (70, 69, 64)
S = 2   # drawn at twice the size so the text is sharp; the thumbnails are doubled with nearest neighbour (their own pixels)
T, PAD, GAP, CAP = 256 * S, 28 * S, 20 * S, 64 * S


def font(size, bold=False):
    for name, index in (("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0), ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0)):
        try:
            return ImageFont.truetype(name, size * S, index=index)
        except OSError:
            pass
    return ImageFont.load_default()


F_TITLE, F_SUB, F_HEAD, F_LABEL, F_NOTE = font(20, True), font(13), font(15, True), font(13, True), font(12)
cols = max(len(r["cells"]) for r in spec["rows"])
W = PAD * 2 + cols * T + (cols - 1) * GAP
d = ImageDraw.Draw(Image.new("RGB", (8, 8)))   # (to measure text before the sheet's size is known)


def wrap(text, f, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        if d.textlength((line + " " + w).strip(), font=f) <= width:
            line = (line + " " + w).strip()
        else:
            lines.append(line); line = w
    return lines + [line] if line else lines


title, sub = wrap(spec["title"], F_TITLE, W - 2 * PAD), wrap(spec.get("subtitle", ""), F_SUB, W - 2 * PAD)
head_h = PAD + len(title) * 26 * S + len(sub) * 18 * S + 22 * S
row_h = 34 * S + T + CAP
H = head_h + len(spec["rows"]) * row_h + PAD
im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)
for n, line in enumerate(title):
    d.text((PAD, PAD - 4 * S + n * 26 * S), line, font=F_TITLE, fill=INK)
for n, line in enumerate(sub):
    d.text((PAD, PAD + len(title) * 26 * S + 2 * S + n * 18 * S), line, font=F_SUB, fill=INK2)
y = head_h
for r in spec["rows"]:
    d.text((PAD, y), r["heading"], font=F_HEAD, fill=INK)
    y0 = y + 30 * S
    for k, c in enumerate(r["cells"]):
        x = PAD + k * (T + GAP)
        d.rectangle([x, y0, x + T - 1, y0 + T - 1], fill=TILE, outline=LINE, width=S)
        if c.get("path"):
            th = Image.open(c["path"]).convert("RGBA")
            th = th.resize((th.width * S, th.height * S), Image.NEAREST)
            im.paste(th, (x + (T - th.width) // 2, y0 + (T - th.height) // 2), th)
        else:
            for n, line in enumerate(wrap(c.get("empty", "no thumbnail"), F_NOTE, T - 40 * S)):
                d.text((x + 20 * S, y0 + T // 2 - 16 * S + n * 16 * S), line, font=F_NOTE, fill=INK2)
        d.text((x, y0 + T + 8 * S), c["label"], font=F_LABEL, fill=INK)
        for n, line in enumerate(wrap(c.get("note", ""), F_NOTE, T)[:2]):
            d.text((x, y0 + T + 27 * S + n * 15 * S), line, font=F_NOTE, fill=INK2)
    y += row_h
im.save(out)
print(out, im.size)
