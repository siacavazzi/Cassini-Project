import sys, json, os, numpy as np
from PIL import Image, ImageDraw
name, n, box, outp = sys.argv[1], sys.argv[2], [int(v) for v in sys.argv[3].split(",")], sys.argv[4]
OPT = [("tA", "A  today: no denoise"), ("tB", "B  gentle (from 2.5, full 6, 50%)"), ("tC", "C  recommended (from 1.8, full 5, 70%)"), ("tD", "D  stronger (from 1.5, full 4, 90%)")]
tiles = []
for d, lab in OPT:
    im = Image.open(f"out/{d}/{n}.png").convert("RGBA"); bg = Image.new("RGB", im.size); bg.paste(im, mask=im.split()[-1])
    s = json.load(open(f"out/{d}/{n}.json"))["sharpen"]
    c = bg.crop(box); k = max(1, 520 // c.size[0]); c = c.resize((c.size[0] * k, c.size[1] * k), Image.NEAREST)
    tiles.append((c, f"{lab}   grain {s.get('grain')}  share {s.get('denoise', 0)}"))
w, h = tiles[0][0].size
S = Image.new("RGB", (2 * w + 10, 2 * (h + 24) + 30), (18, 18, 18)); dr = ImageDraw.Draw(S)
dr.text((6, 8), f"{name}  ({n}, crop {box[2]-box[0]} px at {w // (box[2]-box[0])}x)", fill=(240, 240, 140))
for i, (t, l) in enumerate(tiles):
    x, y = (i % 2) * (w + 10), 30 + (i // 2) * (h + 24)
    dr.text((x + 4, y + 5), l, fill=(230, 230, 230)); S.paste(t, (x, y + 22))
S.save(outp, quality=92); print(outp, S.size)
