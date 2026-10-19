"""Decode DISR imager TABLE_FORMAT products (ASCII DN tables) to 8-bit PNG."""
import sys, os, re, numpy as np
from PIL import Image
for tab in sys.argv[2:]:
    lbl = tab[:-4] + '.LBL'; L = open(lbl, encoding='latin1').read()
    start = int(re.search(r'\^TABLE\s*=\s*\("[^"]+",\s*(\d+)\)', L).group(1))
    rb = int(re.search(r'RECORD_BYTES\s*=\s*(\d+)', L).group(1))
    nrows = int(re.search(r'ROWS\s*=\s*(\d+)', L.split('OBJECT                     = TABLE')[1]).group(1))
    # header records are shorter than RECORD_BYTES on disk, so index by line
    lines = open(tab, encoding='latin1').read().splitlines()[start-1:start-1+nrows]
    a = np.array([[float(v) for v in l.split()] for l in lines])
    a = a[:, 1:] if a.shape[1] in (129, 161, 177) else a   # drop row-index column
    v = a[a > 0]; lo, hi = np.percentile(v, 0.5), np.percentile(v, 99.5)
    img = (np.clip((a - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    out = os.path.join(sys.argv[1], os.path.basename(tab)[:-4] + '.png')
    Image.fromarray(img).save(out); print(out, a.shape, 'DN', a.min(), a.max())
