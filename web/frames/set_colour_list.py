#!/usr/bin/env python3
"""The movies obs_mosaic._set_colour plays in colour (SET_COLOUR's folder): movies whose tile counts made them grey
(colour_of) though they take colour sets of three or more filters (the NAC Titan wind stares of 2005-06-04,
ISS_009TI_1X1WND10001..). A summary, the colour filters each gets, and their frame ids for prebuild.py --only.
Needs the index and the geometry cache (CASSINI_GEOMETRY_CACHE), as units does; reads only.
Run: python web/frames/set_colour_list.py --ids set-colour-ids.txt [--targets TITAN] [--years 2005]"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_mosaic  # noqa: E402
import reel  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", help="write the frame ids of those passes here, one a line")
    ap.add_argument("--targets", help="comma separated")
    ap.add_argument("--years", help="comma separated (the year a pass starts)")
    args = ap.parse_args()
    targets = set(args.targets.split(",")) if args.targets else None
    years = set(args.years.split(",")) if args.years else None
    idx, _ = reel.load_index()
    yr = dict(zip(idx["id"], idx["seconds_1970"]))
    out, by = [], collections.Counter()
    for (target, obs, inst) in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices:
        if not isinstance(obs, str) or inst not in ("ISSNA", "ISSWA") or targets and target not in targets:
            continue
        for u in obs_mosaic.units(target, obs, "N" if inst == "ISSNA" else "W"):
            if not u["frames"] or years and str(1970 + int(yr[u["frames"][0][1]] // 31556952)) not in years:
                continue
            colour = obs_mosaic._filters(u)[3]
            if u.get("set_colour"):
                out.append(u)
                by[target] += 1
                print("\t".join([*map(str, u["key"]), str(len(u["frames"])), u["frames"][0][1], ",".join(colour)]), flush=True)
        with obs_mosaic._lock:
            obs_mosaic._units.clear()
    print(f"{len(out)} movies now in colour, {sum(len(u['frames']) for u in out)} frames: {dict(by.most_common())}")
    if args.ids:
        with open(args.ids, "w") as fh:
            fh.write("".join(fr[1] + "\n" for u in out for fr in u["frames"]))


if __name__ == "__main__":
    main()
