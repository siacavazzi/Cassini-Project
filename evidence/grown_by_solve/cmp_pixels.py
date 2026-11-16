#!/usr/bin/env python3
"""cmp_pixels.py CACHE_A CACHE_B NAMES [--out FILE.json]: the pictures (.webp, .png) under both caches whose path
holds one of the item names, compared as pixels: how many files are byte-identical, and for the rest how far the
pixels moved (levels of 255). For a change that is allowed to move pixels a little: the size of "a little"."""
import collections, hashlib, io, json, os, sys
import numpy as np
from PIL import Image
a, b, names = sys.argv[1], sys.argv[2], sys.argv[3]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
names = [l.split()[0] for l in open(names) if l.strip()] if os.path.isfile(names) else [names]


def files(root):
    got = {}
    for d, _, fs in os.walk(root):
        rel = os.path.relpath(d, root)
        if not any(n in rel for n in names) and not any(any(f.startswith(n) for n in names) for f in fs):
            continue
        for f in fs:
            if f.endswith((".webp", ".png")) and (any(n in rel for n in names) or any(f.startswith(n) for n in names)):
                got[os.path.join(rel, f)] = os.path.join(d, f)
    return got


def kind(rel):
    parts = rel.split(os.sep)
    for i, p in enumerate(parts):
        if p.startswith(("movie-", "tiles-", "seams", "rolling")):
            return "/".join([p.split("-")[0]] + parts[i + 1:-1]) + ("/hdr" if rel.endswith(".hdr.webp") else "")
    return parts[0]


fa, fb = files(a), files(b)
both = sorted(set(fa) & set(fb))
stats = collections.defaultdict(lambda: {"files": 0, "identical": 0, "differ": 0, "max": 0, "px": 0, "px_changed": 0,
                                         "px_over2": 0, "px_over8": 0, "sum_abs": 0.0, "worst": None, "worst_mean": 0.0})
for rel in both:
    s = stats[kind(rel)]
    s["files"] += 1
    ra, rb = open(fa[rel], "rb").read(), open(fb[rel], "rb").read()
    if ra == rb:
        s["identical"] += 1
        continue
    s["differ"] += 1
    ia, ib = np.asarray(Image.open(io.BytesIO(ra)).convert("RGBA")).astype(np.int16), np.asarray(Image.open(io.BytesIO(rb)).convert("RGBA")).astype(np.int16)
    if ia.shape != ib.shape:
        s["max"] = 255; s["worst"] = rel + " (sizes differ)"
        continue
    d = np.abs(ia - ib).max(axis=2)
    s["px"] += d.size; s["px_changed"] += int((d > 0).sum()); s["px_over2"] += int((d > 2).sum()); s["px_over8"] += int((d > 8).sum())
    s["sum_abs"] += float(d.sum()); s["max"] = max(s["max"], int(d.max()))
    if d.mean() > s["worst_mean"]:
        s["worst_mean"], s["worst"] = float(d.mean()), rel
print(f"{len(fa)} pictures in A, {len(fb)} in B, {len(both)} in both; only in A {len(set(fa) - set(fb))}, only in B {len(set(fb) - set(fa))}")
only = collections.Counter()
for rel in set(fa) ^ set(fb):
    only[(kind(rel), "A" if rel in fa else "B")] += 1
for (k, side), c in sorted(only.items()):
    print(f"   only in {side}: {c} {k}")
print("| kind | files | byte-identical | differ | pixels changed in those | by more than 2 levels | by more than 8 | mean change, levels | largest |")
print("|---|---|---|---|---|---|---|---|---|")
for k, s in sorted(stats.items()):
    px = max(1, s["px"])
    print(f"| {k} | {s['files']} | {s['identical']} | {s['differ']} | {100 * s['px_changed'] / px:.2f}% | {100 * s['px_over2'] / px:.3f}% | "
          f"{100 * s['px_over8'] / px:.4f}% | {s['sum_abs'] / px:.3f} | {s['max']} |")
for k, s in sorted(stats.items()):
    if s["worst"]:
        print(f"worst {k}: {s['worst']} (mean {s['worst_mean']:.3f})")
if out:
    json.dump({k: dict(v) for k, v in stats.items()}, open(out, "w"), indent=1)
