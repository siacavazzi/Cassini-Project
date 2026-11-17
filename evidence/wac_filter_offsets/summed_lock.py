"""Do colour sets of summed frames (drawn at 1024 px by repeating each pixel 2x2 or 4x4) have their channel shifts
locked to whole camera pixels (multiples of 2 or 4 px)? From the full cache's own alignment reports."""
import json, os, sqlite3, re, numpy as np, collections
rows = json.load(open(os.path.expanduser("~/cassini-build/audit/out/cache_colour_sets.json")))
lab = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/labels.sqlite"))
mode = {}
def m(f):
    if f not in mode:
        r = lab.execute("SELECT INSTRUMENT_MODE_ID FROM l WHERE frame=?", (f,)).fetchone(); mode[f] = r[0] if r else None
    return mode[f]
num = re.compile(r"([+-]\d+\.\d+),([+-]\d+\.\d+)")
got = collections.defaultdict(list); sets = collections.Counter()
for name, g, gm, aligned, *_ in rows:
    ids = ["_".join(p) for p in zip(name.split("_")[0::2], name.split("_")[1::2])]
    if not aligned or len(aligned) != len(ids): continue
    modes = {m(i) for i in ids}
    if len(modes) != 1: continue
    md = modes.pop(); sets[(name[0], md)] += 1
    for how in aligned:
        if isinstance(how, str) and how.startswith("phase") and "checked" not in how:
            mm = num.search(how)
            if mm: got[(name[0], md)].append((float(mm.group(1)), float(mm.group(2))))
print("colour sets by camera and summing mode:", dict(sets))
for key in sorted(got):
    v = np.array(got[key]).ravel(); v = v[np.abs(v) > 0.05]
    step = {"FULL": 1, "SUM2": 2, "SUM4": 4}[key[1]]
    frac = np.abs(v / step - np.round(v / step))          # 0 = a whole camera pixel, 0.5 = half way between
    print(f"  {key[0]} {key[1]}: {len(v)} shift components; within a tenth of a camera pixel of a whole one: {100*float((frac < 0.1).mean()):.0f}% (20% if evenly spread); "
          f"exactly a multiple of {step} px to 0.1 px: {100*float((np.abs(v - step*np.round(v/step)) < 0.1).mean()):.0f}%")
