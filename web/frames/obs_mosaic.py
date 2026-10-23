#!/usr/bin/env python3
"""
Observation mosaics for the camera windows: when Cassini steps a camera across a body a tile at a
time, the window shows every tile of that pass taken so far, all filters, made like the mosaic
benchmark (web/frames/mosaic_benchmark.py), rather than the reel's rolling window of a few tiles.

A pass (a "unit") is the frames of one camera, one target and one OBSERVATION_ID, split where
the camera pauses more than GAP or the distance to the body changes by more than ZOOM since the
pass began. It is a mosaic when the geometry cache puts its frames at three or more places (at
least mosaic.min_step of a frame apart, once scaled to one distance), its footprint is less than
MAX_FRAMES frames across, and the camera jumps rather than creeps: a movie (a stare, a ring or
storm movie, a moon turning) drifts a little between frames until the drift adds up to "three
places", so a pass whose steps between frames of one filter are at least mosaic.min_step of a
frame less than MOVIE_JUMPS of the time (or that never takes a filter twice), or whose camera stays
MOVIE_DWELL frames of one filter at each place (counting repeat exposures), is a movie, and plays
as frames (no mosaic of any kind) unless the person asks for its mosaic.
Overlap is not required: SPICE places every tile.

Every tile goes through color_image.processed_frame (repeat exposures merged in I/F, calibrated,
centred north up by SPICE) on one display scale for the pass (mosaic_benchmark.display_scale) and
is scaled to the pass's reference distance, so a flyby's tiles keep one km per pixel as Cassini
closes in. Tiles are made when first needed, oldest first, and kept in the cache.

The view: the whole footprint, scaled to fit, worked out once from the geometry cache (so it does
not move or rescale as the mosaic grows, and a tile once drawn never leaves the picture). The mosaic "so far" at a frame is every tile up to it, each
filter drawn by mosaic.compose (calibrated, none pinned) over its own earlier tiles; three or more
filters make false colour (longest wavelength red, middle green, shortest blue, only where all
three have the picture), otherwise the best covered filter in grey. Different filters are never
blended into one another.

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/obs_mosaic.py W1537023863_1 --cache DIR [--all]
  (makes the pass the frame is in ahead of time; the frame server makes it on first request)
"""
import argparse
import collections
import concurrent.futures
import contextlib
import hashlib
import io
import json
import math
import os
import sys
import threading
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reel  # noqa: E402  (puts the repo on the path)
import color_image  # noqa: E402
import calibration  # noqa: E402
import mosaic  # noqa: E402
import mosaic_benchmark  # noqa: E402
import stacking  # noqa: E402

# bumped whenever the way observation mosaics are made changes, so older ones are not served again; one per
# look (calibration.LOOKS), classic being the mosaics made before the balanced display model
VERSIONS = {"balanced": "obs-v13", "classic": "obs-v13-classic"}
CANVAS = 2048        # longest side of the canvas the view is drawn on
OUT = 1024           # longest side of the picture sent
FRAME = 1024         # full resolution frame
HALF = 724           # half the side of a north-up frame's canvas (its diagonal)
GAP = 1800           # seconds without a frame that end a pass (mosaic.max_gap)
ZOOM = 1.4           # change in distance that ends a pass (tiles closer than this are rescaled)
MIN_PLACES = 3       # pointings a pass needs to be a mosaic
MAX_FRAMES = 16      # footprints wider than this many frames stay rolling mosaics
MOVIE_JUMPS = 0.3    # a pass whose same-filter steps jump (mosaic.min_step) less often than this is a movie
MOVIE_FIT = 2.0      # a pass played as a movie shows its whole footprint up to this many frames across, else a
                     # window this wide following the frame, at one scale for the whole pass
MOVIE_MARGIN = 0.15  # of a frame, round a movie's footprint
CENTRE_MARGIN = 0.2  # of the body's diameter, round its disk in a movie centred on it
MOVIE_SAMPLES = 6    # tiles a movie's footprint is measured on
TRAIL = 12           # most earlier frames a movie's rolling trail keeps under the newest
SCALE_FRAMES = 96    # most frames the pass's display scale is measured on (evenly spread over a long movie)
LAP_GAP = 7200       # a mosaic taken again over the same ground within this many seconds is its next lap
LAP_OVERLAP = 0.6    # ... when the two footprints share at least this much (area both cover / either covers)
MOVIE_LAPS = 2       # a mosaic whose places are taken again (median, per filter) this many times is a mosaic movie
MOVIE_DWELL = 8      # ... or whose camera stays this many frames of one filter (median) at each place it goes
RADIUS = {"SATURN": 60268, "JUPITER": 69911, "TITAN": 2575, "RHEA": 764, "IAPETUS": 735, "DIONE": 561,
          "TETHYS": 531, "ENCELADUS": 252, "MIMAS": 198, "HYPERION": 135, "PHOEBE": 107}
IFOV = {"N": 6.0e-6, "W": 60e-6}   # radians per full resolution pixel

_units = {}           # (target, obs, cam) -> [unit dicts]
_lock = threading.Lock()
_unit_locks = {}
_warming = set()
_background = threading.Semaphore(1)   # background work (passes made ahead) runs one at a time, so it never
                                       # crowds out what a window is waiting for
_upto, _from = {}, {}   # a pass being made ahead: the last tile to make, the first mosaic to make
_tile_locks = {}      # (pass key, tile) -> its lock
_making = {}          # path of a mosaic being made -> its lock, so two requests for it make it once


def _row_of():
    idx, _ = reel.load_index()
    with _lock:
        if not hasattr(_row_of, "row"):
            _row_of.row = dict(zip(idx["id"], range(len(idx))))
    return idx, _row_of.row


def units(target, obs, cam):
    """The passes of one camera's frames of one observation: [{key, frames: [(path, id, filter, t, nm, x, y, z)],
    mosaic, whole, z, last, repeat_gap}] in time order, from the index and the geometry cache. Repeat exposures
    (the same filter within the pass's repeat_gap) are left out, as stacking.load_hdr merges them in. repeat_gap
    is REPEAT_GAP, except in a movie that takes a filter more often than that (a spoke movie every 11 s): there it
    is half the movie's own pace, so every frame of the movie is its own picture rather than stacked with the
    next ones (repeat_window)."""
    with _lock:
        if (target, obs, cam) in _units:
            return _units[(target, obs, cam)]
    idx, _ = reel.load_index()
    inst = "ISSNA" if cam == "N" else "ISSWA"
    rows = idx[(idx["OBSERVATION_ID"] == obs) & (idx["TARGET_NAME"] == target) & (idx["INSTRUMENT_ID"] == inst)]
    where = reel.geometry(rows["id"].tolist())
    out, cur, last = [], None, {}
    for r in rows.itertuples(index=False):
        f1, f2 = str(r.filter1), str(r.filter2)
        f = "/".join(x for x in (f1, f2) if not x.startswith("CL")) or "CL1/CL2"
        g = where.get(r.id)
        t = float(r.seconds_1970)
        if cur is None or t - cur["last"] > GAP or (g and cur["z"] and not 1 / ZOOM < g[2] / cur["z"] < ZOOM):
            cur = {"frames": [], "all": [], "taken": [], "z": g and g[2], "last": t}
            out.append(cur)
            last = {}
        cur["last"] = t
        cur["taken"].append((f, *(g or (None, None, None))))   # every frame, repeats too, for _judge
        if not cur["z"] and g:
            cur["z"] = g[2]
        cur["all"].append((r.path, r.id, f, t, reel.wavelength(inst, f1 + f2), *(g or (None, None, None))))
        if f in last and t - last[f] <= mosaic_benchmark.REPEAT_GAP:
            continue
        last[f] = t
        cur["frames"].append((r.path, r.id, f, t, reel.wavelength(inst, f1 + f2), *(g or (None, None, None))))
    # laps: a mosaic taken again over the same places after a pause longer than GAP (the Jupiter approach's 2x2
    # color mosaics, six laps 74 minutes apart in one observation) is one pass, a mosaic movie, rather than a
    # mosaic that starts again from nothing every lap
    laps = []
    for u in out:
        u["key"] = (target, obs, cam, len(laps))
        _judge(u)
        prev = laps[-1] if laps else None
        if (prev and prev["mosaic"] and u["mosaic"] and u["frames"][0][3] - prev["last"] <= LAP_GAP and u["z"]
                and 1 / ZOOM < u["z"] / prev["z"] < ZOOM and _overlap(prev, u) >= LAP_OVERLAP):
            for k in ("frames", "all", "taken"):
                prev[k] += u[k]
            prev["last"] = u["last"]
            _judge(prev)
        else:
            laps.append(u)
    out = laps
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        _judge(u)
        u["repeat_gap"] = repeat_window(u)
        if u["repeat_gap"] < mosaic_benchmark.REPEAT_GAP:
            u["frames"], last = [], {}
            for fr in u["all"]:
                if fr[2] in last and fr[3] - last[fr[2]] <= u["repeat_gap"]:
                    continue
                last[fr[2]] = fr[3]
                u["frames"].append(fr)
        del u["all"]
    with _lock:
        _units[(target, obs, cam)] = out
    return out


