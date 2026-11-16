#!/usr/bin/env python3
"""The cache's mosaic placement solves checked (obs_mosaic.global_places' "misfit"): every pass whose solve leaves
more than SOLVE_MISFIT_SHARE of its kept matches over SOLVE_MISFIT px (a seam where tiles meet), for the cache
rebuild's checks.

  python web/frames/solve_check.py CACHE/obs-v120-q95 [--json OUT] [--all]

Prints one line a flagged pass (pass, kept matches, over 2 px, worst px) and a tally; --all lists every pass with a
solve. Solves kept before the misfit was recorded are counted as "not checked". Exit status 0 always: a report, not
a gate (the rebuild's own checks decide)."""
import argparse
import json
import os
import sys


def scan(cache):
    rows, unchecked = [], 0
    for d in sorted(os.listdir(cache)):
        here = os.path.join(cache, d)
        if not os.path.isdir(here):
            continue
        for f in sorted(os.listdir(here)):
            if "global" not in f or not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(here, f)) as fh:
                    m = json.load(fh).get("misfit")
            except (OSError, ValueError):
                continue
            if m is None:
                unchecked += 1
                continue
            rows.append(dict(m, folder=d, file=f))
    return rows, unchecked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cache", help="a version folder of the cache (obs-v...-q95), its pass folders inside")
    ap.add_argument("--json", help="write every pass's misfit here")
    ap.add_argument("--all", action="store_true", help="list every pass, not only flagged ones")
    a = ap.parse_args()
    rows, unchecked = scan(a.cache)
    flagged = [r for r in rows if r.get("flag")]
    for r in sorted(rows if a.all else flagged, key=lambda r: -r["over"]):
        print(f"{'FLAG ' if r.get('flag') else '     '}{r['folder']}  {r['file']}: {r['over']} of {r['kept']} kept "
              f"matches over 2 px ({r['share']:.0%}), worst {r['worst']} px")
    print(f"{len(rows)} solves checked, {len(flagged)} flagged, {unchecked} not checked (solved before the misfit was kept)")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"flagged": flagged, "checked": len(rows), "unchecked": unchecked, "all": rows}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
