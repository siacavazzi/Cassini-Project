"""sets_passes.POLARIZED_SHARE and IR_POLARIZED_SHARE, measured: for each observation taking a band both through the
polarizers and plainly, the mean total calibrated I/F of one set of the polarizer's angles over the plain frame's nearest
it (within 15 minutes, the body whole in frame), by the repo's own calibration. Narrow-angle camera: the visible
polarizers P0, P60, P120 (first wheel) with BL2, GRN or CB1, plain through CL1. Wide-angle camera (CAM=W): the infrared
polarizers IRP0 and IRP90 (second wheel) with CB2, CB3, MT2, MT3 or IR4, plain through CL2.
Run from web/frames with the archive's environment (CASSINI_DATA, CASSINI_CISSCAL...):
  PER=20 FS=BL2,GRN,CB1 python polarized_share.py OUT.csv            (narrow angle)
  CAM=W PER=20 FS=CB2,CB3,MT2,MT3,IR4 python polarized_share.py OUT.csv   (wide angle)
PER: pairs per band at most. Prints the medians and quartiles."""
import sys, os, numpy as np, pandas as pd, cv2
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.abspath('../..'))
import calibration, label_handler
import data_source as ds

WAC = os.environ.get('CAM', 'N') == 'W'
d = pd.read_csv('../../Image_index.csv', low_memory=False)
n = d[d.INSTRUMENT_ID == ('ISSWA' if WAC else 'ISSNA')].copy()
if WAC:   # band in the first wheel, polarizer (IRP0, IRP90) in the second
    n['band'], n['angle'] = n.filter1.astype(object), n.filter2.astype(object)
    n['pol'] = n.angle.isin(['IRP0', 'IRP90'])
    plain, angles = (lambda x, f: x[~x.pol & (x.band == f) & (x.angle == 'CL2')]), {'IRP0', 'IRP90'}
else:     # polarizer (P0, P60, P120) in the first wheel, band in the second
    n['band'], n['angle'] = n.filter2.astype(object), n.filter1.astype(object)
    n['pol'] = n.angle.isin(['P0', 'P60', 'P120'])
    plain, angles = (lambda x, f: x[~x.pol & (x.band == f) & (x.angle == 'CL1')]), {'P0', 'P60', 'P120'}


def iof(path):
    lbl = label_handler.label(path, as_png=True)
    png = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    return calibration.calibrate(png, lbl.get_info())


def flux(a):
    a = np.nan_to_num(a.astype(np.float64)); bg = np.median(a); lit = a > bg + 0.2 * (np.percentile(a, 99.5) - bg)
    return (a - bg)[lit].sum(), lit.mean()


rows, per = [], {}
for (o, tg), x in n.groupby(['OBSERVATION_ID', 'TARGET_NAME']):
    if not x.pol.any() or x.pol.all() or tg in ('SKY', 'UNK'):
        continue
    for f in os.environ.get('FS', 'CB2,CB3,MT2,MT3,IR4' if WAC else 'BL2,GRN,CB1').split(','):
        if per.get(f, 0) >= int(os.environ.get('PER', '8')):
            continue
        p = x[x.pol & (x.band == f)].sort_values('seconds_1970'); c = plain(x, f)
        if len(p) < len(angles) or not len(c):
            continue
        one = p.iloc[:len(angles)]
        if set(one.angle) != angles:
            continue
        cc = c.iloc[np.argmin(abs(c.seconds_1970.values - one.seconds_1970.mean()))]
        if abs(cc.seconds_1970 - one.seconds_1970.mean()) > 900:
            continue
        try:
            ims = [iof(q) for q in one.path] + [iof(cc.path)]
        except Exception as e:
            print('skip', o, f, e); continue
        if any(a is None for a in ims) or len({a.shape for a in ims}) > 1:
            continue
        fl = [flux(a) for a in ims]
        if fl[-1][1] > 0.6 or fl[-1][1] < 0.002:   # want the whole body in frame
            continue
        polmean = np.mean([q[0] for q in fl[:-1]]); r = polmean / fl[-1][0]
        spread = (max(q[0] for q in fl[:-1]) - min(q[0] for q in fl[:-1])) / polmean
        rows.append((o, tg, f, round(r, 3), round(spread, 3), round(fl[-1][1], 3)))
        per[f] = per.get(f, 0) + 1
        print(rows[-1], flush=True)
r = pd.DataFrame(rows, columns=['obs', 'tg', 'f', 'pol_over_plain', 'angle_spread', 'lit'])
print(r.groupby('f').pol_over_plain.describe().to_string())
print(r.groupby('f').pol_over_plain.median().round(3).to_dict())
r.to_csv(sys.argv[1], index=False)
