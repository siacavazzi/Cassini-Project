import json, os, sqlite3, re, numpy as np, collections
rows = json.load(open(os.path.expanduser("~/cassini-build/audit/out/cache_colour_sets.json")))
smithed = {l.strip() for l in open(os.path.expanduser("~/cassini-build/audit/out/smithed_frames.txt"))}
geo = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/geometry-audit.sqlite"))
lab = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/labels.sqlite"))
def place(f):
    r = geo.execute("SELECT x, y, camera, scale FROM target WHERE frame=? AND error IS NULL", (f,)).fetchone()
    if not r or r[0] is None: return None
    k = (200.956 / 0.012) / r[3] if r[2] and r[2].endswith("WAC") and r[3] else 1.0
    return r[0] * k, r[1] * k
def meta(f):
    r = lab.execute("SELECT FILTER_NAME, IMAGE_MID_TIME, INSTRUMENT_MODE_ID FROM l WHERE frame=?", (f,)).fetchone()
    return (r[0].strip("()").replace("CL1,", "").replace(",CL2", ""), r[1], r[2]) if r else None
num = re.compile(r"([+-]\d+\.\d+),([+-]\d+\.\d+)")
import sys
CAM = sys.argv[1]
d = collections.defaultdict(list)
for name, g, gm, aligned, *_ in rows:
    if name[0] != CAM: continue
    ids = ["_".join(p) for p in zip(name.split("_")[0::2], name.split("_")[1::2])]
    if not aligned or len(aligned) != len(ids) or "reference" not in aligned: continue
    ref = aligned.index("reference"); pr = place(ids[ref]); mr = meta(ids[ref])
    if pr is None or mr is None: continue
    for i, (fid, how) in enumerate(zip(ids, aligned)):
        if i == ref or not isinstance(how, str) or not how.startswith("phase") or "checked" in how: continue
        if CAM == "N" and not (fid in smithed and ids[ref] in smithed): continue
        m = num.search(how); pc = place(fid); mc = meta(fid)
        if not m or pc is None or mc is None: continue
        res = np.array([float(m.group(1)) - (pr[0] - pc[0]), float(m.group(2)) - (pr[1] - pc[1])])
        d[(mc[0], mr[0])].append(res)
print(CAM, "picture match minus SPICE offset, by filter (channel -> reference): mean dx, dy and scatter (px)")
for k, v in sorted(d.items(), key=lambda kv: -len(kv[1]))[:22]:
    v = np.array(v); med = np.median(v, axis=0); sc = 1.4826 * np.median(np.abs(v - med), axis=0)
    print(f"  {k[0]:9s} -> {k[1]:9s} n={len(v):5d}  median offset ({med[0]:+5.2f}, {med[1]:+5.2f})  scatter ({sc[0]:4.2f}, {sc[1]:4.2f})")
