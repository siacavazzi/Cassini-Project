import json, sys, os
from PIL import Image, ImageDraw, ImageFont
B, A = "_snap/out-before", "_snap/out-after"
sb = {r["name"]: r for r in json.load(open(f"{B}/samples.json"))}; sa = {r["name"]: r for r in json.load(open(f"{A}/samples.json"))}
T = 420; PAD = 16; HEAD = 64
try: font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17); small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
except Exception: font = small = ImageFont.load_default()
names = list(sa)
def tile(path):
    im = Image.open(path).convert("RGBA"); im.thumbnail((T, T))
    bg = Image.new("RGB", (T, T), (34, 34, 38)); bg.paste(im, ((T - im.width) // 2, (T - im.height) // 2), im); return bg
W = PAD + 2 * (T + PAD); H = 50 + len(names) * (T + HEAD + PAD)
sheet = Image.new("RGB", (W, H), (18, 18, 20)); d = ImageDraw.Draw(sheet)
d.text((PAD, 14), "BEFORE: #381 + #383 (camera's own square)                          AFTER: quarter turn nearest north up", fill=(230, 230, 230), font=font)
y = 50
for n in names:
    a, b = sa[n], sb[n]
    ext = "png" if a["kind"] == "still" else "webp"
    d.text((PAD, y + 4), f"{n}  ({a['kind']}, frame {a['frame']})", fill=(240, 240, 240), font=font)
    d.text((PAD, y + 28), f"north {b['north_from_top_deg']:.0f}° from the top", fill=(200, 160, 160), font=small)
    d.text((PAD * 2 + T, y + 28), f"north {a['north_from_top_deg']:.0f}° from the top" + ("  (rolled frame: square, own quarter)" if (a.get('view') or {}).get('square') else "") + ("  (ring pass: turned a quarter only)" if (a.get('view') or {}).get('quarter') else ""), fill=(160, 220, 160), font=small)
    sheet.paste(tile(f"{B}/{n}.{ext}"), (PAD, y + HEAD)); sheet.paste(tile(f"{A}/{n}.{ext}"), (PAD * 2 + T, y + HEAD))
    y += T + HEAD + PAD
os.makedirs("evidence/snap-north", exist_ok=True)
sheet.save("evidence/snap-north/snap-north-before-after-sheet.jpg", quality=88)
print(sheet.size, os.path.getsize("evidence/snap-north/snap-north-before-after-sheet.jpg"))
