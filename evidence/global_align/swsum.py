import json,glob,sys
rows=[]
for d in ('swm','swm-mini'):
    for f in sorted(glob.glob(d+'/metric-base-*.json')):
        g=f.replace('metric-base-','metric-sub-')
        try: A=json.load(open(f)); B=json.load(open(g))
        except Exception: continue
        bb={p['pass']:p for p in B}
        for p in A:
            q=bb.get(p['pass'])
            if not q or not p['measured'] or not q['measured']: continue
            rows.append((p['pass'][:45],p['measured'],q['measured'],p['res_median'],q['res_median'],p['res_p90'],q['res_p90'],p['over2px'],q['over2px']))
better=worse=0
for r in rows:
    tag=''
    if r[8]<r[7]-1 or r[6]<r[5]-1: better+=1; tag='+'
    if r[8]>r[7]+1 or r[6]>r[5]+1: worse+=1; tag+='-'
    print(f"{r[0]:45s} n{r[1]:3d}/{r[2]:3d} med {r[3]:6.2f}->{r[4]:6.2f} p90 {r[5]:6.2f}->{r[6]:6.2f} >2px {r[7]:3d}->{r[8]:3d} {tag}")
print('passes',len(rows),'better',better,'worse',worse,'| total >2px', sum(r[7] for r in rows),'->',sum(r[8] for r in rows))
