"""Per-frame stages from the repo's own calls: raw archive codes, calibrated I/F (science_frame), processed_frame
with pipeline steps toggled (calibration.stepping), and the colour set composite. usage: stages.py OUTDIR ID..."""
import sys, time, os, json
W = '/Users/lazarus/dev/wt-pipeposter'; sys.path[:0] = [W, W + '/web/frames']; os.chdir(W)
import numpy as np, cv2
from PIL import Image
import color_image as ci, label_handler as lh, data_source as ds, calibration as cal
out = sys.argv[1]; ids = sys.argv[2:]; os.makedirs(out, exist_ok=True); meta = {}
for i in ids:
    p = f'nac_data/{i}.png'; lbl = lh.label(p, as_png=True); info = lbl.get_info()
    codes = ds.imread(lbl.export(), cv2.IMREAD_GRAYSCALE)
    Image.fromarray(codes).save(f'{out}/{i}_raw.png')
    iof, _, note = ci.science_frame(p)
    np.save(f'{out}/{i}_iof.npy', iof)
    meta[i] = {'info': {k: info.get(k) for k in ('FILTER_NAME', 'EXPOSURE_DURATION', 'GAIN_MODE_ID', 'INSTRUMENT_MODE_ID', 'IMAGE_TIME', 'TARGET_NAME', 'MISSING_LINES', 'DATA_CONVERSION_TYPE', 'ENCODING_TYPE')},
               'note': note, 'iof_pct': [float(x) for x in np.nanpercentile(iof, [0.1, 50, 99.9])], 'nan': int(np.isnan(iof).sum())}
    print(i, meta[i]['info'], flush=True)
json.dump(meta, open(f'{out}/meta.json', 'w'), indent=1)
