import sys, os
sys.path.insert(0, os.path.expanduser("~/cassini-build/denoise/wt/web/frames"))
import numpy as np, studio_look as L
from PIL import Image, ImageDraw
ev = os.path.expanduser("~/cassini-build/denoise/ev")
i, looks, box, labels, outname = sys.argv[1], sys.argv[2].split("|"), [int(v) for v in sys.argv[3].split(",")], sys.argv[4].split("|"), sys.argv[5]
src = Image.open(f"{ev}/{i}.png").convert("RGB")
tiles = []
for k, lk in enumerate(looks):
    gl = Image.open(f"{ev}/gl/{i}_{k}.jpg").convert("RGB")
    py = L.apply(src, L.parse(lk))
    d = np.abs(np.asarray(gl, np.int16) - np.asarray(py, np.int16))
    print(lk, "webgl vs python: max", d.max(), "p99", np.percentile(d, 99), "mean", d.mean().round(3))
    t = gl.crop(box).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.NEAREST)
    tiles.append(t)
w, h = tiles[0].size
sheet = Image.new("RGB", (w * len(tiles) + 8 * (len(tiles) - 1), h + 30), (24, 24, 24))
dr = ImageDraw.Draw(sheet)
for k, t in enumerate(tiles):
    sheet.paste(t, (k * (w + 8), 30)); dr.text((k * (w + 8) + 6, 8), labels[k], fill=(230, 230, 230))
sheet.save(f"{ev}/{outname}")
print("saved", outname, sheet.size)
