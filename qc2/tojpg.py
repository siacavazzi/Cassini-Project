"""Spot check round 2: flatten each fetched PNG onto mid-grey by its alpha and save it as a full-size JPEG."""
import sys, pathlib
from PIL import Image
src, dst = map(pathlib.Path, sys.argv[1:3])
for p in sorted(src.glob(sys.argv[3] + "__*.png")):
    out = dst / (p.stem + ".jpg")
    if out.exists():
        continue
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    bg.alpha_composite(im)
    bg.convert("RGB").save(out, quality=90)
