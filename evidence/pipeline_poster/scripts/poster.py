"""Pipeline-stages poster, 3600x5400: Enceladus ISS_011EN_N9COL001_PRIME pass 0 (14 July 2005).
Every picture is a file the repo's pipeline wrote (worktree ~/dev/wt-pipeposter at origin/main):
  raw      frames/<id>_raw.png    archive codes, label_handler export (stages.py)
  I/F      frames/<id>_iof.npy    color_image.science_frame (calibration.calibrate); shown linear, lost px orange
  centred  steps/<id>__all_on.png color_image.processed_frame (fill, calibrate, SPICE north-up), steps toggled with
                                  calibration.stepping for the ablation row
  tile     <tiles dir>/<n>.png    obs_mosaic.tile (scaled to the pass, registered)
  colour   steps/<ir+grn+uv>__all_on.png  processed_frame of the colour set
  mosaic   mosaic_full.png, filter_<f>.png  obs_mosaic.so_far / filter_mosaic (mosaic_stage.py)
Layout only (PIL): crops to alpha, resizes, type."""
import json, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
O = '/Volumes/SAM_IAC_PHOTO/cassini-work/pipeposter/out/'
TD = '/Volumes/SAM_IAC_PHOTO/cassini-work/caches/pipeposter-cache/obs-v69-q95/ENCELADUS_ISS_011EN_N9COL001_PRIME_N_0_g9/tiles-48bd5682/'
W, H, M = 3600, 5400, 150
BG, FG, DIM, DIM2, ACC = (10, 10, 10), (236, 235, 230), (150, 148, 140), (95, 94, 90), (240, 110, 30)
HN = '/System/Library/Fonts/HelveticaNeue.ttc'
def hn(s, b=1): return ImageFont.truetype(HN, s, index=b)
def mono(s): return ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', s)
F_TITLE, F_NUM, F_BIG, F_LBL, F_M, F_MS = hn(210), hn(64), hn(150), hn(40, 0), mono(30), mono(22)
POINT = 4   # the pointing drilled into: tiger stripes
img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)

def alpha_crop(im):
    im = im.convert('RGBA'); return im.crop(im.getchannel('A').getbbox())

def put(im, x, y, w=None, h=None):
    """paste RGBA im fitted in w x h at x,y (top-left), never upscaled past 2x; returns the box drawn"""
    im = im.convert('RGBA'); s = min((w or 1e9) / im.width, (h or 1e9) / im.height)
    if abs(s - 1) > 1e-3: im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    img.paste(im, (x, y), im); return (x, y, x + im.width, y + im.height), s

def tag(x, y, n, word):
    d.text((x, y), n, font=F_NUM, fill=ACC, anchor='ls'); d.text((x + 92, y), word, font=F_LBL, fill=FG, anchor='ls')

def note(x, y, lines, anchor='la', font=None, fill=DIM):
    for L in lines:
        d.text((x, y), L, font=font or F_MS, fill=fill, anchor=anchor); y += (font or F_MS).size + 10

def arrow(x0, y0, x1, y1, w=4):
    d.line((x0, y0, x1, y1), fill=ACC, width=w)
    v = np.array([x1 - x0, y1 - y0], float); v /= np.linalg.norm(v); n = np.array([-v[1], v[0]])
    tip = np.array([x1, y1]); a = tip - 22 * v + 11 * n; b = tip - 22 * v - 11 * n
    d.polygon([tuple(tip), tuple(a), tuple(b)], fill=ACC)

unit = json.load(open(O + 'unit.json')); frames = unit['frames']; tiles = json.load(open(O + 'tiles.json'))
tmap = json.load(open(O + 'tile_map.json')); meta = json.load(open(O + 'frames/meta.json'))
steps = json.load(open(O + 'steps/N1500061303_1__steps.json')); csteps = json.load(open(O + 'steps/N1500061320_1+N1500061303_1+N1500061286_1__steps.json'))
pt = tmap['pointings'][POINT]; ids = pt['ids']; IR, GR, UV, CL = ids['IR3'], ids['GRN'], ids['UV3'], pt['luminance']['CL1/CL2']
tile_of = {t['id']: t for t in tiles}

