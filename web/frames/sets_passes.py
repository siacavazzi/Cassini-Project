#!/usr/bin/env python3
"""
One rule for filter sets and passes, in one place. The frame server (reel.load_index, obs_mosaic.colour_sets),
the pre-build (prebuild.page_sets) and the replay data (build_data.py --groups: each frame's set and pass id in the
month chunks, which the page uses instead of working them out itself) all group frames through this module.

Filter set: the frames that together make one colour picture. A run of frames from one camera on one target, in
one observation, each taken within SET_GAP seconds of the one before, through different colour filters. Clear and
polarizer frames end a run, and a filter coming round again starts a new one (the next mosaic tile or colour
cycle). A frame taken again through the filter of the frame just before it, within REPEAT_GAP seconds (at most
REPEAT_MAX of them), is a repeat exposure: it stays in the run (the pipeline stacks it into that channel) instead of
starting a new one, so a pointing that takes two exposures through each filter is one set, not a chain of two-filter
sets each taking a filter from the next pointing. Where the geometry cache places the frames, a run also ends where
the camera moves more than SET_PLACE px (the next pointing of a mosaic). A run of two or more filters is a set; its
channel of each filter is that filter's first frame in it. Its channels (channels): RED (or the 619 nm continuum CB1 where a set
has no RED, the narrow-angle camera at Jupiter), GRN and a blue (BL1, else BL2 or VIO) make true colour; any other
three or more filters make false colour from the three nearest the visible (nearest_visible), longest wavelength as
red, the middle one as green, the shortest as blue; two filters make a two-filter picture.

Pass: obs_mosaic.units, the frames of one camera, one target and one observation, split where the camera pauses or
the distance to the body changes, with its laps joined (a mosaic movie). Its kind is obs_mosaic._judge's: "mosaic",
"movie", "mosaic_movie" or None. pass_table numbers every pass of the index and gives every frame its pass,
the repeat exposures units leaves out of a pass's tiles too.

  CASSINI_GEOMETRY_CACHE=... python web/frames/sets_passes.py [--moved OUT.json]
  (counts the sets and passes; --moved lists what moved from the rules each piece of code used before, for a
  targeted remake of the pictures made from them: reel sets, movies' colour sets, passes now played as tracks)
"""
import os
import sys

SET_GAP = 300                          # seconds between the frames of one filter set
REPEAT_GAP = 120                       # seconds: the same filter again this soon after is a repeat exposure (stacking)
REPEAT_MAX = 5                         # ... at most this many frames of a filter in a row (stacking.load_stacked's)
SET_PLACE = 256                        # full resolution px: a camera move further than this ends a set (obs_mosaic.SAME_PLACE)
# full resolution px: the furthest the target's centre may sit off the frame for SPICE's place to say where the camera
# points (0.3 rad: the place is the target's direction on the camera's flat image plane, which runs off to hundreds of
# thousands of px for a target behind the camera, Jupiter flat fields at 440,000 px)
HALF_DIAGONAL = 724                    # full resolution px: a frame's middle to its corner
PLACE_REACH = {"N": 50000, "W": 5000, "ISSNA": 50000, "ISSWA": 5000}
TRUE_REDS = ("RED", "CB1")             # the red of a true colour set, in order of preference
TRUE_BLUES = ("BL1", "BL2", "VIO")     # the blue of a true colour set, in order of preference
# A false colour set's three channels, when it took more than three filters: the three nearest what an eye's red,
# green and blue see (RED, GRN, BL1: 650, 568, 451 nm), longest as red, so a set keeps its visible filters (GRN over
# UV1, IR3 + GRN + UV3 of Pandora's IR3, GRN, UV3, UV1; CB2 + CB1 + BL1 of a gas giant's continuum filters) and
# leaves out its methane bands (MT1, MT2, MT3, which show how high the clouds are, not their colour) wherever three
# others are there. Sam 2026-11-02 (fix plan group C).
VISIBLE_NM = (650.0, 568.0, 451.0)


def is_methane(f):
    """True for a methane band filter, alone or stacked ("MT2", "MT3", "IR2/MT2")."""
    return any(p.startswith("MT") for p in str(f or "").split("/"))


