"""Pruning a mosaic pass's filters-level/ (obs_mosaic._filter_path files, <filter>-<count><solved_on>-<rect>.png).

The build only reads each filter's newest count, and served pictures are the same without the others (the
optimization audit, 2026-10-26); older counts only speed up regrowing a picture on demand. Per group (everything
but <count>) it keeps every multiple of 16 and the highest count, and removes the rest.

The Mac Mini's sweeper (~/server/cache/cassini-prebuild-sweep.py) prunes with this module from ~/server/cache; the
cloud rebuild (cloud_rebuild.py) leaves the same files out when it ships a pass's working files home.
"""
import os, re, subprocess

# the current name, or an older build's with a "-<hash>" after the rect (grouped without it)
NAME = re.compile(r"^(?P<f>.+?)-(?P<c>\d+)(?P<s>[^-]*)-(?P<r>-?\d+(?:_-?\d+)*)(?:-[0-9a-f]{12})?\.png$")


def doomed(names):
    """The names to remove from one filters-level/ listing."""
    groups = {}
    for n in names:
        m = NAME.match(n)
        if m:
            groups.setdefault((m["f"], m["s"], m["r"]), []).append((int(m["c"]), n))
    out = []
    for items in groups.values():
        top = max(c for c, _ in items)
        out += [n for c, n in items if c % 16 and c != top]
    return out


def prune_local(folder):
    """Prunes folder (a real filters-level/ on the SSD). Returns (files removed, bytes freed)."""
    gone = doomed(os.listdir(folder))
    freed = 0
    for n in gone:
        p = os.path.join(folder, n)
        freed += os.path.getsize(p)
        os.remove(p)
    return len(gone), freed


def prune_image(folder, timeout=60):
    """Prunes a filters-level/ in the disk image, every touch a subprocess with a timeout. (files, bytes)."""
    ls = subprocess.run(["ls", "-l", folder], capture_output=True, text=True, timeout=timeout, check=True).stdout
    sizes = {}
    for line in ls.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 9:
            sizes[parts[-1]] = int(parts[4])
    gone = doomed(sizes)
    for k in range(0, len(gone), 200):
        subprocess.run(["rm", "-f"] + [os.path.join(folder, n) for n in gone[k:k + 200]],
                       timeout=timeout, check=True)
    return len(gone), sum(sizes[n] for n in gone)
