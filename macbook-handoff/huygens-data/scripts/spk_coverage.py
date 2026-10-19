import spiceypy as sp,glob,sys
sp.furnsh('raw/spice/lsk/naif0012.tls'); sp.furnsh('raw/spice/pck/pck00011.tpc')
for f in sorted(glob.glob('raw/spice/spk/*.bsp')):
    print('==',f)
    for body in (-150,606):
        try: c=sp.spkcov(f,body)
        except Exception: continue
        n=sp.wncard(c)
        for i in range(n):
            a,b=sp.wnfetd(c,i); print(' ',body,sp.et2utc(a,'ISOC',0),'->',sp.et2utc(b,'ISOC',0))
    # segment-level detail for -150
    h=sp.dafopr(f); sp.dafbfs(h); found=sp.daffna()
    while found:
        dc,ic=sp.dafgs(),None
        d,i=sp.dafus(sp.dafgs(),2,6)
        if i[0]==-150: print('   seg -150 center',i[1],'frame',i[2],'type',i[3],sp.et2utc(d[0],'ISOC',0),sp.et2utc(d[1],'ISOC',0))
        found=sp.daffna()
    sp.dafcls(h)
# sanity: altitude above Titan
sp.furnsh('raw/spice/spk/050214R_SCPSE_04336_05015.bsp')
for t in ['2004-12-25T02:00','2005-01-14T09:00','2005-01-14T09:10','2005-01-14T10:00','2005-01-14T11:38','2005-01-15T00:00']:
    try:
        p,_=sp.spkpos('-150',sp.str2et(t),'IAU_TITAN','NONE','TITAN')
        r,lon,lat=sp.reclat(p); print(t,'alt km %.2f'%(r-2575),'lat %.3f lon %.3f'%(lat*57.2958,lon*57.2958))
    except Exception as e: print(t,str(e).splitlines()[0][:120])
