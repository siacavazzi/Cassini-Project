"""How often geometric_correction._plan's cache misses, by its size: every WAC frame the build corrects, in time order
as one process meets them (all frames), and as 16 processes of the processed phase meet them (stretches of ~18 items dealt round)."""
import sys, collections
sys.path.insert(0, "web/frames"); sys.path.insert(0, ".")
import reel, geometric_correction as gc
idx, _ = reel.load_index()
wac = idx[idx["INSTRUMENT_ID"] == "ISSWA"]
f = [gc.FOCAL_LENGTHS.get((str(a).strip().upper(), str(b).strip().upper()), gc.F_DEFAULT) for a, b in zip(wac["filter1"], wac["filter2"])]
print(len(idx), "frames,", len(wac), "WAC;", len(set(f)), "focal lengths:", collections.Counter(f).most_common(30))
def misses(seq, size):
    lru, n = collections.OrderedDict(), 0
    for k in seq:
        if k in lru: lru.move_to_end(k)
        else:
            n += 1; lru[k] = 1
            if len(lru) > size: lru.popitem(last=False)
    return n
for size in (6, 8, 10, 12, 16, 21):
    one = misses(f, size)
    # 16 processes: consecutive stretches of 18 WAC+NAC items; approximate by dealing stretches of the WAC list round robin
    per = [[] for _ in range(16)]
    pos = idx.index.get_indexer(wac.index) if False else None
    import numpy as np
    order = np.flatnonzero((idx["INSTRUMENT_ID"] == "ISSWA").to_numpy())
    for k, i in zip(f, order):
        per[(i // 18) % 16].append(k)
    many = sum(misses(p, size) for p in per)
    print(f"cache of {size:2d}: one process {one:6d} misses ({100 * one / len(f):4.1f}% of WAC frames); 16 processes {many:6d} ({100 * many / len(f):4.1f}%)")
