"""treecmp.py A B: two caches file by file: files only in one, files whose bytes differ (by kind), the rest the same."""
import collections, hashlib, os, sys
def tree(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            if f == "slices.json" or ".part" in f:
                continue
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = p
    return out
a, b = tree(sys.argv[1]), tree(sys.argv[2])
only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
same = 0; differ = []; kinds = collections.Counter(); nbytes = 0
for rel in sorted(set(a) & set(b)):
    with open(a[rel], "rb") as fa, open(b[rel], "rb") as fb:
        da, db = fa.read(), fb.read()
    nbytes += len(da)
    if da == db: same += 1; kinds[os.path.splitext(rel)[1]] += 1
    else: differ.append(rel)
print(f"{len(a)} files in A, {len(b)} in B; {len(only_a)} only in A, {len(only_b)} only in B; of the {same + len(differ)} in both, "
      f"{same} the same bytes ({nbytes / 1e9:.2f} GB), {len(differ)} differ")
print("same by kind:", dict(kinds.most_common()))
for name, rows in (("only in A", only_a), ("only in B", only_b), ("differ", differ)):
    for r in rows[:15]: print(f"  {name}: {r}")
    if rows:
        print(f"  {name} by kind:", dict(collections.Counter(os.path.splitext(r)[1] for r in rows)))
