import sys, time, os, json
W = '/Users/lazarus/dev/wt-pipeposter'; sys.path[:0] = [W, W + '/web/frames']; os.chdir(W)
import obs_mosaic as om
cache = os.environ['C']; fid = sys.argv[1]
u, n = om.unit_of(fid); p = om.plan(u, cache); t0 = time.time()
print(u['key'], len(u['frames']), {k: u.get(k) for k in ('mosaic','movie','z')}, flush=True)
json.dump({'unit': {k: v for k, v in u.items() if k != 'frames'}, 'frames': u['frames'], 'plan': p}, open(sys.argv[2] + '/unit.json', 'w'), default=str, indent=1)
reps = []
for j in range(len(u['frames'])):
    reps.append(om.tile(u, j, cache, p['display_scale']))
    print(j, reps[-1].get('id'), reps[-1].get('filter'), reps[-1].get('why'), f'{time.time() - t0:.0f} s', flush=True)
json.dump(reps, open(sys.argv[2] + '/tiles.json', 'w'), default=str, indent=1)
print('tiles dir', om._tiles(u, cache, p['display_scale']))
