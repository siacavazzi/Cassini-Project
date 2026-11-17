"""Finding 7: per-filter-combination and per-wheel WAC offset fit from the audit's channel matches (full-res WAC)."""
import json, os, sqlite3, re, numpy as np, collections, random, sys
A = os.path.expanduser("~/cassini-build/audit/out/")
rows = json.load(open(A + "cache_colour_sets.json"))
geo = sqlite3.connect(A + "geometry-audit.sqlite"); lab = sqlite3.connect(A + "labels.sqlite")
def place(f):
    r = geo.execute("SELECT x, y, camera, scale FROM target WHERE frame=? AND error IS NULL", (f,)).fetchone()
    if not r or r[0] is None: return None
    k = (200.956 / 0.012) / r[3] if r[2] and r[2].endswith("WAC") and r[3] else 1.0
    return r[0] * k, r[1] * k
def meta(f):
    r = lab.execute("SELECT FILTER_NAME, IMAGE_MID_TIME, INSTRUMENT_MODE_ID FROM l WHERE frame=?", (f,)).fetchone()
    return (r[0].strip("()").replace('"', '').replace(' ', ''), int(r[1][:4]), r[2]) if r else None
num = re.compile(r"([+-]\d+\.\d+),([+-]\d+\.\d+)")
obs = []
for name, g, gm, aligned, *_ in rows:
    if name[0] != "W": continue
    ids = ["_".join(p) for p in zip(name.split("_")[0::2], name.split("_")[1::2])]
    if not aligned or len(aligned) != len(ids) or "reference" not in aligned: continue
    ref = aligned.index("reference"); pr = place(ids[ref]); mr = meta(ids[ref])
    if pr is None or mr is None: continue
    for i, (fid, how) in enumerate(zip(ids, aligned)):
        if i == ref or not isinstance(how, str) or not how.startswith("phase") or "checked" in how or "SPICE" in how: continue
        m = num.search(how); pc = place(fid); mc = meta(fid)
        if not m or pc is None or mc is None: continue
        res = np.array([float(m.group(1)) - (pr[0] - pc[0]), float(m.group(2)) - (pr[1] - pc[1])])
        if np.hypot(*res) > 12: continue
        obs.append((mc[0], mr[0], res, mc[1], mc[2], name))
obs = [o for o in obs if o[4] == "FULL"]
print("matches", len(obs), "modes", collections.Counter(o[4] for o in obs))
cnt = collections.Counter(); [cnt.update([o[0], o[1]]) for o in obs]
print("filter combos seen:", sorted(cnt.items(), key=lambda x: -x[1]))
def irls(A, bx, by):
    w = np.ones(len(A))
    for _ in range(8):
        tx = np.linalg.lstsq(A * w[:, None], bx * w, rcond=None)[0]; ty = np.linalg.lstsq(A * w[:, None], by * w, rcond=None)[0]
        r = np.hypot(A @ tx - bx, A @ ty - by); w = 1.0 / np.maximum(r, 0.5)
    return tx, ty
# model W: offset(f1,f2) = a[f1] + b[f2], a[CL1]=0, b[CL2]=0 ... but CL1,CL2 rarely used: zero GRN instead (b[GRN]=0)
def wheel_fit(sample, minc=20):
    c = collections.Counter()
    for a, b, *_ in sample:
        for f in (a, b):
            w1, w2 = f.split(","); c["1" + w1] += 1; c["2" + w2] += 1
    keys = sorted(k for k, n in c.items() if n >= minc and k not in ("1CL1", "2GRN"))
    ix = {k: i for i, k in enumerate(keys)}
    def row(f, s, r):
        w1, w2 = f.split(",")
        for k in ("1" + w1, "2" + w2):
            if k in ix: r[ix[k]] += s
            elif k not in ("1CL1", "2GRN"): return False
        return True
    Ar, bx, by = [], [], []
    for a, b, res, *_ in sample:
        r = np.zeros(len(keys))
        if row(a, 1, r) and row(b, -1, r):
            Ar.append(r); bx.append(res[0]); by.append(res[1])
    tx, ty = irls(np.array(Ar), np.array(bx), np.array(by))
    t = {"1CL1": (0.0, 0.0), "2GRN": (0.0, 0.0)}
    t.update({k: (float(tx[i]), float(ty[i])) for k, i in ix.items()})
    return t, c