def _box(u, z):
    """The footprint of pass u's placed frames (x0, y0, x1, y1, reference pixels at distance z from the body's centre)."""
    pts = [(-x * fz / z, -y * fz / z) for *_, x, y, fz in u["frames"] if fz]
    if not pts:
        return None
    pts = np.array(pts)
    return (*(pts.min(0) - HALF), *(pts.max(0) + HALF))


def _overlap(a, b):
    """How much the footprints of passes a and b cover the same ground: area both cover over area either covers."""
    p, q = _box(a, a["z"]), _box(b, a["z"])
    if not p or not q:
        return 0.0
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    both = max(w, 0) * max(h, 0)
    either = (p[2] - p[0]) * (p[3] - p[1]) + (q[2] - q[0]) * (q[3] - q[1]) - both
    return both / either if either > 0 else 0.0


def repeat_window(u):
    """How close two frames of one filter must be for stacking to merge them as repeat exposures, for pass u:
    REPEAT_GAP, or in a movie (u["movie"]) whose same-filter frames come more often than twice that, half the
    median time between them, so the movie's frames are not stacked into one another (which blurs what moves
    and puts later frames into earlier ones)."""
    if not u.get("movie"):
        return mosaic_benchmark.REPEAT_GAP
    last, gaps = {}, []
    for fr in u["all"]:
        if fr[2] in last:
            gaps.append(fr[3] - last[fr[2]])
        last[fr[2]] = fr[3]
    g = float(np.median(gaps)) if gaps else 2 * mosaic_benchmark.REPEAT_GAP
    return min(mosaic_benchmark.REPEAT_GAP, round(g / 2, 1)) if g < 2 * mosaic_benchmark.REPEAT_GAP else mosaic_benchmark.REPEAT_GAP


def _judge(u):
    """Sets u["movie"] (the camera creeps or stares), u["jump_frac"], u["dwell"], u["mosaic"] (enough places,
    footprint not too big, not a movie), u["whole"] (the body's disk inside it), u["place"], u["repeats"] and
    u["kind"]: "movie", "mosaic", "mosaic_movie" (a mosaic whose places are taken lap after lap) or None."""
    pts = [(-x * z / u["z"], -y * z / u["z"]) for _, _, _, _, _, x, y, z in u["frames"] if z]
    # the steps between consecutive frames of one filter, in frames: a mosaic jumps, a movie creeps
    last, steps = {}, []
    for _, _, f, _, _, x, y, z in u["frames"]:
        if z:
            p = (-x * z / u["z"], -y * z / u["z"])
            if f in last:
                steps.append(max(abs(p[0] - last[f][0]), abs(p[1] - last[f][1])) / FRAME)
            last[f] = p
    # no filter taken twice (a stare cycling its filters): every filter's mosaic would be one frame, so it plays
    # as frames too
    u["jump_frac"] = float(np.mean([s >= mosaic.min_step for s in steps])) if steps else 0.0 if len(pts) > 1 else None
    # dwell: over every frame taken (repeat exposures too, which the tiles merge), how many frames of one filter
    # the camera takes at a place before it jumps. A raster takes one to a few per pointing; a movie films the
    # same field for minutes (a spoke movie going back and forth between two patches of ring, one frame every
    # 11 s, looks like a jump every tile once its repeats are merged)
    last, runs = {}, []
    for f, x, y, z in u.get("taken", ()):
        if not z:
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        if f in last and max(abs(p[0] - last[f][0][0]), abs(p[1] - last[f][0][1])) < mosaic.min_step * FRAME:
            last[f] = [p, last[f][1] + 1]   # from the frame before, so a field drifting slowly stays one place
        else:
            if f in last:
                runs.append(last[f][1])
            last[f] = [p, 1]
    runs += [n for _, n in last.values()]
    u["dwell"] = float(np.median(runs)) if runs else None
    u["movie"] = u["jump_frac"] is not None and (u["jump_frac"] < MOVIE_JUMPS or (u["dwell"] or 0) >= MOVIE_DWELL)
    places = []
    for p in pts:
        if all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= mosaic.min_step * FRAME for q in places):
            places.append(p)
    # u["place"]: for each of u["frames"], the place it was taken at (index into places; None when SPICE has no
    # place for it). visits: how many separate times the camera comes back to a place in one filter; a mosaic
    # takes each place once per filter, a mosaic movie goes round the same places again and again (laps)
    u["place"], runs = [], {}
    for _, _, f, _, _, x, y, z in u["frames"]:
        if not z:
            u["place"].append(None)
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        i = min(range(len(places)), key=lambda j: max(abs(p[0] - places[j][0]), abs(p[1] - places[j][1])))
        u["place"].append(i)
        seq = runs.setdefault(f, [])
        if not seq or seq[-1] != i:
            seq.append(i)
    visits = [max(seq.count(i) for seq in runs.values()) for i in range(len(places))] if runs else []
    u["repeats"] = int(np.median(visits)) if visits else 0
    # (a pan along a ring, where every frame shows nearly the same rings, looks like a movie, but a pan across the
    # rings is a good strip mosaic, and the pointing alone cannot tell them apart: the window's chip decides those)
    u["mosaic"] = u["whole"] = False
    u["kind"] = "movie" if u["movie"] else None
    if len(places) < MIN_PLACES or u["movie"]:
        return
    pts = np.array(pts)
    lo, hi = pts.min(0) - FRAME / 2, pts.max(0) + FRAME / 2
    if (hi - lo).max() >= MAX_FRAMES * FRAME:
        return
    u["mosaic"] = True
    u["kind"] = "mosaic_movie" if len(places) >= 2 and u["repeats"] >= MOVIE_LAPS else "mosaic"
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    u["whole"] = bool(radius and (lo < -radius).all() and (hi > radius).all())


def unit_of(frame_id):
    """(unit, index of the newest tile at that frame) for the pass frame_id is in, or None."""
    idx, row = _row_of()
    q = row.get(frame_id)
    if q is None:
        return None
    r = idx.iloc[q]
    cam = "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"
    t = float(r["seconds_1970"])
    for u in units(r["TARGET_NAME"], r["OBSERVATION_ID"], cam):
        ts = [fr[3] for fr in u["frames"]]
        if ts and ts[0] <= t <= u["last"]:
            return u, sum(1 for x in ts if x <= t + 1) - 1
    return None


def kind_of(frame_id):
    """What the camera windows do with the frames of frame_id's observation (one camera): {"mosaic": its pass is
    a mosaic, "movie": every pass of the observation with the camera moving is a movie or a stare, so its frames
    never make a mosaic of any kind and the window need not ask, "kind": its pass's kind (mosaic, movie,
    mosaic_movie or None), "repeats": its laps}."""
    found = unit_of(frame_id)
    if not found:
        return {"mosaic": False, "movie": False, "kind": None}
    us = units(*found[0]["key"][:3])
    judged = [v for v in us if v["jump_frac"] is not None]
    return {"mosaic": bool(found[0]["mosaic"]), "movie": bool(judged) and all(v["movie"] for v in judged),
            "kind": found[0]["kind"], "repeats": found[0]["repeats"]}


def folder(u, cache):
    # a movie's frames stacked with a shorter repeat window are other pictures than the ones made before it
    gap = u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP)
    suffix = "" if gap >= mosaic_benchmark.REPEAT_GAP else f"_r{gap:g}"
    return os.path.join(cache, VERSIONS[calibration.look()], "_".join(map(str, u["key"])) + suffix)


def _ulock(u):
    with _lock:
        return _unit_locks.setdefault(u["key"], threading.RLock())


