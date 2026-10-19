import re, sys, collections
lbl = open('idx/index.lbl').read()
COLS = []
for blk in re.findall(r'OBJECT\s+=\s+COLUMN(.*?)END_OBJECT', lbl, re.S):
    g = lambda k: (re.search(rf'{k}\s+=\s+(\S+)', blk) or [None, None])[1]
    COLS.append((g('NAME'), int(g('START_BYTE')) - 1, int(g('BYTES'))))
def load(p):
    rows = []
    for line in open(p, encoding='latin1'):
        r = {n: line[s:s+b].replace('"', ' ').strip() for n, s, b in COLS}
        r['FILTER_NAME'] = ','.join(x.strip() for x in r['FILTER_NAME'].split(','))
        rows.append(r)
    return rows
if __name__ == '__main__':
    for v in sys.argv[1:]:
        rows = load(f'idx/{v}.tab')
        print(v, len(rows), rows[0]['IMAGE_TIME'], rows[-1]['IMAGE_TIME'], collections.Counter(r['DATA_CONVERSION_TYPE'] for r in rows))
        obs = collections.defaultdict(list)
        for r in rows: obs[(r['OBSERVATION_ID'], r['INSTRUMENT_ID'])].append(r)
        for k, rs in obs.items():
            f = collections.Counter(r['FILTER_NAME'] for r in rs)
            rgb = [x for x in f if any(c in x for c in ('RED','GRN','BL1'))]
            if len(rgb) < 3 or not (20 <= len(rs) <= 150): continue
            twelve = sum(r['DATA_CONVERSION_TYPE']=='12BIT' for r in rs)/len(rs)
            if twelve < 0.6: continue
            tg = collections.Counter(r['TARGET_NAME'] for r in rs).most_common(2)
            print(' ', k, len(rs), round(twelve,2), tg, dict(f), dict(collections.Counter(r['INSTRUMENT_MODE_ID'] for r in rs)), dict(collections.Counter(r['INST_CMPRS_TYPE'] for r in rs)))
