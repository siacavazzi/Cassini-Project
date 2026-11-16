exec(open("fit_wheels.py").read().split("print(\"matches\"")[0])
exec("def irls" + open("fit_wheels.py").read().split("def irls")[1].split("random.seed")[0])
obs = [o for o in obs if o[4] == "FULL"]
tab = {"CL1,GRN": (0, 0), "CL1,RED": (2.03, 1.16), "CL1,BL1": (2.10, -1.35), "CL1,VIO": (2.16, -1.75), "CB2,CL2": (2.42, -0.85), "MT2,CL2": (2.51, -0.32), "CB3,CL2": (2.79, -0.65), "MT3,CL2": (3.08, -0.11), "CL1,IR1": (2.13, 1.35)}
for lab_, lo, hi in (("2000-2001", 0, 2001), ("2004-2008", 2004, 2008), ("2009-2012", 2009, 2012), ("2013-2017", 2013, 2017)):
    s = [o for o in obs if lo <= o[3] <= hi]
    t, c = combo_fit(s, 100)
    diffs = {k: np.hypot(*(np.array(t[k]) - tab[k])) for k in t if k in tab and k != "CL1,GRN"}
    print(f"{lab_} n={len(s)}: " + ", ".join(f"{k.replace('CL1,','').replace(',CL2','')} ({t[k][0]:+.2f},{t[k][1]:+.2f}) n{c[k]} d{diffs[k]:.2f}" for k in sorted(diffs, key=lambda k: -c[k])))
    sc = score(s, lambda f: np.array(tab[f]) if f in tab else None); so = score(s, lambda f: t.get(f))
    print(f"    one table: median {sc[2]:.2f} (before {sc[1]:.2f}); own era fit: median {so[2]:.2f}")
