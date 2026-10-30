#!/usr/bin/env python3
"""The passes obs_mosaic's newer grouping rules (_drop_strays, _piece, 1x2 mosaics) group anew, which get the
GROUPING folder suffix, and the passes its layout rules after them lay out anew (time series, drifting filter sets,
laps over drifted places, maps joined across ZOOM, movies cut at a retarget, a turning camera, a lone frame no
longer setting the filters aside), which get RELAID's, every pass of an observation where TRACK_SPAN judges a
feature track otherwise than before, which gets RETRACKED's, and every pass of an observation where the scan rule (a
scan that pauses is no time series) judges a pass otherwise, which gets RESCANNED's: a summary, and their frame ids for
prebuild.py --only (the remake after the rules land).
Needs the index and the geometry cache (CASSINI_GEOMETRY_CACHE), as units does; reads only, about ten seconds.
Run: python web/frames/regrouped.py --ids regrouped-ids.txt [--targets JUPITER,SATURN]"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_mosaic  # noqa: E402
import reel  # noqa: E402


def regrouped(targets=None):
    """[(unit, every pass of its observation renumbered)] for each pass the newer rules group or lay out anew"""
    idx, _ = reel.load_index()
    out = []
    for (target, obs, inst) in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices:
        if not isinstance(obs, str) or inst not in ("ISSNA", "ISSWA") or targets and target not in targets:
            continue
        us = obs_mosaic.units(target, obs, "N" if inst == "ISSNA" else "W")
        anew = [v.get("regrouped") or v.get("relaid") or v.get("retracked") or v.get("rescanned") for v in us]
        out += [(u, all(anew) and len(us) > 1) for u, new in zip(us, anew) if new]
        with obs_mosaic._lock:
            obs_mosaic._units.clear()
    return out


LAID = ("revisit", "drift", "slot_laps", "joined", "twist", "aside")   # (the layout rules' flags on a pass, obs_mosaic.units)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", help="write the frame ids of the passes grouped anew here, one a line (prebuild.py --only)")
    ap.add_argument("--targets", help="only these targets, comma separated")
    a = ap.parse_args()
    found = regrouped(set(a.targets.split(",")) if a.targets else None)
    why = collections.Counter("rescanned" if u.get("rescanned") else "retracked" if u.get("retracked") else "renumbered" if whole else "strays" if u.get("off") else "1x2" if u.get("pair") else
                              next((k for k in LAID if u.get(k)), "other") for u, whole in found)
    print(f"{len(found)} passes in {len({u['key'][:3] for u, _ in found})} observations, "
          f"{sum(len(u['frames']) for u, _ in found)} frames: {dict(why)}")
    print("kinds:", dict(collections.Counter(u["kind"] for u, _ in found)))
    if a.ids:
        with open(a.ids, "w") as f:
            for u, _ in found:
                f.writelines(fr[1] + "\n" for fr in u["frames"])
        print("ids in", a.ids)
