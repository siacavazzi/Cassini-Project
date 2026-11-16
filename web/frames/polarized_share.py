"""sets_passes.POLARIZED_SHARE, measured: for each narrow-angle observation taking a filter both through the visible
polarizers (a P0, P60, P120 triple) and plainly (CL1), the triple's mean total calibrated I/F over the plain frame's
nearest it (within 15 minutes, the body whole in frame), by the repo's own calibration.
Run from web/frames with the archive's environment (CASSINI_DATA, CASSINI_CISSCAL...):
  PER=20 FS=BL2,GRN,CB1 python polarized_share.py OUT.csv     (PER pairs per filter at most; prints the medians)"""
import sys, os, numpy as np, pandas as pd, cv2
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.abspath('../..'))
import calibration, label_handler
import data_source as ds
d = pd.read_csv('../../Image_index.csv', low_memory=False)
n = d[d.INSTRUMENT_ID == 'ISSNA'].copy()
n['pol'] = n.filter1.astype(str).str.match(r'^P\d')
def iof(path):
    lbl = label_handler.label(path, as_png=True)
    png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    return calibration.calibrate(png, lbl.get_info())
def flux(a):
    a = np.nan_to_num(a.astype(np.float64)); bg = np.median(a); lit = a > bg + 0.2 * (np.percentile(a, 99.5) - bg)
    return (a - bg)[lit].sum(), lit.mean()
rows = []
per = {}
for (o, tg), x in n.groupby(['OBSERVATION_ID', 'TARGET_NAME']):
    if not x.pol.any() or x.pol.all() or tg in ('SKY',):
        continue
    for f2 in os.environ.get('FS','BL2,GRN,CB1').split(','):
        if per.get(f2, 0) >= int(os.environ.get('PER', '8')):
            continue
        p = x[x.pol & (x.filter2 == f2)].sort_values('seconds_1970'); c = x[~x.pol & (x.filter2 == f2) & (x.filter1 == 'CL1')]
        if len(p) < 3 or not len(c):
            continue
        tri = p.iloc[:3]
        if set(tri.filter1) != {'P0', 'P60', 'P120'}:
            continue
        cc = c.iloc[np.argmin(abs(c.seconds_1970.values - tri.seconds_1970.mean()))]
        if abs(cc.seconds_1970 - tri.seconds_1970.mean()) > 900:
            continue
        try:
            ims = [iof(q) for q in tri.path] + [iof(cc.path)]
        except Exception as e:
            print('skip', o, f2, e); continue
        if any(a is None for a in ims) or len({a.shape for a in ims}) > 1:
            continue
        fl = [flux(a) for a in ims]
        if fl[3][1] > 0.6 or fl[3][1] < 0.002:   # want the whole body in frame
            continue
        polmean = np.mean([f[0] for f in fl[:3]]); r = polmean / fl[3][0]
        spread = (max(f[0] for f in fl[:3]) - min(f[0] for f in fl[:3])) / polmean
        rows.append((o, tg, f2, round(r, 3), round(spread, 3), round(fl[3][1], 3)))
        per[f2] = per.get(f2, 0) + 1
        print(rows[-1], flush=True)
r = pd.DataFrame(rows, columns=['obs', 'tg', 'f', 'pol_over_plain', 'angle_spread', 'lit'])
print(r.groupby('f').pol_over_plain.describe().to_string())
print(r.groupby('f').pol_over_plain.median().round(3).to_dict())
r.to_csv(sys.argv[1], index=False)
