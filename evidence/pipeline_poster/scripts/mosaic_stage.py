import sys, time, os, json
W = '/Users/lazarus/dev/wt-pipeposter'; sys.path[:0] = [W, W + '/web/frames']; os.chdir(W)
import numpy as np
from PIL import Image
import obs_mosaic as om
cache = os.environ['C']; fid = sys.argv[1]; out = sys.argv[2]; t0 = time.time()
u, n = om.unit_of(fid); last = len(u['frames']) - 1
made = om.layout(u, last, cache)
p, tiles, rect, count, used, name = made
print('layout', name, rect, count, used, f'{time.time()-t0:.0f}s', flush=True)
ref = max(used, key=lambda f: count[f])
for f in list(used) + [om.LUM]:
    rgba = om.filter_mosaic(u, p, f, tiles, rect, cache, None if f == om.LUM else ref)
    Image.fromarray(rgba, 'RGBA').save(f'{out}/filter_{f.replace("/", "-")}.png')
    print('filter', f, rgba.shape, f'{time.time()-t0:.0f}s', flush=True)
im, rep = om.so_far(u, last, cache, made, out=om.CANVAS)
im.save(f'{out}/mosaic_full.png'); json.dump(rep, open(f'{out}/mosaic_report.json', 'w'), indent=1, default=str)
print('mosaic', im.size, rep, f'{time.time()-t0:.0f}s', flush=True)
json.dump(om.tile_map(fid, cache), open(f'{out}/tile_map.json', 'w'), default=str, indent=1)
json.dump({'rect': rect, 'k': p.get('k'), 'count': count, 'used': used, 'name': name}, open(f'{out}/layout.json', 'w'), default=str, indent=1)
print('done', f'{time.time()-t0:.0f}s')
