#!/usr/bin/env python3
"""sheet.py NAME OUT.jpg TITLE [x0,y0,x1,y1 ...]: before | after full views, then each crop zoomed side by side."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
G = os.environ.get("SHEETSRC", "/Users/samiacavazzi/cassini-build/galign")
name, outp, title = sys.argv[1:4]
crops = [tuple(map(int, c.split(","))) for c in sys.argv[4:]]
sides = [s for s in (sys.argv and ["base", "glob"])]
import os
lab = {"base": "before: today", "glob": "after: global solve", "sub": "after: global solve + sub-pixel"}
if os.environ.get("SIDES"):
    sides = os.environ["SIDES"].split(",")
ims = [Image.open(f"{G}/{s}/{name}/{name}_0_0.png" if os.environ.get("SHEETSRC") else f"{G}/out/{s}/{name}/{name}_0_0.png").convert("RGB") for s in sides]
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22); big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
except Exception:
    font = big = None
W, H = ims[0].size
full_w = 900
k = full_w / W
rows = []
row = Image.new("RGB", (len(ims) * full_w + (len(ims) - 1) * 12, round(H * k) + 34), "white")
d = ImageDraw.Draw(row)
for i, (im, s) in enumerate(zip(ims, sides)):
    x = i * (full_w + 12)
    row.paste(im.resize((full_w, round(H * k)), Image.LANCZOS), (x, 34))
    d.text((x + 4, 4), lab.get(s, s), fill="black", font=font)
    for j, (x0, y0, x1, y1) in enumerate(crops):
        d.rectangle([x + x0 * k, 34 + y0 * k, x + x1 * k, 34 + y1 * k], outline=(255, 200, 0), width=2)
        d.text((x + x0 * k + 3, 34 + y0 * k + 2), str(j + 1), fill=(255, 200, 0), font=font)
rows.append(row)
for j, (x0, y0, x1, y1) in enumerate(crops):
    cw = full_w
    z = cw / (x1 - x0)
    ch = round((y1 - y0) * z)
    r = Image.new("RGB", (len(ims) * cw + (len(ims) - 1) * 12, ch + 34), "white")
    d = ImageDraw.Draw(r)
    for i, (im, s) in enumerate(zip(ims, sides)):
        r.paste(im.crop((x0, y0, x1, y1)).resize((cw, ch), Image.NEAREST if z >= 3 else Image.LANCZOS), (i * (cw + 12), 34))
        d.text((i * (cw + 12) + 4, 4), f"{j + 1}: {lab.get(s, s)} ({z:.0f}x)", fill="black", font=font)
    rows.append(r)
tw = max(r.width for r in rows)
out = Image.new("RGB", (tw, sum(r.height for r in rows) + 50 + 10 * len(rows)), "white")
ImageDraw.Draw(out).text((8, 10), title, fill="black", font=big)
y = 50
for r in rows:
    out.paste(r, (0, y)); y += r.height + 10
out.save(outp, quality=88)
print(outp, out.size, os.path.getsize(outp))