def plan(u, cache):
    """The pass's display scale, rotation, footprint, view mode and colour filters, worked out once and kept."""
    path = os.path.join(folder(u, cache), "plan.json")
    with _ulock(u):
        if os.path.exists(path):
            with open(path) as fh:
                return json.load(fh)
        frames = u["frames"]
        count, nms = {}, {}
        for fr in frames:
            count[fr[2]] = count.get(fr[2], 0) + 1
            nms[fr[2]] = fr[4]
        colour = colour_of(count, nms)
        # a long movie's scale from frames spread evenly over it, each filter's on its own (a step in time could
        # fall in step with the filter wheel and miss a filter): the same scale, without reading every frame first
        picks = []
        for f in count:
            mine = [fr for fr in frames if fr[2] == f]
            picks += mine[::max(1, math.ceil(len(mine) / SCALE_FRAMES))]
        scale = pass_scale(sorted(picks, key=frames.index), u, colour or [max(count, key=count.get)],
                           bool(colour and colour[1] == "GRN" and colour[2] in reel.TRUE_BLUES))
        # the rotation from the camera's frame to north up: the angle between where the geometry cache puts
        # the body and where processed_frame does, from the first tile placed well off the body's centre
        angle = 0.0
        for k, fr in enumerate(frames):
            if fr[7] and math.hypot(fr[5], fr[6]) > 200:
                rep = tile(u, k, cache, scale)
                if "native_offset" in rep:
                    fo = rep["native_offset"]
                    angle = math.atan2(fo[1], fo[0]) - math.atan2(-fr[6], -fr[5])
                    break
        c, s = math.cos(angle), math.sin(angle)
        pts, ks = [], []
        for *_, x, y, z in frames:
            if z:
                k = z / u["z"]
                pts.append(((c * -x - s * -y) * k, (s * -x + c * -y) * k))
                ks.append(k)
        if not pts:
            pts, ks = [(0.0, 0.0)], [1.0]
        x0 = min(p[0] - HALF * k for p, k in zip(pts, ks))
        x1 = max(p[0] + HALF * k for p, k in zip(pts, ks))
        y0 = min(p[1] - HALF * k for p, k in zip(pts, ks))
        y1 = max(p[1] + HALF * k for p, k in zip(pts, ks))
        view = [x1 - x0, y1 - y0]
        p = {"key": list(u["key"]), "display_scale": scale, "angle": angle, "footprint": [x0, y0, x1, y1],
             "fixed": True, "view": view, "k": CANVAS / max(view), "colour": colour,
             "grey": max(count, key=count.get), "whole": u["whole"]}
        reel._cached(path, lambda: json.dumps(p).encode())
        return p


# filter sets with a colour mapping of their own, looked up before the general rule in colour_of: frozenset of the
# pass's filters (as units() names them, e.g. "MT3", "CB2", "BL1") -> [red, green, blue] filters. Empty for now;
# the per-filter-set rules for false colour (color plan phase 2b) go here
COLOUR_SETS = {}


def colour_of(count, nms):
    """The pass's colour filters, [red, green, blue], or None for grey. count = tiles per filter, nms = each
    filter's wavelength. (Near) true colour when the pass takes GRN and a blue at a good share of its tiles, with
    RED or else the continuum filter nearest red (not a methane band); otherwise false colour from the filters
    taken at most tiles (longest wavelength red). Polarizers are left out (they are not a colour)."""
    most = max(count.values())
    good = [f for f in count if count[f] >= most / 4 and not _polarizer(f)]
    for filters, rgb in COLOUR_SETS.items():
        if filters <= set(good):
            return list(rgb)
    blue = next((b for b in reel.TRUE_BLUES if b in good), None)
    reds = [f for f in good if "/" not in f and not f.startswith("MT") and nms[f] > 600]
    red = "RED" if "RED" in good else min(reds, key=lambda f: abs(nms[f] - 650)) if reds else None
    common = sorted([f for f in count if count[f] >= most / 2 and not _polarizer(f)], key=lambda f: -nms[f])
    if blue and red and "GRN" in good:
        return [red, "GRN", blue]
    return [common[0], common[len(common) // 2], common[-1]] if len(common) >= 3 else None


def _polarizer(f):
    return any(p.startswith("IRP") or (p.startswith("P") and p[1:2].isdigit()) for p in f.split("/"))


FILLED = 0.5       # a pass is all body when the body's disk covers the middle of more than this share of its frames
DETAIL = 2.0       # filled passes: how much the local contrast is raised (detail())
DETAIL_SIGMA = 0.05  # ... over this much of a frame


def pass_scale(frames, u, drawn=None, true_colour=False):
    """The display scale of every tile of the pass (calibration.shared_scale over its frames merged in I/F, as
    mosaic_benchmark.display_scale): {"blacks": {filter: I/F}, "white": I/F, "gamma"}. Where the body fills
    the frames (the middle of most frames on its disk, as in Titan's maps), black goes to the darkest of the body, white to
    the 99.5th percentile and the gamma is eased, and the mosaic's local contrast is raised (detail), so
    the surface's few per cent of contrast shows; passes with dark sky keep the benchmark's scale.
    drawn = the filters the mosaic is drawn from (plan's colour, or its grey filter); true_colour = they are a
    true colour set."""
    by = {}
    for path, _, f, *_ in frames:
        _, iof, _ = stacking.load_hdr(path, u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP))
        if iof is not None:
            by.setdefault(f, []).append(iof[::4, ::4].astype(np.float32))
    if not by:
        return {"blacks": {}, "white": 1.0, "gamma": 3.0, "filled": False}
    scale = calibration.shared_scale(list(by.values()), 99.9, gamma=3.0)
    blacks, white = dict(zip(by, scale["blacks"])), scale["white"]
    # all body: the geometry cache puts the middle of most frames on the body's disk (a plume or limb pass of
    # mostly sky, however bright its scattered light, is not)
    radius = RADIUS.get(u["key"][0], 0) / IFOV[u["key"][2]]
    inside = [math.hypot(x, y) < radius / z for *_, x, y, z in frames if z]
    floor = float(np.mean(inside)) if inside else 0.0
    filled = floor > FILLED
    gamma = 3.0
    if filled and calibration.look() == "balanced":
        # The classic gamma 1.5 (a steeper curve lifts the dark end's noise and steps into view). True colour: one black and white for the filters drawn, so the colour is what they saw
        # rather than how differently each was stretched (black the darkest one's 1st percentile, at most half the
        # brightest's 99.5th, which is white: a black above the white would stretch noise into colour). False
        # colour (methane bands, UV, IR: no natural colour to keep) and grey: each filter's black its own 1st
        # percentile, so every band shows its own contrast, under one white (the widest band's): a white per band
        # would stretch a dim band's (MT2's) tile-to-tile errors several times over into coloured tiles
        lows = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 1)) for f, iofs in by.items()}
        tops = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 99.5)) for f, iofs in by.items()}
        mine = [f for f in (drawn or by) if f in by] or list(by)
        gamma = 1.5
        if true_colour:
            top = max(tops[f] for f in mine)
            black = min(min(lows[f] for f in mine), top / 2)
            blacks, white = {f: black for f in by}, top - black
        else:
            blacks, white = dict(lows), max(tops[f] - lows[f] for f in by)
    elif filled:
        blacks = {f: float(np.percentile(np.concatenate([i.ravel() for i in iofs]), 1)) for f, iofs in by.items()}
        white = max(float(np.percentile(np.concatenate([i.ravel() for i in iofs]) - blacks[f], 99.5))
                    for f, iofs in by.items())
        gamma = 1.5
    return {"blacks": blacks, "white": white, "gamma": gamma, "filled": filled, "floor": round(floor, 3)}


