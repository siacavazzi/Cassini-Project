#!/usr/bin/env python3
"""Mosaic scan (read-only): every pass of the mission through the checkout's obs_mosaic rules (units splitting,
_judge), plus motion features to tell movies from mosaics, and a replay of layout()/view_rect() tile by tile to
find where the window's picture would restart. No images are read. From the mosaic reliability investigation
(2026-10-22); works on checkouts before and after the whole-footprint view (obs_mosaic.FIT gone) and the movie
test (u["movie"]). Usage:
  REPO=~/dev/Cassini-Project CASSINI_GEOMETRY_CACHE=... python web/frames/mosaic_scan.py OUTDIR [PLANS_DIR]"""
import os, sys, json, math, re, collections, sqlite3
import numpy as np
REPO = os.path.expanduser(os.environ.get("REPO", "~/dev/Cassini-Project"))
sys.path.insert(0, os.path.join(REPO, "web/frames"))
import reel, obs_mosaic as om, mosaic, mosaic_benchmark  # noqa

out_dir = sys.argv[1]; plans_dir = sys.argv[2] if len(sys.argv) > 2 else None
os.makedirs(out_dir, exist_ok=True)
idx, _ = reel.load_index()
db = sqlite3.connect(os.environ["CASSINI_GEOMETRY_CACHE"])
G = {f: (x, y, z, a) for f, x, y, z, a in db.execute("SELECT frame,x,y,z,angle FROM target WHERE version=1 AND error IS NULL")}
print("geometry rows", len(G), flush=True)
SKIP = {"SKY", "UNK", "NONE", "DARK", "STAR", "PLAQUE", "CAL_LAMPS"}
FR = om.FRAME
MOVIE = re.compile(r"MOVIE|MOV\d|1X1|STARE|NAV|OPNAV|MONITOR|AZSCAN|SPKMV|ROTMOV|TRACK|OCC")
MOSAIC = re.compile(r"MOSAIC|MOS\d|\dX\d|GLOBMAP|REGMAP|MAP|HIRES|HIGHRES|SCAN|COMBINED|GLOCOL|LIMB|PORTRAIT|FP\d")


def build_units(rows, target, obs, cam):
    """obs_mosaic.units() over these rows, verbatim logic, geometry from G."""
    inst = "ISSNA" if cam == "N" else "ISSWA"
    out, cur, last = [], None, {}
    for r in rows:
        f1, f2 = str(r.filter1), str(r.filter2)
        f = "/".join(x for x in (f1, f2) if not x.startswith("CL")) or "CL1/CL2"
        g = G.get(r.id); g = g and g[:3]
        t = float(r.seconds_1970)
        if cur is None or t - cur["last"] > om.GAP or (g and cur["z"] and not 1 / om.ZOOM < g[2] / cur["z"] < om.ZOOM):
            cur = {"frames": [], "z": g and g[2], "last": t, "raw": 0}
            out.append(cur); last = {}
        cur["last"] = t; cur["raw"] += 1
        if not cur["z"] and g:
            cur["z"] = g[2]
        if f in last and t - last[f] <= mosaic_benchmark.REPEAT_GAP:
            continue
        last[f] = t
        cur["frames"].append((r.path, r.id, f, t, reel.wavelength(inst, f1 + f2), *(g or (None, None, None))))
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        om._judge(u)
    return out


