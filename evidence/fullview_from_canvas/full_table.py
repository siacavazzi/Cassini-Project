#!/usr/bin/env python3
"""full_table.py MAIN FULL482 FULLNEW NAMES: the full-view pair as a table. MAIN: the mosaics phase on main; FULL482:
PR 482 fullview phase on a copy of it; FULLNEW: the mosaics phase with the full views made in it. Work as instructions
retired (/usr/bin/time -l)."""
import os, re, sys
main, old, new, names = sys.argv[1:5]
names = [l.split()[0] for l in open(names) if l.strip()]


def ins(d, n, phase):
    try:
        t = open(os.path.join(d, "log", f"{n}-{phase}.time")).read()
    except OSError:
        return None
    m = re.search(r"(\d+)\s+instructions retired", t)
    return int(m.group(1)) / 1e9 if m else None


def count(d, n):
    k = 0
    for root, _, fs in os.walk(os.path.join(d, "cache")):
        if n in root and ("full" in os.path.basename(root)):
            k += sum(f.endswith(".webp") and ".hdr." not in f for f in fs)
    return k


print("| pass | full views | mosaics phase on main | fullview phase after it (PR 482) | mosaics phase making them (this branch) | added by making them | against the fullview phase |")
print("|---|---|---|---|---|---|---|")
tm = to = tn = 0
for n in names:
    m, o, w = ins(main, n, "mosaics"), ins(old, n, "fullview"), ins(new, n, "mosaics")
    if None in (m, o, w):
        print(f"| {n} | missing |"); continue
    tm += m; to += o; tn += w
    print(f"| {n} | {count(old, n)} | {m:.0f} | {o:.0f} | {w:.0f} | {w - m:.0f} | {100 * (w - m - o) / o:+.0f}% |")
print(f"| **all** | | **{tm:.0f}** | **{to:.0f}** | **{tn:.0f}** | **{tn - tm:.0f}** | **{100 * (tn - tm - to) / to:+.0f}%** |")
print()
print(f"Both phases together: {tm + to:.0f} on PR 482, {tn:.0f} on this branch ({100 * (tn - tm - to) / (tm + to):+.1f}%). Billions of instructions.")
