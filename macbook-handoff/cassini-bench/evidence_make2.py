import glob, os, sys
from PIL import Image, ImageDraw, ImageFont
old = sorted(glob.glob(sys.argv[1]+'/*/*.png')); new = sorted(glob.glob(sys.argv[2]+'/*/*.png')); LO, LN, OUT = sys.argv[3], sys.argv[4], sys.argv[5]
try: font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 28)
except Exception: font = ImageFont.load_default()
def flat(p, s, zoom=False):
    im = Image.open(p).convert('RGBA')
    if zoom: im = im.crop((1536-96, 1536-96, 1536+96, 1536+96))
    bg = Image.new('RGBA', im.size, (0,0,0,255))
    return Image.alpha_composite(bg, im).convert('RGB').resize((s, s), Image.LANCZOS)
S = 640
picks = [len(new)//6, len(new)//2, len(new)-1]
sheet = Image.new('RGB', (4*S+50, len(picks)*(S+50)+10), (20,20,20)); d = ImageDraw.Draw(sheet)
for r, i in enumerate(picks):
    y = r*(S+50)+10; name = os.path.basename(new[i])
    sheet.paste(flat(old[i], S), (10, y+40)); sheet.paste(flat(new[i], S), (S+20, y+40)); sheet.paste(flat(old[i], S, True), (2*S+30, y+40)); sheet.paste(flat(new[i], S, True), (3*S+40, y+40)); d.text((2*S+30, y), f'{LO} zoom x16', fill='white', font=font); d.text((3*S+40, y), f'{LN} zoom x16', fill='white', font=font)
    d.text((10, y), f"{LO}", fill='white', font=font); d.text((S+20, y), f"{LN}", fill='white', font=font)
sheet.save(f'evidence/{OUT}.png', optimize=True)
os.makedirs('frames_tmp/new', exist_ok=True); os.makedirs('frames_tmp/sbs', exist_ok=True)
for k, (o, n) in enumerate(zip(old, new)):
    nf = Image.new('RGB',(1536,768)); nf.paste(flat(n, 768),(0,0)); nf.paste(flat(n, 768, True),(768,0)); nf.save(f'frames_tmp/new/{k:03d}.png')
    of = flat(o, 512, True); nf2 = flat(n, 512, True)
    c = Image.new('RGB', (1034, 560), (20,20,20)); dd = ImageDraw.Draw(c)
    c.paste(of, (5, 45)); c.paste(nf2, (517, 45))
    dd.text((5, 8), f"{LO} (zoom)", fill='white', font=font); dd.text((517, 8), f"{LN} (zoom)", fill='white', font=font)
    c.save(f'frames_tmp/sbs/{k:03d}.png')
