"""Why each pass of the finished cache is gray (or plays gray): runs the repo's own rule (obs_mosaic._filters,
colour_sets, plays_colour, calibration.approximate_pair) on every pass in the cache's plan list."""
import json, re, sys, os, time, collections
from multiprocessing import Pool
sys.path.insert(0, os.getcwd())
import obs_mosaic as om, calibration

plans = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
KEYRE = re.compile(r'^(.*?)_((?:ISS|CIRS|VIMS|UVIS|RSS|RADAR|INMS|MAG|NAV|CAPS|MIMI|RPWS|ORS|SP|CDA)_.*)_([NW])_(\d+)(?:_.*)?$')
by_obs = collections.defaultdict(list)
for k, v in plans.items():
    m = KEYRE.match(k)
    if m:
        g = by_obs[(m.group(1), m.group(2), m.group(3))]
        if all(i != int(m.group(4)) for i, _, _ in g):
            g.append((int(m.group(4)), k, v))

def strip_pol(f):
    ps = [p for p in f.split('/') if not om._polarizer(p) and not p.startswith('CL')]
    return '/'.join(ps) or None

def one(item):
    (body, obs, cam), lst = item
    out = []
    try:
        us = {u['key'][3]: u for u in om.units(body, obs, cam)}
    except Exception as e:
        return [dict(key=k, err=repr(e)[:200]) for _, k, _ in lst]
    for i, k, v in lst:
        u = us.get(i)
        if u is None:
            out.append(dict(key=k, err='no unit')); continue
        try:
            frames = u['frames']
            count, nms, aside, colour = om._filters(u)
            sets = [tuple(f for f, j in r) for r in om.colour_sets(frames)]
            grey = max(count, key=count.get)
            plain = sorted({f for f in count if f != 'CL1/CL2' and not om._polarizer(f)})
            polcol = sorted({strip_pol(f) for f in count if om._polarizer(f)} - {None})
            plays = None
            if colour and u.get('kind') == 'movie':
                plays = bool(om.plays_colour(u, colour, grey))
            pairs = [s for s in sets if len(set(s)) == 2 and calibration.approximate_pair(cam, sorted(set(s), key=lambda f: -nms[f]), body)]
            out.append(dict(key=k, body=body, obs=obs, cam=cam, kind=u.get('kind'), n=len(frames), t0=frames[0][3],
                            cached_colour=v['colour'], colour=colour, set_colour=u.get('set_colour'), plays=plays,
                            count=count, plain=plain, polcol=polcol, nsets=len(sets),
                            set_sizes=collections.Counter(len(set(s)) for s in sets), npairsets=len(pairs),
                            sets=[list(s) for s in sets[:6]]))
        except Exception as e:
            out.append(dict(key=k, err=repr(e)[:200]))
    return out

if __name__ == '__main__':
    items = sorted(by_obs.items())
    t = time.time(); res = []
    with Pool(int(os.environ.get('W', '6'))) as p:
        for j, r in enumerate(p.imap_unordered(one, items, chunksize=4)):
            res.extend(r)
            if j % 500 == 0:
                print(j, len(items), round(time.time() - t), flush=True)
    json.dump(res, open(OUT, 'w'), default=str)
    print('done', len(res), round(time.time() - t))
