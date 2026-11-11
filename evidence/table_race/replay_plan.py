import os, sys, json, math
sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)),'wt-65dad65'), os.path.join(os.path.dirname(os.path.abspath(__file__)),'wt-65dad65/web/frames')]
import numpy as np
import stacking, obs_mosaic as om, reel
u = [x for x in om.units('SATURN', 'ISS_269RI_HIPHASEFB001_PIE', 'W') if list(x['key']) == ['SATURN','ISS_269RI_HIPHASEFB001_PIE','W',0]][0]
frames = u['frames']
count, nms, aside, colour = om._filters(u)
picks = []
for f in count:
    mine = [fr for fr in frames if fr[2] == f]
    picks += mine[::max(1, math.ceil(len(mine) / om.SCALE_FRAMES))]
picks = sorted(picks, key=frames.index)
print('frames', len(frames), 'picks', len(picks), {f: sum(1 for p in picks if p[2]==f) for f in count}, 'colour', colour, flush=True)
memo = {}; orig = stacking.load_hdr
def load(path, *a, **k):
    if path not in memo: memo[path] = orig(path, *a, **k)
    return memo[path]
stacking.load_hdr = load
drop = set()
def masked(path, *a, **k):
    r = load(path, *a, **k)
    return (r[0], None, *r[2:]) if path in drop else r
stacking.load_hdr = masked
tc = bool(colour and len(colour) == 3 and colour[1] == "GRN" and colour[2] in reel.TRUE_BLUES)
def run():
    lv = {}; s = om.pass_scale(picks, u, colour or [max(count, key=count.get)], tc, lit_levels=lv)
    lum = om.luminance_of(count, max(count, key=count.get), lv)
    return s, lum
s, lum = run()
print('ALL', list(s['blacks']), s['blacks'].get('RED'), s['blacks'].get('IR3'), s.get('toe'), lum['gains'].get('IR3'), flush=True)
target = (0.00013265963687497944, 0.0009244346993345448)
for fr in [p for p in picks if p[2] in ('IR3',)][:6] + [p for p in picks if p[2]=='RED'][:3]:
    drop = {fr[0]}
    s, lum = run()
    hit = abs(s['blacks'].get('RED',0)-target[0])<1e-12 and abs(s['blacks'].get('IR3',0)-target[1])<1e-12
    print('DROP', fr[1], fr[2], list(s['blacks']), s['blacks'].get('RED'), s['blacks'].get('IR3'), lum['gains'].get('IR3'), 'MATCH_MBP' if hit else '', flush=True)
