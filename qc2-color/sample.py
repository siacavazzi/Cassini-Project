import sys, random, collections, datetime, json, csv
sys.path.insert(0,'.'); sys.path.insert(0,'../..')
import reel
idx, sets = reel.load_index()
ids=idx['id'].tolist(); f1=idx['filter1'].astype(str).tolist(); f2=idx['filter2'].astype(str).tolist()
tg=idx['TARGET_NAME'].astype(str).tolist(); ob=idx['OBSERVATION_ID'].astype(str).tolist(); t=idx['seconds_1970'].tolist()
cam=idx['INSTRUMENT_ID'].tolist()
def fl(q):
    a,b=f1[q],f2[q]; return '/'.join(x for x in (a,b) if x not in ('CL1','CL2')) or 'CLR'
def utc(s): return datetime.datetime.utcfromtimestamp(s).strftime('%Y-%m-%dT%H:%M:%S')
rows=[]
for k,s in enumerate(sets):
    u=s['use']
    if len(u)<2: continue
    q=u[len(u)//2]
    rows.append(dict(set=k, key=ids[u[0]], ids=','.join(ids[x] for x in u), cam='NAC' if cam[q]=='ISSNA' else 'WAC',
        kind=s['kind'], filters='+'.join(fl(x) for x in u), body=tg[q], obs=ob[q], utc=utc(t[q]), year=utc(t[q])[:4], gap=round(max(t[x] for x in u)-min(t[x] for x in u))))
by_id={i:r for r in rows for i in r['ids'].split(',')}
out=[]; seen=set()
def add(r, why):
    if r and r['set'] not in seen:
        seen.add(r['set']); out.append(dict(r, why=why))
# 1. round 1 examples
for line in list(csv.reader(open('/mnt/project-files/quality-check/thumbs/color/index.tsv'),delimiter='\t'))[1:]:
    r=by_id.get(line[2]); 
    if r is None: print('no set for', line[2])
    add(r,'r1:'+line[0])
# 1b. other round1 ids from reports
import re
for i in re.findall(r'[NW]1\d{9}_\d', open('/mnt/project-files/quality-check/color/report.md').read()+open('/mnt/project-files/quality-check/color/report-round2.md').read()):
    add(by_id.get(i),'r1report')
# 2. Sam's 03:44Z set
sam=[r for r in rows if r['cam']=='WAC' and r['utc'].startswith('2005-02-05T22:1')]
for r in sam: print('sam', r)
for i in ('W1486331264_1','W1486330981_1','N1486331265_1','W1486330104_1'): add(by_id.get(i),'sam0344')
rnd=random.Random(20261029)
def pick(pool, n, why, cap_key=None, cap=2):
    pool=pool[:]; rnd.shuffle(pool); c=collections.Counter(); got=0
    for r in pool:
        if got>=n: break
        kk=cap_key(r) if cap_key else None
        if kk is not None and c[kk]>=cap: continue
        if r['set'] in seen: continue
        c[kk]+=1; add(r,why); got+=1
# 3. broad random: per camera x year x kind
for camn in ('NAC','WAC'):
    for kind in ('true','false','two'):
        pool=[r for r in rows if r['cam']==camn and r['kind']==kind]
        pick(pool, 30, f'random', cap_key=lambda r:(r['year'],r['body']), cap=1)
# 4. targeted
pick([r for r in rows if r['cam']=='WAC' and '2012-11-24'<=r['utc']<='2016-07-01'], 20, 'wac-late', cap_key=lambda r:r['body'], cap=4)
pick([r for r in rows if r['kind']=='two'], 40, 'two-filter', cap_key=lambda r:r['filters'], cap=1)
pick([r for r in rows if 'MT' in r['filters']], 20, 'methane', cap_key=lambda r:(r['filters'],r['body']), cap=1)
pick([r for r in rows if r['body'] in ('VENUS','JUPITER','MOON','EARTH','MASURSKY','HIMALIA','IO','EUROPA','GANYMEDE','CALLISTO')], 15, 'cruise', cap_key=lambda r:r['body'], cap=4)
small=('PROMETHEUS','PANDORA','JANUS','EPIMETHEUS','PAN','DAPHNIS','ATLAS','TELESTO','CALYPSO','HELENE','METHONE','PALLENE','POLYDEUCES','HYPERION','PHOEBE','IAPETUS','MIMAS','TETHYS','DIONE','RHEA','ENCELADUS')
pick([r for r in rows if r['body'] in small], 30, 'moons', cap_key=lambda r:r['body'], cap=2)
pick([r for r in rows if r['body']=='SATURN' and r['utc']>='2016-11-30'], 8, 'finale', cap_key=lambda r:r['filters'], cap=2)
pick([r for r in rows if r['body'] in ('SATURN','TITAN') and r['cam']=='WAC' and r['gap']>60], 10, 'big-gap', cap_key=lambda r:r['body'], cap=5)
print(len(out), collections.Counter(r['why'] for r in out))
print(collections.Counter((r['cam'],r['kind']) for r in out))
json.dump(out, open(sys.argv[1],'w'), indent=0)