def nearest_visible(filters, nms):
    """The positions in filters (distinct colour filters, nms their wavelengths) of the three a false colour set
    draws, longest wavelength first: the fewest methane bands, then the green nearest GRN, then the red and blue
    nearest RED and BL1 (the least sum of their distances), then the order the filters come in (a Titan wind stare's
    CB3, CB1, MT1, UV1, UV3 draws CB3 + CB1 + UV3). Three or fewer filters: all of them, longest first."""
    import itertools
    order = sorted(range(len(filters)), key=lambda j: -nms[j])
    if len(order) <= 3:
        return order
    best = None
    for three in itertools.combinations(order, 3):
        r, g, b = three
        key = (sum(is_methane(filters[j]) for j in three), abs(nms[g] - VISIBLE_NM[1]),
               abs(nms[r] - VISIBLE_NM[0]) + abs(nms[b] - VISIBLE_NM[2]), three)
        if best is None or key < best:
            best = key
    return list(best[3])


def is_polarizer(f1, f2):
    return f1.startswith("P") and f1[1:2].isdigit() or f1.startswith("IRP") or f2.startswith("IRP")


def colour_filter(f1, f2):
    """The frame's colour filter ("RED", "CB2", "BL1/GRN"...), or None for clear and polarizer frames."""
    if is_polarizer(f1, f2):
        return None
    return "/".join(f for f in (f1, f2) if not f.startswith("CL")) or None


# Polarized colour. The narrow-angle camera's visible polarizers (P0, P60, P120, in its first filter wheel) sit in front
# of a colour filter in its second; a frame through one is that colour seen through a polarizer, calibrated as its
# clear filter (calibration.calibrate, as CISSCAL). An observation that takes its colours only through them (the 2004
# and 2005 Saturn polarimetry mosaics, 2X2PLRNC and 1X2PLRNC: every frame P0, P60 or P120 with BL2, GRN, CB1, CB2) had
# no colour frame at all by the rule that a polarizer frame is none, and played grey (Sam 2026-11-16). There each
# polarizer frame of a filter of POLARIZED_SHARE is that filter's frame (polarized_as_colour), so its sets form by the
# one rule, and the three angles of a filter, taken seconds apart at one pointing, are repeat exposures stacked into
# one channel (stacking): their mean is the light without its polarization. An observation that also takes plain
# visible colour frames keeps its polarizer frames out of colour, as before, so its colour stays its plain frames' (a polarized
# frame calibrates to about a third of its plain frame's I/F: POLARIZED_SHARE).
VISIBLE_POLARIZERS = ("P0", "P60", "P120")
# the mean of a P0, P60, P120 frame of a filter over a plain (CL1) frame of it taken minutes from them, the body whole
# in frame, both calibrated by the repo (web/frames/polarized_share.py measures it): calibration.calibrate divides a
# polarized colour frame by it, so its channel has its plain frame's I/F and a set its plain set's colour balance.
# BL2 and CB1: medians of 7 and 15 pairs, interquartile range 0.330-0.333 and 0.348-0.349. GRN: the icy moons' 20
# pairs give 0.355 (0.351-0.356 without the dots and Phoebe's turning face); Titan's and Saturn's 7 observations
# taking all three both ways (evidence/polarized_colour/tint_check.txt) put it at 0.350, which leaves their corrected
# polarized sets within 1% of their plain sets' colour. Only these three (true colour) count; other polarizer frames
# stay out of colour
POLARIZED_SHARE = {"BL2": 0.332, "GRN": 0.350, "CB1": 0.349}
VISIBLE_COLOURS = ("RED", "GRN", "BL1", "BL2", "VIO", "CB1")   # an observation taking one of these plainly keeps its polarizers grey
# The wide-angle camera's infrared polarizers (IRP0, IRP90, in its second wheel) behind a near-infrared band in its first
# (CB2, CB3, MT2, MT3, IR4): an observation taking its bands only through them (about 170 Saturn, moon, Titan and
# Jupiter sequences: 00ASA COMPSITB013, the 2006 1X2PLRNC Saturn WACs, the moons' photometry) has no visible band, so it
# is false colour (calibration.color_mix: balanced on the body's measured colour), and played grey. Sam 2026-11-17 (taste
# call 9, "it looks fine"): those play in it. A frame through one is its band's frame there, IRP0 and IRP90 stacked
# (their mean is the unpolarized light), in an observation whose every non-clear frame is IR-polarized and that takes
# two bands or more (ir_polarized_ok). IR_POLARIZED_SHARE: the IRP0 and IRP90 mean over a plain (CL2) frame of the band,
# measured as POLARIZED_SHARE is (polarized_share.py CAM=W, 2026-11-17): CB2 0.477 (IQR 0.475-0.478, 15 pairs), CB3
# 0.492 (0.489-0.493, 15), MT2 0.468 (Saturn's 007SA 1X2WPH pairs 0.468-0.473; 017SA 1X2WPH140's 0.11, Saturn cut at
# the frame's edge and the plain frame at another pointing, left out), MT3 0.485 (Titan's nine whole-disk pairs,
# 0.430-0.508; 017SA's 0.17-0.19 left out as for MT2), IR4 0.500 (Rhea, Enceladus 0.497, 0.503)
IR_POLARIZERS = ("IRP0", "IRP90")
IR_POLARIZED_SHARE = {"CB2": 0.477, "CB3": 0.492, "MT2": 0.468, "MT3": 0.485, "IR4": 0.500}