def wheel_off(t, f):
    w1, w2 = f.split(",")
    if "1" + w1 not in t or "2" + w2 not in t: return None
    return np.add(t["1" + w1], t["2" + w2])
def combo_fit(sample, minc):
    c = collections.Counter(); [c.update([o[0], o[1]]) for o in sample]
    keys = sorted(k for k, n in c.items() if n >= minc and k != "CL1,GRN"); ix = {k: i for i, k in enumerate(keys)}
    Ar, bx, by = [], [], []
    for a, b, res, *_ in sample:
        if (a in ix or a == "CL1,GRN") and (b in ix or b == "CL1,GRN"):
            r = np.zeros(len(keys))
            if a in ix: r[ix[a]] += 1
            if b in ix: r[ix[b]] -= 1
            Ar.append(r); bx.append(res[0]); by.append(res[1])
    tx, ty = irls(np.array(Ar), np.array(bx), np.array(by))
    t = {"CL1,GRN": np.zeros(2)}; t.update({k: np.array((tx[i], ty[i])) for k, i in ix.items()}); return t, c
def score(sample, off):
    b, a = [], []
    for x, y, res, *_ in sample:
        ox, oy = off(x), off(y)
        if ox is None or oy is None: continue
        b.append(np.hypot(*res)); a.append(np.hypot(*(res - (ox - oy))))
    return len(b), np.median(b), np.median(a), np.percentile(a, 90)
random.seed(5); names = sorted({o[5] for o in obs}); random.shuffle(names); half = set(names[:len(names)//2])
tr = [o for o in obs if o[5] in half]; te = [o for o in obs if o[5] not in half]
for minc in (150, 40, 15):
    tc, _ = combo_fit(tr, minc)
    print(f"combo table (min {minc}), held-out: n=%d before %.2f after %.2f p90 %.2f" % score(te, lambda f: tc.get(f)))
tw, _ = wheel_fit(tr)
print("wheel model, held-out: n=%d before %.2f after %.2f p90 %.2f" % score(te, lambda f: wheel_off(tw, f)))
# same held-out pairs for a fair comparison: pairs the 150-combo table covers
tc, _ = combo_fit(tr, 150)
cov = [o for o in te if o[0] in tc and o[1] in tc]
print("on the 150-table's pairs: combo n=%d before %.2f after %.2f p90 %.2f" % score(cov, lambda f: tc.get(f)),
      " wheel n=%d before %.2f after %.2f p90 %.2f" % score(cov, lambda f: wheel_off(tw, f)))
# full fits
tc_all, cc = combo_fit(obs, 15); tw_all, wc = wheel_fit(obs)
print("\nfull combo table (min 15):")
for k in sorted(tc_all, key=lambda k: -cc[k]):
    w = wheel_off(tw_all, k)
    print(f"  {k:10s} n={cc[k]:5d}  ({tc_all[k][0]:+.2f}, {tc_all[k][1]:+.2f})   wheel model ({w[0]:+.2f}, {w[1]:+.2f})" if w is not None else f"  {k:10s} n={cc[k]:5d}  ({tc_all[k][0]:+.2f}, {tc_all[k][1]:+.2f})")
print("\nwheel terms:"); [print(f"  {k:6s} n={wc[k]:5d} ({v[0]:+.2f}, {v[1]:+.2f})") for k, v in sorted(tw_all.items())]
# by era using the full combo table
for lab_, pick in (("2000-2001", lambda o: o[3] <= 2001), ("2004-2008", lambda o: 2004 <= o[3] <= 2008), ("2009-2012", lambda o: 2009 <= o[3] <= 2012), ("2013-2017", lambda o: o[3] >= 2013)):
    s = [o for o in obs if pick(o)]
    print(lab_, "n=%d before %.2f after %.2f p90 %.2f" % score(s, lambda f: tc_all.get(f)))
# by summing mode
for md in ("FULL", "SUM2", "SUM4"):
    s = [o for o in obs if o[4] == md]
    if s: print(md, "n=%d before %.2f after %.2f p90 %.2f" % score(s, lambda f: tc_all.get(f)))
json.dump({k: [round(float(v[0]), 2), round(float(v[1]), 2), cc[k]] for k, v in tc_all.items()}, open("combo_table_full.json", "w"), indent=1)
json.dump({k: [round(v[0], 2), round(v[1], 2), wc.get(k, 0)] for k, v in tw_all.items()}, open("wheel_table_full.json", "w"), indent=1)
