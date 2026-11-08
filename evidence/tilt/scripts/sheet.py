import json, os, sys
from PIL import Image, ImageDraw, ImageFont
out, dest = sys.argv[1], sys.argv[2]
rows = json.load(open(os.path.join(out, "samples.json")))
S, PAD, LAB = 640, 16, 74
W = 2 * S + 3 * PAD
sheet = Image.new("RGB", (W, 60 + len(rows) * (S + LAB + PAD)), (24, 24, 28))
d = ImageDraw.Draw(sheet)
try:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20); fb = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
except Exception:
    f = fb = ImageFont.load_default()
d.text((PAD, 16), "BEFORE: north up (today)                                   AFTER: pass's own orientation (9e05b19)", fill=(230, 230, 230), font=fb)
bg = (70, 40, 90)   # transparent (lost) area shown purple
y = 60
for r in rows:
    m = lambda a: ((a + 45) % 90) - 45
    d.text((PAD, y + 6), f"{r['body']}  {r['date']}  {', '.join(r['ids'])}  ({'centred' if r['centre'] else 'close-up, north pass'})", fill=(255, 255, 255), font=f)
    d.text((PAD, y + 34), f"tilt before {r['tilt_before']:.1f}° (looks {abs(m(r['tilt_before'])):.1f}° off square)   after {r['tilt_after']:.2f}°   "
                          f"pass turn {r['view_turn']}°   transparent {r['before']['transparent']*100:.1f}% -> {r['after']['transparent']*100:.1f}%", fill=(200, 200, 200), font=f)
    for k, tag in enumerate(("before", "after")):
        im = Image.open(os.path.join(out, r[tag]["png"])).convert("RGBA").resize((S, S), Image.LANCZOS)
        tile = Image.new("RGBA", (S, S), bg + (255,)); tile.alpha_composite(im)
        sheet.paste(tile.convert("RGB"), (PAD + k * (S + PAD), y + LAB))
    y += S + LAB + PAD
sheet.save(dest, quality=88)
print(dest, os.path.getsize(dest))
