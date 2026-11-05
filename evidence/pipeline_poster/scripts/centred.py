"""processed_frame (every step on) of single frames. usage: centred.py OUTDIR ID..."""
import sys, os
W = '/Users/lazarus/dev/wt-pipeposter'; sys.path[:0] = [W, W + '/web/frames']; os.chdir(W)
from PIL import Image
import color_image as ci
for i in sys.argv[2:]:
    im, _, rep = ci.processed_frame([f'nac_data/{i}.png'], hdr=True); Image.fromarray(im).save(f'{sys.argv[1]}/{i}__all_on.png'); print(i, rep.get('calibrated'), rep.get('lost_px'))