def tile(u, n, cache, scale=None):
    """Tile n of the pass, made once: its picture north up, scaled to the pass's reference distance and cropped
    (tiles/<n>.png), and its report: offset = where the frame's middle sits from the body's centre and box = the
    crop around it (reference pixels); no offset when SPICE could not place it."""
    base = os.path.join(folder(u, cache), "tiles", str(n))
    # one lock per tile, so a movie's frames made ahead can be made side by side
    with _lock:
        lock = _tile_locks.setdefault((u["key"], n), threading.RLock())
    with lock:
        if os.path.exists(base + ".json"):
            with open(base + ".json") as fh:
                return json.load(fh)
        if scale is None:
            scale = plan(u, cache)["display_scale"]
        path, fid, f, t, nm, x, y, z = u["frames"][n]
        k = z / u["z"] if z else 1.0
        try:
            image, _, rep = color_image.processed_frame([path], hdr=True,
                                                        scale={**scale, "blacks": [scale["blacks"].get(f, 0.0)]},
                                                        repeat_window=u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP))
        except Exception as e:
            image, rep = None, {"why": f"{type(e).__name__}: {e}"[:200]}
        out = {"n": n, "id": fid, "filter": f, "t": t, "stacked": rep.get("stacked"), "calibrated": rep.get("calibrated")}
        os.makedirs(os.path.dirname(base), exist_ok=True)
        if image is not None and "frame_offset" in rep:
            side = round(image.shape[0] * k)
            small = np.asarray(Image.fromarray(image).resize((side, side), Image.LANCZOS)) if side != image.shape[0] else image
            rows, cols = np.flatnonzero(small[..., 3].any(1)), np.flatnonzero(small[..., 3].any(0))
            if len(rows):
                a, b, c, d = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
                Image.fromarray(np.ascontiguousarray(small[a:b, c:d])).save(base + ".png", compress_level=1)
                out.update({"native_offset": rep["frame_offset"], "offset": [v * k for v in rep["frame_offset"]],
                            "box": [int(c) - side / 2, int(a) - side / 2, int(d - c), int(b - a)]})
        else:
            out["why"] = rep.get("why", "not placed by SPICE")
        reel._cached(base + ".json", lambda: json.dumps(out, default=str).encode())
        return out


def view_rect(p, tiles=None):
    """The view (x0, y0, w, h in reference pixels from the body's centre): the pass's whole footprint, the same
    for every tile, so what is drawn stays drawn."""
    x0, y0, x1, y1 = p["footprint"]
    return x0, y0, x1 - x0, y1 - y0


def _window(u, p, mine, rect, cache):
    """The tiles mine drawn on the view rect's canvas, one RGBA frame each, as mosaic.compose takes them:
    ([(frame, None, None, None)], the tiles that are in the view)."""
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)
    window, shown = [], []
    for t in mine:
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        if left >= W or top >= H or left + sw <= 0 or top + sh <= 0:
            continue
        part = _part(os.path.join(folder(u, cache), "tiles", f"{t['n']}.png"), sw, sh)
        frame = np.zeros((H, W, 4), np.uint8)
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
        frame[y0:y1, x0:x1] = part[y0 - top:y1 - top, x0 - left:x1 - left]
        window.append((frame, None, None, None))
        shown.append(t)
    return window, shown


SAME_PLACE = 0.25   # of a frame: tiles of different filters this close are the same pointing (seams)
# balanced look: solve the seams once per pointing on linear values (seams) instead of each filter on its own, as
# the classic look does. Off: on real passes it changed the faint sky's tile colours (Saturn's Shadow, the Jupiter
# approach mosaic's stray light) more often than it helped, and the gains it kept from collapsing to 0.909
# collapse evenly, which only dims a mosaic a little
SHARED_SEAMS = False


def seams(u, p, tiles, rect, ref, cache):
    """Balanced look: the seam correction of every pointing, solved once on the filter ref (the best covered of
    the filters drawn) on linear values, with the gains anchored (mosaic.seams, none pinned), for every filter's
    tile at that pointing, so the filters at one spot start from the same correction and keep their colour.
    {tile n: (gain, offset)}; a tile with no tile of ref at its pointing gets none. Kept in the cache."""
    mine = [t for t in tiles if t["filter"] == ref and "offset" in t]
    name = f"{ref.replace('/', '_')}-{len(mine)}-{'_'.join(str(round(v)) for v in rect)}.json"
    path = os.path.join(folder(u, cache), "seams", name)

    def make():
        window, shown = _window(u, p, mine, rect, cache)
        if len(window) < 2:
            return b"{}"
        with reel._mosaic_lock:
            gains, offsets = mosaic.seams([w[0] for w in window], None, p["display_scale"]["gamma"])
        return json.dumps({t["n"]: [float(g[0]), float(o[0])] for t, g, o in zip(shown, gains, offsets)}).encode()

    solved = {int(n): v for n, v in json.loads(reel._cached(path, make)).items()}
    by_n = {t["n"]: t for t in mine}
    out = {}
    for t in tiles:
        if "offset" not in t:
            continue
        if t["n"] in solved:
            out[t["n"]] = solved[t["n"]]
            continue
        # the tile of ref nearest this one's pointing, then nearest in time
        near = [(math.hypot(by_n[n]["offset"][0] - t["offset"][0], by_n[n]["offset"][1] - t["offset"][1]),
                 abs(by_n[n]["t"] - t["t"]), n) for n in solved]
        near = [x for x in near if x[0] <= SAME_PLACE * FRAME]
        if near:
            out[t["n"]] = solved[min(near)[2]]
    return out


GROW_FROM = 16   # tiles of one filter: a mosaic with more is the one before it with the new tile drawn over it


def _filter_path(u, f, count, rect, cache, solved_on=""):
    name = f"{f.replace('/', '_')}-{count}{solved_on}-{'_'.join(str(round(v)) for v in rect)}.png"
    return os.path.join(folder(u, cache), "filters-level", name)


def _png(rgba):
    out = io.BytesIO()
    Image.fromarray(rgba).save(out, "PNG", compress_level=1)
    return out.getvalue()


def _compose(window, k, **kw):
    """mosaic.compose on the view's canvas, with the benchmark's soft edge on its 0.5 scale canvas at this
    canvas's scale."""
    feather = mosaic.feather_px
    with reel._mosaic_lock:
        try:
            mosaic.feather_px = max(8, round(64 * k / 0.5))
            mosaic.reset()
            if kw.get("pin", -1) is None and "corrections" not in kw and "gamma" not in kw and len(window) > 1:
                # pinned to none, the seams' gains all sink together toward their limit as overlaps come in (the
                # data asks only that they agree), so a mosaic dimmed about 9% while it filled: their mean log is
                # held at 0 instead, so the pass keeps the level its scale gave it from the first tile to the last
                frames = [np.asarray(w[0]) for w in window]
                gains = mosaic.match_gains(frames, mosaic.calibrated_gain, None, mosaic.calibrated_overlap)
                gains = gains / np.exp(np.log(gains).mean(axis=0))
                kw = {**kw, "corrections": (gains, mosaic.match_offsets(frames, gains, None, mosaic.calibrated_overlap))}
            rgba = mosaic.compose(window, False, calibrated=True, **kw)
            mosaic.reset()
        finally:
            mosaic.feather_px = feather
    return rgba


_grown_last = collections.OrderedDict()   # path of a grown filter mosaic -> its RGBA, the few made last
GROWN_KEEP = 6


def _grown(u, p, f, mine, rect, cache):
    """The filter f's mosaic of mine (more than GROW_FROM tiles), grown a tile at a time: the mosaic of the
    tiles before the newest, as it was drawn, with the newest composed over it and matched to it (pin 0), so
    each new tile costs one tile's compose, not all of them again, and what is drawn stays as it was drawn.
    Only the newest tile's part of the canvas (and a margin for its soft edge) is composed, since nothing
    outside it changes. Starts from the largest of those mosaics already made (the first GROW_FROM tiles
    solved together otherwise) and keeps each one it makes on the way."""
    m = len(mine) - 1
    while m > GROW_FROM and _filter_path(u, f, m, rect, cache) not in _grown_last \
            and not os.path.exists(_filter_path(u, f, m, rect, cache)):
        m -= 1
    rgba = filter_mosaic(u, p, f, mine[:m], rect, cache).copy()
    k = p["k"]
    H, W = rgba.shape[:2]
    pad = max(8, round(64 * k / 0.5)) + 1
    for j in range(m, len(mine)):
        t = mine[j]
        bx, by, bw, bh = t["box"]
        left = round((t["offset"][0] + bx - rect[0]) * k)
        top = round((t["offset"][1] + by - rect[1]) * k)
        sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
        x0, y0 = max(left - pad, 0), max(top - pad, 0)
        x1, y1 = min(left + sw + pad, W), min(top + sh + pad, H)
        if x1 > x0 and y1 > y0:
            part = _part(os.path.join(folder(u, cache), "tiles", f"{t['n']}.png"), sw, sh)
            frame = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
            a0, b0 = max(left, 0), max(top, 0)
            a1, b1 = min(left + sw, W), min(top + sh, H)
            frame[b0 - y0:b1 - y0, a0 - x0:a1 - x0] = part[b0 - top:b1 - top, a0 - left:a1 - left]
            below = np.ascontiguousarray(rgba[y0:y1, x0:x1])
            rgba[y0:y1, x0:x1] = _compose([(below, None, None, None), (frame, None, None, None)], k, pin=0)
        path = _filter_path(u, f, j + 1, rect, cache)
        with _lock:
            _grown_last[path] = rgba.copy() if j + 1 < len(mine) else rgba
            _grown_last.move_to_end(path)
            while len(_grown_last) > GROWN_KEEP:
                _grown_last.popitem(last=False)
        if j + 1 < len(mine):
            reel._cached(path, lambda: _png(rgba))
    return _png(rgba)


