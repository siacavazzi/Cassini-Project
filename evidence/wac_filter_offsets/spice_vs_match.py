import json, os, sqlite3, re, numpy as np, collections
rows = json.load(open(os.path.expanduser("~/cassini-build/audit/out/cache_colour_sets.json")))
smithed = {l.strip() for l in open(os.path.expanduser("~/cassini-build/audit/out/smithed_frames.txt"))}
geo = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/geometry-audit.sqlite"))
def place(f):
    r = geo.execute("SELECT x, y, camera, scale FROM target WHERE frame=? AND error IS NULL", (f,)).fetchone()
    if not r or r[0] is None: return None
    k = (200.956 / 0.012) / r[3] if r[2] and r[2].endswith("WAC") and r[3] else 1.0
    return r[0] * k, r[1] * k
num = re.compile(r"([+-]\d+\.\d+),([+-]\d+\.\d+)")
d = collections.defaultdict(list); grey_all = grey_sm = 0; sets_sm = sets_all = 0; grey_any_sm = 0
for name, g, gm, aligned, cal, dropped, centred, stacked in rows:
    ids = ["_".join(p) for p in zip(name.split("_")[0::2], name.split("_")[1::2])]
    if not aligned or len(aligned) != len(ids) or "reference" not in aligned: continue
    ref = aligned.index("reference"); pr = place(ids[ref])
    all_sm = all(i in smithed for i in ids)
    sets_all += 1; sets_sm += all_sm
    if g == "not aligned":
        grey_all += 1; grey_sm += all_sm
    if pr is None: continue
    cam = ids[0][0]
    for i, (fid, how) in enumerate(zip(ids, aligned)):
        if i == ref or not isinstance(how, str): continue
        m = num.search(how); pc = place(fid)
        if not m or pc is None: continue
        if not (how.startswith("phase") and "checked" not in how): continue
        shift = np.array([float(m.group(1)), float(m.group(2))]); guess = np.array([pr[0] - pc[0], pr[1] - pc[1]])
        both = (fid in smithed) and (ids[ref] in smithed)
        none = (fid not in smithed) and (ids[ref] not in smithed)
        key = (cam, "both JPL-corrected" if both else "both raw" if none else "mixed")
        d[key].append(float(np.hypot(*(shift - guess))))
print("colour sets:", sets_all, " with every channel JPL-corrected:", sets_sm)
print("grey for failed alignment:", grey_all, " of them with every channel JPL-corrected:", grey_sm)
print("channels the pipeline matched by phase correlation: how far SPICE's offset between the two frames is from the picture match (frame px)")
for key in sorted(d):
    v = np.array(d[key])
    print(f"  {key[0]} {key[1]:20s} n={len(v):6d}  median {np.median(v):5.2f}  p75 {np.percentile(v,75):5.2f}  p90 {np.percentile(v,90):6.2f}  within 1 px {100*float((v<=1).mean()):4.0f}%  within 2 px {100*float((v<=2).mean()):4.0f}%")
