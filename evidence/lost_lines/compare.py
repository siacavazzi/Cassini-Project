# Compares render.py's old and new pictures: byte for byte for the clean frames, side by side for the lost ones
# (flattened onto mid gray, so the pixels still lost, transparent, show as flat gray), and writes index.html.
# python evidence/lost_lines/compare.py OLD NEW OUTDIR
import os, sys, json, html
import numpy as np
from PIL import Image, ImageDraw

old, new, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
rows, clean_same, clean_diff = [], 0, []
for name in sorted(f[:-5] for f in os.listdir(new) if f.endswith(".json")):
    rn, ro = json.load(open(os.path.join(new, name + ".json"))), json.load(open(os.path.join(old, name + ".json")))
    pn, po = os.path.join(new, name + ".png"), os.path.join(old, name + ".png")
    a = np.asarray(Image.open(po)) if os.path.exists(po) else None
    b = np.asarray(Image.open(pn)) if os.path.exists(pn) else None
    same = a is not None and b is not None and a.shape == b.shape and np.array_equal(a, b)
    if rn["kind"] == "clean":
        if same:
            clean_same += 1
        else:
            clean_diff.append(name)
        continue

    def flat(im):
        im = Image.fromarray(im).convert("RGBA")
        bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
        return Image.alpha_composite(bg, im).convert("RGB")
    pair = Image.new("RGB", (2048 + 16, 1024 + 40), (20, 20, 20))
    pair.paste(flat(a), (0, 40)); pair.paste(flat(b), (1024 + 16, 40))
    d = ImageDraw.Draw(pair)
    d.text((10, 12), f"BEFORE {name}", fill=(255, 255, 255)); d.text((1034, 12), f"AFTER (lost lines filled) {name}", fill=(255, 255, 255))
    pair.save(os.path.join(out, name + "_before_after.jpg"), quality=92)
    lost = rn.get("lost_px")
    rows.append(f"<h3>{html.escape(name)}</h3><p>stacked {rn.get('stacked')}; lost pixels after stacking / still lost "
                f"after the fill (1024 grid): {lost}</p><img src='{html.escape(name)}_before_after.jpg' style='width:100%'>")
summary = f"clean pictures byte-identical: {clean_same} of {clean_same + len(clean_diff)}" + (f"; differ: {clean_diff}" if clean_diff else "")
print(summary)
open(os.path.join(out, "clean_check.txt"), "w").write(summary + "\n")
open(os.path.join(out, "index.html"), "w").write(
    "<!doctype html><meta charset=utf-8><title>Lost lines before/after</title><body style='background:#111;color:#ddd;"
    "font:14px system-ui;max-width:2100px;margin:auto;padding:16px'><h1>Lost lines: before / after</h1>"
    f"<p>{html.escape(summary)}. Gray = pixels still lost (transparent), flattened onto mid gray.</p>" + "".join(rows))