def filter_mosaic(u, p, f, tiles, rect, cache, ref=None, tag=""):
    """The filter f's mosaic of these tiles in the view rect, RGBA on the view's canvas (kept in the cache).
    ref = the filter the seams are solved on (balanced look, seams). Past GROW_FROM tiles it grows from the
    one before (_grown) instead of composing every tile again. tag names a set of tiles that is not every tile
    up to the newest (a mosaic movie's lap, rolling_layout): it has a name of its own and is not grown, since
    growing takes the tiles as the pass's first ones in time order."""
    mine = [t for t in tiles if t["filter"] == f and "offset" in t]
    balanced = calibration.look() == "balanced" and SHARED_SEAMS
    ref = ref or f
    solved_on = f"-{ref.replace('/', '_')}{sum(1 for t in tiles if t['filter'] == ref and 'offset' in t)}" if balanced else ""
    path = _filter_path(u, f, len(mine), rect, cache, solved_on)
    path = path[:-len(".png")] + tag + ".png"
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)

    def make():
        if not balanced and not tag and len(mine) > GROW_FROM:
            return _grown(u, p, f, mine, rect, cache)
        window, shown = _window(u, p, mine, rect, cache)
        corrections = None
        if balanced and window:
            # ref's seams at each pointing; another filter's own overlaps then adjust them where they clearly
            # differ (a frame's own exposure error), pulled toward them, so the filter keeps their overall level
            solved = seams(u, p, tiles, rect, ref, cache)
            pick = [solved.get(t["n"], (1.0, 0.0)) for t in shown]
            corrections = (np.array([[g] * 3 for g, _ in pick]), np.array([[o] * 3 for _, o in pick]))
            if f != ref:
                corrections = mosaic.seams([w[0] for w in window], None, p["display_scale"]["gamma"], corrections)
        if not window:
            rgba = np.zeros((H, W, 4), np.uint8)
        elif corrections:
            rgba = _compose(window, k, pin=None, gamma=p["display_scale"]["gamma"], corrections=corrections)
        else:
            rgba = _compose(window, k, pin=None)
        return _png(rgba)

    with _lock:
        kept = _grown_last.get(path)
    if kept is not None:
        return kept
    data = reel._cached(path, make)
    with _lock:
        kept = _grown_last.get(path)
    return kept if kept is not None else np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


_parts = collections.OrderedDict()   # (tile file, width, height) -> the tile at that size, most recently used last
_parts_bytes = [0]
PARTS_KEEP = int(os.environ.get("CASSINI_MOSAIC_PARTS_MB", "256")) << 20


def _part(path, w, h):
    """A tile at w x h canvas pixels (RGBA): read and resized once and kept in memory (up to PARTS_KEEP bytes),
    since every mosaic of a pass is drawn again from all of its tiles and a tile never changes once made."""
    key = (path, w, h)
    with _lock:
        part = _parts.get(key)
        if part is not None:
            _parts.move_to_end(key)
            return part
    part = np.asarray(Image.open(path).convert("RGBA").resize((w, h), Image.LANCZOS))
    with _lock:
        if key not in _parts:
            _parts[key] = part
            _parts_bytes[0] += part.nbytes
            while _parts_bytes[0] > PARTS_KEEP and len(_parts) > 1:
                _parts_bytes[0] -= _parts.popitem(last=False)[1].nbytes
    return part


def detail(rgba, sigma):
    """Raises the local contrast of a mosaic of a body that fills the frames (Titan's surface is a few per cent
    against its haze): each pixel moved away from its neighbourhood's mean (a Gaussian of sigma canvas pixels,
    over the mosaic's own pixels only, so the empty canvas does not darken its edges) by DETAIL times the
    difference. Local, so a new tile only changes the mosaic next to it. Balanced look: on the luminance only
    (the mean of the channels), the same change added to every channel, so the small misregistration between
    filters does not turn into rainbow texture."""
    import cv2
    a = rgba[..., 3].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32)
    weight = cv2.GaussianBlur(a, (0, 0), sigma)
    if calibration.look() == "balanced":
        lum = rgb.mean(axis=2)
        mean = cv2.GaussianBlur(lum * a, (0, 0), sigma) / np.maximum(weight, 1e-3)
        out = np.clip(rgb + (DETAIL * (lum - mean))[..., None], 0, 255)
        return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])
    mean = cv2.GaussianBlur(rgb * a[..., None], (0, 0), sigma) / np.maximum(weight, 1e-3)[..., None]
    out = np.clip(rgb + DETAIL * (rgb - mean), 0, 255)
    return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])


def layout(u, n, cache):
    """What the pass's mosaic with tiles 0..n is made of: (plan, tiles, view rect, placed tiles per filter, the
    filters drawn, a name for that picture); None before any tile is placed. Frames whose tile is not one of
    the filters drawn (a moon's 30 filter colour pass draws 3) give the same picture and the same name."""
    p = plan(u, cache)
    tiles = [tile(u, j, cache, p["display_scale"]) for j in range(n + 1)]
    rect = view_rect(p, tiles)
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not count:
        return None
    colour = p["colour"]
    if colour and all(count.get(f) for f in colour):
        used = colour
    else:
        used = [p["grey"] if count.get(p["grey"]) else max(count, key=count.get)]
    name = "_".join(f"{f.replace('/', '-')}{count[f]}" for f in used) + "_" + "_".join(str(round(v)) for v in rect)
    return p, tiles, rect, count, used, name


def so_far(u, n, cache, made=None, out=OUT):
    """The pass's mosaic with tiles 0..n, RGBA out px (OUT unless asked for more, up to CANVAS) on its longest
    side, and its report; (None, None) before any tile is placed. made: layout(u, n, cache), when already
    worked out."""
    made = made or layout(u, n, cache)
    if not made:
        return None, None
    p, tiles, rect, count, used, name = made
    tag = "-" + name.rsplit("-", 1)[1] if name.startswith("lap-") else ""
    # the seams are solved on the best covered filter drawn and shared by all (balanced look)
    ref = max(used, key=lambda f: count[f])
    if len(used) == 3:
        colour = used
        acc = [filter_mosaic(u, p, f, tiles, rect, cache, ref, tag) for f in colour]
        rgb = np.dstack([a[..., 0] for a in acc])
        # only where every filter has the picture: past one filter's edge the others alone are a coloured rim
        alpha = np.min([a[..., 3] for a in acc], axis=0)
        rgb = (rgb * (alpha[..., None] / np.float32(255)) + 0.5).astype(np.uint8)
        rgba, used = np.dstack([rgb, alpha]), colour
    else:
        rgba = filter_mosaic(u, p, used[0], tiles, rect, cache, ref, tag)
    if p["display_scale"].get("filled"):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * p["k"])
    im = Image.fromarray(rgba, "RGBA")
    s = min(out, CANVAS) / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    # the label counts the tiles of the filters the plan draws (its colour filters, or its grey one), taken so far
    # of all the pass takes, so its total stays the same while the grey mosaic turns to colour
    drawn = p["colour"] or [p["grey"]]
    # a mosaic movie counts laps: the lap is how many times the camera has come back to a place by tile n
    runs, lap = {}, 1
    for fr, i in zip(u["frames"][:n + 1], u.get("place", [])):
        if i is None:
            continue
        seq = runs.setdefault(fr[2], [])
        if not seq or seq[-1] != i:
            seq.append(i)
            lap = max(lap, seq.count(i))
    laps = {"kind": u.get("kind"), "lap": lap, "laps": u.get("repeats"), "places": len(set(x for x in u.get("place", []) if x is not None))}
    return im, {**laps, "mosaic": sum(count.get(f, 0) for f in drawn), "filters": len(used), "filter_names": used,
                "observation": u["key"][1], "pass": u["key"][3], "of": sum(1 for fr in u["frames"] if fr[2] in drawn),
                "fixed": p["fixed"], "width": im.width, "height": im.height}