def polarized_filter(cam, f1, f2):
    """The band a polarizer frame of camera cam stands for, or None: a visible polarizer frame of the NAC ("ISSNA" or
    "N": P0, P60, P120 with a POLARIZED_SHARE filter, the filter), or an infrared polarizer frame of the WAC ("ISSWA" or
    "W": an IR_POLARIZED_SHARE band with IRP0 or IRP90, the band)."""
    if cam in ("ISSNA", "N"):
        return f2 if f1 in VISIBLE_POLARIZERS and f2 in POLARIZED_SHARE else None
    if cam in ("ISSWA", "W"):
        return f1 if f2 in IR_POLARIZERS and f1 in IR_POLARIZED_SHARE else None
    return None


def polarized_share(cam, f1, f2):
    """The share of its plain frame's I/F a polarized colour frame calibrates to (calibration.polarized_share)."""
    band = polarized_filter(cam, f1, f2)
    return None if band is None else (POLARIZED_SHARE if cam in ("ISSNA", "N") else IR_POLARIZED_SHARE)[band]


def polarized_as_colour(cams, targets, obs, f1s, f2s):
    """For each frame (columns, as filter_sets takes them), whether it is a polarizer frame that counts as its colour
    filter: a visible polarizer frame of a POLARIZED_SHARE filter in an observation (camera, target, observation)
    that takes every filter of POLARIZED_SHARE through the visible polarizers (true colour) and no visible colour
    (VISIBLE_COLOURS) without one. Its plain frames of other bands (a methane, ultraviolet or near-infrared band:
    018SA 1X2PLRNCJ's CL1 MT2) are its own, as before.
    WAC frames: an IR_POLARIZED_SHARE band through IRP0 or IRP90 in an observation whose every non-clear frame is
    such a frame and that takes at least two of those bands (a false colour or two-band set)."""
    keys = list(zip(cams, targets, obs))
    pol = [polarized_filter(c, str(a), str(b)) for c, a, b in zip(cams, f1s, f2s)]
    took, plain = {}, set()
    for k, c, p, a, b in zip(keys, cams, pol, f1s, f2s):
        if p:
            took.setdefault(k, set()).add(p)
        elif c in ("ISSWA", "W"):
            if colour_filter(str(a), str(b)) or str(b) in IR_POLARIZERS:
                plain.add(k)   # (a plain band, or another band through an IR polarizer: not all of its colour is ours)
        elif any(x in VISIBLE_COLOURS for x in str(colour_filter(str(a), str(b)) or "").split("/")):
            plain.add(k)
    ok = {k for k, fs in took.items() if k not in plain
          and (fs >= set(POLARIZED_SHARE) if k[0] in ("ISSNA", "N") else len(fs) >= 2)}
    return [p is not None and k in ok for k, p in zip(keys, pol)]


def polarized_index(idx, filter_cols=True):
    """idx (Image_index rows with INSTRUMENT_ID, TARGET_NAME, OBSERVATION_ID, FILTER_NAME, and filter1 and filter2 when
    filter_cols) with its polarized colour frames (polarized_as_colour) read as their band, in place: a NAC frame CL1
    and its filter (FILTER_NAME "(CL1,GRN)", filter1 "CL1"), a WAC frame its band and CL2 ("(MT2,CL2)", filter2 "CL2"),
    and a column "polarized" marking them. The index loaders (reel.load_index, stacking.load_index) read it so, so
    sets, passes, plans and repeat stacking all take the frame as its colour. Returns idx."""
    # (each value as text, a missing one as "": pandas 3's astype(str) keeps a missing value as NaN, a float)
    text = lambda col: [v if isinstance(v, str) else "" for v in idx[col].tolist()]
    names = text("FILTER_NAME")
    parts = [n.strip("()").split(",") + [""] for n in names]
    f1s = text("filter1") if filter_cols else [p[0] for p in parts]
    f2s = text("filter2") if filter_cols else [p[1] for p in parts]
    use = polarized_as_colour(idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist(),
                              f1s, f2s)
    idx["polarized"] = use
    if any(use):
        wac = [c in ("ISSWA", "W") for c in idx["INSTRUMENT_ID"].tolist()]
        idx["FILTER_NAME"] = [(f"({a},CL2)" if w else f"(CL1,{b})") if u else n
                              for u, w, n, a, b in zip(use, wac, idx["FILTER_NAME"].tolist(), f1s, f2s)]
        if filter_cols:
            idx["filter1"] = ["CL1" if u and not w else a for u, w, a in zip(use, wac, idx["filter1"].tolist())]
            idx["filter2"] = ["CL2" if u and w else b for u, w, b in zip(use, wac, idx["filter2"].tolist())]
    return idx


