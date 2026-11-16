"""Tint check: in observations taking BL2, GRN and CB1 both through the visible polarizers (P0/P60/P120) and plainly,
the corrected polarized colour (three-angle mean / POLARIZED_SHARE) over the plain frame, per filter; equal ratios
mean the polarized set has the plain set's colour."""
import sys, os, numpy as np, pandas as pd, cv2
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.abspath('../..'))
import calibration, label_handler, data_source as ds
import sets_passes; SH = sets_passes.POLARIZED_SHARE
d = pd.read_csv('../../Image_index.csv', low_memory=False)
n = d[d.INSTRUMENT_ID == 'ISSNA'].copy(); n['pol'] = n.filter1.astype(str).str.match(r'^P\d')
def iof(p):
    l = label_handler.label(p, as_png=True); return calibration.calibrate(ds.imread(l.export(), cv2.IMREAD_GRAYSCALE), l.get_info())
def flux(a):
    a = np.nan_to_num(a.astype(np.float64)); bg = np.median(a); lit = a > bg + 0.2 * (np.percentile(a, 99.5) - bg)
    return (a - bg)[lit].sum()
for (o, tg), x in n.groupby(['OBSERVATION_ID', 'TARGET_NAME']):
    if tg in ('SKY',) or not all(((x.filter2 == f) & x.pol).sum() >= 3 and ((x.filter2 == f) & ~x.pol & (x.filter1 == 'CL1')).sum() for f in SH):
        continue
    out = {}
    for f in SH:
        p = x[x.pol & (x.filter2 == f)].sort_values('seconds_1970').iloc[:3]
        c = x[~x.pol & (x.filter2 == f) & (x.filter1 == 'CL1')]
        cc = c.iloc[np.argmin(abs(c.seconds_1970.values - p.seconds_1970.mean()))]
        try:
            ims = [iof(q) for q in p.path] + [iof(cc.path)]
        except Exception:
            break
        if any(a is None for a in ims):
            break
        out[f] = np.mean([flux(a) for a in ims[:3]]) / SH[f] / flux(ims[3])
    if len(out) == 3:
        r = {f: round(v / out["GRN"], 3) for f, v in out.items()}
        print(o, tg, {f: round(v, 3) for f, v in out.items()}, 'relative to GRN', r, flush=True)