def movie_footprint(u, cache, p=None):
    """The ground a movie's frames cover (x0, y0, x1, y1, reference pixels from the body's centre), from where SPICE
    put the tiles themselves rather than the geometry cache (which can be a third of a frame off by the end of a
    movie tracking a propeller): MOVIE_SAMPLES tiles spread over the pass, with MOVIE_MARGIN round them for the
    frames between. Worked out once and kept with the pass."""
    path = os.path.join(folder(u, cache), "movie_footprint.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    p = p or plan(u, cache)
    n = len(u["frames"])
    picks = sorted({round(i * (n - 1) / max(1, MOVIE_SAMPLES - 1)) for i in range(MOVIE_SAMPLES)}) if n else []
    boxes = []
    # the samples made side by side (MOVIE_WORKERS at once): a cold pass's first steady frame waits on them
    look = calibration.look()

    def one(j):
        with calibration.looking(look):
            return tile(u, j, cache, p["display_scale"])
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        made = list(pool.map(one, picks))
    for t in made:
        if "offset" in t:
            bx, by, bw, bh = t["box"]
            boxes.append((t["offset"][0] + bx, t["offset"][1] + by, t["offset"][0] + bx + bw, t["offset"][1] + by + bh))
    if boxes:
        m = MOVIE_MARGIN * FRAME
        fp = [min(b[0] for b in boxes) - m, min(b[1] for b in boxes) - m, max(b[2] for b in boxes) + m, max(b[3] for b in boxes) + m]
        # the geometry cache's footprint too, so no frame between the samples falls outside both
        g = p["footprint"]
        fp = [min(fp[0], g[0]), min(fp[1], g[1]), max(fp[2], g[2]), max(fp[3], g[3])]
    else:
        fp = list(p["footprint"])
    reel._cached(path, lambda: json.dumps(fp).encode())
    return fp


def movie_rect(fp, t, radius=0.0, centre=False):
    """The view of a pass played as a movie (x0, y0, w, h in reference pixels from the body's centre): its whole
    footprint fp (movie_footprint) when that is at most MOVIE_FIT frames across, so the body holds still while the
    pointing wanders; otherwise a window MOVIE_FIT frames across centred on frame t, kept inside fp (a creeping
    ring or limb movie moves along). Either way one size for the whole pass, so the picture never rescales.
    centre: a square view centred on the body (radius: its disk, reference pixels), wide enough for the whole
    footprint round it (a stare's rings stay in) and at least a frame or the disk with CENTRE_MARGIN round it, up
    to MOVIE_FIT frames, when the disk fits that and the frames look at the body (its centre in fp): the body sits
    in the middle of every frame, north up. A body bigger than that or not in the frames (a ring or spoke movie
    past Saturn's limb) keeps the view above. All of it decided once for the pass (fp and radius are the pass's)."""
    x0, y0, x1, y1 = fp
    side = MOVIE_FIT * FRAME
    around = max(FRAME, 2 * radius * (1 + CENTRE_MARGIN))
    if centre and radius > 0 and around <= side and x0 <= 0 <= x1 and y0 <= 0 <= y1:
        half = min(side, max(around, 2 * max(-x0, x1, -y0, y1))) / 2
        return -half, -half, 2 * half, 2 * half
    if max(x1 - x0, y1 - y0) <= side:
        return x0, y0, x1 - x0, y1 - y0
    w, h = min(x1 - x0, side), min(y1 - y0, side)
    cx, cy = t["offset"]
    return min(max(cx - w / 2, x0), x1 - w), min(max(cy - h / 2, y0), y1 - h), w, h


def _place(u, t, rect, k, W, H, cache):
    """Tile t drawn where SPICE puts it in the view rect, on a W x H canvas (k canvas pixels per reference pixel)."""
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    frame = np.zeros((H, W, 4), np.uint8)
    x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
    if x0 < x1 and y0 < y1:
        part = _part(os.path.join(folder(u, cache), "tiles", f"{t['n']}.png"), sw, sh)
        frame[y0:y1, x0:x1] = part[y0 - top:y1 - top, x0 - left:x1 - left]
    return frame


def movie_frame(u, n, cache, trail=0, colour=True, out=OUT, centre=True):
    """Frame n of the pass played as a movie, RGBA out px on its longest side, and its report; (None, report)
    when SPICE could not place it. The frame is the pass's tile n (color_image.processed_frame: repeat exposures
    merged in I/F, calibrated, centred north up by SPICE, scaled to the pass's reference distance, on the pass's
    one display scale), drawn where SPICE puts it in movie_rect: so the picture keeps one brightness scale and one
    size for the whole pass, and the body holds still. colour: when the pass's plan has colour filters and the
    newest frame of each of them was taken within reel.SET_GAP of this one, the three are drawn as one colour
    picture (each where SPICE puts it), as the pass's mosaic does; otherwise the frame in grey. trail: up to that
    many earlier frames of the same filter drawn under it, fading with age (a rolling trail). In a colour pass every
    frame shows the newest complete colour set, held until the next one is complete. centre: the body in the
    middle of the view (movie_rect)."""
    p = plan(u, cache)
    t = tile(u, n, cache, p["display_scale"])
    rep = {"movie": True, "n": n, "of": len(u["frames"]), "filter": t["filter"], "observation": u["key"][1],
           "pass": u["key"][3], "id": t["id"]}
    if "offset" not in t:
        rep["why"] = t.get("why", "not placed by SPICE")
        return None, rep
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    rect = movie_rect(movie_footprint(u, cache, p), t, radius, centre)
    rep["centred"] = rect[0] == -rect[2] / 2 and rect[1] == -rect[3] / 2
    k = out / max(rect[2], rect[3])
    W, H = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    # only the frames this picture needs are made: the newest of each colour filter within SET_GAP, the trail
    frames, used, newest = u["frames"], None, {}
    # a pass with colour plays in colour: every frame shows the newest colour set taken by then (one frame of each
    # colour filter, all within SET_GAP of one another, no clear frame between them), held until the next set is complete, as the camera
    # windows hold a colour movie's last set; a frame of another filter (CB2, a methane band) keeps the set up
    if colour and p["colour"]:
        want = set(p["colour"])
        for m in range(n, max(-1, n - 64), -1):
            if frames[m][2] not in want:
                continue
            got, ts = {}, []
            for j in range(m, max(-1, m - 64), -1):
                f = frames[j][2]
                # a set as the camera windows find them: a clear or polarizer frame ends it, a filter taken again
                # starts a new one (so a set is never put together from two pointings)
                if f == "CL1/CL2" or _polarizer(f) or f in got:
                    break
                if f in want:
                    got[f] = j
                    ts.append(frames[j][3])
                    if len(got) == len(want):
                        break
            if len(got) == len(want) and max(ts) - min(ts) <= reel.SET_GAP:
                for f, j in got.items():
                    q = t if j == n else tile(u, j, cache, p["display_scale"])
                    if "offset" in q:
                        newest[f] = q
                if len(newest) == len(want):
                    used = p["colour"]
                break
    if used:
        planes = [_place(u, newest[f], rect, k, W, H, cache) for f in used]
        alpha = np.min([a[..., 3] for a in planes], axis=0)
        rgba = np.dstack([a[..., 0] for a in planes] + [alpha])
        rep["color"] = used
        rep["ids"] = [newest[f]["id"] for f in used]
    else:
        rgba = _place(u, t, rect, k, W, H, cache)
        # the rolling trail: earlier frames of this filter under it, older ones fainter
        if trail:
            js = [j for j in range(n - 1, max(-1, n - 8 * trail), -1) if frames[j][2] == t["filter"]][:trail]
            older = [q for q in (tile(u, j, cache, p["display_scale"]) for j in reversed(js)) if "offset" in q]
            acc = np.zeros((H, W, 4), np.float32)
            for age, q in zip(range(len(older), 0, -1), older):
                a = _place(u, q, rect, k, W, H, cache).astype(np.float32)
                w = a[..., 3:] / 255 * (1 - age / (len(older) + 1))
                acc[..., :3] = acc[..., :3] * (1 - w) + a[..., :3] * w
                acc[..., 3:] = np.maximum(acc[..., 3:], w * 255)
            w = rgba[..., 3:].astype(np.float32) / 255
            acc[..., :3] = acc[..., :3] * (1 - w) + rgba[..., :3] * w
            acc[..., 3:] = np.maximum(acc[..., 3:], rgba[..., 3:])
            rgba = (acc + 0.5).astype(np.uint8)
            rep["trail"] = len(older)
    if p["display_scale"].get("filled"):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * k)
    rep.update({"view": [round(v, 1) for v in rect], "width": W, "height": H})
    return Image.fromarray(rgba, "RGBA"), rep


