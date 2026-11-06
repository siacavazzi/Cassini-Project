"""Which passes cover their body's whole disk: frame footprints (1024 px squares at the SPICE centring shift)
against the disk (radius km / range * px per radian). Geometry cache + Image_index only."""
import csv, sqlite3, collections, numpy as np, json
R = {'SATURN': 60268, 'TITAN': 2575, 'RHEA': 764, 'IAPETUS': 735, 'DIONE': 561, 'TETHYS': 531, 'ENCELADUS': 252,
     'MIMAS': 198, 'HYPERION': 135, 'PHOEBE': 107, 'JANUS': 90, 'EPIMETHEUS': 58, 'JUPITER': 71492}
db = sqlite3.connect('file:/Users/lazarus/dev/scratch/pipeposter/geometry.sqlite?immutable=1', uri=True)
geo = {r[0]: r[1:] for r in db.execute('select frame,x,y,z,scale,target from target where error is null and version=1')}
groups = collections.defaultdict(list)
for r in csv.DictReader(open('/Users/lazarus/dev/wt-pipeposter/Image_index.csv')):
    i = r['path'].split('/')[-1][:-4]
    if r['TARGET_NAME'] in R and i in geo:
        groups[(r['OBSERVATION_ID'], r['INSTRUMENT_ID'], r['TARGET_NAME'])].append((i, r['filter1'] + '/' + r['filter2'], float(r['seconds_1970'])))
out = []
th = np.linspace(0, 2 * np.pi, 64, endpoint=False); rr = np.sqrt(np.linspace(0.02, 1, 16))
for (obs, inst, tgt), fr in groups.items():
    if len(fr) < 4: continue
    fr.sort(key=lambda f: f[2])
    # split into passes on 30 min gaps
    passes, cur = [], [fr[0]]
    for a, b in zip(fr, fr[1:]):
        if b[2] - a[2] > 1800: passes.append(cur); cur = []
        cur.append(b)
    passes.append(cur)
    for k, ps in enumerate(passes):
        if len(ps) < 4: continue
        g = np.array([geo[i][:4] for i, _, _ in ps]); rad = R[tgt] / np.median(g[:, 2]) * np.median(g[:, 3])
        if rad < 700 or rad > 20000: continue   # bigger than one frame, and not so close it can never be whole
        px = (rr[:, None] * np.cos(th)).ravel() * rad; py = (rr[:, None] * np.sin(th)).ravel() * rad
        cov = np.zeros(px.size, bool)
        for x, y, z, s in g:
            cov |= (np.abs(px + x) <= 512) & (np.abs(py + y) <= 512)
        if cov.mean() < 0.97: continue
        filt = collections.Counter(f for _, f, _ in ps)
        out.append({'obs': obs, 'cam': inst[-2], 'target': tgt, 'pass': k, 'n': len(ps), 'radius_px': round(rad), 'cover': round(float(cov.mean()), 3),
                    'first': ps[0][0], 'last': ps[-1][0], 'filters': dict(filt), 'minutes': round((ps[-1][2] - ps[0][2]) / 60)})
out.sort(key=lambda o: (-o['radius_px']))
json.dump(out, open('/Users/lazarus/dev/scratch/pipeposter/full_mosaics.json', 'w'), indent=1)
print(len(out))
for o in out: print(o['target'], o['obs'], o['cam'], o['pass'], o['n'], o['radius_px'], o['cover'], o['minutes'], o['filters'])
