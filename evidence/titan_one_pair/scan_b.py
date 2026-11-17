"""Which passes fix B changes: _filters' colour on main vs the branch, for every Titan pass with a pair set and the
survey's gray passes. Run from each worktree's web/frames; prints JSON {key: [colour, set_colour, one_pair, folder]}."""
import json, sys, os, collections
sys.path.insert(0, os.getcwd())
import obs_mosaic as om
rep = json.load(open(sys.argv[1]))
obs = sorted({(r['body'], r['obs'], r['cam']) for r in rep if 'err' not in r and r['body'] == 'TITAN'})
out = {}
for b, o, c in obs:
    for u in om.units(b, o, c):
        if not u['frames']:
            continue
        _, _, _, col = om._filters(u)
        out['_'.join(map(str, u['key']))] = [col, u.get('set_colour'), u.get('one_pair'), os.path.basename(om.folder(u, '/x')), u.get('kind'), len(u['frames'])]
json.dump(out, open(sys.argv[2], 'w'))
print(len(out))
