#!/usr/bin/env python3
"""
One rule for filter sets and passes, in one place. The frame server (reel.load_index, obs_mosaic.colour_sets),
the pre-build (prebuild.page_sets) and the replay data (build_data.py --groups: each frame's set and pass id in the
month chunks, which the page uses instead of working them out itself) all group frames through this module.

Filter set: the frames that together make one colour picture. A run of frames from one camera on one target, in
one observation, each taken within SET_GAP seconds of the one before, through different colour filters. Clear and
polarizer frames end a run, and a filter coming round again starts a new one (the next mosaic tile or colour
cycle). A run of two or more frames is a set. Its channels (channels): RED (or the 619 nm continuum CB1 where a set
has no RED, the narrow-angle camera at Jupiter), GRN and a blue (BL1, else BL2 or VIO) make true colour; any other
three or more filters make false colour, longest wavelength as red, the middle one as green, the shortest as blue;
two filters make a two-filter picture.

Pass: obs_mosaic.units, the frames of one camera, one target and one observation, split where the camera pauses or
the distance to the body changes, with its laps joined (a mosaic movie). Its kind is obs_mosaic._judge's: "mosaic",
"movie", "mosaic_movie" or None. pass_table numbers every pass of the index and gives every frame its pass,
the repeat exposures units leaves out of a pass's tiles too.

  CASSINI_GEOMETRY_CACHE=... python web/frames/sets_passes.py [--moved OUT.json]
  (counts the sets and passes; --moved lists what moved from the rules each piece of code used before, for a
  targeted remake of the pictures made from them)
"""
import os
import sys

SET_GAP = 300                          # seconds between the frames of one filter set
TRUE_REDS = ("RED", "CB1")             # the red of a true colour set, in order of preference
TRUE_BLUES = ("BL1", "BL2", "VIO")     # the blue of a true colour set, in order of preference


def is_polarizer(f1, f2):
    return f1.startswith("P") and f1[1:2].isdigit() or f1.startswith("IRP") or f2.startswith("IRP")


def colour_filter(f1, f2):
    """The frame's colour filter ("RED", "CB2", "BL1/GRN"...), or None for clear and polarizer frames."""
    if is_polarizer(f1, f2):
        return None
    return "/".join(f for f in (f1, f2) if not f.startswith("CL")) or None


def runs(frames):
    """The filter sets among frames, in time order: frames is a list of (cam, target, observation, colour filter
    or None, t); the answer is each set's positions in frames, in time order, in the order the sets end."""
    out, run = [], {}

    def close(cam):
        r = run.pop(cam, None)
        if r and len(r["at"]) >= 2:
            out.append(r["at"])

    for q, (cam, target, obs, f, t) in enumerate(frames):
        r = run.get(cam)
        if not f:
            close(cam)
            continue
        if r and target == r["target"] and obs == r["obs"] and t - r["last"] <= SET_GAP and f not in r["filters"]:
            r["at"].append(q); r["filters"].append(f); r["last"] = t
        else:
            close(cam)
            run[cam] = {"target": target, "obs": obs, "at": [q], "filters": [f], "last": t}
    for cam in list(run):
        close(cam)
    return out