def movie_webp(frame_id, size, cache, trail=0, colour=True, wait=False, ahead=6, centre=True):
    """(WebP, report) of frame_id played as a movie of its pass (movie_frame), made once and kept in the cache;
    None when the frame is in no pass. A pass whose plan is not worked out yet (seconds: it measures the pass's
    scale) is started in the background and answers (None, report) unless wait, so the window shows the plain
    frame meanwhile. Then makes the next few tiles in the background. centre: the body in the middle (movie_rect)."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    if not wait and not all(os.path.exists(os.path.join(folder(u, cache), f)) for f in ("plan.json", "movie_footprint.json")):
        warm_movie(u, n, ahead, cache)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3]}
    path = os.path.join(folder(u, cache), "movie", str(size), f"{n}_{trail}_{int(bool(colour))}{'_c2' if centre else ''}.webp")
    report, meta = {}, path[:-4] + "json"

    def make():
        with _asking():
            im, rep = movie_frame(u, n, cache, trail, colour, centre=centre)
        report.update(rep)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        if im is None:
            raise LookupError(rep.get("why"))
        if max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=88, method=4)
        return buf.getvalue()

    try:
        data = reel._cached(path, make)
    except LookupError:
        return None, report
    finally:
        if ahead:
            warm_movie(u, n + 1, ahead, cache)
    if not report:
        with open(meta) as fh:
            report = json.load(fh)
    return data, report


_movie_ahead = {}   # pass key -> (first, last) tile a movie wants made ahead; MOVIE_WORKERS threads per pass make them
MOVIE_WORKERS = int(os.environ.get("CASSINI_MOVIE_WORKERS", "2"))
_movie_background = threading.Semaphore(MOVIE_WORKERS)   # movie frames made ahead, beside the mosaics' one at a time


def warm_movie(u, n, ahead, cache):
    """A movie is at frame n of the pass: work out its plan and make tiles n .. n+ahead in the background, from
    where the movie is rather than from the pass's start, MOVIE_WORKERS at once (a fast movie at high playback
    speed needs several frames a second)."""
    look = calibration.look()
    key, last = (u["key"], look), min(n + ahead, len(u["frames"]) - 1)
    with _lock:
        running = key in _movie_ahead
        _movie_ahead[key] = (n, last)
        if running:
            return

    taking = set()

    def run():
        try:
            with _movie_background, calibration.looking(look):
                p = plan(u, cache)
                if u.get("kind", "movie" if u.get("movie") else None) != "mosaic_movie":
                    movie_footprint(u, cache, p)
                while True:
                    with _lock:
                        first, last = _movie_ahead.get(key, (0, -1))
                        todo = [j for j in range(first, last + 1) if j not in taking
                                and not os.path.exists(os.path.join(folder(u, cache), "tiles", f"{j}.json"))]
                        if not todo:
                            break
                        taking.add(todo[0])
                    _yield()
                    tile(u, todo[0], cache, p["display_scale"])
        except Exception as e:
            print(f"movie {key} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                workers[0] -= 1
                if not workers[0]:
                    _movie_ahead.pop(key, None)

    workers = [MOVIE_WORKERS]
    for _ in range(MOVIE_WORKERS):
        threading.Thread(target=run, daemon=True).start()


def pass_info(frame_id, cache):
    """The pass frame_id is in, for the movie's filmstrip: its observation, which frame this is and every frame
    of it ([id, seconds since 1970, filter]), and how the server judged it; None when it is in no pass."""
    found = unit_of(frame_id)
    if not found:
        return None
    u, n = found
    ts = [fr[3] for fr in u["frames"]]
    gaps = np.diff(ts) if len(ts) > 1 else []
    return {"observation": u["key"][1], "target": u["key"][0], "camera": u["key"][2], "pass": u["key"][3], "n": n,
            "movie": bool(u["movie"]), "mosaic": bool(u["mosaic"]),
            "cadence": round(float(np.median(gaps)), 1) if len(gaps) else None,
            "frames": [[fr[1], fr[3], fr[2]] for fr in u["frames"]]}


def places(u):
    """The place (pointing) index of each frame of the pass: u["place"] from the classifier when it has one,
    otherwise worked out here the same way, frames closer than mosaic.min_step of a frame (at the pass's
    reference distance) being one place."""
    if u.get("place"):
        return u["place"]
    out, seen = [], []
    for *_, x, y, z in u["frames"]:
        if not z:
            out.append(out[-1] if out else 0)
            continue
        pt = (-x * z / u["z"], -y * z / u["z"])
        for i, q in enumerate(seen):
            if max(abs(pt[0] - q[0]), abs(pt[1] - q[1])) < mosaic.min_step * FRAME:
                out.append(i)
                break
        else:
            seen.append(pt)
            out.append(len(seen) - 1)
    return out


def rolling_layout(u, n, cache, laps=1, made_only=False):
    """What a mosaic movie (a raster repeated over the same places: kind "mosaic_movie") shows at frame n, in the
    form of layout(): every place's newest tile of each filter taken by then, so the mosaic never empties when a
    new lap begins and each tile replaces its own earlier copy (laps=1, a time-lapse); laps=N keeps the N newest
    copies of each place, older under newer (a rolling mosaic). Drawn by so_far through filter_mosaic and
    mosaic.compose like the pass's mosaic, on its scale and in its view. made_only: only tile n is made here, the
    other places show the tiles already made (a window playing fast never waits on the tiles it missed;
    tiles_ahead makes them)."""
    p = plan(u, cache)
    where = places(u)
    there = os.path.join(folder(u, cache), "tiles")
    # each place's newest copies that are there to draw: a copy not made yet (made_only) or one SPICE could not
    # place leaves the copy before it up, so a place never drops out of the mosaic and comes back
    keep, seen = [], {}
    for j in range(n, -1, -1):
        # (a frame the classifier gave no place stays up on its own, under the newer ones, rather than taking the
        # place of every other such frame)
        key = (where[j] if where[j] is not None else ("frame", j), u["frames"][j][2])
        if seen.get(key, 0) >= laps:
            continue
        if made_only and j != n and not os.path.exists(os.path.join(there, f"{j}.json")):
            continue
        t = tile(u, j, cache, p["display_scale"])
        if "offset" not in t:
            continue
        seen[key] = seen.get(key, 0) + 1
        keep.append(t)
    tiles = sorted(keep, key=lambda t: t["n"])
    rect = view_rect(p, tiles)
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not count:
        return None
    colour = p["colour"]
    used = colour if colour and all(count.get(f) for f in colour) else [p["grey"] if count.get(p["grey"]) else max(count, key=count.get)]
    ids = hashlib.sha1(",".join(str(t["n"]) for t in tiles if t["filter"] in used).encode()).hexdigest()[:12]
    return p, tiles, rect, count, used, f"lap-{laps}-{ids}"


def rolling_webp(frame_id, size, cache, laps=1, slots=None, fmt="webp", out=OUT, wait=False):
    """(WebP, report) of frame_id's pass played as a mosaic movie (rolling_layout), made once and kept; None when
    the frame is in no pass, (None, report) while the pass is being worked out (unless wait)."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    if not wait and not os.path.exists(os.path.join(folder(u, cache), "plan.json")):
        warm_movie(u, n, 6, cache)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3]}
    with _asking():
        made = rolling_layout(u, n, cache, laps, made_only=not wait)
        if not made:
            return None, {"why": "no tile placed yet"}
        full = size == "full"
        path = os.path.join(folder(u, cache), "rolling-level", f"full{out}" if full else str(size), f"{made[5]}.{fmt}")
        res = _make_mosaic(u, n, size, path, cache, slots, made, fmt, out)
    # the tiles ahead, by the pass's one background thread (tiles_ahead, as a pass mosaic's)
    tiles_ahead(u, n + 1, cache)
    if res:
        res[1].update({"rolling": True, "keep": laps, "n": n})   # laps: the pass's own, from _make_mosaic
    return res