def colour_of(frames):
    """plan()'s colour / grey choice, verbatim."""
    count, nms = {}, {}
    for fr in frames:
        count[fr[2]] = count.get(fr[2], 0) + 1; nms[fr[2]] = fr[4]
    most = max(count.values())
    good = [f for f in count if count[f] >= most / 4 and not om._polarizer(f)]
    blue = next((b for b in reel.TRUE_BLUES if b in good), None)
    reds = [f for f in good if "/" not in f and not f.startswith("MT") and nms[f] > 600]
    red = "RED" if "RED" in good else min(reds, key=lambda f: abs(nms[f] - 650)) if reds else None
    common = sorted([f for f in count if count[f] >= most / 2 and not om._polarizer(f)], key=lambda f: -nms[f])
    if blue and red and "GRN" in good:
        colour = [red, "GRN", blue]
    else:
        colour = [common[0], common[len(common) // 2], common[-1]] if len(common) >= 3 else None
    return colour, max(count, key=count.get)


def plan_geom(u, angle):
    """plan()'s footprint / fixed / view from the geometry, for a given rotation (radians)."""
    c, s = math.cos(angle), math.sin(angle)
    pts, ks = [], []
    for *_, x, y, z in u["frames"]:
        if z:
            k = z / u["z"]; pts.append(((c * -x - s * -y) * k, (s * -x + c * -y) * k)); ks.append(k)
    x0 = min(p[0] - om.HALF * k for p, k in zip(pts, ks)); x1 = max(p[0] + om.HALF * k for p, k in zip(pts, ks))
    y0 = min(p[1] - om.HALF * k for p, k in zip(pts, ks)); y1 = max(p[1] + om.HALF * k for p, k in zip(pts, ks))
    if hasattr(om, "FIT"):   # before the whole-footprint view: a window following the newest tile on wide passes
        fixed = u["whole"] or max(x1 - x0, y1 - y0) <= om.FIT * FR
        view = [x1 - x0, y1 - y0] if fixed else [min(x1 - x0, om.FOLLOW * FR), min(y1 - y0, om.FOLLOW * FR)]
    else:
        fixed, view = True, [x1 - x0, y1 - y0]
    return {"footprint": [x0, y0, x1, y1], "fixed": bool(fixed), "view": view, "k": om.CANVAS / max(view)}, (c, s)


def replay(u, p, cs):
    """layout() tile by tile with tiles placed where SPICE put them (offset = rotated, scaled body shift).
    Returns events where the drawn picture loses most of what it showed."""
    c, s = cs
    tiles, events, prev, prev_used, prev_rect = [], [], set(), None, None
    colour, grey = p["colour"], p["grey"]
    for j, (path, fid, f, t, nm, x, y, z) in enumerate(u["frames"]):
        tl = {"n": j, "filter": f}
        if z:
            k = z / u["z"]; tl["offset"] = [(c * -x - s * -y) * k, (s * -x + c * -y) * k]
        tiles.append(tl)
        rect = om.view_rect(p, tiles)
        count = collections.Counter(t2["filter"] for t2 in tiles if "offset" in t2)
        if not count:
            continue
        used = colour if colour and all(count.get(f2) for f2 in colour) else [grey if count.get(grey) else max(count, key=count.get)]
        rx, ry, rw, rh = rect
        def inview(t2):
            ox, oy = t2["offset"]; return rx - FR / 2 < ox < rx + rw + FR / 2 and ry - FR / 2 < oy < ry + rh + FR / 2
        per = [{t2["n"] for t2 in tiles if "offset" in t2 and t2["filter"] == f2 and inview(t2)} for f2 in used]
        if len(used) == 3:   # only where all three have the picture: approximate by places shared (within half a frame)
            drawn = per[0]   # tiles of the red filter that have the others near them
            others = [[tiles[m]["offset"] for m in q] for q in per[1:]]
            drawn = {m for m in per[0] if all(any(abs(tiles[m]["offset"][0] - o[0]) < FR / 2 and abs(tiles[m]["offset"][1] - o[1]) < FR / 2 for o in oo) for oo in others)}
            # place keys so drawn sets compare across filters
        else:
            drawn = per[0]
        places = {(round(tiles[m]["offset"][0] / (FR / 2)), round(tiles[m]["offset"][1] / (FR / 2))) for m in drawn}
        if len(prev) >= 3 and len(places & prev) <= 0.5 * len(prev):
            why = ("colour switch (grey -> 3-filter overlap)" if prev_used and len(prev_used) == 1 and len(used) == 3 else
                   "grey filter switch" if prev_used != used else
                   "follow window stepped" if rect != prev_rect else "other")
            events.append({"tile": j, "id": fid, "t": t, "why": why, "before": len(prev), "kept": len(places & prev),
                           "after": len(places), "label_tiles": sum(count[f2] for f2 in used),
                           "label_of": sum(1 for fr in u["frames"] if fr[2] in used)})
        prev, prev_used, prev_rect = places, used, rect
    return events


def motion(u):
    """Steps between consecutive frames of one filter (frames of a frame, at the reference distance)."""
    byf = collections.defaultdict(list)
    for *_, f, t, nm, x, y, z in [(fr[0], fr[1], fr[2], fr[3], fr[4], fr[5], fr[6], fr[7]) for fr in u["frames"]]:
        if z:
            byf[f].append((-x * z / u["z"] / FR, -y * z / u["z"] / FR, t))
    steps = []
    for f, ps in byf.items():
        for a, b in zip(ps, ps[1:]):
            steps.append(max(abs(a[0] - b[0]), abs(a[1] - b[1])))
    steps = np.array(steps) if steps else np.zeros(0)
    allp = np.array([(-fr[5] * fr[7] / u["z"] / FR, -fr[6] * fr[7] / u["z"] / FR) for fr in u["frames"] if fr[7]])
    span = float((allp.max(0) - allp.min(0)).max()) if len(allp) else 0.0
    # straightness: a body drifting across a staring camera moves along a line; a raster comes back
    path = float(np.abs(np.diff(allp, axis=0)).max(1).sum()) if len(allp) > 1 else 0.0
    return {"steps": len(steps), "jump_frac": float((steps >= mosaic.min_step).mean()) if len(steps) else 0.0,
            "creep_frac": float(((steps > 0.01) & (steps < mosaic.min_step)).mean()) if len(steps) else 0.0,
            "median_step": float(np.median(steps)) if len(steps) else 0.0, "span_frames": span,
            "straight": span / path if path > 0 else 1.0, "filters": len(byf),
            "per_filter_max": max((len(v) for v in byf.values()), default=0)}


def verdict(m, u):
    """Movie or mosaic, from the pointing alone. A mosaic steps the camera a big share of a frame between tiles of
    one filter; a movie (stare, drift) moves a little between frames and only adds up to 'places' over time."""
    if m["jump_frac"] >= 0.3:
        return "mosaic"
    if m["creep_frac"] >= 0.5 or m["median_step"] < mosaic.min_step:
        return "movie"
    return "unclear"


plans = {}
if plans_dir and os.path.isdir(plans_dir):
    for fn in os.listdir(plans_dir):
        if fn.endswith(".json"):
            try:
                pj = json.load(open(os.path.join(plans_dir, fn))); plans[tuple(pj["key"])] = pj
            except Exception:
                pass
print("plans", len(plans), flush=True)

rows_out, events_out = [], []
cols = ["path", "id", "filter1", "filter2", "seconds_1970", "TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"]
sub = idx[~idx["TARGET_NAME"].isin(SKIP)][cols]
for (target, obs, inst), g in sub.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False):
    if inst not in ("ISSNA", "ISSWA"):
        continue
    cam = "N" if inst == "ISSNA" else "W"
    us = build_units(list(g.itertuples(index=False)), target, obs, cam)
    nmos = sum(u["mosaic"] for u in us)
    for u in us:
        placed = [fr for fr in u["frames"] if fr[7]]
        r = {"target": target, "obs": obs, "cam": cam, "pass": u["key"][3], "passes_in_obs": len(us),
             "mosaic_passes_in_obs": nmos, "frames": u["raw"], "tiles": len(u["frames"]), "placed": len(placed),
             "start": u["frames"][0][3], "first_id": u["frames"][0][1], "mosaic": u["mosaic"], "whole": u["whole"],
             "name_hint": "movie" if MOVIE.search(obs) else "mosaic" if MOSAIC.search(obs) else "",
             "movie": u.get("movie")}
        if len(placed) >= 2:
            m = motion(u); r.update(m); r["verdict"] = verdict(m, u)
        if u["mosaic"]:
            pj = plans.get(u["key"])
            angle = pj["angle"] if pj else 0.0
            pg, cs = plan_geom(u, angle)
            colour, grey = colour_of(u["frames"])
            p = {**pg, "colour": pj["colour"] if pj else colour, "grey": pj["grey"] if pj else grey}
            if pj:
                p.update({k: pj[k] for k in ("footprint", "fixed", "view", "k")})
            r.update({"fixed": p["fixed"], "k": round(p["k"], 4), "view_frames": round(max(p["view"]) / FR, 2),
                      "foot_frames": round(max(p["footprint"][2] - p["footprint"][0], p["footprint"][3] - p["footprint"][1]) / FR, 2),
                      "colour": "/".join(p["colour"] or []), "grey": p["grey"], "from_plan": bool(pj)})
            ev = replay(u, p, cs)
            r["resets"] = len(ev)
            for e in ev:
                events_out.append({"target": target, "obs": obs, "cam": cam, "pass": u["key"][3], **e})
        rows_out.append(r)

import pandas as pd
df = pd.DataFrame(rows_out); ev = pd.DataFrame(events_out)
df.to_csv(os.path.join(out_dir, "passes.csv"), index=False); ev.to_csv(os.path.join(out_dir, "resets.csv"), index=False)
L = []
P = lambda *a: L.append(" ".join(str(x) for x in a))
P("passes", len(df), "mosaic passes", int(df.mosaic.sum()), "frames in mosaic passes", int(df[df.mosaic].frames.sum()))
P("mosaic passes the pointing test calls movies:", int((df.mosaic & (df.verdict == "movie")).sum()),
  "| passes obs_mosaic calls movies:", int((df.movie == True).sum()) if "movie" in df else "n/a")  # noqa: E712
m = df[df.mosaic]
P("\nmosaic passes by target:\n", m.target.value_counts().head(15).to_string())
P("\nmosaic passes by pointing verdict:\n", m.verdict.value_counts(dropna=False).to_string())
P("\nby verdict x camera:\n", pd.crosstab(m.verdict.fillna("?"), m.cam).to_string())
P("\nby verdict x name hint:\n", pd.crosstab(m.verdict.fillna("?"), m.name_hint).to_string())
P("\nnon-mosaic passes with verdict mosaic (missed?):", int(((~df.mosaic) & (df.verdict == "mosaic") & (df.tiles >= 3)).sum()))
miss = df[(~df.mosaic) & (df.verdict == "mosaic") & (df.tiles >= 3)]
P(" of which footprint >= 16 frames:", int((miss.span_frames + 1 >= om.MAX_FRAMES).sum()))
P("\nno geometry at all (never a mosaic):", int((df.placed == 0).sum()), "passes,", int(df[df.placed == 0].frames.sum()), "frames")
P("\nfixed vs follow among mosaics:\n", m.fixed.value_counts().to_string())
P("\nrestart events:", len(ev), "| follow window steps:", int((ev.why == "follow window stepped").sum()) if len(ev) else 0)
P("\nmosaic passes with at least one restart:", int((m.resets > 0).sum()), "of", len(m))
if len(ev):
    P("\nrestart events by cause:\n", ev.why.value_counts().to_string())
    P("\nrestart events by cause x cam:\n", pd.crosstab(ev.why, ev.cam).to_string())
P("\nobservations split into >1 mosaic pass:", int(m.groupby(["target", "obs", "cam"]).size().gt(1).sum()))
for v in ("movie", "mosaic", "unclear"):
    P(f"\nexamples verdict={v} (biggest):\n", m[m.verdict == v].sort_values("tiles", ascending=False).head(12)[
        ["target", "obs", "cam", "pass", "first_id", "tiles", "jump_frac", "creep_frac", "median_step", "span_frames", "fixed"]].to_string())
if len(ev):
    w = ev[(ev.cam == "W") & (ev.label_of.between(15, 19))]
    P("\nWAC restarts in passes whose label says ~17 tiles:\n", w.head(40).to_string())
open(os.path.join(out_dir, "summary.txt"), "w").write("\n".join(L))
print("\n".join(L))
