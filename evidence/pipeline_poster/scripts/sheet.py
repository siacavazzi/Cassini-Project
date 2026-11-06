"""Provenance contact sheet: pointing 05's four frames (rows) through every per-frame stage (columns), each cell the
file a pipeline call wrote, labelled with the call. Layout only."""
import json, numpy as np
from PIL import Image, ImageDraw, ImageFont
O = '/Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter/out/'
TD = '/Volumes/SAM_IAC_PHOTO/cassini-work/caches/pipeposter-cache/obs-v69-q95/ENCELADUS_ISS_011EN_N9COL001_PRIME_N_0_g9/tiles-48bd5682/'
tiles = {t['id']: t for t in json.load(open(O + 'tiles.json'))}; meta = json.load(open(O + 'frames/meta.json'))
rows = [('CLEAR', 'N1500061253_1'), ('UV3', 'N1500061286_1'), ('GRN', 'N1500061303_1'), ('IR3', 'N1500061320_1')]
cols = ['01 raw  (archive codes)', '02 I/F  science_frame', '03 processed_frame', '04 obs_mosaic.tile']
C, LW, TOP, PAD = 600, 300, 140, 30
W, H = LW + 4 * (C + PAD), TOP + 4 * (C + 90)
img = Image.new('RGB', (W, H), (10, 10, 10)); d = ImageDraw.Draw(img)
F = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 24); FB = ImageFont.truetype('/System/Library/Fonts/HelveticaNeue.ttc', 40, index=1)
d.text((30, 60), 'ISS_011EN_N9COL001_PRIME · pointing 05 · every cell is a file the pipeline wrote', font=F, fill=(236, 235, 230))
for c, L in enumerate(cols): d.text((LW + c * (C + PAD), TOP - 30), L, font=F, fill=(240, 110, 30))
def fit(im):
    im = im.convert('RGBA'); bb = im.getchannel('A').getbbox(); im = im.crop(bb); s = C / max(im.size)
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
for r, (f, i) in enumerate(rows):
    y = TOP + r * (C + 90); d.text((30, y + C / 2), f, font=FB, fill=(236, 235, 230), anchor='lm')
    iof = np.load(O + f'frames/{i}_iof.npy'); lost = np.isnan(iof); hi = float(np.nanpercentile(iof, 99.9))
    g = (np.clip(np.nan_to_num(iof) / hi, 0, 1) * 255).astype(np.uint8); rgb = np.dstack([g] * 3); rgb[lost] = (240, 110, 30)
    cells = [Image.open(O + f'frames/{i}_raw.png'), Image.fromarray(rgb), Image.open(O + f'steps/{i}__all_on.png'), Image.open(TD + f"{tiles[i]['n']}.png")]
    for c, im in enumerate(cells):
        t = fit(im); img.paste(t, (LW + c * (C + PAD), y), t)
    inf = meta[i]['info']; t = tiles[i]
    d.text((LW, y + C + 34), f"{i}  {inf['INSTRUMENT_MODE_ID']}  {float(inf['EXPOSURE_DURATION']):.0f} ms", font=F, fill=(150, 148, 140))
    d.text((LW + C + PAD, y + C + 34), f"I/F 0–{hi:.2f}  lost {lost.mean():.0%} (orange)", font=F, fill=(150, 148, 140))
    d.text((LW + 3 * (C + PAD), y + C + 34), f"tile {t['n']}  reg {(t.get('registered') or {}).get('shift')}", font=F, fill=(150, 148, 140))
img.save(O + 'sheet_pointing05_stages.jpg', quality=92); print('wrote', img.size)
