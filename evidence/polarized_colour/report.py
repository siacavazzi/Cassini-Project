import json, sys, collections, datetime as dt, pandas as pd
s = [r for r in json.load(open(sys.argv[1])) if 'err' not in r]
isPol = lambda p: p.startswith('IRP') or (p.startswith('P') and p[1:2].isdigit())
TRUE = {'BL1', 'BL2', 'VIO', 'GRN', 'RED', 'CB1'}
rows = []
for r in s:
    plain = set(r['plain']); pc = set(r['polcol']); allc = plain | pc
    c, kind = r['colour'], r['kind']
    shown_colour = bool(c) and not (kind == 'movie' and r['plays'] is False)
    if shown_colour:
        why = 'colour'
    elif len(allc) < 2:
        why = 'no colour possible (one filter, or clear + one)'
    elif len(plain) < 2:
        why = ('POL-VIS: colour only via visible polarizers (NAC)' if r['cam'] == 'N' and len(allc & TRUE) >= 2
               else 'POL-IR: colour only via polarizers, IR/UV/methane bands')
    elif c and r['plays'] is False:
        why = 'MOVIE-RARE: movie takes its colour set once among many gray frames (plays_colour)'
    elif r['nsets'] == 0:
        why = 'NOSET: colour filters never taken together (no set)'
    elif r['npairsets'] == 1 and all(k == '2' for k in r['set_sizes']):
        why = 'ONEPAIR: one approved pair set only (pair rule needs 2)'
    elif all(k == '2' for k in r['set_sizes']) and r['npairsets'] == 0:
        why = 'PAIR-NOTAPPROVED: two-filter sets, not an approved pair'
    else:
        why = 'COUNTS: sets exist but colour filters a minority / rule keeps gray'
    t = dt.datetime.utcfromtimestamp(r['t0'])
    rows.append(dict(why=why, body=r['body'], cam=r['cam'], kind=kind, n=r['n'], year=t.year, t=t.strftime('%Y-%m-%dT%H:%M:%S'),
                     key=r['key'], filters='+'.join(sorted(allc)), sets=r['sets'][:3], nsets=r['nsets']))
d = pd.DataFrame(rows)
print('passes', len(d)); print(d.why.value_counts().to_string())
print('\nmovies only'); print(d[d.kind == 'movie'].why.value_counts().to_string())
g = d[~d.why.isin(['colour', 'no colour possible (one filter, or clear + one)'])]
for w, x in g.groupby('why'):
    print(f'\n== {w}: {len(x)} passes ({(x.kind=="movie").sum()} movies), {x.n.sum()} frames')
    print('  bodies', x.body.value_counts().head(8).to_dict())
    print('  years', x.year.value_counts().sort_index().to_dict())
    print('  filters', x.filters.value_counts().head(6).to_dict())
    for _, e in x.sort_values('n', ascending=False).head(4).iterrows():
        print(f'   {e.key} n={e.n} {e.t} {e.filters} sets={e.sets}')
d.to_csv(sys.argv[2], index=False)
