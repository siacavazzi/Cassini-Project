"""Fit one offset per WAC filter from the full cache's own picture matches (phase correlation) against SPICE's
offsets between the channels of each colour set, and check it by year, summing mode and held-out sets."""
import json, os, sqlite3, re, numpy as np, collections, random
rows = json.load(open(os.path.expanduser("~/cassini-build/audit/out/cache_colour_sets.json")))
geo = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/geometry-audit.sqlite"))
lab = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/labels.sqlite"))
def place(f):
    r = geo.execute("SELECT x, y, camera, scale FROM target WHERE frame=? AND error IS NULL", (f,)).fetchone()
    if not r or r[0] is None: return None
    k = (200.956 / 0.012) / r[3] if r[2] and r[2].endswith("WAC") and r[3] else 1.0
    return r[0] * k, r[1] * k
def meta(f):
    r = lab.execute("SELECT FILTER_NAME, IMAGE_MID_TIME, INSTRUMENT_MODE_ID FROM l WHERE frame=?", (f,)).fetchone()
    return (r[0].strip("()"), int(r[1][:4]), r[2]) if r else None
num = re.compile(r"([+-]\d+\.\d+),([+-]\d+\.\d+)")
obs = []   # (filter of channel, filter of reference, residual vector, year, mode, set name)
for name, g, gm, aligned, *_ in rows:
    if name[0] != "W": continue
    ids = ["_".join(p) for p in zip(name.split("_")[0::2], name.split("_")[1::2])]
    if not aligned or len(aligned) != len(ids) or "reference" not in aligned: continue
    ref = aligned.index("reference"); pr = place(ids[ref]); mr = meta(ids[ref])
    if pr is None or mr is None: continue
    for i, (fid, how) in enumerate(zip(ids, aligned)):
        if i == ref or not isinstance(how, str) or not how.startswith("phase") or "checked" in how: continue
        m = num.search(how); pc = place(fid); mc = meta(fid)
        if not m or pc is None or mc is None: continue
        res = np.array([float(m.group(1)) - (pr[0] - pc[0]), float(m.group(2)) - (pr[1] - pc[1])])
        if np.hypot(*res) > 12: continue        # a wild match is no measure
        obs.append((mc[0], mr[0], res, mc[1], mc[2], name))
print("WAC channel matches used:", len(obs))
filters = sorted({o[0] for o in obs} | {o[1] for o in obs})
count = collections.Counter(); [count.update([o[0], o[1]]) for o in obs]
keep = [f for f in filters if count[f] >= 150]
ix = {f: i for i, f in enumerate(keep)}
def fit(sample):
    # robust: iteratively reweighted least squares on res = t[a] - t[b], t[zero] = 0
    A, bx, by = [], [], []
    for a, b, res, *_ in sample:
        if a in ix and b in ix:
            row = np.zeros(len(keep)); row[ix[a]] += 1; row[ix[b]] -= 1
            A.append(row); bx.append(res[0]); by.append(res[1])
    A = np.array(A); bx = np.array(bx); by = np.array(by)
    zero = ix["CL1,GRN"]
    A2 = np.delete(A, zero, axis=1)
    w = np.ones(len(A))
    for _ in range(6):
        tx = np.linalg.lstsq(A2 * w[:, None], bx * w, rcond=None)[0]; ty = np.linalg.lstsq(A2 * w[:, None], by * w, rcond=None)[0]
        r = np.hypot(A2 @ tx - bx, A2 @ ty - by); w = 1.0 / np.maximum(r, 0.5)
    t = {f: (0.0, 0.0) for f in keep}
    for f in keep:
        if ix[f] != zero:
            j = ix[f] - (ix[f] > zero); t[f] = (float(tx[j]), float(ty[j]))
    return t
t_all = fit(obs)
print("offset per filter (frame px as drawn, relative to CL1,GRN):")
for f in sorted(keep, key=lambda f: -count[f]): print(f"   {f:10s} ({t_all[f][0]:+.2f}, {t_all[f][1]:+.2f})   in {count[f]} matches")
def left(sample, t):
    before, after = [], []
    for a, b, res, *_ in sample:
        if a in t and b in t:
            before.append(np.hypot(*res)); after.append(np.hypot(res[0] - (t[a][0] - t[b][0]), res[1] - (t[a][1] - t[b][1])))
    return np.array(before), np.array(after)
b, a = left(obs, t_all)
print("SPICE's offset against the picture match, all matches: before median %.2f p90 %.2f px; with the table median %.2f p90 %.2f px" % (np.median(b), np.percentile(b, 90), np.median(a), np.percentile(a, 90)))
# held out: fit on half the sets, test on the other half
random.seed(5); names = sorted({o[5] for o in obs}); random.shuffle(names); half = set(names[:len(names) // 2])
t_half = fit([o for o in obs if o[5] in half]); b, a = left([o for o in obs if o[5] not in half], t_half)
print("held-out half of the sets: before median %.2f px; with a table fitted on the other half median %.2f px, p90 %.2f" % (np.median(b), np.median(a), np.percentile(a, 90)))
for label, pick in (("2004-2008", lambda o: o[3] <= 2008), ("2009-2012", lambda o: 2009 <= o[3] <= 2012), ("2013-2017", lambda o: o[3] >= 2013),
                    ("FULL", lambda o: o[4] == "FULL"), ("SUM2", lambda o: o[4] == "SUM2"), ("SUM4", lambda o: o[4] == "SUM4"), ("2000-2001 Jupiter", lambda o: o[3] <= 2001)):
    s = [o for o in obs if pick(o)]
    if len(s) < 300: print(f"   {label}: only {len(s)} matches"); continue
    t = fit(s); b, a = left(s, t_all)
    show = ", ".join(f"{f.split(',')[1] if f.startswith('CL1') else f.split(',')[0]} ({t[f][0]:+.1f},{t[f][1]:+.1f})" for f in ("CL1,RED", "CL1,BL1", "CL1,VIO", "CB2,CL2", "MT2,CL2") if f in t)
    print(f"   {label:18s} n={len(s):6d}  own fit: {show}   with the one table: median {np.median(a):.2f} px (before {np.median(b):.2f})")
json.dump({f: [round(v, 2) for v in t_all[f]] for f in keep}, open(os.path.expanduser("~/cassini-build/audit/out/wac_table.json"), "w"), indent=1)
