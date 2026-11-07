#!/usr/bin/env python3
"""compare.py OFF_CACHE ON_CACHE: every file of the prebuild with CASSINI_HDR=0 is the same bytes in the run with HDR
on, and the run with HDR on has only the recovery maps (hdr-r1) besides; prints the maps' sizes"""
import filecmp, os, statistics, sys
def files(r):
    return {os.path.relpath(os.path.join(d, f), r): os.path.join(d, f) for d, _, fs in os.walk(r) for f in fs}
a, b = files(sys.argv[1]), files(sys.argv[2])
same = sum(k in b and filecmp.cmp(a[k], b[k], shallow=False) for k in a)
extra = [k for k in b if k not in a]
maps = [k for k in extra if "/hdr-r1/" in k]
sz = [os.path.getsize(b[k]) for k in maps]
print(f"files without HDR: {len(a)}, the same bytes with HDR on: {same}; new files: {len(extra)}, of them maps: {len(maps)}")
print(f"map KB: mean {statistics.mean(sz)/1024:.1f}, median {statistics.median(sz)/1024:.1f}, max {max(sz)/1024:.1f}")