# ---------- header
d.text((M, M + 170), 'ENCELADUS', font=F_TITLE, fill=FG, anchor='ls')
note(W - M, M + 20, ['ISS_011EN_N9COL001_PRIME  ·  PASS 0  ·  ISS NAC', '2005-07-14  19:04:49 – 19:24:52 UTC',
                     'RANGE 24 780 → 14 945 km'], anchor='ra', font=F_M, fill=DIM)
note(W - M, M + 150, ['RAW  →  I/F  →  CENTRED  →  TILE  →  COLOUR  →  MOSAIC'], anchor='ra', font=F_M, fill=ACC)
d.line((M, 420, W - M, 420), fill=DIM2, width=2)

# ---------- 06 mosaic hero (native pixels, 1:1)
TOP = 560
mos = Image.open(O + 'mosaic_full.png').convert('RGBA'); mw, mh = mos.size
bb = mos.getchannel('A').getbbox()
tag(M, TOP - 40, '06', 'MOSAIC')
note(M + 420, TOP - 70, ['obs_mosaic.so_far', f'{mw} × {mh} px  ·  29 colour tiles + 10 clear'], font=F_MS)
hx, hy = M - bb[0] + 20, TOP + 10 - bb[1] + 20
img.paste(mos, (hx, hy), mos)
poly = [(hx + u * mw, hy + v * mh) for u, v in pt['poly']]
for i, p in enumerate(tmap['pointings']):   # every pointing's footprint, faint; the drilled one in orange
    q = [(hx + u * mw, hy + v * mh) for u, v in p['poly']]
    if i != POINT: d.line(q + [q[0]], fill=(70, 70, 66), width=2)
    cx, cy = hx + p['center'][0] * mw, hy + p['center'][1] * mh
d.line(poly + [poly[0]], fill=ACC, width=5)
for i, p in enumerate(tmap['pointings']):
    cx, cy = hx + p['center'][0] * mw, hy + p['center'][1] * mh
    d.text((cx, cy), f'{i + 1:02d}', font=mono(26), fill=ACC if i == POINT else (120, 120, 114), anchor='mm')

# ---------- right column: the drill-down into pointing POINT
RX, RW = 1960, W - M - 1960
d.line((RX - 60, TOP - 90, RX - 60, 2900), fill=ACC, width=3)
d.text((W - M, TOP - 40), f'POINTING {POINT + 1:02d}', font=F_LBL, fill=ACC, anchor='rs')
# 05 colour set
y = TOP; tag(RX, y - 40, '05', 'COLOUR')
col = alpha_crop(Image.open(O + f'steps/{IR}+{GR}+{UV}__all_on.png'))
cbox, _ = put(col, RX, y + 10, 560, 560)
al = csteps['reports']['all_on'].get('aligned') or []
note(cbox[2] + 60, y + 20, ['color_image.processed_frame', '', 'R  IR3  930 nm', 'G  GRN  568 nm', 'B  UV3  338 nm', '',
                            'aligned onto GRN', f'IR3 {al[0]}', f'UV3 {al[2]}'] if len(al) == 3 else ['color_image.processed_frame'], font=F_MS)
