"""Pipeline-stages poster, 3600x5400, for a whole-disk mosaic (config JSON: out, tiles, point, title, lines).
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
CFG = json.load(open(sys.argv[1])); O = CFG['out']; TD = CFG['tiles']
W, H, M = 3600, 5400, 150
BG, FG, DIM, DIM2, ACC = (10, 10, 10), (236, 235, 230), (150, 148, 140), (95, 94, 90), (240, 110, 30)
HN = '/System/Library/Fonts/HelveticaNeue.ttc'
def hn(s, b=1): return ImageFont.truetype(HN, s, index=b)
def mono(s): return ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', s)
F_TITLE, F_NUM, F_BIG, F_LBL, F_M, F_MS = hn(210), hn(64), hn(150), hn(40, 0), mono(30), mono(22)
POINT = CFG['point']
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
pt = tmap['pointings'][POINT]; ids = pt['ids']; FR, FG_, FB = tmap['filters']; IR, GR, UV = ids[FR], ids[FG_], ids[FB]
NM = {'IR3': '930', 'IR1': '752', 'RED': '649', 'GRN': '568', 'BL1': '451', 'UV3': '338'}
steps = json.load(open(O + f'steps/{GR}__steps.json')); csteps = json.load(open(O + f'steps/{IR}+{GR}+{UV}__steps.json'))
tile_of = {t['id']: t for t in tiles}
NP = len(tmap['pointings']); NF = len(frames)
times = sorted(v['info']['IMAGE_TIME'] for v in meta.values())
zs = [f[7] for f in frames if f[7]]

# ---------- header
d.text((M, M + 170), CFG['title'], font=F_TITLE, fill=FG, anchor='ls')
note(W - M, M + 20, [f"{tmap['observation']}  ·  PASS {tmap['pass']}  ·  ISS NAC", CFG['when'],
                     f'RANGE {zs[0]:,.0f} → {zs[-1]:,.0f} km'.replace(',', ' ')], anchor='ra', font=F_M, fill=DIM)
note(W - M, M + 150, ['RAW  →  I/F  →  CENTRED  →  TILE  →  COLOUR  →  MOSAIC'], anchor='ra', font=F_M, fill=ACC)
d.line((M, 420, W - M, 420), fill=DIM2, width=2)

# ---------- 06 mosaic hero (native pixels, 1:1)
TOP = 560
mos = Image.open(O + 'mosaic_full.png').convert('RGBA'); mw, mh = mos.size
bb = mos.getchannel('A').getbbox()
rep = json.load(open(O + 'mosaic_report.json'))
tag(M, TOP - 40, '06', 'MOSAIC')
note(M + 420, TOP - 70, ['obs_mosaic.so_far', f"{mw} × {mh} px  ·  {rep['mosaic']} colour tiles, {NP} pointings"], font=F_MS)
hx, hy = M - bb[0], TOP + 10 - bb[1]
img.paste(mos, (hx, hy), mos)
poly = [(hx + u * mw, hy + v * mh) for u, v in pt['poly']]
for i, p in enumerate(tmap['pointings']):
    q = [(hx + u * mw, hy + v * mh) for u, v in p['poly']]
    if i != POINT: d.line(q + [q[0]], fill=(48, 48, 46), width=1)
d.line(poly + [poly[0]], fill=ACC, width=5)
for i, p in enumerate(tmap['pointings']):
    cx, cy = hx + p['center'][0] * mw, hy + p['center'][1] * mh
    d.text((cx, cy), f'{i + 1:02d}', font=mono(26), fill=ACC if i == POINT else (200, 200, 194), anchor='mm', stroke_width=3, stroke_fill=(10, 10, 10))
HERO_R = hx + bb[2]

# ---------- right column: the drill-down into pointing POINT
RX = HERO_R + 110; RW = W - M - RX
d.text((W - M, TOP - 40), f'POINTING {POINT + 1:02d}', font=F_LBL, fill=ACC, anchor='rs')
y = TOP; tag(RX, y - 40, '05', 'COLOUR')
col = alpha_crop(Image.open(O + f'steps/{IR}+{GR}+{UV}__all_on.png'))
cbox, _ = put(col, RX, y + 10, 500, 500)
note(cbox[2] + 40, y + 20, ['processed_frame', '', f'R  {FR}  {NM.get(FR, "")} nm', f'G  {FG_}  {NM.get(FG_, "")} nm', f'B  {FB}  {NM.get(FB, "")} nm'], font=F_MS)
d.text((cbox[2] + 40, cbox[3] - 70), f"{csteps['diff']['align']:.2f}", font=hn(120), fill=FG, anchor='ls')
note(cbox[2] + 40, cbox[3] - 45, ['change with align off'], font=F_MS)
GAP = 150
y = cbox[3] + GAP; tag(RX, y - 40, '04', 'TILES')
note(RX + 320, y - 62, ['obs_mosaic.tile'], font=F_MS)
tw = (RW - 2 * 36) // 3; x = RX
for f, i in ((FR, IR), (FG_, GR), (FB, UV)):
    t = tile_of[i]; tb, _ = put(Image.open(TD + f"{t['n']}.png"), x, y + 10, tw, tw)
    sh = (t.get('registered') or {}).get('shift')
    note(x, tb[3] + 16, [f"{f}  tile {t['n']:02d}", (f'{sh[0]:+.2f}, {sh[1]:+.2f} px' if sh else 'reference')], font=F_MS)
    x += tw + 36
y = y + 10 + tw + GAP + 45
tag(RX, y - 40, '03', ''); tag(RX + tw + 36, y - 40, '02', ''); tag(RX + 2 * (tw + 36), y - 40, '01', '')
for k, L in enumerate(('CENTRED', 'I/F', 'RAW')): d.text((RX + k * (tw + 36) + 92, y - 40), L, font=F_LBL, fill=FG, anchor='ls')
c3, _ = put(alpha_crop(Image.open(O + f'steps/{GR}__all_on.png')), RX, y + 10, tw, tw)
iof = np.load(O + f'frames/{GR}_iof.npy'); lost = np.isnan(iof); hi = float(np.nanpercentile(iof, 99.9))
g = (np.clip(np.nan_to_num(iof) / hi, 0, 1) * 255).astype(np.uint8); rgb = np.dstack([g] * 3); rgb[lost] = ACC
c2, _ = put(Image.fromarray(rgb), RX + tw + 36, y + 10, tw, tw)
raw = Image.open(O + f'frames/{GR}_raw.png'); c1, _ = put(raw, RX + 2 * (tw + 36), y + 10, tw, tw)
inf = meta[GR]['info']
note(RX, c3[3] + 16, ['processed_frame', 'SPICE north up'], font=F_MS)
note(c2[0], c2[3] + 16, ['science_frame', f'I/F 0–{hi:.2f}'], font=F_MS)
note(c1[0], c1[3] + 16, [GR, f"{inf['INSTRUMENT_MODE_ID']} {raw.width}² {float(inf['EXPOSURE_DURATION']):.0f} ms"], font=F_MS)
y = c3[3] + GAP + 45
tag(RX, y - 40, '±', 'ONE STEP OFF')
aw = (RW - 3 * 24) // 4; x = RX
for s in ('calibrate', 'fill', 'flat', 'dark'):
    ab, _ = put(alpha_crop(Image.open(O + f'steps/{GR}__off_{s}.png')), x, y + 10, aw, aw)
    d.text((x, ab[3] + 62), f"{steps['diff'][s]:.2f}", font=hn(54), fill=FG, anchor='ls')
    d.text((x, ab[3] + 98), f"− {s}", font=F_MS, fill=DIM, anchor='ls'); x += aw + 24
ABL_END = ab[3] + 110
d.line((RX - 55, TOP - 90, RX - 55, max(ABL_END, hy + bb[3])), fill=ACC, width=3)

# ---------- one mosaic per colour filter = the colour mosaic
y = max(ABL_END, hy + bb[3]) + 130
d.line((M, y - 60, W - M, y - 60), fill=DIM2, width=2)
d.text((M, y + 10), 'ONE MOSAIC PER FILTER', font=F_LBL, fill=FG, anchor='ls')
note(M + 560, y - 18, ['obs_mosaic.filter_mosaic  →  colour_picture'], font=F_MS)
y += 60; n = 4; pw = 720; gap = (W - 2 * M - n * pw) // (n - 1); x = M
cnt = rep.get('count') or {}
lay = json.load(open(O + 'layout.json'))['count']
panels = [(f, f'filter_{f}.png') for f in tmap['filters']] + [('COLOUR', 'mosaic_full.png')]
for k, (name, path) in enumerate(panels):
    pb, _ = put(Image.open(O + path).crop(bb), x, y, pw, None)
    num = rep['mosaic'] if name == 'COLOUR' else lay.get(name)
    d.text((x, pb[3] + 50), name, font=F_LBL, fill=FG, anchor='ls'); d.text((x + pw, pb[3] + 50), str(num), font=F_LBL, fill=DIM, anchor='rs')
    if k < n - 1: d.text((x + pw + gap / 2, (pb[1] + pb[3]) / 2), '=' if k == n - 2 else '+', font=F_NUM, fill=ACC, anchor='mm')
    x += pw + gap
y = pb[3] + 130

# ---------- big numbers
d.line((M, y - 40, W - M, y - 40), fill=DIM2, width=2)
lost_share = sum(v['nan'] for v in meta.values()) / sum((512 if v['info']['INSTRUMENT_MODE_ID'] == 'SUM2' else 1024) ** 2 for v in meta.values())
import datetime as dt
def t_of(s): return dt.datetime.strptime(s[:17], '%Y-%jT%H:%M:%S')
mins = round((t_of(times[-1]) - t_of(times[0])).total_seconds() / 60)
nfilt = len({f[2] for f in frames})
stats = [(str(NF), 'frames'), (str(NP), 'pointings'), (str(nfilt), 'filters'), (str(mins), 'minutes'), (f'{lost_share:.0%}', 'pixels lost'), ('1', 'mosaic')]
sw = (W - 2 * M) // len(stats); x = M
for v, L in stats:
    d.text((x, y + 140), v, font=F_BIG, fill=FG, anchor='ls'); d.text((x, y + 190), L, font=F_M, fill=DIM, anchor='ls'); x += sw
y += 280

# ---------- frame-ID wall: every raw frame, pointing (columns, time order) x filter (rows, order taken)
d.line((M, y - 20, W - M, y - 20), fill=DIM2, width=2); y += 60
tag(M, y, '01', 'EVERY RAW FRAME')
y += 50
order = CFG.get('rows', list(tmap['filters'][::-1]) + ['CL1/CL2'])
LW = 150; cg = 10; cw = (W - 2 * M - LW - (NP - 1) * cg) // NP; ch = cw + 30
def frame_of(p, f):
    return p['ids'].get(f) or p.get('luminance', {}).get(f) or p.get('also', {}).get(f)
for r, f in enumerate(order):
    d.text((M, y + r * ch + cw / 2), 'CLEAR' if f == 'CL1/CL2' else f, font=F_LBL, fill=DIM, anchor='lm')
for c, p in enumerate(tmap['pointings']):
    x = M + LW + c * (cw + cg)
    if c == POINT: d.rectangle((x - 6, y - 6, x + cw + 6, y + len(order) * ch - 8), outline=ACC, width=4)
    for r, f in enumerate(order):
        i = frame_of(p, f); yy = y + r * ch
        if i is None:
            d.line((x, yy, x + cw, yy + cw), fill=DIM2, width=2); d.line((x + cw, yy, x, yy + cw), fill=DIM2, width=2); continue
        put(Image.open(O + f'frames/{i}_raw.png'), x, yy, cw, cw)
        d.text((x, yy + cw + 18), i[1:11], font=mono(13), fill=ACC if c == POINT else DIM, anchor='ls')
    d.text((x + cw / 2, y + len(order) * ch + 22), f'{c + 1:02d}', font=mono(22), fill=ACC if c == POINT else DIM, anchor='mm')
WALL_END = y + len(order) * ch + 40

note(M, H - 75, ['Images NASA/JPL/Space Science Institute  ·  every picture made by the Cassini Project pipeline, origin/main 5609624'], font=F_MS, fill=DIM2)
print('content ends at', WALL_END, 'of', H)
out = CFG['out'] + CFG['name'] + '.png'
img.save(out); img.convert('RGB').resize((W // 4, H // 4), Image.LANCZOS).save(CFG['out'] + CFG['name'] + '_preview.jpg', quality=90)
print('wrote', out)