def mosaic_webp(frame_id, size, cache, slots=None, ahead=3, fmt="webp", out=OUT, force=False):
    """(WebP, report) of the mosaic so far at frame_id when its pass is a mosaic (or force: the person asked for
    the pass as a mosaic, whatever _judge says); otherwise None. Then makes the next few tiles and the mosaics
    with them in the background, so the next frames' mosaics are ready when the window asks for them. Never
    waits for tiles beyond the first: past the tiles made so far it answers with their mosaic (report "behind":
    how many frames short of frame_id it is). size
    "full" = out px on the longest side (the full view's picture, never warmed ahead); fmt "png" for a PNG
    instead."""
    found = unit_of(frame_id)
    if not found or not (found[0]["mosaic"] or force) or found[1] < 0:
        return None
    u, n = found
    # the mosaic of the tiles made so far, when the clock has run past them (playing faster than a frame is
    # processed): the window gets a picture at once, a little behind, and catches up as the tiles behind it
    # (tiles_ahead) are made, instead of waiting for every tile up to n
    m = _made_through(u, n, cache)
    tiles_ahead(u, m + 1, cache)
    if m < n:
        if m < 0:
            return None
        n, ahead = m, 0
    with _asking():
        if size == "full":
            made = _mosaic_at(u, n, size, cache, slots, fmt, out)
        else:
            made = _mosaic_at(u, n, size, cache, slots)
    if made:
        made = made[0], {**made[1], "behind": found[1] - n}
    if made and ahead and size != "full":
        warm(u, n + ahead, cache, size, slots, start=n + 1, force=force)
    return made


_made = {}   # (pass, look) -> the last tile of the pass up to which every tile is made (or -1)


def _made_through(u, n, cache):
    """The last tile j <= n of the pass with tiles 0..j all made (their reports in the cache), -1 for none.
    Tile 0 is made here when nothing is (with the plan, seconds), so a pass's first mosaic does not wait for
    the background."""
    key = (u["key"], calibration.look())
    base = os.path.join(folder(u, cache), "tiles")
    with _lock:
        j = _made.get(key, -1)
    if j < 0 and not os.path.exists(os.path.join(base, "0.json")):
        with _asking():
            tile(u, 0, cache)
    while j < n and os.path.exists(os.path.join(base, f"{j + 1}.json")):
        j += 1
    with _lock:
        _made[key] = max(_made.get(key, -1), j)
    return min(j, n)


_asked = [0]   # mosaics a window is waiting for right now: work made ahead waits while there are any


@contextlib.contextmanager
def _asking():
    with _lock:
        _asked[0] += 1
    try:
        yield
    finally:
        with _lock:
            _asked[0] -= 1


def _yield():
    """Background work waits here, between one tile or mosaic and the next, while a window waits for a
    mosaic, so the mosaic asked for goes first (one compose at a time, reel._mosaic_lock) instead of after
    the ones being made ahead of it."""
    while _asked[0]:
        time.sleep(0.02)


def _mosaic_at(u, n, size, cache, slots=None, fmt="webp", out=OUT):
    """(WebP, report) of the pass's mosaic with tiles 0..n at size, made once (kept in the cache under the name
    of what it is made of, so frames that add nothing to it share it; a request that comes while it is being
    made waits for it); None before any tile is placed."""
    made = layout(u, n, cache)
    if not made:
        return None
    full = size == "full"
    path = os.path.join(folder(u, cache), f"full{out}" if full else str(size), f"{made[5]}.{fmt}")
    if not os.path.exists(path):
        with _lock:
            lock = _making.setdefault(path, threading.Lock())
        with lock:
            try:
                return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out)
            finally:
                with _lock:
                    _making.pop(path, None)
    return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out)


def _make_mosaic(u, n, size, path, cache, slots, made, fmt="webp", out=OUT):
    report, full, meta = {}, size == "full", path[:-len(fmt)] + "json"

    def make():
        with slots or contextlib.nullcontext():
            im, rep = so_far(u, n, cache, made, out if full else OUT)
        if im is None:
            raise LookupError("no tile placed yet")
        report.update(rep)
        if not full and max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "png":
            im.save(buf, "PNG", compress_level=6)
        else:
            im.save(buf, "WEBP", quality=92 if full else 85, method=4)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        return buf.getvalue()

    try:
        data = reel._cached(path, make)
    except LookupError:
        return None
    if not report:
        with open(meta) as fh:
            report = json.load(fh)
    return data, report


def warm(u, upto, cache, size=None, slots=None, start=0, force=False):
    """Makes the pass's plan and its tiles up to upto in the background, and with a size the mosaics at tiles
    start..upto. One thread per pass and size: a later call while it runs moves its end on. Background work
    runs one pass at a time (_background). force: a pass _judge does not call a mosaic, asked for as one."""
    if not (u["mosaic"] or force):
        return
    look = calibration.look()
    key = (u["key"], size, look)
    with _lock:
        _upto[key] = max(_upto.get(key, -1), min(upto, len(u["frames"]) - 1))
        _from[key] = max(_from.get(key, 0), start)
        if key in _warming:
            return
        _warming.add(key)

    def run():
        try:
            with _background, calibration.looking(look):
                p = plan(u, cache)
                done = -1
                while True:
                    with _lock:
                        last, first = _upto[key], _from[key]
                        if last <= done:   # nothing more asked: finished (a later call starts a new thread)
                            _warming.discard(key)
                            _upto.pop(key, None)
                            _from.pop(key, None)
                            return
                    for j in range(done + 1, last + 1):
                        _yield()
                        tile(u, j, cache, p["display_scale"])
                    if size:
                        for j in range(max(first, done + 1), last + 1):
                            _yield()
                            # a window that has asked for a later frame meanwhile (a burst) has passed this one
                            if j >= _from[key]:
                                _mosaic_at(u, j, size, cache, slots)
                    done = last
        except Exception as e:
            print(f"observation mosaic {u['key']} failed: {type(e).__name__}: {e}", flush=True)
            with _lock:
                _warming.discard(key)
                _upto.pop(key, None)
                _from.pop(key, None)

    threading.Thread(target=run, daemon=True).start()


_ahead_passes = collections.deque(maxlen=2)   # the passes windows were in last (a NAC and a WAC window)
_ahead_running = set()


def tiles_ahead(u, n, cache):
    """Makes the pass's tiles from the first one not made to its end in the background (n: the frame the window
    is at, kept for the callers), one thread per pass, so a playing window's
    mosaic finds its tiles made (processing a frame is the slow part of a cold mosaic) instead of waiting for
    each. Stops once windows have moved on to two other passes. Waits between tiles while a window waits for a
    mosaic (_yield), so the pass's lock goes to the request first instead of to the next tile ahead."""
    with _lock:
        if u["key"] in _ahead_passes:
            _ahead_passes.remove(u["key"])
        _ahead_passes.append(u["key"])
        if u["key"] in _ahead_running:
            return
        _ahead_running.add(u["key"])
    look = calibration.look()

    def run():
        try:
            with calibration.looking(look):
                p = plan(u, cache)
                # from the first tile not made: a window's mosaic is the tiles made so far in a row (mosaic_webp)
                with _lock:
                    first = _made.get((u["key"], look), -1) + 1
                for j in range(first, len(u["frames"])):
                    _yield()
                    if u["key"] not in _ahead_passes:
                        return
                    tile(u, j, cache, p["display_scale"])
        except Exception as e:
            print(f"observation tiles {u['key']} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                _ahead_running.discard(u["key"])

    threading.Thread(target=run, daemon=True).start()


def warm_frame(frame_id, cache, ahead=4):
    """A frame was asked for: when it is in a mosaic pass, start making that pass's tiles from it on."""
    found = unit_of(frame_id)
    if found and found[0]["mosaic"]:
        tiles_ahead(found[0], max(found[1], 0), cache)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frame", help="a frame of the pass, e.g. W1537023863_1")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--all", action="store_true", help="also make the mosaic at every tile (1024 px)")
    args = ap.parse_args()
    u, _ = unit_of(args.frame)
    print(u["key"], len(u["frames"]), "tiles", "mosaic" if u["mosaic"] else "not a mosaic", "whole body" if u["whole"] else "")
    t0 = time.time()
    p = plan(u, args.cache)
    print("plan", {k: v for k, v in p.items() if k != "display_scale"}, f"{time.time() - t0:.1f} s", flush=True)
    if args.all:
        for fr in u["frames"]:
            t0 = time.time()
            made = mosaic_webp(fr[1], 1024, args.cache, ahead=0)
            print(fr[1], fr[2], made and made[1]["mosaic"], f"{time.time() - t0:.2f} s", flush=True)


if __name__ == "__main__":
    main()