def runs(frames):
    """The filter sets among frames, in time order: frames is a list of (cam, target, observation, colour filter
    or None, t), each optionally with a sixth item, where SPICE places the frame ((x, y, ...) as stacking.places
    gives it, or None); the answer is each set's positions in frames, in time order, in the order the sets end."""
    out, run = [], {}

    def close(cam):
        r = run.pop(cam, None)
        if r and len(set(r["filters"])) >= 2:
            out.append(r["at"])

    for q, fr in enumerate(frames):
        cam, target, obs, f, t = fr[:5]
        place = fr[5] if len(fr) > 5 else None
        r = run.get(cam)
        if not f:
            close(cam)
            continue
        reach = PLACE_REACH.get(cam)
        if place is not None and (reach is None or place[0] is None or max(abs(place[0]), abs(place[1])) > reach):
            place = None
        same = r and target == r["target"] and obs == r["obs"] and t - r["last"] <= SET_GAP and not moved(r["place"], place)
        repeat = same and f == r["filters"][-1] and t - r["last"] <= REPEAT_GAP and r["row"] < REPEAT_MAX
        if same and (repeat or f not in r["filters"]):
            r["at"].append(q); r["filters"].append(f); r["last"] = t
            r["row"] = r["row"] + 1 if repeat else 1
            r["place"] = place if place is not None else r["place"]
        else:
            close(cam)
            run[cam] = {"target": target, "obs": obs, "at": [q], "filters": [f], "last": t, "row": 1, "place": place}
    for cam in list(run):
        close(cam)
    return out


def pointing(place, radius_km, ifov):
    """place (x, y, range km), as runs takes it, or None for a frame that lies wholly on its target's disk: there
    SPICE's centre offset cannot say whether two frames show the same ground, as the view swings across a close
    flyby (Titan at 6,000 km: 5 degrees, 15,000 px, in the 200 s of a CB3, MT3, MT1 set on one patch of haze), and
    a set is joined on time and filters alone, as before the pointing rule. radius_km: the target's radius (None:
    unknown, the place kept); ifov: radians per full resolution px."""
    if place is None or place[0] is None or not radius_km or len(place) < 3 or not place[2] or place[2] <= 0:
        return place
    return None if (place[0] ** 2 + place[1] ** 2) ** 0.5 + HALF_DIAGONAL < radius_km / (place[2] * ifov) else place


def moved(a, b):
    """True when SPICE puts two frames more than SET_PLACE px apart (a, b: (x, y, range km) or None); False when
    either has no place. The places are compared on the ground: the body's centre is off a close-up by tens of
    thousands of px, and a range change of a few percent between filters moves it by thousands though the camera
    keeps looking at the same ground (Titan, N1616821718_1). So a's offset is scaled to b's range before they are
    compared (offset x range is the ground's sky-plane distance from the centre, which stays put)."""
    if a is None or b is None or a[0] is None or b[0] is None:
        return False
    k = a[2] / b[2] if len(a) > 2 and len(b) > 2 and a[2] and b[2] else 1.0
    return ((a[0] * k - b[0]) ** 2 + (a[1] * k - b[1]) ** 2) ** 0.5 > SET_PLACE


