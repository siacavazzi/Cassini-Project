"""processed_frame of one frame (or set) with each pipeline step off in turn, and cumulative chains. usage: steps.py OUTDIR ID [ID ID]"""
import sys, time, os, json
W = '/Users/lazarus/dev/wt-pipeposter'; sys.path[:0] = [W, W + '/web/frames']; os.chdir(W)
import numpy as np
from PIL import Image
import color_image as ci, calibration as cal
out = sys.argv[1]; ids = sys.argv[2:]; paths = [f'nac_data/{i}.png' for i in ids]; tag = '+'.join(ids)
os.makedirs(out, exist_ok=True); reps = {}
def run(name, off):
    with cal.stepping(off):
        im, lbl, rep = ci.processed_frame(paths, hdr=True)
    Image.fromarray(im).save(f'{out}/{tag}__{name}.png'); reps[name] = {'off': list(off), **{k: v for k, v in rep.items() if k != 'lost_px'}, 'lost_px': rep.get('lost_px')}
    return im
base = run('all_on', [])
diff = {}
for s in cal.STEPS:
    if s in ('blend', 'level', 'surface', 'panels'): continue
    im = run('off_' + s, [s]); diff[s] = float(np.abs(im[..., :3].astype(int) - base[..., :3]).mean())
    print(s, round(diff[s], 3), flush=True)
run('all_off', [s for s in cal.STEPS])
json.dump({'diff': diff, 'reports': reps}, open(f'{out}/{tag}__steps.json', 'w'), indent=1, default=str)