def channels(filters, nms):
    """(kind, positions of the red, green and blue channels in filters) of a set: "true", "false" or "two" (two
    positions, longer wavelength first). nms: each filter's effective wavelength, in the same order."""
    at = {f: j for j, f in enumerate(filters)}
    red = next((f for f in TRUE_REDS if f in at), None)
    blue = next((f for f in TRUE_BLUES if f in at), None)
    if red and "GRN" in at and blue:
        return "true", [at[red], at["GRN"], at[blue]]
    w = sorted(range(len(filters)), key=lambda j: -nms[j])
    return ("false", [w[0], w[len(w) // 2], w[-1]]) if len(w) >= 3 else ("two", w)


def filter_sets(cams, targets, obs, f1s, f2s, t, nm):
    """Every filter set of the frames given as columns, in time order (cams "ISSNA"/"ISSWA" or "N"/"W"; nm(q):
    frame q's effective wavelength): (set of each frame, -1 outside any, and the sets, each {"kind", "use" (its
    channels' frame positions), "rows", "filters", "ready" (when its last channel was taken)})."""
    colour = {pair: colour_filter(*pair) for pair in set(zip(f1s, f2s))}
    fs = [colour[a, b] for a, b in zip(f1s, f2s)]
    set_of, sets = [-1] * len(fs), []
    for at in runs(list(zip(cams, targets, obs, fs, t))):
        kind, use = channels([fs[q] for q in at], [nm(q) for q in at])
        use = [at[j] for j in use]
        for q in at:
            set_of[q] = len(sets)
        sets.append({"kind": kind, "use": use, "rows": at, "filters": [fs[q] for q in at], "ready": max(t[q] for q in use)})
    return set_of, sets


def pass_table():
    """Every pass of the index (obs_mosaic.units over each target, observation and camera), numbered in the
    order the observations first appear: (pass number of each index row, -1 for a frame in no pass, and the
    passes, each {"key": (target, observation, cam, n), "kind", "rows" (first and last index row), "frames"}).
    Needs the geometry cache, as units does."""
    import numpy as np
    import obs_mosaic
    import reel
    idx, _ = reel.load_index()
    t = idx["seconds_1970"].to_numpy()
    pass_of, passes = np.full(len(idx), -1), []
    for (target, ob, inst), rows in idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices.items():
        if not isinstance(ob, str):
            continue
        rows = np.sort(rows)
        for u in obs_mosaic.units(target, ob, "N" if inst == "ISSNA" else "W"):
            if not u["frames"]:
                continue
            # a pass's frames run from its first tile to its last frame taken (repeat exposures included): the
            # passes of one observation never overlap in time
            mine = rows[(t[rows] >= u["frames"][0][3]) & (t[rows] <= u["last"])]
            pass_of[mine] = len(passes)
            passes.append({"key": u["key"], "kind": u.get("kind"), "rows": [int(mine[0]), int(mine[-1])], "frames": len(mine)})
    return pass_of, passes


def groups():
    """{frame id: (set id, pass id)} for every frame of the index, and the tables the page reads with them:
    sets {set id: [kind, [channel frame ids]]} and passes {pass id: [kind or "", observation, pass number in it,
    last frame id, frames]}. Set ids are reel.load_index's set numbers, pass ids pass_table's."""
    import reel
    idx, sets = reel.load_index()
    ids = idx["id"].tolist()
    pass_of, passes = pass_table()
    by_id = dict(zip(ids, zip(idx["set"].tolist(), pass_of.tolist())))
    set_table = {n: [s["kind"], [ids[q] for q in s["use"]]] for n, s in enumerate(sets)}
    pass_table_ = {n: [p["kind"] or "", p["key"][1], p["key"][3], ids[p["rows"][1]], p["frames"]] for n, p in enumerate(passes)}
    return by_id, set_table, pass_table_


def _old_reel_sets(idx):
    """The filter sets reel.load_index made before this module (RED only as a true red), for --moved."""
    cams, f1s, f2s = idx["INSTRUMENT_ID"].tolist(), idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist()
    import reel
    out = []
    fs = [colour_filter(a, b) for a, b in zip(f1s, f2s)]
    for at in runs(list(zip(cams, idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist(), fs, idx["seconds_1970"].tolist()))):
        by = {fs[q]: q for q in at}
        blue = next((f for f in TRUE_BLUES if f in by), None)
        if "RED" in by and "GRN" in by and blue:
            out.append([by["RED"], by["GRN"], by[blue]])
        else:
            w = sorted(at, key=lambda q: -reel.wavelength(cams[q], f1s[q] + f2s[q]))
            out.append([w[0], w[len(w) // 2], w[-1]] if len(w) >= 3 else w)
    return out


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--moved", help="write what moved between the old rules and this one here (JSON)")
    ap.add_argument("--no-passes", action="store_true", help="sets only (no geometry cache needed)")
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import reel
    import obs_mosaic
    idx, sets = reel.load_index()
    ids = idx["id"].tolist()
    kinds = {}
    for s in sets:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    print(f"{len(idx)} frames, {len(sets)} filter sets {kinds}, {sum(len(s['rows']) for s in sets)} frames in sets", flush=True)
    moved = {}
    # reel (body reels, movie export): CB1 is now a true red, as the camera windows and the pre-build had it
    old = _old_reel_sets(idx)
    moved["reel_sets"] = [[ids[q] for q in o] for o, s in zip(old, sets) if o != s["use"]]
    print(f"reel sets whose channels changed: {len(moved['reel_sets'])}", flush=True)
    if not args.no_passes:
        pass_of, passes = pass_table()
        pk = {}
        for p in passes:
            pk[p["kind"]] = pk.get(p["kind"], 0) + 1
        print(f"{len(passes)} passes {pk}, {int((pass_of >= 0).sum())} frames in a pass", flush=True)
        # movies (obs_mosaic.colour_sets): a pass's colour sets were found on its tiles (repeat exposures left out),
        # now they are the windows' sets; a movie pass whose sets differ shows other colour frames
        changed = []
        for p in passes:
            if p["kind"] not in ("movie", "mosaic_movie"):
                continue
            u = next(v for v in obs_mosaic.units(*p["key"][:3]) if v["key"] == p["key"])
            if [[j for _, j in s] for s in obs_mosaic.colour_sets(u["frames"])] != [[j for _, j in s] for s in obs_mosaic._own_sets(u["frames"])]:
                changed.append({"key": list(p["key"]), "first": ids[p["rows"][0]], "last": ids[p["rows"][1]], "frames": p["frames"]})
        moved["movie_passes"] = changed
        print(f"movie passes whose colour sets changed: {len(changed)}", flush=True)
    if args.moved:
        json.dump(moved, open(args.moved, "w"), indent=1)


if __name__ == "__main__":
    main()