def channels(filters, nms, times=None):
    """(kind, positions of the red, green and blue channels in filters) of a set: "true", "false" or "two" (two
    positions, longer wavelength first). nms: each filter's effective wavelength, in the same order. times: when
    each was taken; a filter's channel is then its frame nearest in time to a frame of another filter (a run of
    repeat exposures ends next to the next filter: Titan N1574127426_1, CB3 three times 105 s apart, then MT1),
    else its first frame. The repeats around a channel are stacked into it (stacking.find_repeats)."""
    at = {}
    for j, f in enumerate(filters):
        if times is None:
            at.setdefault(f, j)
            continue
        gap = min((abs(times[j] - times[i]) for i, g in enumerate(filters) if g != f), default=0.0)
        if f not in at or gap < at[f][1]:
            at[f] = (j, gap)
    if times is not None:
        at = {f: j for f, (j, _) in at.items()}
    red = next((f for f in TRUE_REDS if f in at), None)
    blue = next((f for f in TRUE_BLUES if f in at), None)
    if red and "GRN" in at and blue:
        return "true", [at[red], at["GRN"], at[blue]]
    fs = list(at)
    w = [at[fs[k]] for k in nearest_visible(fs, [nms[at[f]] for f in fs])]
    return ("false", w) if len(w) >= 3 else ("two", w)


def filter_sets(cams, targets, obs, f1s, f2s, t, nm, places=None):
    """Every filter set of the frames given as columns, in time order (cams "ISSNA"/"ISSWA" or "N"/"W"; nm(q):
    frame q's effective wavelength; places: where SPICE puts each frame, (x, y, ...) or None, or None for none):
    (set of each frame, -1 outside any, and the sets, each {"kind", "use" (its channels' frame positions), "rows",
    "filters", "ready" (when its last channel was taken)})."""
    colour = {pair: colour_filter(*pair) for pair in set(zip(f1s, f2s))}
    fs = [colour[a, b] for a, b in zip(f1s, f2s)]
    set_of, sets = [-1] * len(fs), []
    cols = (cams, targets, obs, fs, t) if places is None else (cams, targets, obs, fs, t, places)
    for at in runs(list(zip(*cols))):
        kind, use = channels([fs[q] for q in at], [nm(q) for q in at], [t[q] for q in at])
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
    t, ids = idx["seconds_1970"].to_numpy(), idx["id"].to_numpy()
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
            if u.get("off"):   # (frames obs_mosaic._drop_strays took out of the pass are in none)
                mine = mine[~np.isin(ids[mine], list(u["off"]))]
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
    # repeats and pointings (REPEAT_GAP, SET_PLACE): the sets whose channels changed from the rule before them (no
    # repeat exposures in a set, no pointing), named by their channels' ids, for a remake of their composites
    keep = globals()["REPEAT_MAX"]
    globals()["REPEAT_MAX"] = 0
    try:
        _, before = filter_sets(idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist(),
                                idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(),
                                idx["seconds_1970"].tolist(), lambda q: reel.wavelength(idx["INSTRUMENT_ID"].iat[q],
                                                                                      idx["filter1"].iat[q] + idx["filter2"].iat[q]))
    finally:
        globals()["REPEAT_MAX"] = keep
    was = {tuple(b["use"]) for b in before}
    moved["set_rule"] = [[ids[q] for q in s["use"]] for s in sets if tuple(s["use"]) not in was]
    print(f"sets new or changed by the repeat and pointing rule: {len(moved['set_rule'])}", flush=True)
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
        # tracks (obs_mosaic._judge): passes following a moving feature play as movies; what they were before
        tracks, keep = [], obs_mosaic.TRACK_VISITS
        for p in passes:
            u = next(v for v in obs_mosaic.units(*p["key"][:3]) if v["key"] == p["key"])
            if not u.get("track"):
                continue
            old = dict(u)
            obs_mosaic.TRACK_VISITS = 10 ** 9
            try:
                obs_mosaic._judge(old)
            finally:
                obs_mosaic.TRACK_VISITS = keep
            tracks.append({"key": list(p["key"]), "was": old["kind"], "first": ids[p["rows"][0]], "last": ids[p["rows"][1]], "frames": p["frames"]})
        moved["track_passes"] = tracks
        was = {}
        for x in tracks:
            was[x["was"]] = was.get(x["was"], 0) + 1
        print(f"passes now played as tracks (movies): {len(tracks)}, before {was}", flush=True)
        # the passes pass_benchmarks.json names: what Auto calls them now against what they should be
        bench = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pass_benchmarks.json")))["passes"]
        for b in bench:
            us = obs_mosaic.units(b["target"], b["obs"], b["cam"])
            print(f"benchmark {b['obs']} {b['cam']}: expect {b['expect']}, now {[v['kind'] for v in us]}"
                  f"{' (track)' if any(v.get('track') for v in us) else ''}", flush=True)
    if args.moved:
        json.dump(moved, open(args.moved, "w"), indent=1)


if __name__ == "__main__":
    main()
