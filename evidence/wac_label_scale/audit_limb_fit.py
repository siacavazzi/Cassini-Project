import json, sys, numpy as np, collections
rows=[json.loads(l) for l in open(sys.argv[1])]
print(len(rows), "errors", collections.Counter((r.get("err") or "")[:25] for r in rows if "err" in r).most_common(4))
for cam, names in (("N", {"nominal 6.0":6.0e-6, "kernel 2003.44 mm":0.012/2003.44}), ("W", {"labels' 5.9907e-5":5.9907e-5, "kernel 200.77 mm":0.012/200.77, "as drawn 200.956 mm":0.012/200.956})):
    v=[r for r in rows if r["cam"]==cam and "err" not in r and r["resid"]<0.45 and r["rays"]<=200 and r["tan_spread"]<0.006]
    if len(v)<8: print(cam, "too few", len(v)); continue
    t=np.array([r["tan"] for r in v]); R=np.array([r["radius_px"] for r in v])
    print(f"\n{cam}: {len(v)} frames kept; radius {R.min():.0f} to {R.max():.0f} px; limb fit residual median {np.median([r['resid'] for r in v]):.2f} px")
    for nm, ifov in names.items():
        d=R - t/ifov
        print(f"   {nm:22s} {ifov:.5e}: measured minus predicted radius: median {np.median(d):+.2f} px; small disks (below median size) {np.median(d[R<np.median(R)]):+.2f}, large {np.median(d[R>=np.median(R)]):+.2f}")
    # R = tan / ifov + bias: robust line (iterated least squares with 2.5 sigma clipping)
    keep=np.ones(len(v),bool)
    for _ in range(5):
        A=np.c_[t[keep], np.ones(keep.sum())]; sol,res,_,_=np.linalg.lstsq(A, R[keep], rcond=None)
        r_=R - (sol[0]*t+sol[1]); s=np.std(r_[keep]); keep=np.abs(r_)<2.5*s
    n=keep.sum(); cov=s**2*np.linalg.inv(A.T@A)
    ifov=1/sol[0]; err=np.sqrt(cov[0,0])/sol[0]**2
    print(f"   line fit on {n} frames: {ifov:.5e} +- {err:.1e} rad/px, limb bias {sol[1]:+.2f} +- {np.sqrt(cov[1,1]):.2f} px, scatter {s:.2f} px")
    for nm, val in names.items(): print(f"      {nm}: {(val-ifov)/err:+.1f} sigma from the fit ({(val/ifov-1)*100:+.3f}%)")
    by=collections.Counter(r["target"] for r in v); print("   ", dict(by))