d.text((cbox[2] + 60, cbox[3] - 70), f"{csteps['diff']['align']:.2f}", font=F_BIG, fill=FG, anchor='ls')
note(cbox[2] + 60, cbox[3] - 45, ['mean change (of 255) with align off'], font=F_MS)
GAP = 150
# 04 tiles of the three filters (obs_mosaic.tile)
y = cbox[3] + GAP; tag(RX, y - 40, '04', 'TILES')
note(RX + 330, y - 62, ['obs_mosaic.tile  ·  north up, pass scale, registered'], font=F_MS)
tw = (RW - 2 * 40) // 3; x = RX
for f, i in (('IR3', IR), ('GRN', GR), ('UV3', UV)):
    t = tile_of[i]; tb, _ = put(Image.open(TD + f"{t['n']}.png"), x, y + 10, tw, tw)
    r = t.get('registered') or {}
    sh = r.get('shift'); note(x, tb[3] + 16, [f"{f}  tile {t['n']:02d}", 'shift ' + (f'{sh[0]:+.2f}, {sh[1]:+.2f} px' if sh else '–')], font=F_MS)
    x += tw + 40
y = y + 10 + tw + GAP + 45
# 03 -> 01 the GRN frame, back to its raw codes
tag(RX, y - 40, '03', 'CENTRED'); tag(RX + tw + 40, y - 40, '02', 'I/F'); tag(RX + 2 * (tw + 40), y - 40, '01', 'RAW')
c3, _ = put(alpha_crop(Image.open(O + f'steps/{GR}__all_on.png')), RX, y + 10, tw, tw)
iof = np.load(O + f'frames/{GR}_iof.npy'); lost = np.isnan(iof); hi = float(np.nanpercentile(iof, 99.9))
g = (np.clip(np.nan_to_num(iof) / hi, 0, 1) * 255).astype(np.uint8); rgb = np.dstack([g] * 3); rgb[lost] = ACC
c2, s2 = put(Image.fromarray(rgb), RX + tw + 40, y + 10, tw, tw)
raw = Image.open(O + f'frames/{GR}_raw.png'); c1, s1 = put(raw, RX + 2 * (tw + 40), y + 10, tw, tw)
inf = meta[GR]['info']
note(RX, c3[3] + 16, ['processed_frame', 'fill · calibrate · SPICE'], font=F_MS)
note(c2[0], c2[3] + 16, ['science_frame', f'I/F 0–{hi:.2f} · orange lost'], font=F_MS)
note(c1[0], c1[3] + 16, [f"{GR}", f"{inf['INSTRUMENT_MODE_ID']} {raw.width}² · {float(inf['EXPOSURE_DURATION']):.0f} ms"], font=F_MS)
y = c3[3] + GAP + 45
# ablation: the frame with one pipeline step off (calibration.stepping)
tag(RX, y - 40, '±', 'ONE STEP OFF'); note(RX + 520, y - 62, ['calibration.stepping  ·  mean change, of 255'], font=F_MS)
aw = (RW - 3 * 30) // 4; x = RX
for s in ('calibrate', 'fill', 'flat', 'dark'):
    ab, _ = put(alpha_crop(Image.open(O + f'steps/{GR}__off_{s}.png')), x, y + 10, aw, aw)
    d.text((x, ab[3] + 66), f"{steps['diff'][s]:.2f}", font=F_NUM, fill=FG, anchor='ls')
    d.text((x, ab[3] + 104), f"− {s}", font=F_M, fill=DIM, anchor='ls'); x += aw + 30
ABL_END = ab[3] + 110
d.line((RX - 60, TOP - 90, RX - 60, ABL_END), fill=ACC, width=3)

# ---------- filter mosaics: IR3 + GRN + UV3 (+ clear) = colour
y = max(ABL_END, hy + bb[3]) + 110
d.line((M, y - 60, W - M, y - 60), fill=DIM2, width=2)
d.text((M, y + 10), 'ONE MOSAIC PER FILTER', font=F_LBL, fill=FG, anchor='ls')
note(M + 560, y - 18, ['obs_mosaic.filter_mosaic  →  colour_picture over the clear base'], font=F_MS)
y += 60; n = 5; gap = 130; pw = 470; gap = (W - 2 * M - n * pw) // (n - 1); x = M
panels = [('IR3', O + 'filter_IR3.png'), ('GRN', O + 'filter_GRN.png'), ('UV3', O + 'filter_UV3.png'), ('CLEAR', O + 'filter_L.png'), ('COLOUR', O + 'mosaic_full.png')]
cnt = {'IR3': 10, 'GRN': 9, 'UV3': 10, 'CLEAR': 10, 'COLOUR': 39}
for k, (name, path) in enumerate(panels):
    pb, _ = put(Image.open(path).crop(bb), x, y, pw, None)
    d.text((x, pb[3] + 50), name, font=F_LBL, fill=FG, anchor='ls'); d.text((x + pw, pb[3] + 50), str(cnt[name]), font=F_LBL, fill=DIM, anchor='rs')
    if k < n - 1: d.text((x + pw + gap / 2, (pb[1] + pb[3]) / 2), '=' if k == n - 2 else '+', font=F_NUM, fill=ACC, anchor='mm')
    x += pw + gap
