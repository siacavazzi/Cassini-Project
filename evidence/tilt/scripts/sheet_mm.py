"""sheet_mm.py OUT_BEFORE OUT_AFTER SHEET.jpg SUMMARY.txt: before left, after right, one row per picture."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
ob, oa, dest, summ = sys.argv[1:5]
B = {r["name"]: r for r in json.load(open(os.path.join(ob, "samples.json")))}
A = json.load(open(os.path.join(oa, "samples.json")))
S, PAD, LAB = 600, 16, 74
pairs = [(ra, B.get(ra["name"]), k) for ra in A for k in range(len(ra["pictures"]))]
W = 2 * S + 3 * PAD
sheet = Image.new("RGB", (W, 60 + len(pairs) * (S + LAB + PAD)), (24, 24, 28))
d = ImageDraw.Draw(sheet)
try:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 19); fb = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
except Exception:
    f = fb = ImageFont.load_default()
d.text((PAD, 16), "BEFORE 0ebe157: tiles north up                      AFTER ef2f872: the pass's own axes", fill=(230, 230, 230), font=fb)
bg = (70, 40, 90)   # transparent area purple
y = 60
lines = ["Movies and mosaics, no-tilt fix: BEFORE 0ebe157 (= regression-2017 for movies/mosaics) vs AFTER ef2f872 (claude/project-thread-mu5ya4)",
         "obs_mosaic.movie_webp(frame, 1024, cache, wait=True, ahead=0) (centre=True default) and obs_mosaic.mosaic_webp(last frame, 1024, cache) waited until nothing behind",
         "(= frame_server /frames/mosaic/<ID>.webp?size=1024). Offline on the T7 worktrees, full SPICE kernels zip, nice 19, 1 BLAS thread, fresh scratch caches, no server.",
         "turn vs axes = the frame's own north angle minus the pass's view_turn (AFTER: how far the tile is still turned; BEFORE: tiles turned by the full north angle).", ""]
for ra, rb, k in pairs:
    pa = ra["pictures"][k]; pb = rb["pictures"][k] if rb else {}
    ta, tb = pa.get("transparent"), pb.get("transparent")
    h1 = f"{ra['name']}  {ra['kind']}{' (twist)' if ra['twist'] else ''}  {pa['frame']} (tile {pa['n']+1}/{ra['tiles']})  {pa['date']}"
    h2 = (f"view_turn {ra['view_turn']}°  pass turns {ra['turn_range_vs_axes']}° vs axes  this tile {pa.get('turn_vs_axes')}°   "
          f"transparent {tb if tb is None else f'{tb*100:.1f}%'} -> {ta if ta is None else f'{ta*100:.1f}%'}")
    d.text((PAD, y + 6), h1, fill=(255, 255, 255), font=f); d.text((PAD, y + 34), h2, fill=(200, 200, 200), font=f)
    lines += [h1, "   " + h2, f"   before {pb.get('size')} {pb.get('secs')}s {pb.get('why') or ''} | after {pa.get('size')} {pa.get('secs')}s {pa.get('why') or ''}"]
    for c, (o, p) in enumerate(((ob, pb), (oa, pa))):
        if p.get("file"):
            im = Image.open(os.path.join(o, p["file"])).convert("RGBA"); im.thumbnail((S, S), Image.LANCZOS)
            tile = Image.new("RGBA", (S, S), bg + (255,)); tile.alpha_composite(im, ((S - im.width) // 2, (S - im.height) // 2))
            sheet.paste(tile.convert("RGB"), (PAD + c * (S + PAD), y + LAB))
        else:
            d.text((PAD + c * (S + PAD) + 20, y + LAB + 20), f"no picture: {p.get('why')}", fill=(255, 120, 120), font=f)
    y += S + LAB + PAD
sheet.save(dest, quality=85)
q = 85
while os.path.getsize(dest) > 15e6 and q > 50:
    q -= 10; sheet.save(dest, quality=q)
open(summ, "w").write("\n".join(lines) + "\n")
print(dest, os.path.getsize(dest))
