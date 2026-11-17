#!/usr/bin/env python3
"""cmp_items.py CACHE_A CACHE_B NAME [NAME ...]: every file under the cache folders whose name starts with one of the
item names (a pass's folders, a frame's or set's pictures), compared byte for byte; files only in one are listed."""
import hashlib, os, sys
a, b, names = sys.argv[1], sys.argv[2], sys.argv[3:]
if len(names) == 1 and os.path.isfile(names[0]):
    names = [l.strip() for l in open(names[0]) if l.strip()]


def files(root):
    out = {}
    for d, subs, fs in os.walk(root):
        rel = os.path.relpath(d, root)
        parts = rel.split(os.sep)
        for f in fs:
            p = os.path.join(rel, f)
            if any(part.startswith(n) for n in names for part in parts + [f]):
                out[p] = os.path.join(d, f)
    return out


def digest(p):
    h = hashlib.sha1()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


fa, fb = files(a), files(b)
only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
differ = [p for p in sorted(set(fa) & set(fb)) if os.path.getsize(fa[p]) != os.path.getsize(fb[p]) or digest(fa[p]) != digest(fb[p])]
size = sum(os.path.getsize(fa[p]) for p in fa)
print(f"{len(fa)} files in A ({size / 1e6:.0f} MB), {len(fb)} in B; {len(set(fa) & set(fb)) - len(differ)} identical, "
      f"{len(differ)} differ, {len(only_a)} only in A, {len(only_b)} only in B")
for label, lst in (("differ", differ), ("only in A", only_a), ("only in B", only_b)):
    for p in lst[:15]:
        print("  ", label, p)
sys.exit(1 if differ or only_a or only_b else 0)