y = pb[3] + 120

# ---------- frame-ID wall (every raw frame, pointing x filter, time runs left to right) + big numbers beside it
d.line((M, y - 50, W - M, y - 50), fill=DIM2, width=2); y += 50
tag(M, y, '01', 'EVERY RAW FRAME')
y += 50
rows = ['CL1/CL2', 'UV3', 'GRN', 'IR3']; LW = 190; cg = 20; cw = 232; ch = cw + 46
for r, f in enumerate(rows):
    d.text((M, y + r * ch + cw / 2), 'CLEAR' if f == 'CL1/CL2' else f, font=F_LBL, fill=DIM, anchor='lm')
for c in range(10):
    p = tmap['pointings'][c]; x = M + LW + c * (cw + cg)
    if c == POINT: d.rectangle((x - 9, y - 9, x + cw + 9, y + 4 * ch - 12), outline=ACC, width=4)
    for r, f in enumerate(rows):
        i = p['luminance'].get(f) if f == 'CL1/CL2' else p['ids'].get(f)
        yy = y + r * ch
        if i is None:
            d.line((x, yy, x + cw, yy + cw), fill=DIM2, width=2); d.line((x + cw, yy, x, yy + cw), fill=DIM2, width=2); continue
        put(Image.open(O + f'frames/{i}_raw.png'), x, yy, cw, cw)
        d.text((x, yy + cw + 26), i, font=mono(19), fill=ACC if c == POINT else DIM, anchor='ls')
    d.text((x + cw / 2, y + 4 * ch + 26), f'{c + 1:02d}', font=F_M, fill=ACC if c == POINT else DIM, anchor='mm')
WALL_END = y + 4 * ch + 40
lost_share = sum(v['nan'] for v in meta.values()) / sum((512 if v['info']['INSTRUMENT_MODE_ID'] == 'SUM2' else 1024) ** 2 for v in meta.values())
stats = [('39', 'frames'), ('10', 'pointings'), ('4', 'filters'), ('20', 'minutes'), (f'{lost_share:.0%}', 'of pixels lost'), ('1', 'mosaic')]
SX = M + LW + 10 * (cw + cg) + 50; sy = y - 20; step = (4 * ch) / len(stats)
d.line((SX - 30, y - 10, SX - 30, y + 4 * ch - 20), fill=DIM2, width=2)
for v, L in stats:
    d.text((SX, sy + step - 40), v, font=hn(118), fill=FG, anchor='ls'); d.text((W - M, sy + step - 44), L, font=F_MS, fill=DIM, anchor='rs'); sy += step

# ---------- footer
note(M, H - 75, ['Images NASA/JPL/Space Science Institute  ·  every picture made by the Cassini Project pipeline, origin/main 5609624'], font=F_MS, fill=DIM2)
print('content ends at', WALL_END, 'of', H)
out = sys.argv[1] if len(sys.argv) > 1 else O + 'pipeline_poster_3600x5400.png'
img.save(out); img.convert('RGB').resize((W // 4, H // 4), Image.LANCZOS).save(out.rsplit('.', 1)[0] + '_preview.jpg', quality=90)
print('wrote', out)
