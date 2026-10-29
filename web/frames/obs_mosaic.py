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
import contextvars
import hashlib
import io
import json
import math
import os
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reel  # noqa: E402  (puts the repo on the path)
import sets_passes  # noqa: E402
import color_image  # noqa: E402
import calibration  # noqa: E402
import mosaic  # noqa: E402
import mosaic_benchmark  # noqa: E402
import image_correction  # noqa: E402
import stacking  # noqa: E402

# bumped whenever the way observation mosaics are made changes, so older ones are not served again; one per
# display model (calibration.style), classic being the mosaics made before the balanced display model, raw the
# balanced ones before natural color
# obs-v47/v30/v17: calibration takes the flat field (dust rings, mottle) and the nonlinearity out
VERSIONS = {"balanced": "obs-v47", "raw": "obs-v30", "classic": "obs-v17-classic"}
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
LAP_INSIDE = 0.9     # a few frames after a mosaic (a lap stopped short) are part of it when this much of them is inside it
PAIR_STEP = 1.0      # two places at most this many frames apart (their tiles touching) are a 1x2 mosaic
STRAY_LINK = 4       # frames of a pass within this many frames of one another are one patch of sky (_drop_strays) ...
STRAY_SHARE = 0.5    # ... and patches holding less than this share of its frames, away from the rest, are not the pass's
GROUPING = "_g2"     # the folder suffix of a pass these three rules (_drop_strays, _piece, a 1x2) group anew, so the
                     # passes made before them are not served for it; every other pass keeps its folder
MOVIE_DWELL = 8      # ... or whose camera stays this many frames of one filter (median) at each place it goes
TRACK_VISITS = 2     # ... or that follows a moving feature (_judge's track): at least this many visits of 3+ filters,
TRACK_SPAN = 0.08    # ... whose frames spread (median) over more than this much of a frame (twice REGISTER_MAX)
TRACK_CARRY = 0.5    # ... and, on a turning body (SPIN), whose turning carries a feature at least this share of that spread
RELAID = "_g3"       # the folder suffix, after GROUPING's, of a pass the layout rules below lay out anew (a time series, a
                     # drifting filter set, laps over drifted places, a map split by ZOOM joined again, a movie cut at a
                     # retarget, a turning camera, filters a lone frame set aside), or of every pass of an observation
                     # they renumber
REVISIT_PAUSE = 2    # a pause: a gap between frames this many times the pass's usual one (and at least REGISTER_GAP) ...
REVISIT_SHARE = 0.5  # ... and a mosaic whose frames mostly retake, after a pause, one view their filter took is a time series
JOIN_ZOOM = ZOOM * ZOOM   # a map units split at ZOOM is joined again while its frames stay within this of its first distance
TWIST = 0.04         # of a frame: a pass the camera turns under (reel.turns) by more than this at its frames' places is drawn
                     # on a footprint turned frame by frame
RADIUS = {"SATURN": 60268, "JUPITER": 69911, "TITAN": 2575, "RHEA": 764, "IAPETUS": 735, "DIONE": 561,
          "TETHYS": 531, "ENCELADUS": 252, "MIMAS": 198, "HYPERION": 135, "PHOEBE": 107}
# Saturn's small moons (mean radius, Thomas 2010, Denk et al. 2018; web/replay/build_data.SMALL_MOONS), so Auto center
# has a disk to centre their passes on; under the catalog's own names (bootleg_autonav.CATALOG_NAMES). pass_scale's
# filled scale (a body filling the frames) stays with the bodies above: frames centred on a small moon are mostly
# sky round a disk a few per cent of the frame, which that scale (gamma 1.5) blew out to white
SMALL_RADIUS = {"JANUS": 89.5, "EPIMETHEUS": 58.1, "PROMETHEUS": 43.1, "PANDORA": 40.6, "HELENE": 18, "ATLAS": 15.1,
                "PAN": 14, "TELESTO": 12.4, "CALYPSO": 9.5, "DAPHNIS": 3.8, "PALLENE": 2.2, "METHONE": 1.45,
                "POLYDEUCES": 1.3, "ANTHE": 0.5, "K07S4": 0.5, "AEGAEON": 0.33,
                "SIARNAQ": 20, "ALBIORIX": 16, "PAALIAQ": 11, "YMIR": 9, "KIVIUQ": 8, "TARVOS": 7.5, "IJIRAQ": 6,
                "ERRIAPUS": 5, "ERRIAPO": 5, "SKATHI": 4, "SKADI": 4, "THRYMR": 4, "THRYM": 4, "HYROKKIN": 4,
                "SUTTUNGR": 3.5, "SUTTUNG": 3.5, "MUNDILFARI": 3.5, "NARVI": 3.5, "BESTLA": 3.5, "KARI": 3.5,
                "TARQEQ": 3.5, "BEBHIONN": 3, "BERGELMIR": 3, "FORNJOT": 3, "HATI": 3, "LOGE": 3, "SKOLL": 3, "SURTUR": 3,
                "JARNSAXA": 3, "GREIP": 3, "S13_2004": 3, "S12_2004": 2.5}
FILL_RADIUS = dict(RADIUS)
RADIUS.update(SMALL_RADIUS)
IFOV = {"N": 6.0e-6, "W": 60e-6}   # radians per full resolution pixel
# radius (km) and rotation period (hours) of the bodies a camera can follow a feature on (_judge's track): a feature
# the body's turning carries along. The moons turn with their orbits (Phoebe and Hyperion on their own)
SPIN = {"SATURN": (60268, 10.66), "JUPITER": (71492, 9.925), "EARTH": (6378, 23.93), "VENUS": (6052, 5832.5),
        "MOON": (1737, 655.7), "IO": (1822, 42.46), "EUROPA": (1561, 85.23), "GANYMEDE": (2634, 171.7),
        "CALLISTO": (2410, 400.5), "TITAN": (2575, 382.7), "RHEA": (764, 108.4), "IAPETUS": (735, 1903.9),
        "DIONE": (561, 65.69), "TETHYS": (531, 45.31), "ENCELADUS": (252, 32.89), "MIMAS": (198, 22.62),
        "HYPERION": (135, 312.0), "PHOEBE": (107, 9.27)}
QUALITY = 95         # WebP quality of every picture sent; its folders carry it (frame_server.QUALITY)

_units = {}           # (target, obs, cam) -> [unit dicts]
_lock = threading.Lock()
_unit_locks = {}
_warming = set()
_background = threading.Semaphore(1)   # background work (passes made ahead) runs one at a time, so it never
                                       # crowds out what a window is waiting for
_upto, _from = {}, {}   # a pass being made ahead: the last tile to make, the first mosaic to make
_tile_locks = {}      # (pass key, mode, tile) -> its lock (calibration.mode: another look or step set is another tile)
_making = {}          # path of a mosaic being made -> its lock, so two requests for it make it once


def _row_of():
    idx, _ = reel.load_index()
    with _lock:
        if not hasattr(_row_of, "row"):
            _row_of.row = dict(zip(idx["id"], range(len(idx))))
    return idx, _row_of.row


_observations_lock = threading.Lock()


def _observations():
    """{(target, observation, instrument): the index's row numbers of its frames, in index order}, made once (a third of
    a second, as the server starts), so units finds an observation's frames in a lookup instead of comparing three
    fields of every frame in the index (70 ms the first time a server met each observation, on the request threads)"""
    idx, _ = reel.load_index()
    with _observations_lock:
        if not hasattr(_observations, "rows"):
            _observations.rows = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
    return idx, _observations.rows


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
    idx, observations = _observations()
    inst = "ISSNA" if cam == "N" else "ISSWA"
    at = observations.get((target, obs, inst))
    # the rows of idx[(idx["OBSERVATION_ID"] == obs) & (idx["TARGET_NAME"] == target) & (idx["INSTRUMENT_ID"] == inst)]
    rows = idx.iloc[at] if at is not None else idx.iloc[:0]
    where = reel.geometry(rows["id"].tolist())
    turned = reel.turns(rows["id"].tolist())
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
    for u in out:
        _drop_strays(u)
    laps, shifted, relaid = [], False, False
    for u in out:
        u["key"] = (target, obs, cam, len(laps))
        _judge(u)
        prev = laps[-1] if laps else None
        # (and one view taken lap after lap, a filter set each time, is one pass: a time series, _judge's views)
        views = bool(prev and (prev.get("drift") or prev.get("views")) and u.get("drift"))
        if (prev and (prev["mosaic"] or views) and u["frames"] and u["frames"][0][3] - prev["last"] <= LAP_GAP and u["z"]
                and 1 / ZOOM < u["z"] / prev["z"] < ZOOM
                and (views and _overlap(prev, u) >= LAP_OVERLAP
                     or not views and (u["mosaic"] and _overlap(prev, u) >= LAP_OVERLAP or _piece(prev, u)))):
            prev["views"] = views
            relaid = relaid or views   # (the passes after it are renumbered)
            # (a piece, or a lap that is a mosaic only by the newer rules, joining it renumbers the passes after it)
            shifted = shifted or not u["mosaic"] or any(v.get("pair") or v.get("off") for v in (prev, u))
            for k in ("frames", "all", "taken"):
                prev[k] += u[k]
            prev["last"] = u["last"]
            prev["off"] = prev.get("off", set()) | u.get("off", set())
            _judge(prev)
        elif prev and _zoom_join(prev, u):
            relaid = True   # (the passes after it are renumbered)
        else:
            laps.append(u)
    # a movie that re-points to sky it never comes back to plays each view as a pass of its own
    out = []
    for u in laps:
        pieces = _retargets(u)
        relaid = relaid or len(pieces) > 1
        out += pieces
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        _judge(u)
        # GROUPING's folder: a pass grouped anew (strays out, or a mosaic only as a 1x2), or every pass of an
        # observation whose passes these rules renumbered; RELAID's: a pass the layout rules after them changed, or
        # every pass of an observation they renumbered
        u["regrouped"] = bool(shifted or u.get("off") or u.get("pair"))
        u["repeat_gap"] = repeat_window(u)
        if u["repeat_gap"] < mosaic_benchmark.REPEAT_GAP:
            u["frames"], last = [], {}
            for fr in u["all"]:
                if fr[2] in last and fr[3] - last[fr[2]] <= u["repeat_gap"]:
                    continue
                last[fr[2]] = fr[3]
                u["frames"].append(fr)
        del u["all"]
        # the camera turning under a mosaic: its footprint is turned frame by frame (plan)
        if u["kind"] in ("mosaic", "mosaic_movie") and _twist(u, turned) > TWIST * FRAME:
            u["twist"] = {fr[1]: turned[fr[1]] for fr in u["frames"] if fr[1] in turned}
        # (and a mosaic whose filters aside a lone frame near the middle had decided: its plan draws other filters)
        u["aside"] = u["kind"] in ("mosaic", "mosaic_movie") and _aside(u["frames"], u) != _aside(u["frames"], u, 0, False)
        u["relaid"] = bool(relaid or u["revisit"] or u["drift"] or u["slot_laps"] or u.get("joined") or u.get("twist")
                           or u["aside"])
    with _lock:
        _units[(target, obs, cam)] = out
    return out


def _drop_strays(u):
    """Takes out of pass u the frames that are not of its sky: patches of frames (frames within STRAY_LINK frames
    of one another) away from the biggest one, together less than STRAY_SHARE of its placed frames, repeats too.
    The Jupiter approach's 2x2 laps have clear frames or one UV1 frame 38 to 430 frames off Jupiter, which
    made the lap's footprint too wide for a mosaic, so its tiles played on their own and split the mosaic movie in
    two. Their ids go in u["off"] (unit_of leaves them out of the pass, so they show as themselves) and the pass
    is regrouped (GROUPING). A pass whose frames all lie within MAX_FRAMES of one another is left as it is."""
    pts = [(q, -fr[5] * fr[7] / u["z"] / FRAME, -fr[6] * fr[7] / u["z"] / FRAME)
           for q, fr in enumerate(u["all"]) if fr[7] and u["z"]]
    if len(pts) < 2:
        return
    xy = np.array([(x, y) for _, x, y in pts])
    if (xy.max(0) - xy.min(0)).max() < MAX_FRAMES:
        return
    # patches: grid cells STRAY_LINK frames wide, a cell joined to the cells round it
    cells = {}
    for (q, x, y) in pts:
        cells.setdefault((math.floor(x / STRAY_LINK), math.floor(y / STRAY_LINK)), []).append(q)
    parent = {c: c for c in cells}

    def root(c):
        while parent[c] != c:
            c = parent[c]
        return c
    for (a, b) in cells:
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                if (a + da, b + db) in cells and root((a + da, b + db)) != root((a, b)):
                    parent[root((a + da, b + db))] = root((a, b))
    patch = {}
    for c, qs in cells.items():
        patch.setdefault(root(c), []).extend(qs)
    main = max(patch.values(), key=len)
    strays = {q for qs in patch.values() if qs is not main for q in qs}
    if not strays or len(strays) >= STRAY_SHARE * len(pts):
        return
    u["off"] = {u["all"][q][1] for q in strays}
    u["all"] = [fr for q, fr in enumerate(u["all"]) if q not in strays]
    u["taken"] = [fr for q, fr in enumerate(u["taken"]) if q not in strays]
    u["frames"] = [fr for fr in u["frames"] if fr[1] not in u["off"]]


def _piece(prev, u):
    """Pass u is the rest of mosaic prev's last lap: a few frames taken after a pause (too few places for a mosaic
    of their own, the camera not staying on them: a lap stopped short), at least LAP_INSIDE of them inside prev's
    footprint. 18ATM2X2A139's three frames at one place between two laps were a pass of their own, a movie, which
    kept the laps either side of it from being one mosaic movie."""
    if u["mosaic"] or not u["frames"] or (u["dwell"] or 0) >= MOVIE_DWELL or u["track"]:
        return False
    if len({i for i in u["place"] if i is not None}) >= MIN_PLACES:
        return False
    p, q = _box(prev, prev["z"]), _box(u, prev["z"])
    if not p or not q:
        return False
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    return max(w, 0) * max(h, 0) >= LAP_INSIDE * (q[2] - q[0]) * (q[3] - q[1])


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


def _zoom_join(prev, u):
    """Joins pass u into prev when the two are one map that units split where the distance changed by ZOOM (Titan's
    042TI_GLOBMAP001: its middle, then the ring round it as Cassini closed in, drawn as two mosaics with a hole in the
    second): both mosaics, u straight after prev (within GAP), every frame of u within JOIN_ZOOM of prev's distance,
    u's footprint touching prev's and not a closer look at ground prev already took (LAP_INSIDE of it inside prev's),
    and the two still a mosaic together (tiles at another distance are scaled to the pass's, as ever). True when
    joined (prev is the joined pass)."""
    if prev["kind"] != "mosaic" or u["kind"] != "mosaic" or not u["frames"] or not prev["z"]:
        return False
    if u["frames"][0][3] - prev["last"] > GAP:
        return False
    zs = [fr[7] for fr in u["frames"] if fr[7]]
    if not zs or not (1 / JOIN_ZOOM < min(zs) / prev["z"] and max(zs) / prev["z"] < JOIN_ZOOM):
        return False
    p, q = _box(prev, prev["z"]), _box(u, prev["z"])
    if not p or not q:
        return False
    w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
    if w <= 0 or h <= 0 or w * h >= LAP_INSIDE * (q[2] - q[0]) * (q[3] - q[1]):
        return False
    joined = dict(prev, **{k: prev[k] + u[k] for k in ("frames", "all", "taken")})
    joined.update(last=u["last"], off=prev.get("off", set()) | u.get("off", set()))
    _judge(joined)
    if joined["kind"] != "mosaic":
        return False
    prev.clear()
    prev.update(joined, joined=True)
    return True


def _retargets(u):
    """Pass u in pieces where it re-points to sky it never comes back to (a Grand Finale retarget's four ring patches
    in one movie, 287RI_PROPRETRG001, which jumped from view to view): a movie is cut between two frames when no frame
    after them shares any ground with a frame before (their footprints, frames at the pass's distance, do not touch).
    [u] when there is nothing to cut (a movie going back and forth between two patches comes back, so is never cut)."""
    if u["kind"] != "movie":
        return [u]
    pts = [(q, -fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) for q, fr in enumerate(u["all"]) if fr[7]]
    if len(pts) < 2:
        return [u]
    xy = np.array([(x, y) for _, x, y in pts])
    lo, hi = np.minimum.accumulate(xy), np.maximum.accumulate(xy)   # the frames up to each one
    rlo, rhi = np.minimum.accumulate(xy[::-1])[::-1], np.maximum.accumulate(xy[::-1])[::-1]   # ... and from it on
    cuts = [pts[i + 1][0] for i in range(len(pts) - 1)
            if ((rlo[i + 1] - hi[i] >= FRAME) | (lo[i] - rhi[i + 1] >= FRAME)).any()]
    if not cuts:
        return [u]
    pieces = []
    for a, b in zip([0] + cuts, cuts + [len(u["all"])]):
        part = u["all"][a:b]
        z = next((fr[7] for fr in part if fr[7]), None)
        pieces.append({"key": u["key"], "all": part, "taken": u["taken"][a:b], "z": z, "last": part[-1][3],
                       "frames": [fr for fr in u["frames"] if part[0][3] <= fr[3] <= part[-1][3]],
                       **({"off": u["off"]} if u.get("off") else {})})
    return pieces


def _twist(u, turned):
    """How far (reference pixels) the camera turning under pass u (reel.turns: degrees from north up, frame by frame)
    moves its frames from where the turn of its first frame placed well off the body (as plan measures it) puts them."""
    ref = next((turned[fr[1]] for fr in u["frames"] if fr[7] and fr[1] in turned and math.hypot(fr[5], fr[6]) > 200), None)
    if ref is None or not u["z"]:
        return 0.0
    most = 0.0
    for fr in u["frames"]:
        if fr[7] and fr[1] in turned:
            d = (math.radians(turned[fr[1]] - ref) + math.pi) % (2 * math.pi) - math.pi
            most = max(most, abs(d) * math.hypot(fr[5], fr[6]) * fr[7] / u["z"])
    return most


def _one_view(u):
    """Pass u shows one view, not a mosaic: the frames its mosaic draws (its luminance base's filters, as plan and
    luminance_of choose them) all lie within mosaic.min_step of the first, or the camera drifts through a set of
    filters (each frame within SAME_PLACE and REGISTER_GAP of the one before, at least three filters and none taken
    more than twice: a storm rider's five filters sliding 0.7 of a frame, the Moon's nine in 1999, Mimas's fifteen in
    072MI_MIDIECLN001), so its mosaic is offset strips of one picture. Its frames and colour sets show as themselves."""
    aside = _aside(u["frames"], u)
    count = collections.Counter(fr[2] for fr in u["frames"] if fr[2] not in aside) or collections.Counter(fr[2] for fr in u["frames"])
    grey = max(count, key=count.get)
    pts = [(f, t, -x * z / u["z"], -y * z / u["z"]) for _, _, f, t, _, x, y, z in u["frames"]
           if z and f in count and (f == grey or not _polarizer(f))]
    if not pts:
        return False
    if all(max(abs(p[2] - pts[0][2]), abs(p[3] - pts[0][3])) < mosaic.min_step * FRAME for p in pts):
        return True
    taken = collections.Counter(p[0] for p in pts)
    if len(taken) < 3 or max(taken.values()) > 2:
        return False
    return all(b[1] - a[1] <= REGISTER_GAP and math.hypot(b[2] - a[2], b[3] - a[3]) <= SAME_PLACE * FRAME
               for a, b in zip(pts, pts[1:]))


def _revisits(u):
    """Pass u is a time series, not a mosaic: most of its frames that take a filter again (REVISIT_SHARE) come back
    after a pause (REVISIT_PAUSE) to the view of one frame of that filter taken before the pause (LAP_OVERLAP of the
    frame), a little way off, so they counted as new places, and they come back at least twice (one return is a
    two-tile mosaic with a wide overlap): Saturn's limb sampled every 28 minutes (267SA_LIMBINT002), the WAC beside a
    NAC feature track (191SA_FEATRAK001), a CIRS feature track's two or three filters every few minutes (FTRACK),
    Titan's cloud monitors. A mosaic steps on to new ground, even where it overlaps its earlier columns
    (221DI_REGMAP001's interleaved columns, 242SA_NHEMOSAIC001's slow steps); a dense strip overlaps the frames just
    before it, taken without a pause."""
    fr = [(f, t, -x * z / u["z"] / FRAME, -y * z / u["z"] / FRAME) for _, _, f, t, _, x, y, z in u["frames"] if z]
    if len(fr) < 3:
        return False
    gaps = np.diff([q[1] for q in fr])
    pause = max(REVISIT_PAUSE * float(np.median(gaps)), REGISTER_GAP)
    seen, start, back, again, returns = {}, 0, 0, 0, set()
    for i, (f, t, x, y) in enumerate(fr):
        if i and gaps[i - 1] >= pause:
            start = i   # (frames before start were taken before a pause)
        mine = seen.setdefault(f, [])
        if mine:
            again += 1
            if any(j < start and (1 - abs(a - x)) * (1 - abs(b - y)) >= LAP_OVERLAP
                   for j, a, b in mine if abs(a - x) < 1 and abs(b - y) < 1):
                back += 1
                returns.add(start)
        mine.append((i, x, y))
    return len(returns) >= 2 and back >= REVISIT_SHARE * again


def _slot_laps(u):
    """How many times (median over its slots, in one filter) pass u comes back to a slot: a lap over places a little
    way off the last lap's (slots) counts as a lap, not as new places."""
    where, runs = _slot_of(u, u["place"]), {}
    for fr, i in zip(u["frames"], where):
        if i is not None:
            seq = runs.setdefault(fr[2], [])
            if not seq or seq[-1] != i:
                seq.append(i)
    visits = [max(seq.count(i) for seq in runs.values()) for i in {i for i in where if i is not None}]
    return int(np.median(visits)) if visits else 0


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
    u["kind"]: "movie", "mosaic", "mosaic_movie" (a mosaic whose places are taken lap after lap) or None, and
    u["track"] (the camera follows a moving feature: a movie); a pass the later layout rules judge says which
    (u["slot_laps"], u["drift"], u["revisit"])."""
    for k in ("slots", "lap_of", "_lum"):   # (worked out from the frames the pass had when last judged)
        u.pop(k, None)
    pts = [(-x * z / u["z"], -y * z / u["z"]) for _, _, _, _, _, x, y, z in u["frames"] if z]
    # the steps between consecutive frames of one filter, in frames: a mosaic jumps, a movie creeps
    last, steps = {}, []
    for _, _, f, _, _, x, y, z in u["frames"]:
        if z:
            p = (-x * z / u["z"], -y * z / u["z"])
            if f in last:
                steps.append(max(abs(p[0] - last[f][0]), abs(p[1] - last[f][1])) / FRAME)
            last[f] = p
    # no filter taken twice: the luminance base draws every filter's tiles in one gray mosaic, so the steps are
    # counted between consecutive frames whatever their filter. A scan that steps one filter a pointing (a limb
    # scan, a methane band map) jumps every frame and is a mosaic; a stare cycling its filters stays put and is a movie
    if not steps:
        prev = None
        for _, _, f, _, _, x, y, z in u["frames"]:
            if z:
                p = (-x * z / u["z"], -y * z / u["z"])
                if prev is not None:
                    steps.append(max(abs(p[0] - prev[0]), abs(p[1] - prev[1])) / FRAME)
                prev = p
    u["jump_frac"] = float(np.mean([s >= mosaic.min_step for s in steps])) if steps else None
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
    # track: the camera follows something that moves across the body (a cloud feature, FEATRAK), so the filters of
    # one pointing do not land on one another: ISS_191SA_FEATRAK001 creeps 0.13 of a frame over each 10-filter visit
    # (and one CB3 frame sits 585 px off), ISS_222SA_FEATRAK001 drifts all the way through. Drawn as a mosaic that
    # makes narrow colour strips and doubled limbs, so it plays as a movie. A visit is a run of frames through
    # different filters, each within REGISTER_GAP and SAME_PLACE of the one before; in a mosaic a visit holds still
    # (SPICE within REGISTER_MAX, what registration believes), in a track its frames spread over more than TRACK_SPAN
    # (median over the pass's visits of three or more frames). A raster stepping a pointing every frame has no visits.
    # The spread is where SPICE puts each frame on the pass's canvas (body centred, at its reference distance), which
    # already follows the spacecraft; what is left in a close flyby is the view turning as Cassini passes (parallax).
    # So on a body whose turning is known (SPIN) a pass is a track only where that turning can carry a surface feature
    # across at least TRACK_CARRY of the spread in a visit's time: Saturn's clouds 10 km/s, a moon's surface centimetres
    # to metres a second, so a moon's regional map stays a mosaic. A target with no body (rings named by themselves,
    # the sky) keeps the spread alone.
    spans, visit, took = [], [], []
    for _, _, f, t, _, x, y, z in u["frames"]:
        if not z:
            continue
        p = (-x * z / u["z"], -y * z / u["z"], t, f)
        if visit and (t - visit[-1][2] > REGISTER_GAP or f in {q[3] for q in visit}
                      or math.hypot(p[0] - visit[-1][0], p[1] - visit[-1][1]) > SAME_PLACE * FRAME):
            if len(visit) >= 3:
                spans.append(max(math.hypot(a[0] - c[0], a[1] - c[1]) for a in visit for c in visit) / FRAME)
                took.append(visit[-1][2] - visit[0][2])
            visit = []
        visit.append(p)
    if len(visit) >= 3:
        spans.append(max(math.hypot(a[0] - c[0], a[1] - c[1]) for a in visit for c in visit) / FRAME)
        took.append(visit[-1][2] - visit[0][2])
    u["track"] = bool(len(spans) >= TRACK_VISITS and np.median(spans) > TRACK_SPAN)
    spin = SPIN.get(u["key"][0])
    if u["track"] and spin and u["z"]:
        carried = 2 * math.pi * spin[0] / (spin[1] * 3600) * float(np.median(took)) / (u["z"] * IFOV[u["key"][2]]) / FRAME
        u["track"] = carried >= TRACK_CARRY * float(np.median(spans))
    u["movie"] = u["jump_frac"] is not None and (u["jump_frac"] < MOVIE_JUMPS or (u["dwell"] or 0) >= MOVIE_DWELL or u["track"])
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
    # laps over places the camera drifted off (slots, as a mosaic movie plays them) are laps, not new places
    laps = _slot_laps(u)
    u["slot_laps"] = len(places) >= 2 and u["repeats"] < MOVIE_LAPS <= laps
    u["repeats"] = max(u["repeats"], laps)
    # (a pan along a ring, where every frame shows nearly the same rings, looks like a movie, but a pan across the
    # rings is a good strip mosaic, and the pointing alone cannot tell them apart: the window's chip decides those)
    u["mosaic"] = u["whole"] = u["revisit"] = u["drift"] = False
    u["kind"] = "movie" if u["movie"] else None
    if u.get("views"):
        # laps of one view (units): a time series, a movie (C44SA_APPRMOVB001's colour set of Saturn every 104 minutes)
        u["movie"], u["kind"], u["revisit"], u["pair"], u["slot_laps"] = True, "movie", True, False, False
        return
    # two places whose tiles touch (ISS_C24JU_1X2NITE, a 2x2 seen by one camera as two) are a 1x2 mosaic
    u["pair"] = len(places) == 2 and max(abs(places[0][0] - places[1][0]), abs(places[0][1] - places[1][1])) <= PAIR_STEP * FRAME
    if len(places) < MIN_PLACES and not u["pair"] or u["movie"]:
        u["pair"] = u["slot_laps"] = False
        return
    pts = np.array(pts)
    lo, hi = pts.min(0) - FRAME / 2, pts.max(0) + FRAME / 2
    if (hi - lo).max() >= MAX_FRAMES * FRAME:
        u["pair"] = u["slot_laps"] = False
        return
    kind = "mosaic_movie" if len(places) >= 2 and u["repeats"] >= MOVIE_LAPS else "mosaic"
    if kind == "mosaic" and _one_view(u):
        # a filter set taken as the camera drifts, or one place: its frames and colour sets, no mosaic
        u["drift"], u["pair"] = True, False
        return
    if kind == "mosaic" and _revisits(u):
        # a time series: a movie
        u["movie"], u["kind"], u["revisit"], u["pair"] = True, "movie", True, False
        return
    u["mosaic"] = True
    u["kind"] = kind
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    u["whole"] = bool(radius and (lo < -radius).all() and (hi > radius).all())


_unit_of = {}   # frame id -> unit_of's answer (the passes of an observation are worked out once, units)
UNIT_OF_KEEP = 200000


def unit_of(frame_id):
    """(unit, index of the newest tile at that frame) for the pass frame_id is in, or None."""
    with _lock:
        if frame_id in _unit_of:
            return _unit_of[frame_id]
    idx, row = _row_of()
    q = row.get(frame_id)
    if q is None:
        return None
    r = idx.iloc[q]
    cam = "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"
    t = float(r["seconds_1970"])
    found = None
    for u in units(r["TARGET_NAME"], r["OBSERVATION_ID"], cam):
        ts = [fr[3] for fr in u["frames"]]
        if ts and ts[0] <= t <= u["last"]:
            # (a frame _drop_strays took out of the pass is in none)
            found = None if frame_id in u.get("off", ()) else (u, sum(1 for x in ts if x <= t + 1) - 1)
            break
    with _lock:
        if len(_unit_of) >= UNIT_OF_KEEP:
            _unit_of.clear()
        _unit_of[frame_id] = found
    return found


def kind_of(frame_id):
    """What the camera windows do with the frames of frame_id's observation (one camera): {"mosaic": its pass is
    a mosaic, "movie": every pass of the observation with the camera moving is a movie or a stare, so its frames
    never make a mosaic of any kind and the window need not ask, "kind": its pass's kind (mosaic, movie,
    mosaic_movie or None), "repeats": its laps, "lap_ends": the ids of the frames that finish a lap of its mosaic
    movies, when it has any}."""
    found = unit_of(frame_id)
    if not found:
        return {"mosaic": False, "movie": False, "kind": None}
    us = units(*found[0]["key"][:3])
    judged = [v for v in us if v["jump_frac"] is not None]
    # lap_ends: the frames of the observation's mosaic movies that finish a lap, for Whole mosaics (lap_ends)
    ends = [v["frames"][j][1] for v in us for j in lap_ends(v)]
    return {"mosaic": bool(found[0]["mosaic"]), "movie": bool(judged) and all(v["movie"] for v in judged),
            "kind": found[0]["kind"], "repeats": found[0]["repeats"], **({"lap_ends": ends} if ends else {})}


def folder(u, cache):
    # a movie's frames stacked with a shorter repeat window are other pictures than the ones made before it
    gap = u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP)
    suffix = (("" if gap >= mosaic_benchmark.REPEAT_GAP else f"_r{gap:g}")
              + (RELAID if u.get("relaid") else GROUPING if u.get("regrouped") else ""))
    return os.path.join(cache, f"{VERSIONS[calibration.style()]}{calibration.variant()}-q{QUALITY}", "_".join(map(str, u["key"])) + suffix)


def drawn(u, cache):
    """The folder of the pass's mosaics as drawn (its filter mosaics and pictures, its mosaic movie's): the pass's own
    folder with the blend step off, as they were drawn before it, else a folder of it named for the blend and level
    steps (mosaic.drawing). The tiles, the plan and the seams do not depend on them and stay in the pass's folder."""
    name = mosaic.drawing()
    return os.path.join(folder(u, cache), name) if name else folder(u, cache)


def _ulock(u):
    with _lock:
        return _unit_locks.setdefault(u["key"], threading.RLock())


PLAN_FILE = "plan4.json"   # renamed when the plan's rules change, so cached plans are worked out again
# a movie's footprint (movie_footprint), worked out with the plan and named after it, so a new plan redoes it
FOOTPRINT_FILE = "movie_footprint-" + PLAN_FILE
# a feature track's steady places (track_places), and its footprint drawn from them; renamed (with the track's movie
# frames, movie_webp) whenever the rule changes
TRACK_FILE = "track2-" + PLAN_FILE
TRACK_FOOTPRINT_FILE = "movie_footprint-" + TRACK_FILE


def _tiles(u, cache, scale):
    """The folder of the pass's tiles made on this display scale: a plan that changes its scale (its rules
    changed) makes its tiles again instead of drawing them next to tiles on the old one."""
    return os.path.join(folder(u, cache), "tiles-" + hashlib.md5(json.dumps(scale, sort_keys=True).encode()).hexdigest()[:8])


def _pic(u, cache, scale, t):
    """The picture tile t is drawn from: its own (_tiles/<n>.png), or the one its layout gave it (t["pic"]: its
    surface redrawn as at the mosaic's epoch, surface_pictures)."""
    return t.get("pic") or os.path.join(_tiles(u, cache, scale), f"{t['n']}.png")


# ---------- what the cache holds of a pass, kept in memory ----------
# A pass's plan, its movie footprint and its tiles' reports are each written once and never change (the plan file is
# renamed when its rules change, the tiles' folder is named after the plan's display scale): each is read from the
# cache once and kept here, so the layout of the pass's mosaic at tile n (the reports of tiles 0..n), which every
# mosaic, mosaic movie picture, tile map and look-ahead works out, comes from memory instead of a file per tile per
# request. A pass's record is kept with its plan file's identity (inode and mtime), which every plan() looks at: a
# pass whose cache folder was cleared or made again is read from the cache afresh. Only what is made is kept, so a
# tile not in memory is looked for in the cache (a server sharing the cache may have made it).
PASSES_KEEP = 64   # passes kept in memory, the most recently used (a pass's tile reports are ~1 KB each)
# plan file -> {"stamp", "plan", "scale", "tiles_dir", "tiles": {n: report}, "made": tiles seen in the cache (not read),
# "footprint", "rolled": {(size, out, fade): frames whose mosaic movie picture is made, rolling_ahead}, "mapped": the last
# tile whose mosaic's tile map is worked out, _map_later}
_passes = collections.OrderedDict()


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns


def _plan_path(u, cache):
    return os.path.join(folder(u, cache), PLAN_FILE)


def _record(u, cache):
    """The pass's record in memory, while its plan file is the one it was read from (one stat); else None."""
    path = _plan_path(u, cache)
    with _lock:
        rec = _passes.get(path)
    if rec is None:
        return None
    if _stamp(path) != rec["stamp"]:
        with _lock:
            if _passes.get(path) is rec:
                del _passes[path]
        return None
    with _lock:
        if path in _passes:
            _passes.move_to_end(path)
    return rec


def _keep_plan(u, cache, p, stamp):
    rec = {"stamp": stamp, "plan": p, "scale": p["display_scale"], "tiles_dir": _tiles(u, cache, p["display_scale"]),
           "tiles": {}, "made": set(), "footprint": None, "track_footprint": None, "track": None, "steady": None, "exposure": None, "rolled": {}}
    path = _plan_path(u, cache)
    with _lock:
        _passes[path] = rec
        _passes.move_to_end(path)
        while len(_passes) > PASSES_KEEP:
            _passes.popitem(last=False)
    return rec


def _kept_tiles(u, cache, scale):
    """The pass's record when scale is its kept plan's display scale (no stat: plan() looked at it); else None."""
    with _lock:
        rec = _passes.get(_plan_path(u, cache))
    return rec if rec is not None and rec["scale"] is scale else None


def _reports(u, cache, p, js):
    """The reports of tiles js of the pass (on its plan p's scale), in that order: from memory, the others from the
    cache (or made, as tile() does)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _lock:
        kept = dict(rec["tiles"]) if rec is not None else {}
    return [kept.get(j) or tile(u, j, cache, p["display_scale"]) for j in js]


def _has_tile(u, j, cache, p):
    """Whether tile j of the pass is made: known in memory, or its report file in the cache (then remembered: a
    pass's tiles stay while its plan file does)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is not None and (j in rec["tiles"] or j in rec["made"]):
        return True
    there = os.path.exists(os.path.join(rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"]), f"{j}.json"))
    if there and rec is not None:
        with _lock:
            rec["made"].add(j)
    return there


def _all_made(u, cache, p, first, last, look=False):
    """Whether tiles first..last of the pass are all made, as far as memory knows (read once, or seen in the
    cache); look: those memory does not know are looked for in the cache (a server started on a made cache)."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is None:
        return False
    with _lock:
        unknown = [j for j in range(first, last + 1) if j not in rec["tiles"] and j not in rec["made"]]
    return not unknown or (look and all(_has_tile(u, j, cache, p) for j in unknown))


def plan(u, cache):
    """The pass's display scale, rotation, footprint, view mode and colour filters, worked out once and kept."""
    path = _plan_path(u, cache)
    rec = _record(u, cache)
    if rec is not None:
        return rec["plan"]
    with _ulock(u):
        rec = _record(u, cache)
        if rec is not None:
            return rec["plan"]
        if os.path.exists(path):
            stamp = _stamp(path)
            with open(path) as fh:
                p = json.load(fh)
            _keep_plan(u, cache, p, stamp)
            return p
        frames = u["frames"]
        count, nms = {}, {}
        for fr in frames:
            count[fr[2]] = count.get(fr[2], 0) + 1
            nms[fr[2]] = fr[4]
        # the filters chosen from those pointed at the body: a pass whose most taken filter looks beside it (the
        # clear frames of ISS_C23RI_RMOV001_PRIME are a frame further off Jupiter, on dark sky) is drawn in
        # the filters that see the body, not as a black mosaic of that sky
        aside = _aside(frames, u)
        count = {f: c for f, c in count.items() if f not in aside} or count
        colour = colour_of(count, nms)
        # a long movie's scale from frames spread evenly over it, each filter's on its own (a step in time could
        # fall in step with the filter wheel and miss a filter): the same scale, without reading every frame first
        picks = []
        for f in count:
            mine = [fr for fr in frames if fr[2] == f]
            picks += mine[::max(1, math.ceil(len(mine) / SCALE_FRAMES))]
        levels = {}
        scale = pass_scale(sorted(picks, key=frames.index), u, colour or [max(count, key=count.get)],
                           bool(colour and colour[1] == "GRN" and colour[2] in reel.TRUE_BLUES), lit_levels=levels)
        # the rotation from the camera's frame to north up: the angle between where the geometry cache puts
        # the body and where processed_frame does, from the first tile placed well off the body's centre
        angle, ref = 0.0, None
        for k, fr in enumerate(frames):
            if fr[7] and math.hypot(fr[5], fr[6]) > 200:
                rep = tile(u, k, cache, scale)
                if "native_offset" in rep:
                    fo = rep["native_offset"]
                    angle = math.atan2(fo[1], fo[0]) - math.atan2(-fr[6], -fr[5])
                    ref = fr[1]
                    break
        x0, y0, x1, y1 = footprint(u, angle, ref, aside)
        view = [x1 - x0, y1 - y0]
        p = {"key": list(u["key"]), "display_scale": scale, "angle": angle, "footprint": [x0, y0, x1, y1],
             "fixed": True, "view": view, "k": CANVAS / max(view), "colour": colour,
             "grey": max(count, key=count.get), "whole": u["whole"]}
        p["luminance"] = luminance_of(count, p["grey"], levels)
        reel._cached(path, lambda: json.dumps(p).encode())
        stamp = _stamp(path)
        if stamp is not None:
            # kept as it reads back from its file (lists, not tuples): the plan every later request gets
            p = json.loads(json.dumps(p))
            _keep_plan(u, cache, p, stamp)
        return p


def footprint(u, angle, ref, aside=()):
    """The canvas rectangle [x0, y0, x1, y1] round pass u's frames (but those of the filters aside), turned north up
    by angle, which the frame ref was measured at (plan). A pass the camera turns under (TWIST: 033RI_AZDKMRHPH001
    turns 134 degrees, 173RI_DRCLOSE001 5 degrees 22,000 px from Saturn's centre) has each frame turned by its own
    angle from the geometry cache (processed_frame turns it by that angle), measured from frame ref (or, with none,
    by that angle alone): one angle for the whole pass put its footprint where the tiles are not, and cut them off
    or left the canvas nearly empty."""
    turned = u.get("twist") or {}

    def turn(fid):
        if fid not in turned:
            return angle
        return angle + math.radians(turned[ref] - turned[fid]) if ref in turned else math.pi - math.radians(turned[fid])
    pts, ks = [], []
    # the footprint of the filters drawn: frames of a filter left out (aside) would only hold empty canvas
    for _, fid, f, _, _, x, y, z in u["frames"]:
        if z and f not in aside:
            k = z / u["z"]
            c, s = math.cos(turn(fid)), math.sin(turn(fid))
            pts.append(((c * -x - s * -y) * k, (s * -x + c * -y) * k))
            ks.append(k)
    if not pts:
        pts, ks = [(0.0, 0.0)], [1.0]
    # (and room round them for what registration may move a tile by, REGISTER_MAX and PANEL_MAX)
    room = HALF + ((REGISTER_MAX + PANEL_MAX) * FRAME if turned else 0)
    return [min(p[0] - room * k for p, k in zip(pts, ks)), min(p[1] - room * k for p, k in zip(pts, ks)),
            max(p[0] + room * k for p, k in zip(pts, ks)), max(p[1] + room * k for p, k in zip(pts, ks))]


ASIDE_SHARE = 0.25   # of the frames of the filter taken most: a filter with fewer never sets where the pass points (_aside)


def _aside(frames, u, share=ASIDE_SHARE, disk=True):
    """The filters whose frames point, as a rule, more than half a frame further from the body's centre than the
    filter pointed closest (median over each filter's placed frames, at the pass's reference distance) among those
    taken at least share as often as the filter taken most, and off the body's disk (RADIUS, when disk and the body's
    size is known). In ISS_C23RI_RMOV001_PRIME the colour frames sit 316 px from Jupiter's centre, on the disk, and
    the clear and IR1 frames 1331 px out, beside it; the filters of a mosaic share their pointings and come out within
    pixels. (Measured from any filter, a lone frame near the middle, the one IR2/IR1 frame of 044RI_PHOTDRK003's 96,
    put every other filter aside, and the mosaic was that one frame; so did a close flyby's frames scattered over
    Titan's disk, 005TI_HIGHRESNA001's one MT1 frame left of five.)"""
    far = {}
    for fr in frames:
        if fr[7]:
            far.setdefault(fr[2], []).append(math.hypot(fr[5], fr[6]) * fr[7] / u["z"])
    med = {f: sorted(v)[len(v) // 2] for f, v in far.items()}
    if not med:
        return set()
    most = max(len(v) for v in far.values())
    near = min(m for f, m in med.items() if len(far[f]) >= share * most)
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]]) if disk and u["z"] else 0
    return {f for f, m in med.items() if m > near + FRAME / 2 and m > radius}


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
    # a clear frame is no color: it is left out wherever the color filters still make a set of their own (it
    # sees several times their light, so as a channel it outshines them, green on Saturn's rings)
    plain = [f for f in count if f != "CL1/CL2" and not _polarizer(f)]
    if len([f for f in plain if count[f] >= most / 2]) >= 3:
        count = {f: count[f] for f in plain}
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


# ---------- the luminance base (placed tiles) ----------
# A pass's mosaic is drawn on a gray base made from every tile it has placed so far, each where SPICE puts it, and its
# colour is laid over that base only where all three colour filters have the picture, fading into the gray at that
# edge. So the mosaic never shrinks when its colour begins (the colour picture alone is only the ground all three
# filters cover), and its gray never changes filter part way through a pass. The gray is the plan's grey filter
# wherever the pass takes it; the pass's other filters fill in only the places that filter never covers (a scan
# that steps one filter a pointing, a colour pointing without a clear frame), each brought to the grey filter's
# brightness by its gain.
LUM = "L"                # the luminance base, where a filter's name goes (filter_mosaic, its cache files)
LUM_GAIN = (0.25, 4.0)   # the furthest a band's gain to the grey filter's level goes
LUM_FEATHER = 64         # px on the benchmark's 0.5 scale canvas (as mosaic.feather_px): colour fades into gray over this


def luminance_of(count, grey, levels):
    """The plan's luminance base: {"filters": the filters it may draw (the pass's less polarizers, the grey filter
    first), "gains": {filter: linear gain bringing its lit median (pass_scale's levels) to the grey filter's}}."""
    filters = [grey] + sorted(f for f in count if f != grey and not _polarizer(f))
    ref = levels.get(grey) or 0.0
    gains = {}
    for f in filters[1:]:
        if ref > 0 and levels.get(f, 0) > 0:
            gains[f] = round(float(np.clip(ref / levels[f], *LUM_GAIN)), 4)
    return {"filters": filters, "gains": gains}


def _luminance(p):
    # (a plan made before the luminance base: its grey filter alone)
    return p.get("luminance") or {"filters": [p["grey"]], "gains": {}}


def lum_frames(u, p):
    """The frames the pass's luminance base draws (indices into u["frames"], as tiles are numbered): every frame of
    the grey filter, and a frame of another of its filters where no frame of the grey filter is at that place
    (within SAME_PLACE of a frame) anywhere in the pass, from the geometry cache, so the set only grows as the pass
    goes on and each mosaic grows from the one before. Kept with the pass."""
    lum = _luminance(p)
    key = tuple(lum["filters"])
    hit = u.get("_lum")
    if hit and hit[0] == key:
        return hit[1]
    grey, allowed = lum["filters"][0], set(lum["filters"])

    def at(fr):
        return (-fr[5] * fr[7] / u["z"], -fr[6] * fr[7] / u["z"]) if fr[7] and u["z"] else None
    greys = [q for q in (at(fr) for fr in u["frames"] if fr[2] == grey) if q]
    out = set()
    for j, fr in enumerate(u["frames"]):
        if fr[2] == grey:
            out.add(j)
        elif fr[2] in allowed:
            q = at(fr)
            if q is None or not any(math.hypot(q[0] - g[0], q[1] - g[1]) <= SAME_PLACE * FRAME for g in greys):
                out.add(j)
    out = frozenset(out)
    u["_lum"] = (key, out)
    return out


def _mine(u, p, tiles, f):
    """The placed tiles filter_mosaic draws for f: the filter's own, or for LUM the luminance base's (lum_frames),
    a band other than the grey filter carrying its gain (applied by _shade)."""
    if f != LUM:
        return [t for t in tiles if t["filter"] == f and "offset" in t]
    lum, frames = _luminance(p), lum_frames(u, p)
    gamma = p["display_scale"].get("gamma", 2.2)
    out = []
    for t in tiles:
        if "offset" in t and t["n"] in frames:
            g = lum["gains"].get(t["filter"], 1.0)
            out.append(dict(t, gain=g, gamma=gamma) if g != 1.0 else t)
    return out


_luts = {}


def _shade(part, t):
    """A tile's picture (RGBA at its canvas size) with its tile dict's "gain" applied: the luminance base's gain of
    a band other than the grey filter, on linear brightness (the pass's display gamma, t["gamma"]), alpha as it
    is. The same array when the tile has none."""
    g = t.get("gain")
    if not g or g == 1.0:
        return part
    key = (g, t.get("gamma", 2.2))
    lut = _luts.get(key)
    if lut is None:
        v = np.arange(256, dtype=np.float64) / 255
        lut = _luts[key] = (calibration.encode(np.clip(calibration.decode(v, key[1]) * g, 0, 1), key[1]) * 255
                            + 0.5).astype(np.uint8)
    out = part.copy()
    out[..., :3] = lut[part[..., :3]]
    return out


def lum_base(u, p, tiles, used):
    """Whether the mosaic of these tiles, drawn in the filters used, needs its luminance base under it: a tile of
    the base sits where the picture would otherwise have nothing (no tile of every colour filter at its place, or,
    drawn in gray, a tile of a filter other than the one drawn)."""
    frames = lum_frames(u, p)
    base = [t for t in tiles if "offset" in t and t["n"] in frames]
    if len(used) != 3:
        return any(t["filter"] != used[0] for t in base)
    by = {f: [t["offset"] for t in tiles if t["filter"] == f and "offset" in t] for f in used}
    near = lambda o, os_: any(math.hypot(o[0] - q[0], o[1] - q[1]) <= SAME_PLACE * FRAME for q in os_)
    return any(not all(near(t["offset"], by[f]) for f in used) for t in base)


LUM_MATCH = (0.25, 4.0)   # the furthest the gray's match to the colour it borders goes, per channel
LUM_MATCH_MIN = 500       # lit pixels each side needs for the match; fewer, and the gray stays as it is


def match_grey(colour, grey, ca, only, feather, gamma):
    """The gain per channel (linear brightness) that brings the gray base to the colour it borders: the colour's
    median over the gray's where both lie under the picture, or, where the gray only goes on past the colour (a
    colour tile beside gray ones), the colour's within two feathers of that edge over the gray's within two feathers
    on its side. So the gray continues the colour's brightness and its average hue (Titan's gray reads orange beside
    its orange disk, a dim clear-filter gray is lifted to the colour beside it), and the detail stays the gray's.
    None when either side has too little lit picture to measure."""
    lin = lambda v: calibration.decode(v.astype(np.float32) / 255, gamma)
    ga = grey[..., 3] > 250
    both = (ca > 0.99) & ga
    if both.sum() >= LUM_MATCH_MIN:
        cside, gside = both, both
    else:
        near = 2 * feather
        to_only = cv2.distanceTransform((~only).astype(np.uint8), cv2.DIST_L2, 5)
        to_colour = cv2.distanceTransform((ca < 0.99).astype(np.uint8), cv2.DIST_L2, 5)
        cside, gside = (ca > 0.99) & (to_only <= near), only & ga & (to_colour <= near)
    g = lin(grey[..., 0])
    rgb = lin(colour[..., :3] / np.maximum(ca, 1 / 255)[..., None])
    gl = g[gside]
    cl = rgb[cside]
    # lit: above a tenth of each side's bright end, so sky and the night side do not set the match
    gl = gl[gl > 0.1 * np.percentile(gl, 99)] if gl.size else gl
    cl = cl[cl.mean(axis=1) > 0.1 * np.percentile(cl.mean(axis=1), 99)] if len(cl) else cl
    if gl.size < LUM_MATCH_MIN or len(cl) < LUM_MATCH_MIN or np.median(gl) <= 0:
        return None
    return np.clip(np.median(cl, axis=0) / np.median(gl), *LUM_MATCH).astype(np.float32)


def grey_gain(colour, grey, k, gamma=2.2):
    """The match over_grey gives the gray base under this colour picture (match_grey), or None (no match, or no
    gray past the colour)."""
    ca = colour[..., 3].astype(np.float32) / 255
    only = (grey[..., 3].astype(np.float32) / 255 > 0.5) & (ca < 0.5)
    if not only.any():
        return None
    return match_grey(colour, grey, ca, only, max(8, round(LUM_FEATHER * k / 0.5)), gamma)


def tinted(grey, gain, gamma=2.2):
    """The gray (its first channel, levels) given the per channel gain on linear brightness: levels, float, 3 channels."""
    if gain is None:
        return np.repeat(grey[..., :1].astype(np.float32), 3, axis=2)
    return calibration.encode(np.clip(calibration.decode(grey[..., :1].astype(np.float32) / 255, gamma) * gain, 0, 1), gamma) * 255


def over_grey(colour, grey, k, gamma=2.2, gain=...):
    """The colour picture (colour_picture: its colour times where all three filters cover) laid over the luminance
    base (grey, RGBA on the same canvas): colour where all three filters cover, the gray elsewhere, the colour fading
    into the gray over LUM_FEATHER (at this canvas's scale) inward from where the gray goes on past it. The gray is
    first matched to the colour it borders (match_grey), so the join shows no step in brightness or hue. Where
    nothing lies beyond the colour (the mosaic's own edge) it keeps its edge as colour_picture drew it. gain: the
    match worked out already (grey_gain, on the whole mosaic: a native mosaic's blocks, mosaic_native)."""
    ca = colour[..., 3].astype(np.float32) / 255
    ga = grey[..., 3].astype(np.float32) / 255
    only = (ga > 0.5) & (ca < 0.5)   # the gray goes on past the colour
    if not only.any():
        return colour
    feather = max(8, round(LUM_FEATHER * k / 0.5))
    if gain is ...:
        gain = match_grey(colour, grey, ca, only, feather, gamma)
    under = grey[..., :3].astype(np.float32) if gain is None else tinted(grey, gain, gamma)
    dist = cv2.distanceTransform((~only).astype(np.uint8), cv2.DIST_L2, 5)
    w = ca * np.clip(dist / feather, 0, 1)
    rgb = colour[..., :3].astype(np.float32) / np.maximum(ca, 1 / 255)[..., None]
    out = rgb * w[..., None] + under * (ga * (1 - w))[..., None]
    alpha = w + ga * (1 - w)
    return np.dstack([np.clip(out + 0.5, 0, 255).astype(np.uint8), np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8)])


FILLED = 0.5       # a pass is all body when the body's disk covers the middle of more than this share of its frames
DETAIL = 2.0       # filled passes: how much the local contrast is raised (detail())
DETAIL_SIGMA = 0.05  # ... over this much of a frame


SKY_MIN = 0.05   # balanced: the share of a pass's pixels that must be dark sky for its blacks to be set from the sky
# ... measured on the darker half of the sky: the noise floor at this percentile above its median (a single
# picture's is the 98th; lower here, since a long-exposure pass's whole sky can glow faintly, Saturn's Shadow's E ring)
SKY_FLOOR_PCT = 90
SKY_TOP_PCT = 99     # ... and each band's black at least this percentile of that dark sky (a single picture's SKY_DARK)
SKY_SMOOTH = 9      # ... on the sky less its mean over this many pixels (of the quarter-size frames, 36 full size)
SKY_TOE = 1.0    # ... and the soft toe above those blacks, this many times the black's height over the sky wide
                 # (calibration.display): the sky's scan lines, not its pixel noise, set how far grain reaches


def _sky_fine(iofs, masks):
    """The sky's fine structure in the pictures iofs (sky masks): the sky less its own mean over SKY_SMOOTH pixels
    (row and column stray-light stripes, compression blocks, noise), on the darker half of the sky by its 5 pixel
    mean, as one array. Smooth faint light (haze, a ring, the body's glow) is not in it."""
    local = [cv2.blur(i, (5, 5)) for i in iofs]
    sky = np.concatenate([l[m] for l, m in zip(local, masks)])
    return np.concatenate([(i - cv2.blur(i, (SKY_SMOOTH, SKY_SMOOTH)))[m & (l <= np.median(sky))]
                           for i, l, m in zip(iofs, local, masks)])


def tile_scale(scale, f, own_sky=False, seen=None):
    """The display scale of one tile of filter f: the pass's, and with own_sky (a movie's frames, each shown
    alone) a black raised to the frame's own sky level plus the band's height over it (sky_tops) where that sky
    sits above the pass's: in the Jupiter approach movie one color set's stray light lifts its sky over the
    pass's level, and its frame showed as an olive square that the next set's didn't. Never lowered (the sky's
    stripes would come back as a veil), and never in a mosaic, whose tiles meet (one tile's black of its own
    shows as a step). seen: a dict the raised black is put in."""
    out = {**scale, "blacks": [scale["blacks"].get(f, 0.0)]}
    top = scale.get("sky_tops", {}).get(f)
    if not own_sky or top is None:
        return out
    black = out["blacks"][0]

    def black_of(iof):
        # the frame's sky as pass_scale finds it, at the size it measures on
        q = iof[::4, ::4].astype(np.float32)
        m = q < 0.05 * np.percentile(q, 99.9)
        if m.mean() <= SKY_MIN:
            return None
        (level,), _ = calibration.sky_levels([[q]], [[m]])
        # the band's height over the sky at least this frame's own (its sky's fine structure, as pass_scale measures
        # the pass's): a frame lit by stray light has a grainier sky than the pass's typical one, and in the Jupiter
        # approach movie its red and green grain rose over a black set by the pass's height, a faint red cast
        fine = _sky_fine([q], [m])
        own = float(np.percentile(fine, SKY_TOP_PCT) - np.median(fine)) if fine.size > 100 else 0.0
        raised = level + max(top, own)
        if raised <= black:
            return None
        if seen is not None:
            seen["black"] = raised
        return {"black": raised, "toe": scale.get("toe")}

    out["black_of"] = black_of
    return out


def pass_scale(frames, u, drawn=None, true_colour=False, sky_tops=None, lit_levels=None):
    """The display scale of every tile of the pass (calibration.shared_scale over its frames merged in I/F, as
    mosaic_benchmark.display_scale): {"blacks": {filter: I/F}, "white": I/F, "gamma"}. Where the body fills
    the frames (the middle of most frames on its disk, as in Titan's maps), black goes to the darkest of the body, white to
    the 99.5th percentile and the gamma is eased, and the mosaic's local contrast is raised (detail), so
    the surface's few per cent of contrast shows; passes with dark sky keep the benchmark's scale.
    drawn = the filters the mosaic is drawn from (plan's colour, or its grey filter); true_colour = they are a
    true colour set; sky_tops = optional {filter: I/F} overriding how far above its sky each filter's black sits
    (the measured values come back as "sky_tops", with the soft "toe" above black). lit_levels: a dict given here gets
    each filter's lit median on the scale (linear, white = 1), which the luminance base's gains come from; the
    scale itself is the same with or without it."""
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
    radius = FILL_RADIUS.get(u["key"][0], 0) / IFOV[u["key"][2]]
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
    toe = None
    if calibration.look() == "balanced":
        # where the pass has dark sky, no band's black below that sky's level plus the noise margin, as a single
        # picture's (calibration.sky_levels): the 1st percentile of a pass that is mostly sky sits in the sky's
        # noise, so the sky came out a gray, scan-lined veil around the body once the tiles were put together
        masks = {f: [i < 0.05 * np.percentile(i, 99.9) for i in iofs] for f, iofs in by.items()}
        if all(sum(int(m.sum()) for m in ms) > SKY_MIN * sum(m.size for m in ms) for ms in masks.values()):
            levels, margin = calibration.sky_levels(list(by.values()), list(masks.values()))
            # How far each band's black sits over its sky is measured on the sky's fine structure only: the sky
            # less its own mean over SKY_SMOOTH pixels (its row and column stray-light stripes, compression
            # blocks and noise), on the darker half of the sky. Smooth faint light (Saturn's Shadow's haze and E
            # ring, a haze limb, the body's glow) is not in it, so it stays above black
            fine = {f: _sky_fine(iofs, masks[f]) for f, iofs in by.items()}
            # with a noise floor (the noisiest band's SKY_FLOOR_PCT percentile above the median): the pixel-difference
            # noise is about 0 on frames stored in 8 bits
            margin = max(margin, calibration.noise_floor(list(fine.values()), SKY_FLOOR_PCT))
            # and each band on its own over SKY_TOP_PCT of that fine structure: the false color gains (MT3's up to
            # 5x) lift whatever of a dim band's sky is left above its black far more than the others'
            tops = {}
            for f, v in fine.items():
                if sky_tops and f in sky_tops:
                    tops[f] = float(sky_tops[f])
                else:
                    top = float(np.percentile(v, SKY_TOP_PCT) - np.median(v)) if v.size > 100 else 0.0
                    tops[f] = max(margin, top)
            toe = SKY_TOE * max(tops.values())
            blacks = {f: max(blacks[f], level + tops[f]) for f, level in zip(by, levels)}
    out = {"blacks": blacks, "white": white, "gamma": gamma, "filled": filled, "floor": round(floor, 3)}
    if toe:
        out["toe"], out["sky_tops"] = toe, tops
    mine = [f for f in (drawn or []) if f in by]
    if calibration.style() == "balanced" and len(mine) == 3 and not true_colour:
        # false color: each band's gain to bring the body's lit median (above that band's black) to the bands'
        # mean, so the planet comes out gray and only its differences between bands show (calibration.false_gains);
        # measured on the whole pass, so every tile has the same balance
        levels = []
        for f in mine:
            v = np.concatenate([i.ravel() for i in by[f]]) - blacks[f]
            lit = v[v > 0.2 * np.percentile(v, 99)]
            levels.append(float(np.median(lit)) if lit.size else 0.0)
        if min(levels) > 0:
            out["balance"] = dict(zip(mine, calibration.balance(levels, calibration.tint_of(u["key"][0]))))
            # and the body's typical color after it, so the broad-color flattening holds one color as tiles arrive
            shown = [out["balance"][f] * v for f, v in zip(mine, levels)]
            out["typical"] = {f: float(np.log(v * len(shown) / sum(shown))) for f, v in zip(mine, shown)}
    if lit_levels is not None:
        for f, iofs in by.items():
            v = (np.concatenate([i.ravel() for i in iofs]) - blacks[f]) / white
            lit = v[v > 0.2 * np.percentile(v, 99)]
            lit_levels[f] = float(np.median(lit)) if lit.size else 0.0
    return out


def _lit_crop(image, side):
    """A tile's picture: image (an RGBA canvas, unlit outside the frame on it) at side x side px, the bytes PIL's
    LANCZOS resize of the whole canvas gives (the canvas itself when side is its size), cut to its lit pixels: (the
    cut, its top row, its left column), or None when no pixel is lit. Made from the lit part: PIL resizes RGBA
    premultiplied (RGBa), across and then down, each row and then each column on its own, and an unlit pixel is 0
    premultiplied, so only the rows with a lit pixel are resized across, and only the columns those leave lit are
    resized down (a movie tile's 3072 px canvas is ~1400 px lit, and the whole canvas's resize was half of making
    the tile). The lit boxes are PIL's getbbox, one pass over the pixels in C, and the resized canvas is never made
    whole (both cost more than the lit part's resize)."""
    h, w = image.shape[:2]
    box = Image.fromarray(image).getbbox(alpha_only=True)
    if box is None:
        return None
    c0, r0, c1, r1 = box
    if side == h:
        return image[r0:r1, c0:c1].copy(), r0, c0
    strip = Image.new("RGBa", (w, r1 - r0))
    strip.paste(Image.fromarray(np.ascontiguousarray(image[r0:r1, c0:c1])).convert("RGBa"), (c0, 0))
    across = strip.resize((side, r1 - r0), Image.LANCZOS)
    # the columns with anything in them, colour or alpha
    used = across.getbbox(alpha_only=False)
    if used is None:
        return None
    x0, x1 = used[0], used[2]
    tall = Image.new("RGBa", (x1 - x0, h))
    tall.paste(across.crop((x0, 0, x1, r1 - r0)), (0, r0))
    down = tall.resize((x1 - x0, side), Image.LANCZOS)
    box = down.getbbox(alpha_only=True)
    if box is None:
        return None
    return np.asarray(down.crop(box).convert("RGBA")), box[1], x0 + box[0]


def tile(u, n, cache, scale=None):
    """Tile n of the pass, made once: its picture north up, scaled to the pass's reference distance and cropped
    (_tiles/<n>.png), and its report: offset = where the frame's middle sits from the body's centre and box = the
    crop around it (reference pixels); no offset when SPICE could not place it."""
    if scale is None:
        scale = plan(u, cache)["display_scale"]
    rec = _kept_tiles(u, cache, scale)
    if rec is not None:
        with _lock:
            kept = rec["tiles"].get(n)
        if kept is not None:
            return kept
    return _tile(u, n, cache, scale, rec["tiles_dir"] if rec is not None else _tiles(u, cache, scale), rec)


def _tile(u, n, cache, scale, there, rec=None):
    """Tile n's report from the cache, or the tile made (tile) and its report, as it reads back from the cache;
    kept in the pass's record rec, so it is read once."""
    base = os.path.join(there, str(n))
    # one lock per tile, so a movie's frames made ahead can be made side by side
    with _lock:
        lock = _tile_locks.setdefault((u["key"], calibration.mode(), n), threading.RLock())
    with lock:
        if rec is not None:
            with _lock:
                kept = rec["tiles"].get(n)
            if kept is not None:
                return kept
        out = _tile_made(u, n, cache, scale, base)
        if rec is not None:
            with _lock:
                out = rec["tiles"].setdefault(n, out)
        return out


def _tile_made(u, n, cache, scale, base):
    """(_tile, holding the tile's lock) the report in base.json, or the tile made and its report."""
    if os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            return json.load(fh)
    path, fid, f, t, nm, x, y, z = u["frames"][n]
    k = z / u["z"] if z else 1.0
    seen = {}
    try:
        image, _, rep = color_image.processed_frame([path], hdr=True, scale=tile_scale(scale, f, bool(u.get("movie")), seen),
                                                    repeat_window=u.get("repeat_gap", mosaic_benchmark.REPEAT_GAP))
    except Exception as e:
        image, rep = None, {"why": f"{type(e).__name__}: {e}"[:200]}
    out = {"n": n, "id": fid, "filter": f, "t": t, "stacked": rep.get("stacked"), "calibrated": rep.get("calibrated"), **seen}
    os.makedirs(os.path.dirname(base), exist_ok=True)
    if image is not None and "frame_offset" in rep:
        side = round(image.shape[0] * k)
        lit = _lit_crop(image, side)
        if lit is not None:
            crop, a, c = lit
            b, d = a + crop.shape[0], c + crop.shape[1]
            Image.fromarray(crop).save(base + ".png", compress_level=1)
            _keep_made(base + ".png", crop)
            out.update({"native_offset": rep["frame_offset"], "offset": [v * k for v in rep["frame_offset"]],
                        "box": [int(c) - side / 2, int(a) - side / 2, int(d - c), int(b - a)]})
            _register(u, n, out, crop, cache, scale)
            out["outline"] = _corners(out, crop[..., 3])
    else:
        out["why"] = rep.get("why", "not placed by SPICE")
    data = json.dumps(out, default=str)
    reel._cached(base + ".json", data.encode)
    return json.loads(data)


REGISTER_GAP = 180   # s: a tile of another filter taken this soon before, at the same pointing, is what it is registered to
REGISTER_MAX = 0.04  # of a frame: the largest correction to SPICE's placement that is believed


def _register_to(u, n):
    """The tile tile n is registered to (_register): the first frame of the pass in another filter at its pointing
    (SAME_PLACE, by the geometry cache) taken at most REGISTER_GAP before it, so every filter of a pointing lands on
    that pointing's first frame; None for a pointing's first frame, or one SPICE (the geometry cache) has no place for."""
    frames = u["frames"]
    _, _, f, t, _, x, y, z = frames[n]
    if not z:
        return None
    k = z / u["z"] if u["z"] else 1.0
    for j in range(n):
        _, _, fj, tj, _, xj, yj, zj = frames[j]
        if fj != f and zj and 0 <= t - tj <= REGISTER_GAP and math.hypot(x - xj, y - yj) * k <= SAME_PLACE * FRAME:
            return j
    return None


def _register(u, n, out, crop, cache, scale):
    """C8, the filters registered to each other: SPICE places each frame on its own, and the few pixels its pointing
    is off differ from frame to frame, so the filters of one pointing landed a little apart and every limb had a red
    and a cyan rim (Dione). Tile n (its report out, crop its picture as made) is moved onto the tile it is registered
    to (_register_to) by the pipeline's own alignment of a set's channels (image_correction.align_with_masks: phase
    correlation, then on edges, then by the lit area's centroid) over the part of the view both cover; out["offset"]
    is changed by the shift found (out["spice_offset"] keeps SPICE's), out["registered"] says to what and how. A
    shift past REGISTER_MAX of a frame, or none found, leaves SPICE's place."""
    j = _register_to(u, n)
    if j is None or not calibration.step("align"):   # Settings > Processing: SPICE's places as they are
        return
    q = tile(u, j, cache, scale)
    path = os.path.join(_tiles(u, cache, scale), f"{j}.png")
    if "offset" not in q or not os.path.exists(path):
        return
    with _lock:
        ref = _made_pictures.get(path)
    if ref is None:
        ref = np.asarray(Image.open(path).convert("RGBA"))
    shift, how = _shift_onto(q, ref, q["offset"], out, crop, out["offset"])
    if shift is None and how is not None and how.startswith("failed"):
        out["registered"] = {"to": q["id"], "why": how[7:]}
        return
    if shift is None or math.hypot(*shift) > REGISTER_MAX * FRAME:
        if how is not None:
            out["registered"] = {"to": q["id"], "how": how, "kept": "SPICE's place"}
        return
    # align_with_masks moves the picture by -shift to land on the reference: its place moves the same way
    dx, dy = shift
    out["spice_offset"] = out["offset"]
    out["offset"] = [out["offset"][0] - dx, out["offset"][1] - dy]
    out["registered"] = {"to": q["id"], "how": how, "shift": [round(dx, 2), round(dy, 2)]}


def _shift_onto(q, ref, at_q, t, crop, at_t):
    """How far tile t (its picture crop, its middle put at at_t) is from tile q (picture ref, middle at at_q) over
    the part of the view both cover, by the pipeline's own alignment of a set's channels
    (image_correction.align_with_masks: phase correlation, then on edges, then by the lit area's centroid): (dx, dy),
    reference pixels, that t's place moves back by to land on q, and how it was found; (None, how) when nothing was
    found, (None, None) when the two hardly overlap there, (None, "failed <why>") when the alignment broke."""
    corners = []
    for s, at, im in ((q, at_q, ref), (t, at_t, crop)):
        corners.append((at[0] + s["box"][0], at[1] + s["box"][1], im))
    x0 = max(c[0] for c in corners)
    y0 = max(c[1] for c in corners)
    x1 = min(c[0] + c[2].shape[1] for c in corners)
    y1 = min(c[1] + c[2].shape[0] for c in corners)
    if x1 - x0 < 64 or y1 - y0 < 64:
        return None, None
    imgs, masks = [], []
    for cx, cy, im in corners:
        left, top = int(round(x0 - cx)), int(round(y0 - cy))
        part = im[top:top + int(y1 - y0), left:left + int(x1 - x0)]
        gray = cv2.cvtColor(np.ascontiguousarray(part[..., :3]), cv2.COLOR_RGB2GRAY)
        imgs.append(cv2.cvtColor(np.where(part[..., 3] > 0, gray, 0).astype(np.uint8), cv2.COLOR_GRAY2BGR))
        masks.append(part[..., 3] > 0)
    h = min(i.shape[0] for i in imgs)
    w = min(i.shape[1] for i in imgs)
    imgs, masks = [i[:h, :w] for i in imgs], [m[:h, :w] for m in masks]
    # the rounding of each crop's corner to whole pixels, put back on the shift found
    rest = [(cx - x0) - round(cx - x0) for cx, _, _ in corners], [(cy - y0) - round(cy - y0) for _, cy, _ in corners]
    shifts, how = [], []
    try:
        image_correction.align_with_masks(imgs, masks, 0, how, found=shifts)
    except Exception as e:
        return None, f"failed {type(e).__name__}: {e}"[:200]
    if shifts[1] is None:
        return None, how[1]
    return (shifts[1][0] + rest[0][1] - rest[0][0], shifts[1][1] + rest[1][1] - rest[1][0]), how[1]


# of a frame: the largest correction to SPICE's place of a pointing that registration is believed for. SPICE's pointing
# is 3 to 5 px off on the moons' mapping mosaics once the surface's motion between panels is taken out (median; 11 at
# most, panel_motion); a larger match is the surface's own motion, or a planet's clouds turning (Jupiter's matched 35
# px off), and moving a panel that far puts its limb off the body
PANEL_MAX = 12 / 1024
PANEL_MATCHES = 6    # earlier tiles a pointing's first tile is measured against at most (those it overlaps most)
PANEL_NARROW = 24    # px: the narrowest overlap (across) a pair of tiles is measured on
PANEL_AREA = 6000    # px: ... and the least area the two share
PANEL_NCC = 0.25     # the least the two overlaps must agree (normalized cross-correlation, detail only) once moved
PANEL_GAIN = 0.02    # ... and how much better than at SPICE's places they must agree, for a move of over half a pixel
PANEL_LEAST = 0.3    # px: a smaller move is the measure's own noise, and the pointing stays where SPICE put it
PANEL_AGREE = 2.0    # px: matches further than this from the others' median are left out
# a pass's panel registration (panel_places), kept with it; renamed whenever the rule changes
PANEL_FILE = "panels1-" + PLAN_FILE
PANEL_TAG = "-p1"    # in the name of a layout whose tiles registration moved (layout), so its pictures are its own


def _detail(gray, mask, sigma=6.0):
    """A tile's overlap for registration: its detail (the picture less its mean over sigma, measured on the mask only,
    so the tile's own edge adds none), scaled to unit spread on the mask, 0 off it."""
    m = mask.astype(np.float32)
    low = cv2.GaussianBlur(gray * m, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(m, (0, 0), sigma), 1e-3)
    d = (gray - low) * m
    sd = float(d[mask].std()) if mask.any() else 0.0
    return d / sd if sd > 1e-6 else None


def _even(a):
    """a padded with 0 to a size cv2.phaseCorrelate measures without bias: it pads to an optimal DFT size itself, and
    where that is odd its peak comes out half a pixel off (a strip 218 px wide shifted 0 measured +0.5)."""
    h, w = a.shape
    H, W = cv2.getOptimalDFTSize(h), cv2.getOptimalDFTSize(w)
    H, W = H if H % 2 == 0 else cv2.getOptimalDFTSize(H + 1), W if W % 2 == 0 else cv2.getOptimalDFTSize(W + 1)
    return cv2.copyMakeBorder(a, 0, H - h, 0, W - w, cv2.BORDER_CONSTANT, value=0)


def _agree(a, b, mask):
    """Normalized cross-correlation of a and b on mask."""
    x, y = a[mask], b[mask]
    x, y = x - x.mean(), y - y.mean()
    d = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
    return float((x * y).sum()) / d if d > 0 else 0.0


def panel_shift(q, ref, at_q, t, crop, at_t):
    """How far tile t (its picture crop, its middle put at at_t) is from tile q (picture ref, middle at at_q), where
    two pointings of a mosaic overlap: (dx, dy) reference pixels that t's place moves back by to land on q (as
    _shift_onto), and what was measured {"ncc": [at SPICE's places, moved], "area", "response"}; (None, why) when
    the overlap is too small, featureless, or the match is not believed. Measured by phase correlation (as the
    pipeline's alignment of a set's channels, image_correction.find_shift) on the detail of the two pictures over
    the part both cover, each tapered to that part's edge, so neither tile's own outline (where SPICE put it) is
    matched, and believed only when the two agree better moved than not (PANEL_NCC, PANEL_GAIN)."""
    corners = [(at[0] + s["box"][0], at[1] + s["box"][1], im) for s, at, im in ((q, at_q, ref), (t, at_t, crop))]
    x0 = max(c[0] for c in corners)
    y0 = max(c[1] for c in corners)
    x1 = min(c[0] + c[2].shape[1] for c in corners)
    y1 = min(c[1] + c[2].shape[0] for c in corners)
    if x1 - x0 < PANEL_NARROW or y1 - y0 < PANEL_NARROW:
        return None, "apart"
    grays, masks = [], []
    for cx, cy, im in corners:
        left, top = int(round(x0 - cx)), int(round(y0 - cy))
        part = im[top:top + int(y1 - y0), left:left + int(x1 - x0)]
        grays.append(part[..., :3].astype(np.float32).mean(axis=2))
        masks.append(part[..., 3] > 0)
    h, w = min(g.shape[0] for g in grays), min(g.shape[1] for g in grays)
    grays, masks = [g[:h, :w] for g in grays], [m[:h, :w] for m in masks]
    both = cv2.erode((masks[0] & masks[1]).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    area = int(both.sum())
    if area < PANEL_AREA or min(np.ptp(np.nonzero(both)[0]), np.ptp(np.nonzero(both)[1])) < PANEL_NARROW - 8:
        return None, "little overlap"
    ds = [_detail(g, both) for g in grays]
    if ds[0] is None or ds[1] is None:
        return None, "featureless"
    taper = cv2.GaussianBlur(both.astype(np.float32), (0, 0), 4.0) * both
    (dx, dy), response = cv2.phaseCorrelate(*(_even(d * taper) for d in ds))
    # (the rounding of each crop's corner to whole pixels, put back on the shift found)
    rx = [(cx - x0) - round(cx - x0) for cx, _, _ in corners]
    ry = [(cy - y0) - round(cy - y0) for _, cy, _ in corners]
    before = _agree(ds[0], ds[1], both)
    moved = image_correction.shift_image(ds[1], dx, dy)
    inner = cv2.erode(both.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=int(math.ceil(max(abs(dx), abs(dy)))) + 1) > 0
    if inner.sum() < PANEL_AREA / 2:
        return None, "little overlap once moved"
    after = _agree(ds[0], moved, inner)
    seen = {"ncc": [round(before, 3), round(after, 3)], "area": area, "response": round(float(response), 3)}
    shift = (dx + rx[1] - rx[0], dy + ry[1] - ry[0])
    if math.hypot(*shift) > PANEL_MAX * FRAME:
        return None, f"too far {shift[0]:+.1f},{shift[1]:+.1f}"
    if after < PANEL_NCC or (math.hypot(*shift) > 0.5 and after < before + PANEL_GAIN):
        return None, f"not believed {shift[0]:+.1f},{shift[1]:+.1f} ncc {before:.2f}->{after:.2f}"
    return shift, seen


def _pointing_root(u, n, roots):
    """The tile whose correction tile n takes: the tile C8 registers it to (_register_to, the first frame of its
    pointing in another filter), followed back to the pointing's first; n itself for a pointing's first tile."""
    j = _register_to(u, n)
    return roots.get(j, j) if j is not None else n


SURFACE_STEP = 16    # reference px: the grid a tile's surface motion (reproject.sky_field) is worked out on
# a pass's tiles redrawn as at its epoch (surface_pictures), kept beside its tiles; renamed whenever the rule changes
SURFACE_DIR = "surface4"
SURFACE_TAG = "-s4"  # in the name of a layout whose tiles are redrawn so (layout), so its pictures are its own
# what is seen of these is cloud or haze that moves on its own, not a surface turning with the body (Titan's
# mapping mosaic came out 25 px apart redrawn, Saturn's rings pass lost its one match): their tiles stay as taken
SURFACE_CLOUDED = frozenset({"SATURN", "JUPITER", "TITAN", "URANUS", "NEPTUNE", "VENUS", "EARTH"})
# a tile whose redrawing would stretch or squeeze its picture by more than this (the shift's change per pixel, where
# it fades to none at the limb or the terminator) stays as taken: on Rhea's mapping mosaic a limb panel shifted
# ~40 px squeezed its limb out of the picture and streaked its night side (round 5 of the panel probe)
SURFACE_STRETCH = 0.5
_spice_lock = threading.RLock()


def _with_kernels(t):
    """SPICE kernels loaded for the year of a frame taken at t (s since 1970), as label_handler.auto_center loads
    them (one year at a time); False when they cannot be."""
    import label_handler as lh
    import bootleg_autonav as ba
    year = time.gmtime(t).tm_year
    if getattr(lh, "cur_year", None) != year:
        try:
            ba.unload_kernels()
            lh.cur_year = year
            ba.load_kernels(year, year)
        except Exception as e:
            print(f"no kernels for {year}: {e}", flush=True)
            return False
    return True


def _ets(ids):
    """{frame id: et} of frames, from the geometry cache (find_target's time, IMAGE_MID_TIME)."""
    import bootleg_autonav as ba
    if not ba.GEOMETRY_CACHE or not os.path.exists(ba.GEOMETRY_CACHE):
        return {}
    db, out = ba._geometry_db(), {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        out.update(db.execute(f"SELECT frame, et FROM target WHERE version = ? AND error IS NULL AND frame IN "
                              f"({','.join('?' * len(part))})", (ba.GEOMETRY_VERSION, *part)).fetchall())
    return out


def surface_pictures(u, cache, p, tiles):
    """Surface reprojection of a mosaic's panels: {tile n: the path of its picture redrawn as at the pass's epoch}.
    A mosaic's panels are taken minutes apart, and the body turns and Cassini moves in between, so the surface under
    one place on the sky moves between panels (8 to 18 px on the moons' mapping mosaics, which SPICE predicts to 3 to
    5 px, panel_motion) while every tile is put on the body's centre: craters double or step at the seams. Each tile's
    lit surface is moved to where it was at the epoch (the pass's middle frame's time, fixed before any tile is made,
    so a mosaic grown a tile at a time stays as drawn), with SPICE's shape, orientation and Cassini's position
    (reproject.sky_field, warp_sky); the sky, the rings, the night side and the limb's edge stay where they are. Made
    once per tile and kept. {} with Settings > Processing's surface step off, for a body SPICE has no shape for, or
    when the kernels or the geometry cache cannot say; none for a clouded body (SURFACE_CLOUDED), and not a tile
    the redrawing would distort (SURFACE_STRETCH), which keeps SPICE's place and the panels step's nudge."""
    if not calibration.step("surface") or not tiles or u["key"][0] in SURFACE_CLOUDED:
        return {}
    import reproject as rp
    there = _tiles(u, cache, p["display_scale"])
    out_dir = os.path.join(there, SURFACE_DIR)
    out, todo = {}, []
    for t in tiles:
        if "offset" not in t:
            continue
        path = os.path.join(out_dir, f"{t['n']}.png")
        if os.path.exists(path):
            out[t["n"]] = path
        elif os.path.exists(os.path.join(there, f"{t['n']}.png")):
            todo.append(t)
    if not todo:
        return out
    fr = u["frames"]
    mid = fr[len(fr) // 2]
    ets = _ets([mid[1]] + [t["id"] for t in todo])
    if mid[1] not in ets:
        return out
    km_px = IFOV[u["key"][2]] * u["z"]
    with _spice_lock:
        if not _with_kernels(mid[3]):
            return out
        try:
            epoch = rp.sky_view(u["key"][0], ets[mid[1]])
        except Exception as e:
            print(f"no surface for {u['key'][0]}: {type(e).__name__}: {e}"[:200], flush=True)
            return out
        os.makedirs(out_dir, exist_ok=True)
        for t in todo:
            if t["id"] not in ets or not _with_kernels(t["t"]):
                continue
            try:
                if time.gmtime(t["t"]).tm_year != time.gmtime(mid[3]).tm_year:
                    continue   # (one year's kernels at a time: a pass across New Year keeps those tiles as they are)
                view = rp.sky_view(u["key"][0], ets[t["id"]])
            except Exception as e:
                print(f"no surface for {t['id']}: {type(e).__name__}: {e}"[:200], flush=True)
                continue
            src = os.path.join(there, f"{t['n']}.png")
            with _lock:
                image = _made_pictures.get(src)
            if image is None:
                image = np.asarray(Image.open(src).convert("RGBA"))
            h, w = image.shape[:2]
            # (the grid's first point is the tile's pixel (0, 0), at the tile's corner on the sky)
            gy, gx = np.mgrid[0:h + SURFACE_STEP:SURFACE_STEP, 0:w + SURFACE_STEP:SURFACE_STEP].astype(np.float64)
            x0, y0 = t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]
            dx, dy, weight = rp.sky_field(epoch, view, gx + x0, gy + y0, km_px)
            path = os.path.join(out_dir, f"{t['n']}.png")
            stretch = rp.field_stretch(dx, dy, weight, SURFACE_STEP)
            if stretch > SURFACE_STRETCH:
                print(f"surface: tile {t['n']} kept as taken (stretch {stretch:.2f})", flush=True)
                continue
            Image.fromarray(rp.warp_sky(image, dx, dy, weight, SURFACE_STEP)).save(path + ".part.png", compress_level=1)
            os.replace(path + ".part.png", path)
            out[t["n"]] = path
    return out


def panel_places(u, cache, p, tiles, pic=None, report=None):
    """Panel registration: {tile n: [dx, dy]}, how far each tile is moved from SPICE's place (reference pixels), so
    a mosaic's pointings line up where they overlap. SPICE places each frame on its own and its pointing is a few
    pixels off, differently for each pointing (more where the c-smithed pointing is missing, PR #5), so panels of a
    mosaic land a little apart and a limb or a crater rim steps at their seam. A pointing's first tile is measured
    (panel_shift) against the earlier tiles of other pointings it overlaps most (PANEL_MATCHES, its own filter
    first), each where it was itself put, and moved by the median of the matches that agree (PANEL_AGREE); the
    other filters of the pointing (registered onto it by C8) move with it, so its colours stay together. A pointing
    nothing matches keeps SPICE's place. Earlier pointings never move for a later one, so a mosaic grown a tile at a
    time stays as it was drawn, and every tile is worked out once and kept with the pass. {} with Settings >
    Processing's panels (or align) step off. report: a dict that gets each tile's measurements."""
    if not (calibration.step("align") and calibration.step("panels")):
        return {}
    # (measured on the tiles as drawn: their surface redrawn as at the epoch, or not, each kept apart)
    surfaced = any("pic" in t for t in tiles)
    path = os.path.join(folder(u, cache), (SURFACE_DIR + "-" if surfaced else "") + PANEL_FILE)
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _ulock(u):
        kept = rec.get("panels" + SURFACE_TAG * surfaced) if rec is not None else None
        if kept is None:
            kept = {}
            if os.path.exists(path):
                with open(path) as fh:
                    kept = {int(n): v for n, v in json.load(fh).items()}
            if rec is not None:
                rec["panels" + SURFACE_TAG * surfaced] = kept
        todo = [t for t in tiles if "offset" in t and t["n"] not in kept]
        if not todo:
            return {n: v[:2] for n, v in kept.items() if v[:2] != [0, 0]}
        there = _tiles(u, cache, p["display_scale"])
        pics = {}

        def picture(j):
            if pic is not None:
                return pic(j)
            if j not in pics:
                fp = by_n[j].get("pic") or os.path.join(there, f"{j}.png")
                with _lock:
                    pics[j] = _made_pictures.get(fp)
                if pics[j] is None:
                    pics[j] = np.asarray(Image.open(fp).convert("RGBA")) if os.path.exists(fp) else None
            return pics[j]
        by_n = {t["n"]: t for t in tiles if "offset" in t}
        roots = {}
        for t in tiles:
            if "offset" in t:
                roots[t["n"]] = _pointing_root(u, t["n"], roots)
        for t in sorted(todo, key=lambda t: t["n"]):
            n = t["n"]
            if roots[n] != n:
                kept[n] = list(kept.get(roots[n], [0, 0, "root"])[:2]) + [f"with {roots[n]}"]
                continue
            here = t["offset"]
            cands = []
            for s in by_n.values():
                if s["n"] >= n or roots.get(s["n"]) == n or s["n"] not in kept:
                    continue
                a, b = s["offset"], here
                w = min(a[0] + s["box"][0] + s["box"][2], b[0] + t["box"][0] + t["box"][2]) - max(a[0] + s["box"][0], b[0] + t["box"][0])
                h = min(a[1] + s["box"][1] + s["box"][3], b[1] + t["box"][1] + t["box"][3]) - max(a[1] + s["box"][1], b[1] + t["box"][1])
                if w >= PANEL_NARROW and h >= PANEL_NARROW:
                    cands.append((s["filter"] != t["filter"], -w * h, s["n"]))
            found, seen = [], {}
            mine = picture(n)
            for _, _, j in sorted(cands)[:PANEL_MATCHES]:
                ref = picture(j)
                if ref is None or mine is None:
                    continue
                s = by_n[j]
                # measured where SPICE put both (the overlap SPICE says, the same however far the earlier one has
                # been moved), and taken from where the earlier one now is
                shift, how = panel_shift(s, ref, s["offset"], t, mine, here)
                seen[j] = how if shift is None else {**how, "shift": [round(shift[0], 2), round(shift[1], 2)]}
                if shift is not None:
                    was = kept.get(j, [0, 0])
                    found.append((was[0] - shift[0], was[1] - shift[1]))
            move = [0.0, 0.0]
            if found:
                f = np.array(found)
                mid = np.median(f, axis=0)
                ok = f[np.hypot(*(f - mid).T) <= PANEL_AGREE]
                if len(ok) and (len(ok) * 2 > len(f) or len(f) == 1) and math.hypot(*ok.mean(axis=0)) >= PANEL_LEAST:
                    move = [round(float(v), 2) for v in ok.mean(axis=0)]
            kept[n] = move + [f"{len(found)} of {len(seen)}"]
            if report is not None:
                report[n] = {"move": move, "matches": seen}
        # (kept again as it grows: a later tile's moves add to it, earlier ones never change)
        part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(part, "w") as fh:
                json.dump({str(n): v for n, v in sorted(kept.items())}, fh)
            os.replace(part, path)
        except OSError as e:
            print(f"cannot keep {path} in the cache ({e})", flush=True)
        return {n: v[:2] for n, v in kept.items() if v[:2] != [0, 0]}


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
        part = _shade(_part(_pic(u, cache, p["display_scale"], t), sw, sh), t)
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
    return os.path.join(drawn(u, cache), "filters-level", name)


def _png(rgba):
    out = io.BytesIO()
    Image.fromarray(rgba).save(out, "PNG", compress_level=1)
    return out.getvalue()


def held_level(frames):
    """The seams' (gains, offsets) of frames on one calibrated scale, none pinned (mosaic.seams' pin None), for
    mosaic.compose's corrections. Pinned to none, the gains all sink together toward their limit as overlaps come
    in (the data asks only that they agree), so a mosaic dimmed about 9% while it filled: their mean log is held
    at 0 instead, so the pass keeps the level its scale gave it from the first tile to the last."""
    gains = mosaic.match_gains(frames, mosaic.calibrated_gain, None, mosaic.calibrated_overlap)
    gains = gains / np.exp(np.log(gains).mean(axis=0))
    return gains, mosaic.match_offsets(frames, gains, None, mosaic.calibrated_overlap)


def _compose(window, k, **kw):
    """mosaic.compose on the view's canvas, with the benchmark's soft edge on its 0.5 scale canvas at this
    canvas's scale."""
    feather = mosaic.feather_px
    with reel._mosaic_lock:
        try:
            mosaic.feather_px = max(8, round(64 * k / 0.5))
            mosaic.reset()
            if kw.get("pin", -1) is None and "corrections" not in kw and "gamma" not in kw and len(window) > 1:
                kw = {**kw, "corrections": held_level([np.asarray(w[0]) for w in window])}
            rgba = mosaic.compose(window, False, calibrated=True, **kw)
            mosaic.reset()
        finally:
            mosaic.feather_px = feather
    return rgba


def _over(u, p, rgba, t, rect, cache, match=True, kept=None):
    """Tile t composed over the mosaic rgba (in place) and matched to it (pin 0): only the tile's part of the
    canvas, and a margin for its soft edge, is composed, since nothing outside it changes. match=False: drawn
    over it with its soft edge as it is, on the pass's one scale (a mosaic movie's new lap is not pulled toward
    the older picture of its place under it). kept: as draw_over."""
    k = p["k"]
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    draw_over(rgba, lambda: _shade(_part(_pic(u, cache, p["display_scale"], t), sw, sh), t),
              left, top, sw, sh, k, match, kept)


def draw_over(rgba, part, left, top, sw, sh, k, match=True, kept=None):
    """_over's drawing: the tile part() (RGBA, sw x sh canvas pixels, its top left corner at left, top) composed over
    the mosaic rgba in place, on the tile's part of the canvas and a margin for its soft edge. kept: a list that gets
    what the blend step decided for the tile (mosaic.composite's kept, at the canvas's pixels), or None."""
    H, W = rgba.shape[:2]
    pad = max(8, round(64 * k / 0.5)) + 1
    x0, y0 = max(left - pad, 0), max(top - pad, 0)
    x1, y1 = min(left + sw + pad, W), min(top + sh + pad, H)
    a0, b0 = max(left, 0), max(top, 0)
    a1, b1 = min(left + sw, W), min(top + sh, H)
    # (a tile wholly past the canvas's edge, only its soft edge's margin on it, has nothing to draw: SPICE, filter
    # registration or a person's tuning can put a tile outside the pass's footprint)
    if x1 > x0 and y1 > y0 and a1 > a0 and b1 > b0:
        part = part()
        frame = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        frame[b0 - y0:b1 - y0, a0 - x0:a1 - x0] = part[b0 - top:b1 - top, a0 - left:a1 - left]
        below = np.ascontiguousarray(rgba[y0:y1, x0:x1])
        same = (np.ones((2, 3)), np.zeros((2, 3)))
        # matched to the picture so far (pin 0), and with the level step leveled to it along its seams as well
        # (mosaic._levels, pinned to it): leveled alone (gains of 1, each tile on the pass's one scale away from its
        # seams), Saturn's 725 tile mosaic movie of 2013 drawn whole came out 12% darker at the bottom than matched
        kw = {"corrections": same, "level": False} if not match else {"pin": 0}
        decided = [] if kept is not None else None
        rgba[y0:y1, x0:x1] = _compose([(below, None, None, None), (frame, None, None, None)], k, under=0, kept=decided, **kw)
        if kept is not None:
            kept.append(mosaic.moved(decided[-1], y0, x0) if decided else None)
    elif kept is not None:
        kept.append(None)


_grown_last = collections.OrderedDict()   # path of a grown filter mosaic -> its RGBA, the few made last
GROWN_KEEP = 6


def _grown(u, p, f, mine, rect, cache, tag=""):
    """The filter f's mosaic of mine (more than GROW_FROM tiles), grown a tile at a time: the mosaic of the
    tiles before the newest, as it was drawn, with the newest composed over it and matched to it (pin 0), so
    each new tile costs one tile's compose, not all of them again, and what is drawn stays as it was drawn.
    Only the newest tile's part of the canvas (and a margin for its soft edge) is composed, since nothing
    outside it changes. Starts from the largest of those mosaics already made (the first GROW_FROM tiles
    solved together otherwise) and keeps each one it makes on the way."""
    named = lambda m: _filter_path(u, f, m, rect, cache)[:-len(".png")] + tag + ".png"
    m = len(mine) - 1
    while m > GROW_FROM and named(m) not in _grown_last and not os.path.exists(named(m)):
        m -= 1
    rgba = filter_mosaic(u, p, f, mine[:m], rect, cache, tag=tag).copy()
    for j in range(m, len(mine)):
        _over(u, p, rgba, mine[j], rect, cache)
        path = named(j + 1)
        with _lock:
            _grown_last[path] = rgba.copy() if j + 1 < len(mine) else rgba
            _grown_last.move_to_end(path)
            while len(_grown_last) > GROWN_KEEP:
                _grown_last.popitem(last=False)
        if j + 1 < len(mine):
            reel._cached(path, lambda: _png(rgba))
    return _png(rgba)


_rolling = contextvars.ContextVar("rolling", default=False)   # drawing a laps=1 mosaic movie (rolling_webp)
_rolled = collections.OrderedDict()   # (pass, look, filter, view) -> [(tiles drawn, RGBA)]: each mosaic movie's last pictures
# mosaic movies whose last pictures are kept, whole passes (every filter of each), the least recently drawn let go
# first: one per thread drawing them at once and a window or two, so threads making different passes side by side
# (the pre-build) do not throw out each other's pictures and draw every frame whole (a canvas is up to 16 MB)
ROLLED_PASSES = int(os.environ.get("CASSINI_ROLLED_PASSES", "4"))
ROLLED_EACH = 2    # pictures kept of each filter


def rolled_room(passes):
    """Keep the last pictures of at least this many mosaic movies (a caller drawing that many at once)."""
    global ROLLED_PASSES
    with _lock:
        ROLLED_PASSES = max(ROLLED_PASSES, int(passes))


def _rolled_put(key, drawn, rgba):
    with _lock:
        kept = [x for x in _rolled.get(key, []) if x[0] != drawn][-(ROLLED_EACH - 1):] + [(drawn, rgba)]
        _rolled[key] = kept
        _rolled.move_to_end(key)
        # the pass (and look) is let go as a whole, the one drawn longest ago
        passes = list(dict.fromkeys(k[:2] for k in _rolled))
        for old in passes[:max(0, len(passes) - ROLLED_PASSES)]:
            for k in [k for k in _rolled if k[:2] == old]:
                del _rolled[k]
ROLL_STEPS = 8   # most new tiles a mosaic movie's picture grows by from its last one; further than that, it is drawn anew


def _roll(u, p, key, mine, rect, cache):
    """A mosaic movie's picture of one filter (every place's newest tile, mine), grown from the last one drawn
    (_rolled) by composing its new tiles over it, a tile's part of the canvas each (_over, as _grown does for a
    pass's mosaic), so a new frame costs one tile's compose instead of every place's again: a playing window
    gets its pictures about as fast as tiles are made. None when there is nothing to grow from (the first
    picture, a jump, a step back in time): the caller draws it whole."""
    with _lock:
        kept = list(_rolled.get(key, []))
    want = {t["n"] for t in mine}
    # only forward: what is kept of a picture is all still wanted or covered by a newer copy of its place; the
    # one kept with the fewest tiles to add
    best = None
    for drawn, rgba in kept:
        new = sorted(want - drawn)
        if new and len(new) <= ROLL_STEPS and (not drawn or new[0] > max(drawn)) and (best is None or len(new) < len(best[0])):
            best = (new, rgba)
    if best is None:
        return None
    new, rgba = best
    rgba = rgba.copy()
    by_n = {t["n"]: t for t in mine}
    for n in new:
        _over(u, p, rgba, by_n[n], rect, cache, match=False)
    return rgba


def filter_mosaic(u, p, f, tiles, rect, cache, ref=None, tag=""):
    """The filter f's mosaic of these tiles in the view rect, RGBA on the view's canvas (kept in the cache).
    ref = the filter the seams are solved on (balanced look, seams). Past GROW_FROM tiles it grows from the
    one before (_grown) instead of composing every tile again. tag names a set of tiles that is not every tile
    up to the newest (a mosaic movie's lap, rolling_layout): it has a name of its own and is not grown, since
    growing takes the tiles as the pass's first ones in time order. f = LUM: the pass's luminance base (_mine)."""
    mine = _mine(u, p, tiles, f)
    balanced = calibration.look() == "balanced" and SHARED_SEAMS and f != LUM
    ref = ref or f
    solved_on = f"-{ref.replace('/', '_')}{sum(1 for t in tiles if t['filter'] == ref and 'offset' in t)}" if balanced else ""
    path = _filter_path(u, f, len(mine), rect, cache, solved_on)
    path = path[:-len(".png")] + tag + ".png"
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)

    roll = (u["key"], calibration.mode(), f, tuple(round(v) for v in rect)) if tag and _rolling.get() and not balanced else None
    drew = {}

    def make():
        # (panel registration's tiles are every tile up to the newest too, each kept where it was first put)
        if not balanced and tag in ("", PANEL_TAG, SURFACE_TAG, SURFACE_TAG + PANEL_TAG) and len(mine) > GROW_FROM:
            return _grown(u, p, f, mine, rect, cache, tag)
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
        drew["rgba"] = rgba
        return _png(rgba)

    with _lock:
        kept = _grown_last.get(path)
        same = [x[1] for x in _rolled.get(roll, []) if x[0] == frozenset(t["n"] for t in mine)] if roll else []
    if kept is not None:
        return kept
    # a mosaic movie's filter whose tiles did not change since one of its last pictures (the new tile is another
    # filter's): that picture again, though the movie's picture has a new name
    if same:
        return same[0]
    # a mosaic movie's next picture, grown from one before it: kept in memory only (the movie's picture made of
    # it is kept in the cache), as writing the filter's whole canvas costs more than growing it
    grew = _roll(u, p, roll, mine, rect, cache) if roll and not os.path.exists(path) else None
    if grew is not None:
        _rolled_put(roll, frozenset(t["n"] for t in mine), grew)
        return grew
    data = reel._cached(path, make)
    with _lock:
        kept = _grown_last.get(path)
    if kept is not None:
        return kept
    rgba = drew.get("rgba")
    if rgba is None:
        rgba = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))
    if roll:
        # a picture the mosaic movie's next ones grow from (_roll)
        _rolled_put(roll, frozenset(t["n"] for t in mine), rgba)
    return rgba


_parts = collections.OrderedDict()   # (tile file, width, height) -> the tile at that size, most recently used last
_parts_bytes = [0]
PARTS_KEEP = int(os.environ.get("CASSINI_MOSAIC_PARTS_MB", "256")) << 20
_made_pictures = collections.OrderedDict()   # tile file -> its picture (RGBA) as it was made and written, the newest last
_made_pictures_bytes = [0]
MADE_KEEP = int(os.environ.get("CASSINI_MOSAIC_MADE_MB", "64")) << 20


def _keep_made(path, picture):
    """A tile's picture as made and written to path, kept in memory (the newest, up to MADE_KEEP bytes): a movie
    frame or a mosaic draws its new tile right after making it (_part), the next filter's tile at its pointing is
    registered to it (_register), and reading the PNG back cost ~35 ms each time."""
    picture = picture.view()
    picture.flags.writeable = False
    with _lock:
        old = _made_pictures.pop(path, None)
        if old is not None:
            _made_pictures_bytes[0] -= old.nbytes
        _made_pictures[path] = picture
        _made_pictures_bytes[0] += picture.nbytes
        while _made_pictures and _made_pictures_bytes[0] > MADE_KEEP:
            _made_pictures_bytes[0] -= _made_pictures.popitem(last=False)[1].nbytes


def _part(path, w, h):
    """A tile at w x h canvas pixels (RGBA): read and resized once and kept in memory (up to PARTS_KEEP bytes),
    since every mosaic of a pass is drawn again from all of its tiles and a tile never changes once made."""
    key = (path, w, h)
    with _lock:
        part = _parts.get(key)
        if part is not None:
            _parts.move_to_end(key)
            return part
        made = _made_pictures.get(path)
    # a tile just made is resized from its picture in memory, the pixels its PNG holds
    im = Image.fromarray(made) if made is not None else Image.open(path).convert("RGBA")
    part = np.asarray(im.resize((w, h), Image.LANCZOS))
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
        # the channels' mean: 8-bit values, so the sum is exact and this is numpy's mean(axis=2) to the bit (all
        # 2^24 colours), without its slow reduce over three
        lum = (rgb[..., 0] + rgb[..., 1] + rgb[..., 2]) / 3
        mean = cv2.GaussianBlur(lum * a, (0, 0), sigma) / np.maximum(weight, 1e-3)
        out = np.clip(rgb + (DETAIL * (lum - mean))[..., None], 0, 255)
        return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])
    mean = cv2.GaussianBlur(rgb * a[..., None], (0, 0), sigma) / np.maximum(weight, 1e-3)[..., None]
    out = np.clip(rgb + DETAIL * (rgb - mean), 0, 255)
    return np.dstack([out.round().astype(np.uint8), rgba[..., 3]])


def layout(u, n, cache):
    """What the pass's mosaic with tiles 0..n is made of: (plan, tiles, view rect, placed tiles per filter, the
    filters drawn, a name for that picture); None before any tile is placed. Frames whose tile is not one of
    the filters drawn (a moon's 30 filter colour pass draws 3) give the same picture and the same name.
    The filters used are the plan's colour filters once each has a tile, before that its grey filter (or, until
    the grey filter's first tile, the luminance base's filter most taken so far); the picture is drawn on the
    luminance base (so_far), whose tiles the name counts (L<n>) when it holds more than the filters used. None
    before a tile of the base is placed: the gray never starts in a filter it then leaves."""
    p = plan(u, cache)
    tiles = _reports(u, cache, p, range(n + 1))
    rect = view_rect(p, tiles)
    # each tile's surface redrawn as at the pass's epoch (surface reprojection), then each pointing moved onto the
    # ones before it where they overlap (panel registration: what is left is SPICE's pointing, a few pixels)
    surfaced = surface_pictures(u, cache, p, tiles)
    if surfaced:
        tiles = [dict(t, pic=surfaced[t["n"]]) if t["n"] in surfaced else t for t in tiles]
    moved = panel_places(u, cache, p, tiles)
    if moved:
        tiles = [dict(t, offset=[t["offset"][0] + moved[t["n"]][0], t["offset"][1] + moved[t["n"]][1]], spice_place=t["offset"])
                 if t["n"] in moved and "offset" in t else t for t in tiles]
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not count:
        return None
    colour = p["colour"]
    frames = lum_frames(u, p)
    base = [t["filter"] for t in tiles if "offset" in t and t["n"] in frames]
    if colour and all(count.get(f) for f in colour):
        used = colour
    elif count.get(p["grey"]):
        used = [p["grey"]]
    elif base:
        used = [max(dict.fromkeys(base), key=base.count)]   # (ties: the filter taken first)
    else:
        return None
    name = "_".join(f"{f.replace('/', '-')}{count[f]}" for f in used)
    if any(f not in used for f in base):
        name += f"_L{len(base)}"
    return p, tiles, rect, count, used, name + "_" + "_".join(str(round(v)) for v in rect) + (SURFACE_TAG if surfaced else "") + (PANEL_TAG if moved else "")


TUNE_MAX = 0.5   # furthest a pointing can be moved, as a fraction of the picture


def parse_tune(tune, hide):
    """The person's changes to a mosaic's tiles (Cassini Studio) from the request: tune "3:0.012:-0.004,7:0:0.02"
    (pointing n as tile_map numbers them, moved by dx, dy fractions of the picture) and hide "2,9" (pointings left
    out). ({n: (dx, dy)}, {n}); ValueError when it does not read."""
    moves, gone = {}, set()
    for part in filter(None, (tune or "").split(",")):
        n, dx, dy = part.split(":")
        dx, dy = float(dx), float(dy)
        if not (math.isfinite(dx) and math.isfinite(dy)):
            raise ValueError(part)
        moves[int(n)] = (max(-TUNE_MAX, min(TUNE_MAX, dx)), max(-TUNE_MAX, min(TUNE_MAX, dy)))
    for n in filter(None, (hide or "").split(",")):
        gone.add(int(n))
    if len(moves) + len(gone) > 400:
        raise ValueError("too many")
    return moves, gone


def tuned_layout(made, mapped, moves, gone):
    """A layout (layout()) with the person's changes laid over SPICE's placement: each moved pointing's tiles (every
    filter of it, so its colours stay together) offset by its move, hidden pointings' tiles left out. The tiles'
    own pictures, the plan and the view are untouched: the mosaic is composed from them by mosaic.compose as
    always, under a name of its own (-tune<hash>), so the untouched mosaic stays as it is, one request away.
    mapped: tile_map() of the same frame (its pointing numbers). made unchanged when there is nothing to change."""
    if not made or not mapped or not (moves or gone):
        return made
    p, tiles, rect, count, used, name = made
    by = {q["n"]: q["tiles"] for q in mapped["pointings"]}
    shift, out = {}, set()
    for q, (dx, dy) in moves.items():
        for n in by.get(q, []):
            shift[n] = (dx * rect[2], dy * rect[3])
    for q in gone:
        out.update(by.get(q, []))
    shift = {n: v for n, v in shift.items() if v != (0.0, 0.0)}
    if not shift and not out:
        return made
    tiles = [dict(t, offset=[t["offset"][0] + shift[t["n"]][0], t["offset"][1] + shift[t["n"]][1]]) if t["n"] in shift and "offset" in t else t
             for t in tiles if t["n"] not in out]
    count = {}
    for t in tiles:
        if "offset" in t:
            count[t["filter"]] = count.get(t["filter"], 0) + 1
    if not any(count.get(f) for f in used):
        return None
    for f in used:
        count.setdefault(f, 0)
    key = json.dumps([sorted((n, round(v[0], 2), round(v[1], 2)) for n, v in shift.items()), sorted(out)])
    return p, tiles, rect, count, used, f"{name}-tune{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def colour_picture(u, p, colour, planes):
    """The colour picture of a pass's three colour filters' planes (RGBA, each on the pass's display scale), RGBA:
    the pass's mosaic and its movie frames mixed alike. Natural color: a true color pass turned into what an eye
    would see, a false color one balanced so the body comes out gray, on the pass's own measure of its body
    (pass_scale's balance); without the mix the bands stay on the grey scale, where the blue and green of a red
    body are close to black."""
    rgb = np.dstack([a[..., 0] for a in planes])
    scale = p["display_scale"]
    bal = scale.get("balance")
    mix = calibration.color_mix(u["key"][2], colour, u["key"][0], [bal[f] for f in colour] if bal else None)
    if mix is not None and scale.get("typical"):
        mix.typical = [scale["typical"][f] for f in colour]
    if mix is not None:
        rgb = calibration.mix_display(rgb, mix, scale["gamma"])
    # only where every filter has the picture: past one filter's edge the others alone are a coloured rim
    alpha = np.min([a[..., 3] for a in planes], axis=0)
    rgb = (rgb * (alpha[..., None] / np.float32(255)) + 0.5).astype(np.uint8)
    return np.dstack([rgb, alpha])


# the last picture so_far or movie_frame made on this thread, kept for the next size asked: the pre-build and the
# segment pre-render ask for each frame's mosaic, mosaic movie picture or movie frame at 1024 and 512 in turn
# (make_pass), and both sizes are made at OUT and shrunk after, so the second was the same picture made again. Kept
# up to OUT only (a full view's larger picture is not); each call gets a copy, as the callers shrink theirs in place
_last_made = threading.local()


def _kept_for_next_size(make, key_of):
    def kept(*args, **kwargs):
        key = key_of(*args, **kwargs)
        last = getattr(_last_made, "picture", None)
        if key is not None and last is not None and last[0] == key:
            return last[1].copy(), dict(last[2])
        im, rep = make(*args, **kwargs)
        _last_made.picture = (key, im.copy(), dict(rep)) if key is not None and im is not None else None
        return im, rep
    kept.__doc__ = make.__doc__
    return kept


def so_far(u, n, cache, made=None, out=OUT):
    """The pass's mosaic with tiles 0..n, RGBA out px (OUT unless asked for more, up to CANVAS) on its longest
    side, and its report; (None, None) before any tile is placed. made: layout(u, n, cache), when already
    worked out."""
    made = made or layout(u, n, cache)
    if not made:
        return None, None
    p, tiles, rect, count, used, name = made
    # a set of tiles other than every tile up to n has a name of its own (tag): a mosaic movie's lap, a tuned layout
    plain, _, tuned = name.partition("-tune")
    # (and a layout whose tiles panel registration moved: its tiles are not where the pre-built pictures have them)
    tag = ("-" + plain.rsplit("-", 1)[1] if plain.startswith("lap-") else "") + \
        "".join(x for x in (SURFACE_TAG, PANEL_TAG) if x in plain) + ("-tune" + tuned if tuned else "")
    # the seams are solved on the best covered filter drawn and shared by all (balanced look)
    ref = max(used, key=lambda f: count[f])
    # the luminance base under the picture, where it holds tiles the picture would not show (a mosaic movie's
    # picture, rolling_layout, keeps its own drawing: its name does not count the base's tiles)
    base = not plain.startswith("lap-") and lum_base(u, p, tiles, used)
    if len(used) == 3:
        colour = used
        acc = [filter_mosaic(u, p, f, tiles, rect, cache, ref, tag) for f in colour]
        rgba, used = colour_picture(u, p, colour, acc), colour
        if base:
            rgba = over_grey(rgba, filter_mosaic(u, p, LUM, tiles, rect, cache, None, tag), p["k"],
                             p["display_scale"]["gamma"])
    elif base:
        rgba = filter_mosaic(u, p, LUM, tiles, rect, cache, None, tag)
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
    laps = {"kind": u.get("kind"), "lap": lap_of(u)[min(n, len(u["frames"]) - 1)] if u["frames"] else 1, "laps": u.get("repeats"), "places": len(set(x for x in u.get("place", []) if x is not None))}
    return im, {**laps, "mosaic": sum(count.get(f, 0) for f in drawn), "filters": len(used), "filter_names": used,
                "observation": u["key"][1], "pass": u["key"][3], "of": sum(1 for fr in u["frames"] if fr[2] in drawn),
                "fixed": p["fixed"], "luminance": bool(base), "width": im.width, "height": im.height}


# the same layout, tile and size: named in the cache by folder and layout name (_mosaic_path)
so_far = _kept_for_next_size(so_far, lambda u, n, cache, made=None, out=OUT:
                             (drawn(u, cache), made[5], n, out) if made and out <= OUT else None)


def _footprint_file(u):
    return TRACK_FOOTPRINT_FILE if u.get("track") else FOOTPRINT_FILE


def _footprint_kept(u, rec):
    """The pass's movie footprint kept in its record rec, or None (a track's is kept apart: track_footprint)."""
    return None if rec is None else rec.get("track_footprint" if u.get("track") else "footprint")


def movie_footprint(u, cache, p=None):
    """The ground a movie's frames cover (x0, y0, x1, y1, reference pixels from the body's centre), from where SPICE
    put the tiles themselves rather than the geometry cache (which can be a third of a frame off by the end of a
    movie tracking a propeller): MOVIE_SAMPLES tiles spread over the pass, with MOVIE_MARGIN round them for the
    frames between. A feature track's is every tile at its steady place (track_places). Worked out once and kept
    with the pass."""
    p = p or plan(u, cache)
    rec = _kept_tiles(u, cache, p["display_scale"])
    if _footprint_kept(u, rec) is not None:
        return _footprint_kept(u, rec)
    path = os.path.join(folder(u, cache), _footprint_file(u))
    if os.path.exists(path):
        with open(path) as fh:
            fp = json.load(fh)
        if rec is not None:
            rec["track_footprint" if u.get("track") else "footprint"] = fp
        return fp
    track = track_places(u, cache, p) if u.get("track") else None
    n = len(u["frames"])
    picks = sorted({round(i * (n - 1) / max(1, MOVIE_SAMPLES - 1)) for i in range(MOVIE_SAMPLES)}) if n else []
    if track:
        picks = sorted(track)
    boxes = []
    # the samples made side by side (MOVIE_WORKERS at once): a cold pass's first steady frame waits on them
    mode = calibration.mode()

    def one(j):
        with calibration.in_mode(mode):
            return tile(u, j, cache, p["display_scale"])
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        made = list(pool.map(one, picks))
    for t in made:
        if "offset" in t:
            ox, oy = track[t["n"]] if track else t["offset"]
            bx, by, bw, bh = t["box"]
            boxes.append((ox + bx, oy + by, ox + bx + bw, oy + by + bh))
    if boxes:
        m = MOVIE_MARGIN * FRAME
        fp = [min(b[0] for b in boxes) - m, min(b[1] for b in boxes) - m, max(b[2] for b in boxes) + m, max(b[3] for b in boxes) + m]
        # the geometry cache's footprint too, so no frame between the samples falls outside both (a track's
        # footprint has every frame, at places the geometry cache does not know)
        g = p["footprint"]
        if not track:
            fp = [min(fp[0], g[0]), min(fp[1], g[1]), max(fp[2], g[2]), max(fp[3], g[3])]
    else:
        fp = list(p["footprint"])
    reel._cached(path, lambda: json.dumps(fp).encode())
    if rec is not None:
        rec["track_footprint" if u.get("track") else "footprint"] = fp
    return fp


TRACK_MAX = 0.1   # of a frame: the largest step between a track's frames that registration is believed for


def _every_tile(u, cache, p):
    """Every tile of the pass made (MOVIE_WORKERS at once), and pic(j): tile j's picture (the newest 16 read kept)."""
    mode = calibration.mode()

    def one(j):
        with calibration.in_mode(mode):
            return tile(u, j, cache, p["display_scale"])
    with concurrent.futures.ThreadPoolExecutor(MOVIE_WORKERS) as pool:
        made = list(pool.map(one, range(len(u["frames"]))))
    there, pics = _tiles(u, cache, p["display_scale"]), collections.OrderedDict()

    def pic(j):
        if j not in pics:
            path = os.path.join(there, f"{j}.png")
            with _lock:
                pics[j] = _made_pictures.get(path)
            if pics[j] is None:
                pics[j] = np.asarray(Image.open(path).convert("RGBA"))
            while len(pics) > 16:
                pics.popitem(last=False)
        return pics[j]
    return made, pic, there


def _chain(made, pic, there, believed, step):
    """Each placed tile registered to the tile before it ({n: [x, y]} and how), the chain track_places and
    steady_places are made of. Tile n is put first where step(j, n) says it is from tile j's place, and registered
    there to the tile before it, or to the newest earlier tile of its own filter (another filter can look too
    different: a methane band after a continuum), by the pipeline's own alignment of a set's channels (_shift_onto,
    as C8 registers a pointing's filters); a shift of at most believed (reference pixels) moves it, otherwise it
    keeps step's place from the tile before it. step(places, j, n) reads the places made so far. The first tile keeps
    SPICE's place."""
    places, hows, prev, newest = {}, {}, None, {}
    for t in made:
        n = t["n"]
        if "offset" not in t or not os.path.exists(os.path.join(there, f"{n}.png")):
            continue
        if prev is None:
            places[n], hows[n] = list(t["offset"]), "first"
        else:
            for j in dict.fromkeys(j for j in (prev, newest.get(t["filter"])) if j is not None):
                at = step(places, j, n)
                shift, how = _shift_onto(made[j], pic(j), (0.0, 0.0), t, pic(n), (at[0] - places[j][0], at[1] - places[j][1]))
                if shift is not None and math.hypot(*shift) <= believed:
                    places[n] = [at[0] - shift[0], at[1] - shift[1]]
                    hows[n] = f"{how} to {j}"
                    break
            else:
                places[n], hows[n] = step(places, prev, n), f"held from {prev}"
        prev = n
        newest[t["filter"]] = n
    return places, hows


def _chained(u, cache, p, name, key, work):
    """A pass's chain kept with it (in the file name and its record's key): {n: [x, y]}, made by work() once."""
    rec = _kept_tiles(u, cache, p["display_scale"])
    if rec is not None and rec.get(key) is not None:
        return rec[key]
    path = os.path.join(folder(u, cache), name)
    with _ulock(u):
        if rec is not None and rec.get(key) is not None:
            return rec[key]
        if not os.path.exists(path):
            places, hows = work()
            data = json.dumps({"places": {str(n): [round(v, 2) for v in xy] for n, xy in places.items()}, "how": hows})
            reel._cached(path, data.encode)
        with open(path) as fh:
            kept = {int(n): xy for n, xy in json.load(fh)["places"].items()}
        if rec is not None:
            rec[key] = kept
        return kept


def track_places(u, cache, p=None):
    """A feature track's steady places: {tile n: [x, y]}, where each placed tile's middle is drawn (reference pixels,
    in the place of its offset), so the feature the camera follows holds still from frame to frame. The camera
    follows a cloud the planet's turning carries along (FEATRAK, WIND5HR), so where SPICE puts each frame round the
    body's centre moves 150 px a frame and more, while what the frames show hardly moves in the frame itself. Each
    tile is registered to the tile before it (_chain), with the two frames' middles on one another: the shift found
    is how far the feature moved in the frame, and the tile's steady place is the earlier tile's moved by it. One
    that matches neither the tile before it nor the newest of its own filter is held where the tile before it is:
    the camera follows the feature, so SPICE's step between two frames is that following, the very motion a track
    takes out (taking it added up to 11,000 px over ISS_191SA_FEATRAK001's 360 frames, and WIND5HR003's filters
    jumped 60 to 160 px back and forth). So a colour set's filters land on one another too (they are taken one after
    another), and the first tile keeps SPICE's place. This is steady_places with SPICE's motion left out altogether
    (no smoothing back towards it). Worked out once over every tile of the pass and kept with it; {} with
    Settings > Processing's alignment off (SPICE's places)."""
    p = p or plan(u, cache)
    if not calibration.step("align"):
        return {}

    def work():
        made, pic, there = _every_tile(u, cache, p)
        # a track's tile starts where the tile before it is
        return _chain(made, pic, there, TRACK_MAX * FRAME, lambda places, j, n: list(places[j]))
    return _chained(u, cache, p, TRACK_FILE, "track", work)


STEADY_MAX = 0.05     # of a frame: the largest correction to SPICE's step between two frames that registration is believed for
STEADY_SMOOTH = 12    # frames: Settings > Movie's stabilization smoothing by default (0: SPICE's places)
STEADY_MOST = 60      # frames: the most smoothing asked for
# a movie's stabilization chain (steady_chain), kept with the pass; renamed (with the movie frames drawn on it,
# movie_webp) whenever the rule changes
STEADY_FILE = "steady1-" + PLAN_FILE


def steady_chain(u, cache, p=None):
    """Image stabilization of a movie pass: {tile n: [x, y]}, each placed tile registered to the tile before it with
    SPICE's step between the two as the starting guess. SPICE puts each frame on its own, from where the spacecraft
    and the camera were said to point, and the pointing is a few pixels off, differently from frame to frame: a
    movie of a body wobbles by that much (C8 lands a pointing's filters on one another only within REGISTER_MAX and
    SAME_PLACE). Here tile n starts where SPICE's step from tile j's place puts it (_chain) and the pipeline's
    alignment of a set's channels (_shift_onto) moves it onto tile j by what the pictures show, up to STEADY_MAX of a
    frame; a tile that matches neither keeps SPICE's step. The chain follows the pictures frame to frame, so it
    drifts away from SPICE slowly (each registration is a fraction of a pixel off): steady_places holds it to SPICE
    over longer spans. Worked out once over every tile of the pass and kept with it; {} with Settings > Processing's
    alignment off."""
    p = p or plan(u, cache)
    if not calibration.step("align"):
        return {}

    def work():
        made, pic, there = _every_tile(u, cache, p)

        def step(places, j, n):
            # SPICE's step from tile j to tile n, from where tile j was put
            return [places[j][0] + made[n]["offset"][0] - made[j]["offset"][0],
                    places[j][1] + made[n]["offset"][1] - made[j]["offset"][1]]
        return _chain(made, pic, there, STEADY_MAX * FRAME, step)
    return _chained(u, cache, p, STEADY_FILE, "steady", work)


def steady_places(u, cache, p=None, smooth=STEADY_SMOOTH):
    """Each placed tile's stabilized place ({n: [x, y]}, in the place of its offset): the chain (steady_chain)
    held to SPICE over smooth frames. SPICE's place is right on average and the chain is right frame to frame, so
    the place is the chain plus a Gaussian average (sigma smooth placed frames) of how far SPICE is from the
    chain: the wobble from one frame to the next comes out, the slow drift of the chain does not build up, and the
    body stays where SPICE puts it over the pass. smooth 0: SPICE's places ({}); the more smoothing, the longer
    the pictures are believed over SPICE. A feature track (track_places) is the same chain with no smoothing back
    to SPICE at all, since SPICE's motion there is the camera following the feature."""
    if smooth <= 0:
        return {}
    p = p or plan(u, cache)
    chain = steady_chain(u, cache, p)
    if not chain:
        return {}
    ns = sorted(chain)
    held = held_to_spice([tile(u, n, cache, p["display_scale"])["offset"] for n in ns], [chain[n] for n in ns], smooth)
    return {n: xy for n, xy in zip(ns, held)}


def _gaussian(values, smooth):
    """values (one row per frame) averaged with a Gaussian of sigma smooth frames, cut at 3 sigma, normalized at the ends."""
    i = np.arange(len(values), dtype=float)
    w = np.exp(-0.5 * ((i[:, None] - i[None, :]) / smooth) ** 2)
    w[np.abs(i[:, None] - i[None, :]) > 3 * smooth] = 0
    return (w @ np.asarray(values, float)) / w.sum(axis=1).reshape((-1,) + (1,) * (np.ndim(values) - 1))


def _gaussian_line(values, smooth):
    """values (one row per frame) smoothed over smooth frames: at each frame, a straight line fitted to the frames round
    it weighted by a Gaussian of sigma smooth (cut at 3 sigma), read at that frame. A plain Gaussian average would bend
    a steady drift or brightening at the ends of the pass (only the frames on one side are there); the line keeps it."""
    y = np.asarray(values, float)
    i = np.arange(len(y), dtype=float)
    dist = i[None, :] - i[:, None]
    w = np.exp(-0.5 * (dist / smooth) ** 2)
    w[np.abs(dist) > 3 * smooth] = 0
    s0, s1, s2 = w.sum(axis=1), (w * dist).sum(axis=1), (w * dist * dist).sum(axis=1)
    flat = y.reshape(len(y), -1)
    t0, t1 = w @ flat, (w * dist) @ flat
    det = s0 * s2 - s1 * s1
    # (one frame, or every weight on one frame: the plain average)
    ok = det > 1e-9 * np.maximum(s0 * s2, 1e-300)
    out = np.where(ok[:, None], (s2[:, None] * t0 - s1[:, None] * t1) / np.where(ok, det, 1)[:, None], t0 / s0[:, None])
    return out.reshape(y.shape)


def held_to_spice(spice, chain, smooth):
    """steady_places' math on its own (pure, so it can be ported to the viewer with a conformance test): the places of
    a pass's placed frames in order, [[x, y], ...], from SPICE's [[x, y], ...] and the registration chain's, the chain
    plus a Gaussian average over smooth frames of how far SPICE is from it, rounded to 1/100 px."""
    spice, chain = np.asarray(spice, float), np.asarray(chain, float)
    held = chain + _gaussian(spice - chain, smooth)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in held]


EXPOSURE_SMOOTH = 8      # frames: Settings > Movie's exposure smoothing by default (0: each frame as the pass's scale draws it)
EXPOSURE_MOST = 30       # frames: the most smoothing asked for
EXPOSURE_FLASH = 3       # frames: a brightness change lasting fewer frames than this (one frame bright, then back) is taken out
EXPOSURE_GAIN = 4.0      # the most a frame is brightened or dimmed by
EXPOSURE_LIT = 0.04      # of the brightest: the pixels a brightness is measured on (the body, not the sky's noise)
EXPOSURE_SIDE = 160      # px: the movie pictures a pass's brightness is measured on (exposure_chain) are this big
# a movie's brightness chain (exposure_chain), kept with the pass for each way of drawing it; renamed (with the movie
# frames drawn with it, movie_webp) whenever the rule changes
EXPOSURE_FILE = "exposure4-{}-" + PLAN_FILE
EXPOSURE_RULE = 6        # the way the gains are worked out from the chain: in the movie frames' names (movie_webp)
EXPOSURE_GREY_RUN = 6    # frames: a colour pass's grey frames (its filters coming in) evened only in a run this long
EXPOSURE_SAME = 0.5      # of the larger lit area: two pictures sharing less lit view than this show different scenes


def _lit_level(a, gamma):
    """The linear brightness of a movie picture's part (RGBA): the median of its lit pixels, None when few are lit."""
    v = calibration.decode(a[..., :3].astype(np.float64).mean(axis=2)[a[..., 3] > 0] / 255, gamma)
    if v.size < 64:
        return None
    lit = v[v > EXPOSURE_LIT * max(float(np.percentile(v, 99.5)), 1e-6)]
    return float(np.median(lit)) if lit.size >= 64 else None


def _exposure_name(colour, centre, steady):
    return EXPOSURE_FILE.format(f"c{int(bool(colour))}{int(bool(centre))}s{steady}")


def exposure_chain(u, cache, p=None, colour=True, centre=True, steady=0):
    """How the movie's brightness steps from one picture to the next ({frame n: log brightness}): the pass is drawn on
    one display scale, so a frame whose exposure the calibration did not fully even out, a frame lit by stray light,
    a colour set after a grey frame or a filter brighter than the one before shows as a jump or a flash. What is
    measured is the movie itself: each frame's picture as movie_frame draws it (colour, centre, steady as asked; no
    trail, EXPOSURE_SIDE px), against the picture before it, over the part of the view both show (one view for the
    pass), as the ratio of the medians of the lit pixels in linear brightness; the chain adds up the logs. A pair with
    too little lit in common adds nothing (the same brightness); a held colour set is the same picture. The chain is
    cut into stretches ({n: [log, stretch, in colour]}) where the picture changes kind (grey frames before the colour set is
    complete, then colour; another set of filters) or scene (the two share less than EXPOSURE_SAME of their lit
    view: a narrow ring arc between two wide views): a step there is the picture changing, not its exposure, and
    exposure_gains evens each stretch on its own. Worked out once over every frame of the pass, for each way of
    drawing it, and kept with it."""
    p = p or plan(u, cache)
    gamma = p["display_scale"].get("gamma", 2.2)
    key = ("exposure", bool(colour), bool(centre), steady)

    def work():
        logs, hows, last, stretch = {}, {}, None, 0

        def lit(a):
            v = calibration.decode(a[..., :3].astype(np.float64).mean(axis=2) / 255, gamma)
            return (a[..., 3] > 0) & (v > EXPOSURE_LIT * max(float(np.percentile(v[a[..., 3] > 0], 99.5)) if (a[..., 3] > 0).any() else 0, 1e-6))
        for n in range(len(u["frames"])):
            im, rep = movie_frame(u, n, cache, 0, colour, out=EXPOSURE_SIDE, centre=centre, steady=steady)
            if im is None:
                continue
            a, kind = np.asarray(im), tuple(rep.get("color") or ())
            if last is None:
                logs[n], hows[n] = [0.0, stretch, bool(kind)], "first"
            else:
                j, b, was = last
                la, lb = lit(a), lit(b)
                shared = (la & lb).sum() / max(1, la.sum(), lb.sum()) if a.shape == b.shape else 0.0
                if kind != was or shared < EXPOSURE_SAME:
                    stretch += 1
                    logs[n], hows[n] = [0.0, stretch, bool(kind)], "another kind of picture" if kind != was else f"another scene ({shared:.2f} shared)"
                else:
                    logs[n], hows[n] = [logs[j][0], stretch, bool(kind)], f"same as {j}"
                    both = (a[..., 3] > 0) & (b[..., 3] > 0)
                    levels = [_lit_level(np.where(both[..., None], q, 0), gamma) for q in (b, a)]
                    if None not in levels and min(levels) > 0:
                        step = math.log(levels[1] / levels[0])
                        logs[n], hows[n] = [logs[j][0] + step, stretch, bool(kind)], f"{math.exp(step):.3f} x {j}"
            last = (n, a, kind)
        return logs, hows

    rec = _kept_tiles(u, cache, p["display_scale"])
    kept = (rec.get("exposure") or {}).get(key) if rec is not None else None
    if kept is not None:
        return kept
    path = os.path.join(folder(u, cache), _exposure_name(colour, centre, steady))
    with _ulock(u):
        if not os.path.exists(path):
            logs, hows = work()
            data = json.dumps({"logs": {str(n): [round(v[0], 5), v[1], v[2]] for n, v in logs.items()}, "how": hows})
            reel._cached(path, data.encode)
        with open(path) as fh:
            kept = {int(n): v for n, v in json.load(fh)["logs"].items()}
        if rec is not None:
            with _lock:
                rec["exposure"] = {**(rec.get("exposure") or {}), key: kept}
        return kept


def exposure_gains(u, cache, p=None, smooth=EXPOSURE_SMOOTH, colour=True, centre=True, steady=0):
    """Each movie frame's exposure gain ({n: gain}, on linear brightness, one for the whole picture so a colour set
    keeps its colour): the movie's brightness (exposure_chain) moved to the brightness of the frames round it
    (evened_gains), each stretch of one kind of picture and one scene on its own: a flash of a frame or two brought
    to its neighbours' level, a jump spread over smooth frames. A stretch shorter than EXPOSURE_FLASH frames is left
    as it is (gain 1: too short to tell a flash from the picture), and so is a run of fewer than EXPOSURE_GREY_RUN grey
    frames in a pass that plays in colour (each a filter of the set filling in, as bright as that filter is: in the
    UV aurora stares' four, evening them out only moved their steps onto their neighbours; COMPHILIT001's ten flicker
    filter to filter and are evened). Slow changes (a body coming into sunlight over the
    pass) stay; the frames' data stays, only scaled. smooth 0: no gains ({})."""
    if smooth <= 0:
        return {}
    # (measured once per pass on SPICE's places, whatever the stabilization: a few px of it hardly change which lit
    # pixels two pictures share, and one chain serves every smoothing, here and in the viewer)
    logs = exposure_chain(u, cache, p, colour, centre, 0)
    stretches = collections.defaultdict(list)
    in_colour = any(v[2] for v in logs.values())
    gains = {}
    for n in sorted(logs):
        stretches[logs[n][1]].append(n)
    for key, ns in list(stretches.items()):
        if in_colour and not logs[ns[0]][2] and len(ns) < EXPOSURE_GREY_RUN:
            gains.update((n, 1.0) for n in ns)
            del stretches[key]
    for ns in stretches.values():
        gains.update(zip(ns, evened_gains([logs[n][0] for n in ns], smooth) if len(ns) >= EXPOSURE_FLASH else [1.0] * len(ns)))
    return gains


def evened_gains(logs, smooth):
    """exposure_gains' math on its own for a movie's frames in order (pure, so it can be ported to the viewer with a
    conformance test): their log brightnesses (exposure_chain) in, each frame's gain out: flashes shorter than
    EXPOSURE_FLASH frames taken out by a running median, the rest smoothed with a Gaussian over smooth frames, the gain
    the smoothed brightness over the frame's own, within EXPOSURE_GAIN either way, to 1/200 (the movie frame's lookup
    table is made once per gain)."""
    L = np.asarray(logs, float)
    h = EXPOSURE_FLASH // 2
    pad = np.concatenate([np.repeat(L[:1], h), L, np.repeat(L[-1:], h)])
    steady = np.array([np.median(pad[k:k + EXPOSURE_FLASH]) for k in range(len(L))])
    # (a line through the frames round each, so a pass brightening all through keeps its brightening at its ends)
    target = _gaussian_line(steady, smooth)
    return [round(float(np.clip(math.exp(want - own), 1 / EXPOSURE_GAIN, EXPOSURE_GAIN)) * 200) / 200
            for own, want in zip(L, target)]


def steady_table(frame_id, cache, centre=True, colour=False):
    """What a browser needs to stabilize the pass frame_id is in by itself (web/cassini-os/src/steady-local.js): the
    pass's stabilization chain (steady_chain), each tile's SPICE place and box, and the movie's view (movie_rect)
    with its scale at OUT, so steady_places and the integer place _place draws a tile at are worked out in the page
    for any smoothing, and a movie frame drawn at SPICE's places (steady 0, the pre-built frames) is moved by the
    difference. "fixed": the view is the pass's whole (it does not follow the tile), the case where a single
    tile's frame moved by that difference is the frame drawn at its steady place; a pass whose view follows its
    frames, a feature track and a pass with Settings > Processing's alignment off answer {"local": false} (the
    server draws them). None when the frame is in no pass; {"working": true} while the chain is not worked out
    (the page asks the server for the stabilized frames meanwhile)."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    return _steady_table(*found, cache, centre, colour)


def _steady_table(u, n, cache, centre=True, colour=False):
    """steady_table for frame n of pass u. "exposure": the pass's brightness chain as the movie is drawn (colour,
    centre; the steady-0 chain exposure_gains evens for every smoothing) and what exposure_gains needs besides, so the page evens it for
    any smoothing; "local" false where the gain cannot be put on the drawn frame (a tile with a gain of its own);
    null while the chain is worked out (in the background). "detail": a filled pass, whose frames end in detail()
    ("sigma", "amount"): the page gains, mixes and trails the frames drawn without it (sharpen False) and sharpens
    them itself."""
    if u.get("track") or not calibration.step("align"):
        return {"local": False}
    rec = _record(u, cache)
    if not _steady_ready(u, cache, rec):
        warm_movie(u, n, 6, cache, steady=True)
        return {"working": True}
    p = plan(u, cache)
    chain = steady_chain(u, cache, p)
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    fp = movie_footprint(u, cache, p)
    x0, y0, x1, y1 = fp
    fixed = bool((centre and centre_half(fp, radius)) or max(x1 - x0, y1 - y0) <= MOVIE_FIT * FRAME)
    if not fixed:
        return {"local": False}
    ns = sorted(chain)
    tiles = {n: tile(u, n, cache, p["display_scale"]) for n in ns}
    rect = movie_rect(fp, tiles[ns[0]], radius, centre)
    how = (bool(colour), bool(centre), 0)
    exposure = None
    if _exposure_ready(u, cache, rec, how):
        logs = exposure_chain(u, cache, p, *how)
        exposure = {"local": all(tiles[m].get("gain", 1.0) == 1.0 for m in ns),
                    "logs": {str(m): v for m, v in logs.items()}, "gamma": p["display_scale"].get("gamma", 2.2),
                    "flash": EXPOSURE_FLASH, "gain": EXPOSURE_GAIN, "greyRun": EXPOSURE_GREY_RUN, "most": EXPOSURE_MOST}
    else:
        warm_movie(u, n, 6, cache, exposure=how)
    return {"local": True, "fixed": True, "ids": [fr[1] for fr in u["frames"]], "n": ns, "exposure": exposure,
            "sets": _colour_recipes(u, p, cache, ns, tiles) if colour and p.get("colour") else None,
            "filters": [fr[2] for fr in u["frames"]], "trail_most": TRAIL,
            "chain": [chain[n] for n in ns], "spice": [tiles[n]["offset"] for n in ns],
            "box": [tiles[n]["box"] for n in ns], "view": list(rect), "out": OUT, "k": OUT / max(rect[2], rect[3]),
            "colour": bool(p.get("colour")), "most": STEADY_MOST, "detail": bool(p["display_scale"].get("filled")),
            "sigma": DETAIL_SIGMA * FRAME * OUT / max(rect[2], rect[3]), "amount": DETAIL}


def _colour_recipes(u, p, cache, ns, tiles):
    """How movie_frame draws each frame of a colour pass, for the page: {"filters", "mix" (colour_picture's 3x3
    natural mix, or None to draw the filters straight), "gamma", "shoulder", "by": {frame n: the tiles of its colour
    set in the filters' order, or absent when the frame is drawn alone}}; None for a false colour pass (its mix
    blurs and balances the picture: drawn by the server). The set is the one movie_frame picks at SPICE's places."""
    want = p["colour"]
    scale = p["display_scale"]
    bal = scale.get("balance")
    mix = calibration.color_mix(u["key"][2], want, u["key"][0], [bal[f] for f in want] if bal else None)
    if isinstance(mix, calibration.FalseMix):
        return None
    by, placed = {}, set(ns)
    for n in ns:
        for run in reversed(colour_sets(u["frames"][:n + 1])):
            got = {f: j for f, j in run if f in want}
            if len(got) < len(want):
                continue
            if all(got[f] in placed for f in want):
                by[str(n)] = [got[f] for f in want]
            break
    return {"filters": list(want), "mix": None if mix is None else np.asarray(mix, float).tolist(),
            "gamma": scale.get("gamma", 2.2), "shoulder": calibration.SHOULDER, "by": by}


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
    half = centre_half(fp, radius) if centre else None
    if half:
        return -half, -half, 2 * half, 2 * half
    if max(x1 - x0, y1 - y0) <= side:
        return x0, y0, x1 - x0, y1 - y0
    w, h = min(x1 - x0, side), min(y1 - y0, side)
    cx, cy = t["offset"]
    return min(max(cx - w / 2, x0), x1 - w), min(max(cy - h / 2, y0), y1 - h), w, h


def centre_half(fp, radius):
    """Half the side of the square view centred on the body that movie_rect uses (reference pixels), or None when
    the body is not centred: its disk (radius) does not fit MOVIE_FIT frames with CENTRE_MARGIN round it, or the
    frames do not look at it (its centre outside the footprint fp)."""
    x0, y0, x1, y1 = fp
    side = MOVIE_FIT * FRAME
    around = max(FRAME, 2 * radius * (1 + CENTRE_MARGIN))
    if radius > 0 and around <= side and x0 <= 0 <= x1 and y0 <= 0 <= y1:
        return min(side, max(around, 2 * max(-x0, x1, -y0, y1))) / 2
    return None


_centre_views = {}   # pass key -> centre_view's decision for it
_centre_of = {}      # frame id -> centre_view's answer, for a frame SPICE places (a request per picture asks)


def centre_view(frame_id):
    """Auto center for a picture shown on its own (a frame or a color composite) in the camera windows: the rule
    of a movie centred on its body (centre_half), decided once for the pass the frame is in, from the geometry
    cache's footprint of the pass (_box), so a pass is centred all through or not at all. A frame in no pass is its
    own pass. Each picture keeps its frame's own scale: the view is one frame (FRAME full resolution pixels) square
    round the body, so the picture is the size it is today, only moved so the body is in the middle (a movie's view
    is the pass's, movie_rect). Answers {"centre": True, "side": FRAME, "radius": ..., "pass": [...]}, or
    {"centre": False, "north": True, "side": FRAME, "why": ...} for a close-up (frames on a body too big for the
    view): turned north up where it is, so the surface holds still; {"centre": False, "why": ...} for a ring, spoke
    or sky pass (Cassini kept those upright in the camera) or a frame SPICE has no place for, which keep the
    picture as it is."""
    with _lock:
        hit = _centre_of.get(frame_id)
    if hit is not None:
        return dict(hit)
    idx, row = _row_of()
    q = row.get(frame_id)
    if q is None:
        return {"centre": False, "why": "not in the index"}
    g = reel.geometry([frame_id]).get(frame_id)
    if not g or not g[2]:
        # (not kept: the geometry cache may place the frame later)
        return {"centre": False, "why": "SPICE has no place for the frame"}
    found = unit_of(frame_id)
    if found:
        u = found[0]
        key, target, cam, z = u["key"], u["key"][0], u["key"][2], u["z"]
    else:
        r = idx.iloc[q]
        target, cam, z = r["TARGET_NAME"], "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W", g[2]
        key = (target, frame_id, cam)
    with _lock:
        hit = _centre_views.get(key)
    if hit is None:
        radius = RADIUS.get(target, 0) / (z * IFOV[cam])
        fp = _box(u, z) if found else (-g[0] - HALF, -g[1] - HALF, -g[0] + HALF, -g[1] + HALF)
        half = centre_half(fp, radius) if fp and radius else None
        hit = {"centre": bool(half), "pass": [str(v) for v in key]}
        if not half:
            hit["why"] = "no disk of a known body that fits the view" if not radius else \
                "the body is too big for the view or the frames do not look at it"
            # north up where it is only when the frames are on the body's disk (a close-up): the body's surface
            # then holds still. Off the disk (rings, sky) Cassini rolled to keep the scene upright in the camera,
            # so the camera's own orientation is the steady one and north up would turn it frame to frame
            boxes = [(-x * fz / z - HALF, -y * fz / z - HALF, -x * fz / z + HALF, -y * fz / z + HALF)
                     for *_, x, y, fz in u["frames"] if fz] if found else [fp]
            # most of the pass's frames, each on its own (an arcing ring scan's footprint can clip the disk though
            # none of its frames is on it)
            on = sum(_on_disk(b, radius) for b in boxes) if radius else 0
            hit["north"] = bool(boxes) and on * 2 > len(boxes)
        with _lock:
            _centre_views[key] = hit
    # the frame's own disk of the body (full resolution pixels), so centred knows whether the frame cuts it
    if hit["centre"]:
        hit = dict(hit, side=FRAME, radius=RADIUS.get(target, 0) / (g[2] * IFOV[cam]))
    else:
        hit = dict(hit, side=FRAME) if hit.get("north") else dict(hit)
    with _lock:
        if len(_centre_of) >= UNIT_OF_KEEP:
            _centre_of.clear()
        _centre_of[frame_id] = hit
    return dict(hit)


def _on_disk(fp, radius):
    """True when the box fp (a frame's footprint, reference pixels round the body's centre) takes in part of the
    body's disk."""
    x0, y0, x1, y1 = fp
    dx, dy = max(x0, 0, -x1), max(y0, 0, -y1)
    return dx * dx + dy * dy < radius * radius


def _place(u, t, rect, k, W, H, cache, scale):
    """Tile t (made on the display scale) drawn where SPICE puts it in the view rect, on a W x H canvas (k canvas
    pixels per reference pixel)."""
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    frame = np.zeros((H, W, 4), np.uint8)
    x0, y0, x1, y1 = max(left, 0), max(top, 0), min(left + sw, W), min(top + sh, H)
    if x0 < x1 and y0 < y1:
        part = _shade(_part(os.path.join(_tiles(u, cache, scale), f"{t['n']}.png"), sw, sh), t)
        frame[y0:y1, x0:x1] = part[y0 - top:y1 - top, x0 - left:x1 - left]
    return frame


def colour_sets(frames):
    """The pass's frames grouped into filter sets, the camera windows' own (sets_passes, the one rule: reel.load_index's
    sets, which the page reads from the data): a run of frames, each taken within SET_GAP of the one before, through
    different filters; a clear or polarizer frame ends it, and a filter coming round again starts a new one (the next
    pointing of a mosaic, the next colour cycle). Each set is a list of (filter, frame index), in time order, with the
    set's frames that are tiles of the pass (a repeat exposure units leaves out is stacked into its tile). Frames
    the index does not have are grouped by the same rule among themselves."""
    try:
        idx, row = _row_of()
    except FileNotFoundError:   # no index (a synthetic pass)
        idx, row = None, {}
    qs = [row.get(fr[1]) for fr in frames]
    if not frames or any(q is None for q in qs):
        return _own_sets(frames)
    set_of, by = idx["set"].to_numpy(), {}
    for j, (fr, q) in enumerate(zip(frames, qs)):
        if set_of[q] >= 0:
            by.setdefault(int(set_of[q]), []).append((fr[2], j))
    return [run for _, run in sorted(by.items(), key=lambda kv: kv[1][0][1]) if len(run) >= 2]


def _own_sets(frames):
    """colour_sets' rule applied to frames on their own (one camera, target and observation)."""
    at = sets_passes.runs([("", "", "", None if fr[2] == "CL1/CL2" or _polarizer(fr[2]) else fr[2], fr[3]) for fr in frames])
    return [[(frames[j][2], j) for j in run] for run in sorted(at, key=lambda r: r[0])]


def movie_frame(u, n, cache, trail=0, colour=True, out=OUT, centre=True, steady=0, exposure=0, sharpen=True):
    """Frame n of the pass played as a movie, RGBA out px on its longest side, and its report; (None, report)
    when SPICE could not place it. The frame is the pass's tile n (color_image.processed_frame: repeat exposures
    merged in I/F, calibrated, centred north up by SPICE, scaled to the pass's reference distance, on the pass's
    one display scale), drawn where SPICE puts it in movie_rect: so the picture keeps one brightness scale and one
    size for the whole pass, and the body holds still. colour: when the pass's plan has colour filters and the
    newest frame of each of them was taken within reel.SET_GAP of this one, the three are drawn as one colour
    picture (each where SPICE puts it), as the pass's mosaic does; otherwise the frame in grey. trail: up to that
    many earlier frames of the same filter drawn under it, fading with age (a rolling trail). In a colour pass every
    frame shows the newest complete colour set, held until the next one is complete. centre: the body in the
    middle of the view (movie_rect). steady: image stabilization (Settings > Movie), every tile drawn at its
    stabilized place (steady_places, smoothed over that many frames) instead of SPICE's; 0: SPICE's places.
    exposure: exposure normalization (Settings > Movie), the whole picture drawn with frame n's exposure gain
    (exposure_gains, smoothed over that many frames); 0: as the pass's display scale draws it. sharpen: a filled
    pass's last step, detail(); False leaves it out (the plane a browser gains, mixes and sharpens itself,
    steady-local.html)."""
    p = plan(u, cache)
    t = tile(u, n, cache, p["display_scale"])
    rep = {"movie": True, "n": n, "of": len(u["frames"]), "filter": t["filter"], "observation": u["key"][1],
           "pass": u["key"][3], "id": t["id"]}
    if "offset" not in t:
        rep["why"] = t.get("why", "not placed by SPICE")
        return None, rep
    # a feature track: every tile drawn at its steady place (track_places), so the feature holds still; the body
    # moves past it instead, so a track is not centred on the body
    track = track_places(u, cache, p) if u.get("track") else None
    # any other movie: stabilized, each tile where the pictures put it from the tile before, held to SPICE
    places = track or (steady_places(u, cache, p, steady) if steady else None)

    # one gain for every tile of the picture (a colour set's filters, the trail), so its colour stays
    gain = exposure_gains(u, cache, p, exposure, colour, centre, steady).get(n, 1.0) if exposure else 1.0
    gamma = p["display_scale"].get("gamma", 2.2)

    def at(q):
        if places and q.get("n") in places:
            q = dict(q, offset=places[q["n"]])
        if gain != 1.0:
            q = dict(q, gain=round(q.get("gain", 1.0) * gain, 3), gamma=q.get("gamma", gamma))
        return q
    spice, raw = t["offset"], t
    t = at(t)
    if track:
        rep["steady"] = "track"
    elif places:
        rep["steady"] = "stabilized"
        rep["stabilized"] = {"smooth": steady, "shift": [round(t["offset"][0] - spice[0], 2), round(t["offset"][1] - spice[1], 2)]}
    if exposure:
        rep["exposure"] = {"smooth": exposure, "gain": gain}
    radius = RADIUS.get(u["key"][0], 0) / (u["z"] * IFOV[u["key"][2]])
    rect = movie_rect(movie_footprint(u, cache, p), t, radius, centre and not track)
    rep["centred"] = rect[0] == -rect[2] / 2 and rect[1] == -rect[3] / 2
    k = out / max(rect[2], rect[3])
    W, H = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    # only the frames this picture needs are made: the newest of each colour filter within SET_GAP, the trail
    frames, used, newest = u["frames"], None, {}
    # a pass with colour plays in colour: every frame shows the newest colour set taken by then (colour_sets, the
    # camera windows' sets, so the movie mixes the frames color.webp does), held until the next set is complete, as
    # the camera windows hold a colour movie's last set; a frame of another filter (CB2, a methane band) keeps it up
    if colour and p["colour"]:
        want = p["colour"]
        for run in reversed(colour_sets(frames[:n + 1])):
            got = {f: j for f, j in run if f in want}
            if len(got) < len(want):
                continue
            for f, j in got.items():
                # (frame n's own tile as made: at() is applied once, below, so its gain is not taken twice)
                q = raw if j == n else tile(u, j, cache, p["display_scale"])
                if "offset" in q:
                    newest[f] = at(q)
            if len(newest) == len(want):
                used = want
            break
    if used:
        planes = [_place(u, newest[f], rect, k, W, H, cache, p["display_scale"]) for f in used]
        # a colour set held from an earlier pointing that is out of this frame's view (a track's last visit, a
        # thousand px away) leaves the picture empty: the frame is drawn on its own instead
        if any(a[..., 3].any() for a in planes):
            rgba = colour_picture(u, p, used, planes)
            rep["color"] = used
            rep["ids"] = [newest[f]["id"] for f in used]
        else:
            used = None
    if not used:
        rgba = _place(u, t, rect, k, W, H, cache, p["display_scale"])
        # the rolling trail: earlier frames of this filter under it, older ones fainter
        if trail:
            js = [j for j in range(n - 1, max(-1, n - 8 * trail), -1) if frames[j][2] == t["filter"]][:trail]
            older = [at(q) for q in (tile(u, j, cache, p["display_scale"]) for j in reversed(js)) if "offset" in q]
            acc = np.zeros((H, W, 4), np.float32)
            for age, q in zip(range(len(older), 0, -1), older):
                a = _place(u, q, rect, k, W, H, cache, p["display_scale"]).astype(np.float32)
                w = a[..., 3:] / 255 * (1 - age / (len(older) + 1))
                acc[..., :3] = acc[..., :3] * (1 - w) + a[..., :3] * w
                acc[..., 3:] = np.maximum(acc[..., 3:], w * 255)
            w = rgba[..., 3:].astype(np.float32) / 255
            acc[..., :3] = acc[..., :3] * (1 - w) + rgba[..., :3] * w
            acc[..., 3:] = np.maximum(acc[..., 3:], rgba[..., 3:])
            rgba = (acc + 0.5).astype(np.uint8)
            rep["trail"] = len(older)
    if p["display_scale"].get("filled") and sharpen:
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * k)
    rep.update({"view": [round(v, 1) for v in rect], "width": W, "height": H})
    return Image.fromarray(rgba, "RGBA"), rep


# the same frame drawn the same way: named in the cache by folder, frame, trail, colour and centring (movie_webp)
movie_frame = _kept_for_next_size(movie_frame, lambda u, n, cache, trail=0, colour=True, out=OUT, centre=True, steady=0, exposure=0, sharpen=True:
                                  (folder(u, cache), n, trail, colour, out, centre, bool(u.get("track")), steady, exposure, sharpen)
                                  if out <= OUT else None)


# a pass's movie frames, renamed whenever the way they are drawn changes (movie-2: colour frames mixed as the mosaic is)
MOVIE_DIR = "movie-2"
MOVIE_SIZES = (512, 1024)   # the sizes the windows play a movie at, smallest first (a smaller one is shrunk from them)


def steady_of(u, steady):
    """The stabilization smoothing a movie of pass u is drawn with: steady (Settings > Movie, frames) within
    0..STEADY_MOST, 0 for a feature track (always steady, track_places) and with Settings > Processing's alignment
    off (SPICE's places)."""
    if u.get("track") or not calibration.step("align"):
        return 0
    return max(0, min(STEADY_MOST, int(steady or 0)))


def exposure_of(exposure):
    """The exposure smoothing a movie is drawn with: exposure (Settings > Movie, frames) within 0..EXPOSURE_MOST."""
    return max(0, min(EXPOSURE_MOST, int(exposure or 0)))


def _exposure_ready(u, cache, rec, how):
    """True when the pass's brightness chain for this way of drawing it (how: colour, centre, steady) is in memory
    or in the cache."""
    return (rec is not None and ("exposure",) + tuple(how) in (rec.get("exposure") or {})) or \
        os.path.exists(os.path.join(folder(u, cache), _exposure_name(*how)))


def _steady_ready(u, cache, rec):
    """True when the pass's stabilization chain is in memory or in the cache."""
    return (rec is not None and rec.get("steady") is not None) or os.path.exists(os.path.join(folder(u, cache), STEADY_FILE))


def movie_webp(frame_id, size, cache, trail=0, colour=True, wait=False, ahead=6, centre=True, steady=0, exposure=0, sharpen=True):
    """(WebP, report) of frame_id played as a movie of its pass (movie_frame), made once and kept in the cache;
    None when the frame is in no pass. A pass whose plan is not worked out yet (seconds: it measures the pass's
    scale) is started in the background and answers (None, report) unless wait, so the window shows the plain
    frame meanwhile. Then makes the next few tiles in the background. centre: the body in the middle (movie_rect).
    steady: image stabilization smoothed over that many frames (steady_places), 0 for SPICE's places; a pass whose
    stabilization is not worked out yet (every tile registered: seconds to a minute) answers as a new pass does.
    exposure: exposure normalization smoothed over that many frames (exposure_gains), 0 for none; the same.
    sharpen False: a filled pass's frame before detail() (movie_frame), named apart (_d0); the same picture as
    sharpen True for any other pass."""
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    steady, exposure = steady_of(u, steady), exposure_of(exposure)
    rec = _record(u, cache)
    if not wait and ((_footprint_kept(u, rec) is None and
                      not all(os.path.exists(os.path.join(folder(u, cache), f)) for f in (PLAN_FILE, _footprint_file(u))))
                     or (steady and not _steady_ready(u, cache, rec)) or (exposure and not _exposure_ready(u, cache, rec, (bool(colour), bool(centre), 0)))):
        warm_movie(u, n, ahead, cache, steady=bool(steady), exposure=(bool(colour), bool(centre), 0) if exposure else None)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3]}
    # (a feature track's frames, at their steady places, are named apart from the frames it played before, and so
    # are a stabilized movie's, by its smoothing; a filled pass's frame before detail() by _d0)
    filled = not sharpen and bool(plan(u, cache)["display_scale"].get("filled"))
    path = os.path.join(folder(u, cache), MOVIE_DIR, str(size),
                        f"{n}_{trail}_{int(bool(colour))}{'_c2' if centre else ''}{'_k2' if u.get('track') else ''}"
                        f"{f'_s{steady}' if steady else ''}{f'_e{exposure}r{EXPOSURE_RULE}' if exposure else ''}{'_d0' if not sharpen and filled else ''}.webp")
    report, meta = {}, path[:-4] + "json"

    def make():
        # a strip (smaller than the sizes a window plays) of a frame already kept at one of them is that picture
        # shrunk (both are movie_frame at OUT, shrunk): the pass's tiles are not read again
        for big in MOVIE_SIZES:
            kept = os.path.join(folder(u, cache), MOVIE_DIR, str(big), os.path.basename(path))
            if size < MOVIE_SIZES[0] and os.path.exists(kept) and os.path.exists(kept[:-4] + "json"):
                im, rep = Image.open(kept), reel.report_of(kept[:-4] + "json")
                im.load()
                break
        else:
            with _asking():
                im, rep = movie_frame(u, n, cache, trail, colour, centre=centre, steady=steady, exposure=exposure, sharpen=sharpen)
        report.update(rep)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        reel.keep_report(meta, rep)
        if im is None:
            raise LookupError(rep.get("why"))
        if max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=QUALITY, method=4)
        return buf.getvalue()

    try:
        data = reel._cached(path, make)
    except LookupError:
        return None, report
    finally:
        if ahead:
            warm_movie(u, n + 1, ahead, cache)
    if not report:
        report = reel.report_of(meta)
    return data, report


_movie_ahead = {}   # pass key -> (first, last) tile a movie wants made ahead; MOVIE_WORKERS threads per pass make them
MOVIE_WORKERS = int(os.environ.get("CASSINI_MOVIE_WORKERS", "2"))
_movie_background = threading.Semaphore(MOVIE_WORKERS)   # movie frames made ahead, beside the mosaics' one at a time


def warm_movie(u, n, ahead, cache, steady=False, exposure=None):
    """A movie is at frame n of the pass: work out its plan and make tiles n .. n+ahead in the background, from
    where the movie is rather than from the pass's start, MOVIE_WORKERS at once (a fast movie at high playback
    speed needs several frames a second). steady: the pass's stabilization chain too (steady_chain); exposure: (colour, centre, steady) of its brightness chain (exposure_chain) to work out too."""
    mode = calibration.mode()
    key, last = (u["key"], mode), min(n + ahead, len(u["frames"]) - 1)
    # nothing to make (the plan, footprint and those tiles are in memory): no workers
    rec = _record(u, cache)
    if rec is not None and (_footprint_kept(u, rec) is not None or u.get("kind", "movie" if u.get("movie") else None) == "mosaic_movie") \
            and _all_made(u, cache, rec["plan"], n, last, look=True) and not (steady and not _steady_ready(u, cache, rec)) \
            and not (exposure and not _exposure_ready(u, cache, rec, exposure)):
        return
    with _lock:
        running = key in _movie_ahead
        _movie_ahead[key] = (n, last)
        if running:
            return

    taking = set()

    def run():
        try:
            with _movie_background, calibration.in_mode(mode):
                p = plan(u, cache)
                if u.get("kind", "movie" if u.get("movie") else None) != "mosaic_movie":
                    movie_footprint(u, cache, p)
                    if steady:
                        steady_chain(u, cache, p)
                    if exposure:
                        exposure_chain(u, cache, p, *exposure)
                while True:
                    with _lock:
                        first, last = _movie_ahead.get(key, (0, -1))
                    todo = [j for j in range(first, last + 1) if j not in taking and not _has_tile(u, j, cache, p)]
                    with _lock:
                        todo = [j for j in todo if j not in taking]
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


def slots(u):
    """The place of each frame of pass u (places), with the camera's drift over a long mosaic movie taken out:
    places closer than half the pass's step (the median jump from one place to the next in one filter) are one
    slot. The Jupiter approach's 2x2s drift over nine laps by more than mosaic.min_step, so the classifier gives
    their last laps places of their own (8 for 4 tiles), and without this a lap over the drifted places would run
    on into the next (lap_of) and a drifted tile would stay up beside its own older copy (rolling_layout). None
    for a frame with no place."""
    if "slots" in u:
        return u["slots"]
    u["slots"] = _slot_of(u, places(u))
    return u["slots"]


def _slot_of(u, where):
    """(slots) the slot of each frame of pass u, its places being where."""
    at, last, steps = {}, {}, []
    for fr, i in zip(u["frames"], where):
        x, y, z = fr[5:8]
        if i is None or not z or not u.get("z"):
            continue
        p = (-x * z / u["z"], -y * z / u["z"])
        at.setdefault(i, []).append(p)
        if fr[2] in last and last[fr[2]][0] != i:
            steps.append(max(abs(p[0] - last[fr[2]][1][0]), abs(p[1] - last[fr[2]][1][1])))
        last[fr[2]] = (i, p)
    near = 0.5 * float(np.median(steps)) if steps else 0.0
    centre = {i: np.mean(v, 0) for i, v in at.items()}
    parent = {i: i for i in centre}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    if near > mosaic.min_step * FRAME:
        for a in sorted(centre):
            for b in sorted(centre):
                if b > a and np.abs(centre[a] - centre[b]).max() < near and root(a) != root(b):
                    parent[max(root(a), root(b))] = min(root(a), root(b))
    return [root(i) if i in parent else i for i in where]


def lap_of(u):
    """The lap each frame of pass u is in: how many times the camera has come back to a slot in one filter by that
    frame (a run of frames at one slot counts once), the most over its filters; 1 for a pass that never comes back."""
    if "lap_of" in u:
        return u["lap_of"]
    runs, lap, out = {}, 1, []
    for fr, i in zip(u["frames"], slots(u) if u["frames"] else []):
        if i is not None:
            seq = runs.setdefault(fr[2], [])
            if not seq or seq[-1] != i:
                seq.append(i)
                lap = max(lap, seq.count(i))
        out.append(lap)
    u["lap_of"] = out
    return out


def lap_ends(u):
    """The frames (indices into u["frames"]) that finish a whole lap of a mosaic movie: the last frame before the
    camera comes back to a slot it has already taken in this lap (lap_of), or the pass's last frame, of a lap that
    took every slot in every filter the pass's laps usually take (the median over its laps: a lap that started or
    stopped short, or missed a filter's tile, is not whole). At one of them every tile is new, so the rolling
    picture there (rolling_layout) is a whole new mosaic (Settings > Movie > Mosaic movie frames: Whole mosaics),
    rather than new tiles over the last lap's, which Jupiter has turned a sixth of a turn away from. When no lap
    is whole, the pass's last frame. [] for a pass that is not a mosaic movie."""
    if u.get("kind") != "mosaic_movie" or not u["frames"]:
        return []
    lap = lap_of(u)
    ends = [j for j in range(len(lap) - 1) if lap[j + 1] > lap[j]] + [len(lap) - 1]
    took = {n: {} for n in set(lap)}
    for fr, i, n in zip(u["frames"], slots(u), lap):
        if i is not None:
            took[n].setdefault(fr[2], set()).add(i)
    filters = {f for t in took.values() for f in t}
    need = {f: float(np.median([len(t.get(f, ())) for t in took.values()])) for f in filters}
    whole = [j for j in ends if all(len(took[lap[j]].get(f, ())) >= need[f] for f in filters)]
    return whole or ends[-1:]


def lap_end(frame_id):
    """True when frame_id finishes a lap of a mosaic movie (lap_ends), False for another frame of one, None when
    it is in no mosaic movie."""
    found = unit_of(frame_id)
    if not found or found[0].get("kind") != "mosaic_movie":
        return None
    u, n = found
    return u["frames"][n][1] == frame_id and n in lap_ends(u)


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


FADE_MAX = 120       # most frames a mosaic movie's older tiles fade over (Settings > Movie > Older tiles fade over)
FADE_PERSIST = 35    # how bright a faded tile stays, per cent (Settings > Movie > Faded tiles keep)


def fade_style(fade=0, persist=FADE_PERSIST):
    """A mosaic movie's fade as (frames, per cent), clamped; (0, 0) when off, so every name made without one stays
    as it was."""
    fade = max(0, min(FADE_MAX, int(fade or 0)))
    return (fade, max(0, min(100, int(persist)))) if fade else (0, 0)


def _fade_weight(age, fade):
    """How bright a tile age frames older than the newest drawn stays when older tiles fade over fade[0] frames
    down to fade[1] per cent: 1 for the newest, falling evenly to that floor and staying there."""
    floor = fade[1] / 100
    return 1.0 if age <= 0 else max(floor, 1 - (1 - floor) * age / fade[0])


def rolling_layout(u, n, cache, laps=1, made_only=False, skipped=None, fade=(0, 0)):
    """What a mosaic movie (a raster repeated over the same places: kind "mosaic_movie") shows at frame n, in the
    form of layout(): every place's newest tile of each filter taken by then, so the mosaic never empties when a
    new lap begins and each tile replaces its own earlier copy (laps=1, a time-lapse); laps=N keeps the N newest
    copies of each place, older under newer (a rolling mosaic). Drawn by so_far through filter_mosaic and
    mosaic.compose like the pass's mosaic, on its scale and in its view. made_only: only tile n is made here, the
    other places show the tiles already made (a window playing fast never waits on the tiles it missed;
    tiles_ahead makes them); skipped (a list) gets the tiles left out for that, so the caller knows the picture
    is not yet the frame's own. fade (fade_style): older tiles fade (Rolling) rather than stay as bright as the
    newest (Time-lapse): each drawn tile gets a "fade" field (0-1, _fade_weight of its age in frames behind the
    newest drawn), which _faded applies to the composed picture, and the picture's name says so."""
    p = plan(u, cache)
    where = slots(u)
    rec = _kept_tiles(u, cache, p["display_scale"])
    with _lock:
        kept = dict(rec["tiles"]) if rec is not None else {}
    there = rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"])
    # each place's newest copies that are there to draw: a copy not made yet (made_only) or one SPICE could not
    # place leaves the copy before it up, so a place never drops out of the mosaic and comes back
    keep, seen = [], {}
    for j in range(n, -1, -1):
        # (a frame the classifier gave no place stays up on its own, under the newer ones, rather than taking the
        # place of every other such frame)
        key = (where[j] if where[j] is not None else ("frame", j), u["frames"][j][2])
        if seen.get(key, 0) >= laps:
            continue
        t = kept.get(j)
        if t is None:
            if made_only and j != n and not os.path.exists(os.path.join(there, f"{j}.json")):
                if skipped is not None:
                    skipped.append(j)
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
    if not fade[0]:
        return p, tiles, rect, count, used, f"lap-{laps}-{ids}"
    # ages from the newest tile drawn, so frames of a filter the picture does not draw share its picture; copies
    # of the tile dicts, since the pass's record keeps the originals
    newest = max(t["n"] for t in tiles if t["filter"] in used)
    tiles = [dict(t, fade=_fade_weight(newest - t["n"], fade)) for t in tiles]
    return p, tiles, rect, count, used, f"lap-{laps}-f{fade[0]}p{fade[1]}-{ids}"


FADE_SCALE = 4   # the fade's brightness map is worked out at this fraction of the picture's size (it is smooth)


def _faded(u, made, cache):
    """The post step (_make_mosaic) of a mosaic movie whose older tiles fade: the composed picture's colour
    multiplied by each place's fade, a map drawn from the tiles' own alpha oldest first (newer over older, as
    compose draws them, soft at their feathered edges) at 1/FADE_SCALE of the picture's size. Done after compose,
    so the filter mosaics stay the time-lapse's own (grown a tile a frame, _roll, and shared with it) and the
    seams are solved on the tiles as they are."""
    import cv2
    p, tiles, rect, _, used, _ = made
    there = _tiles(u, cache, p["display_scale"])

    def post(im):
        W, H = im.size
        w, h = max(1, W // FADE_SCALE), max(1, H // FADE_SCALE)
        light = np.ones((h, w), np.float32)
        for t in tiles:
            if t["filter"] not in used or "offset" not in t:
                continue
            part = _fade_part(t, rect, w, h, there)
            if part is None:
                continue
            (a0, b0, a1, b1), a = part
            a = a.astype(np.float32) / 255
            light[b0:b1, a0:a1] = light[b0:b1, a0:a1] * (1 - a) + t.get("fade", 1.0) * a
        light = cv2.resize(light, (W, H), interpolation=cv2.INTER_LINEAR)
        rgba = np.asarray(im.convert("RGBA")).astype(np.float32)
        rgba[..., :3] *= light[..., None]
        return Image.fromarray((rgba + 0.5).clip(0, 255).astype(np.uint8), "RGBA")
    return post


def _fade_part(t, rect, w, h, there):
    """Where tile t lies on a fade's brightness map (w x h, the view rect) and its alpha there (uint8), or None
    when it is off the map: ((a0, b0, a1, b1), alpha)."""
    k = w / rect[2]
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    a0, b0, a1, b1 = max(left, 0), max(top, 0), min(left + sw, w), min(top + sh, h)
    if a1 <= a0 or b1 <= b0:
        return None
    return (a0, b0, a1, b1), _part(os.path.join(there, f"{t['n']}.png"), sw, sh)[b0 - top:b1 - top, a0 - left:a1 - left, 3]


def fade_table(frame_id, cache, laps=1, W=0, H=0):
    """What a browser needs to fade a mosaic movie's older tiles by itself (steady-local.html, cassiniFadeLocal),
    on the time-lapse picture the server already has (fade 0, W x H px as made at OUT), for any fade and persistence:
    every frame's drawn tiles and the filters it draws (rolling_layout at laps), and each tile's place and alpha on
    the fade's brightness map (_fade_part, the map 1/FADE_SCALE of the picture; zlib, base64), so _faded's post step is worked out
    in the page. None when the frame is in no mosaic movie; {"working": true} while some of its tiles are not made
    (the page asks the server for the faded pictures meanwhile)."""
    import base64
    import zlib
    found = unit_of(frame_id)
    if not found or found[1] < 0 or found[0].get("kind") != "mosaic_movie":
        return None
    u = found[0]
    if not W or not H:
        return {"local": False}
    p = plan(u, cache)
    there = _tiles(u, cache, p["display_scale"])
    w, h = max(1, W // FADE_SCALE), max(1, H // FADE_SCALE)
    frames, parts, rect = [], {}, None
    for j in range(len(u["frames"])):
        skipped = []
        made = rolling_layout(u, j, cache, laps, made_only=True, skipped=skipped)
        if skipped:
            tiles_ahead(u, j, cache)
            return {"working": True}
        if not made:
            frames.append(None)
            continue
        _, tiles, rect, _, used, _ = made
        drawn = [t for t in tiles if t["filter"] in used and "offset" in t]
        frames.append({"n": [t["n"] for t in drawn], "newest": max([t["n"] for t in drawn] or [j])})
        for t in drawn:
            if str(t["n"]) not in parts:
                part = _fade_part(t, rect, w, h, there)
                parts[str(t["n"])] = None if part is None else {
                    "at": list(part[0]), "alpha": base64.b64encode(zlib.compress(np.ascontiguousarray(part[1]).tobytes(), 6)).decode()}
    return {"local": True, "laps": laps, "W": W, "H": H, "w": w, "h": h, "frames": frames, "parts": parts,
            "ids": [fr[1] for fr in u["frames"]], "fade_max": FADE_MAX}


def _rolling_picture(u, n, size, cache, laps, slots, fmt, out, made_only, read=True, skipped=None, fade=(0, 0)):
    """(WebP, report) of the pass's mosaic movie at frame n, made once and kept; None before any tile is placed.
    One frame's picture is made once at a time (a window's request and the one made ahead wait for each other).
    read=False (made ahead): True when the picture is in the cache already, without reading it. skipped: as
    rolling_layout's. fade: older tiles fade (fade_style), applied after compose (_faded)."""
    made = rolling_layout(u, n, cache, laps, made_only=made_only, skipped=skipped, fade=fade)
    if not made:
        return None
    post = _faded(u, made, cache) if fade[0] else None
    full = size == "full"
    path = os.path.join(drawn(u, cache), "rolling-level", f"full{out}" if full else str(size), f"{made[5]}.{fmt}")
    if os.path.exists(path):
        return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out, post) if read else True
    with _lock:
        lock = _making.setdefault(path, threading.Lock())
    token = _rolling.set(laps == 1)
    try:
        with lock:
            return _make_mosaic(u, n, size, path, cache, slots, made, fmt, out, post)
    finally:
        _rolling.reset(token)
        with _lock:
            _making.pop(path, None)


_roll_ahead = {}   # (pass, look) -> [the frame a window is at, size, out]: the mosaic movie pictures to make ahead
ROLL_AHEAD = 10    # frames of a mosaic movie made ahead of the window playing it
ROLL_WORKERS = int(os.environ.get("CASSINI_ROLL_WORKERS", "2"))   # ... this many at once (a color picture's mix is ~1 s)


def _picture_made(rec, size, out, n, skipped, fade=(0, 0)):
    """Frame n's mosaic movie picture is made: drawn with every tile it shows (none skipped as not made yet), it is
    the frame's picture for good, and the pass's record keeps that it is made (rolling_ahead)."""
    if rec is not None and not skipped:
        with _lock:
            rec["rolled"].setdefault((size, out, fade), set()).add(n)


def rolling_ahead(u, n, size, cache, slots=None, out=OUT, fade=(0, 0)):
    """A window plays the mosaic movie at frame n: make the pictures of frames n+1 .. n+ROLL_AHEAD (their tiles
    first) in the background, in order, each grown from one before it (_roll), so the window's next requests
    are answered from the cache. ROLL_WORKERS threads per pass, each taking the next frame not taken (a picture
    waits for the tiles before it, which the other thread may be making); a later call moves them on. Waits
    while a window waits for a mosaic (_yield). fade: the window's (fade_style), so they are its pictures."""
    mode = calibration.mode()
    key = (u["key"], mode, fade)
    rec = _record(u, cache)
    with _lock:
        # every picture ahead made already (the pass's record keeps which are): no workers
        known = rec["rolled"].get((size, out, fade), ()) if rec is not None else ()
        if known and all(j in known for j in range(n + 1, min(n + ROLL_AHEAD, len(u["frames"]) - 1) + 1)):
            return
        running = key in _roll_ahead
        taken = _roll_ahead[key][3] if running else [-1]
        _roll_ahead[key] = [n, size, out, taken, ROLL_WORKERS if not running else _roll_ahead[key][4]]
        if running:
            return

    def run():
        try:
            with calibration.in_mode(mode):
                p = plan(u, cache)
                kept = _kept_tiles(u, cache, p["display_scale"])
                while True:
                    with _lock:
                        at, sz, o, taken = _roll_ahead[key][:4]
                        made = kept["rolled"].get((sz, o, fade), ()) if kept is not None else ()
                        j = max(at, taken[0]) + 1
                        while j in made:   # (made already: nothing to do)
                            j += 1
                        taken[0] = j
                    if j > min(at + ROLL_AHEAD, len(u["frames"]) - 1):
                        return
                    for i in range(at + 1, j + 1):
                        _yield()
                        tile(u, i, cache, p["display_scale"])
                    _yield()
                    # one made already is not read again
                    skipped = []
                    if _rolling_picture(u, j, sz, cache, 1, slots, "webp", o, made_only=True, read=False, skipped=skipped,
                                        fade=fade):
                        _picture_made(kept, sz, o, j, skipped, fade)
        except Exception as e:
            print(f"mosaic movie ahead {u['key']} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                _roll_ahead[key][4] -= 1
                if not _roll_ahead[key][4]:
                    _roll_ahead.pop(key, None)

    for _ in range(ROLL_WORKERS):
        threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()


def rolling_webp(frame_id, size, cache, laps=1, slots=None, fmt="webp", out=OUT, wait=False, fade=(0, 0)):
    """(WebP, report) of frame_id's pass played as a mosaic movie (rolling_layout), made once and kept; None when
    the frame is in no pass, (None, report) while the pass is being worked out (unless wait). fade: older tiles
    fade (fade_style: frames, per cent; Rolling) instead of staying as bright as the newest (Time-lapse)."""
    fade = fade_style(*fade)
    found = unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    if not wait and not os.path.exists(os.path.join(folder(u, cache), PLAN_FILE)):
        warm_movie(u, n, 6, cache)
        return None, {"why": "working out the pass", "observation": u["key"][1], "pass": u["key"][3]}
    skipped = []
    with _asking():
        res = _rolling_picture(u, n, size, cache, laps, slots, fmt, out, made_only=not wait, skipped=skipped, fade=fade)
        if res is None:
            return None, {"why": "no tile placed yet"}
    if laps == 1 and fmt == "webp":
        _picture_made(_record(u, cache), size, out, n, skipped, fade)
    # the tiles ahead, by the pass's one background thread (tiles_ahead, as a pass mosaic's), and the pictures of
    # the next frames, so a playing window finds them made (rolling_ahead)
    tiles_ahead(u, n + 1, cache)
    if laps == 1 and size != "full" and fmt == "webp":
        rolling_ahead(u, n, size, cache, slots, out, fade)
    if res:
        res[1].update({"rolling": True, "keep": laps, "n": n, "fade": list(fade)})   # laps: the pass's own, from _make_mosaic
        if skipped:
            # drawn without tiles not made yet: the frame's picture for now, not for good (the server says so)
            res[1]["partial"] = len(skipped)
    return res


def _rims(mask):
    """The first and last set pixel of each row of mask (once when they are one pixel), as cv2.findNonZero gives
    points, or None when nothing is set. Every set pixel's convex hull is these points' hull, so minAreaRect finds
    the same rectangle from them, without sorting the million points of a tile (190 ms to 8 ms)."""
    rows = np.flatnonzero(mask.any(1))
    if not len(rows):
        return None
    sub = mask[rows]
    left, right = sub.argmax(1), mask.shape[1] - 1 - sub[:, ::-1].argmax(1)
    xs, ys = np.stack([left, right], 1).ravel(), np.repeat(rows, 2)
    keep = np.ones(len(xs), bool)
    keep[1::2] = right != left
    return np.stack([xs[keep], ys[keep]], 1).astype(np.int32).reshape(-1, 1, 2)


def _corners(t, alpha):
    """The four corners of the frame in a tile's picture (its alpha): the smallest rotated rectangle around it, so
    a frame turned north up keeps its slant, in reference pixels from the body's centre."""
    import cv2
    pts = _rims(alpha > 0)
    corners = cv2.boxPoints(cv2.minAreaRect(pts)) if pts is not None else np.zeros((4, 2))
    bx, by = t["box"][:2]
    return [[float(t["offset"][0] + bx + x), float(t["offset"][1] + by + y)] for x, y in corners]


def outline(u, t, cache):
    """Tile t's outline (_corners): kept in its report when the tile is made; for a tile made before that,
    measured once from tiles/<n>.png and kept beside it."""
    if "outline" in t:
        return t["outline"]
    base = os.path.join(_tiles(u, cache, plan(u, cache)["display_scale"]), str(t["n"]))
    with _lock:
        kept = _outlines.get(base)
    if kept is None:
        make = lambda: json.dumps(_corners(t, np.asarray(Image.open(base + ".png"))[..., 3])).encode()
        kept = json.loads(reel._cached(base + ".outline.json", make))
        with _lock:
            if len(_outlines) >= UNIT_OF_KEEP:
                _outlines.clear()
            _outlines[base] = kept
    return kept


_outlines = {}   # tile (its path, less .png) -> its outline, for tiles made before outlines were in their reports


def tile_map(frame_id, cache):
    """Where each frame sits in the mosaic shown for frame_id (the same layout as mosaic_webp, so the same
    tiles and view), for the camera windows' drill-down and Cassini Studio's tile tuning, the picture's manifest:
    {observation, target, pass, filters (the colour set or the gray filter drawn), layers {color: the colour
    filters when the picture has colour, else null; luminance: the luminance base's filters with a tile so far},
    pointings: [{n, t, ids {filter: id} (the filters drawn), luminance {filter: id} (frames drawn in the gray base
    only), set (every colour filter is there, so the pointing shows in colour), also {filter: id} (frames taken
    there that the picture does not draw), tiles, poly [[x, y] x4], center [x, y]}]} with x, y as fractions (0-1)
    of the picture. A pointing is the drawn tiles of different filters at one place (within SAME_PLACE of a frame)
    taken one after another; its outline is its newest tile's, which is the one on top. Kept beside the pass's
    mosaics (MAPS_DIR/<layout name>.json) once every tile in it is made. None when frame_id is not in a mosaic pass or
    nothing is placed yet."""
    found = unit_of(frame_id)
    if not found or not found[0]["mosaic"] or found[1] < 0:
        return None
    u, n = found
    made = layout(u, n, cache)
    if not made:
        return None
    key = (folder(u, cache), made[5])
    with _lock:
        if key in _maps:
            return _maps[key]
    kept = os.path.join(key[0], MAPS_DIR, f"{made[5]}.json")
    if os.path.exists(kept):
        with open(kept) as fh:
            found = json.load(fh)
        with _lock:
            _maps[key] = found
        return found
    p, tiles, rect, count, used, _ = made
    frames = lum_frames(u, p)
    colour = used if len(used) == 3 else None
    x0, y0, w, h = rect
    frac = lambda x, y: [round((x - x0) / w, 5), round((y - y0) / h, 5)]
    pointings, complete = [], True
    rec = _kept_tiles(u, cache, p["display_scale"])
    there = rec["tiles_dir"] if rec is not None else _tiles(u, cache, p["display_scale"])
    also = []
    for t in tiles:
        if "offset" not in t:
            continue
        if t["filter"] not in used and t["n"] not in frames:
            also.append(t)
            continue
        # (a tile's report is written after its picture: a tile whose report is kept in memory has its picture)
        if not (rec is not None and t["n"] in rec["tiles"]) and not os.path.exists(os.path.join(there, f"{t['n']}.png")):
            complete = False   # still being written: this map is not kept
            continue
        last = pointings[-1] if pointings else None
        if last and t["filter"] not in last["ids"] and t["filter"] not in last["luminance"] and \
                t["t"] - last["t1"] <= REPEAT_POINTING and \
                math.hypot(t["offset"][0] - last["at"][0], t["offset"][1] - last["at"][1]) <= SAME_PLACE * FRAME:
            pass
        else:
            last = {"ids": {}, "luminance": {}, "also": {}, "tiles": []}
            pointings.append(last)
        last["ids" if t["filter"] in used else "luminance"][t["filter"]] = t["id"]
        last["tiles"].append(t["n"])
        last["t1"], last["at"] = t["t"], t["offset"]
        last.setdefault("t", t["t"])
        last["poly"] = [frac(x, y) for x, y in outline(u, t, cache)]
        last["center"] = frac(*t["offset"])
    # the frames not drawn, each with the pointing at its place nearest in time
    for t in also:
        near = [(abs(q["t1"] - t["t"]), i) for i, q in enumerate(pointings)
                if math.hypot(t["offset"][0] - q["at"][0], t["offset"][1] - q["at"][1]) <= SAME_PLACE * FRAME]
        if near:
            pointings[min(near)[1]]["also"].setdefault(t["filter"], t["id"])
    out = []
    for q in pointings:
        q.pop("t1"); q.pop("at")
        q["set"] = bool(colour) and all(f in q["ids"] for f in colour)
        if not (max(c[0] for c in q["poly"]) <= 0 or min(c[0] for c in q["poly"]) >= 1 or
                max(c[1] for c in q["poly"]) <= 0 or min(c[1] for c in q["poly"]) >= 1):   # in the view
            out.append(dict(q, n=len(out) + 1))   # numbered as shown, so "n of N" holds
    found = {"observation": u["key"][1], "target": u["key"][0], "pass": u["key"][3], "filters": used,
             "layers": {"color": colour, "luminance": sorted({t["filter"] for t in tiles if "offset" in t and t["n"] in frames},
                                                              key=_luminance(p)["filters"].index)},
             "fixed": p["fixed"], "pointings": out}
    if complete:
        reel._cached(kept, lambda: json.dumps(found).encode())
    with _lock:
        if complete:
            _maps[key] = found
        while len(_maps) > MAPS_KEEP:
            _maps.pop(next(iter(_maps)))
    return found


MAPS_DIR = "maps-1"   # the kept manifests (under the pass's versioned folder), renamed whenever tile_map's answer changes
_maps = {}   # (pass folder, layout name) -> its tile map: a mosaic's map is asked for on every hover of a new picture
MAPS_KEEP = 512   # a few passes' every mosaic (a map is ~100 bytes a pointing), so a pass played again maps none again


POINT_MAX = 2048   # longest side of a pointing opened from its mosaic (its tiles are at the pass's reference distance)
POINTINGS_DIR = "pointings-3"   # the kept pictures of opened pointings (under the pass's versioned folder), renamed
#                                 whenever pointing_picture's answer changes


def pointing_of(mapped, ids):
    """The pointing of the tile map mapped (tile_map) that holds the frames ids (drawn there, or in its gray base), as
    the camera windows' older links name a pointing; None when no one pointing holds them all."""
    for q in mapped["pointings"]:
        if set(ids) <= set(q["ids"].values()) | set(q.get("luminance", {}).values()):
            return q
    return None


def pointing_picture(frame_id, n, cache, size="full", fmt="webp", slots=None, channel=None):
    """(picture, report) of pointing n (as tile_map numbers them) of the mosaic shown for frame_id, opened from it:
    the tiles the mosaic draws there, on a canvas of their own at the tiles' full size (up to POINT_MAX), each given
    the seam correction the mosaic gave it (_seam_of, fitted against its filter's mosaic) and composed through
    mosaic.compose, then mixed (colour_picture) and given the pass's local contrast (detail) as so_far does: the
    mosaic's own picture of that spot, larger. A pointing the colour set covers is in colour; elsewhere it is the gray
    the mosaic draws there (the luminance base, or the one filter drawn), before the gray's tint toward the colour it
    borders (match_grey). channel 0-2: one colour filter's plane, gray, as in that filter's mosaic (before the mix).
    None when the frame is not in a mosaic pass or there is no pointing n. Kept in the cache. The report's box is where
    the picture lies in the mosaic's picture (x, y, w, h as fractions of it), so the two can be laid on one another."""
    found = unit_of(frame_id)
    if not found or not found[0]["mosaic"] or found[1] < 0:
        return None
    u, i = found
    made, mapped = layout(u, i, cache), tile_map(frame_id, cache)
    q = next((q for q in mapped["pointings"] if q["n"] == n), None) if made and mapped else None
    if q is None:
        return None
    p, tiles, rect, count, used, name = made
    by_id = {t["id"]: t for t in tiles if "offset" in t}
    colour = q["set"] and len(used) == 3
    if colour:
        layers = [(by_id[q["ids"][f]], f) for f in used]
    else:
        # the gray the mosaic draws at a place its colour set does not cover: the luminance base's newest tile there
        # (so_far draws the base when lum_base says so), else the filter drawn
        mine = []
        if lum_base(u, p, tiles, used):
            frames, f = lum_frames(u, p), LUM
            mine = [by_id[v] for v in list(q["ids"].values()) + list(q.get("luminance", {}).values()) if v in by_id]
            mine = sorted((t for t in mine if t["n"] in frames), key=lambda t: t["n"])
        if not mine:
            # no base, or a place whose frames the base leaves to the grey filter's nearby: its own drawn filter, gray
            f, mine = None, [by_id[q["ids"][g]] for g in used if g in q["ids"]]
        if not mine:
            return None
        layers = [(mine[-1], f)]
    # a gray place in a colour mosaic: the gray takes the tint over_grey gives it toward the colour it borders
    tint = None
    if not colour and len(used) == 3 and layers[0][1] == LUM and channel is None:
        ref = max(used, key=lambda g: count[g])
        tint = grey_gain(colour_picture(u, p, used, [filter_mosaic(u, p, g, tiles, rect, cache, ref) for g in used]),
                         filter_mosaic(u, p, LUM, tiles, rect, cache), p["k"], p["display_scale"]["gamma"])
    if channel is not None and not 0 <= channel < len(layers):
        return None
    ids = [t["id"] for t, _ in layers]
    cut = "" if channel is None else f"_c{channel}"
    path = os.path.join(folder(u, cache), POINTINGS_DIR, name, f"{n}-{'_'.join(ids)}{cut}-{size}.{fmt}")

    def make():
        with slots or contextlib.nullcontext():
            rgba = _pointing(u, p, tiles, rect, count, used, layers, cache, channel, tint)[0]
        im = Image.fromarray(rgba, "RGBA") if channel is None else \
            Image.fromarray(np.ascontiguousarray(np.dstack([rgba[..., 0], rgba[..., 3]])), "LA")
        if size != "full" and max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "png":
            im.save(buf, "PNG", compress_level=6)
        else:
            im.save(buf, "WEBP", quality=QUALITY, method=4)
        return buf.getvalue()

    bx, by, bw, bh = pointing_box(layers)
    box = [round((bx - rect[0]) / rect[2], 5), round((by - rect[1]) / rect[3], 5), round(bw / rect[2], 5), round(bh / rect[3], 5)]
    return reel._cached(path, make), {"observation": u["key"][1], "pointing": n, "of": len(mapped["pointings"]), "ids": ids,
                                      "filters": [t["filter"] for t, _ in layers], "color": colour, "box": box}


def pointing_box(layers):
    """The canvas of an opened pointing: its tiles' boxes together (x0, y0, w, h, reference pixels from the body's centre)."""
    x0 = min(t["offset"][0] + t["box"][0] for t, _ in layers)
    y0 = min(t["offset"][1] + t["box"][1] for t, _ in layers)
    x1 = max(t["offset"][0] + t["box"][0] + t["box"][2] for t, _ in layers)
    y1 = max(t["offset"][1] + t["box"][1] + t["box"][3] for t, _ in layers)
    return x0, y0, x1 - x0, y1 - y0


def _pointing(u, p, tiles, rect, count, used, layers, cache, channel=None, tint=None):
    """pointing_picture's (RGBA, (x, y, k)): layers [(tile, LUM or None)], one per colour filter (red, green, blue) or
    one gray (tint: grey_gain's gain for it); x, y where its top left corner sits (reference pixels from the body's
    centre), k its pixels per them."""
    ref = max(used, key=lambda f: count[f])
    own = pointing_box(layers)
    x0, y0 = own[:2]
    k = min(1.0, POINT_MAX / max(own[2], own[3]))
    planes = []
    for t, f in layers:
        # the tile at its own size where it sits (_window on this canvas), corrected as the mosaic corrected it
        window, _ = _window(u, dict(p, k=k), [t], own, cache)
        gain, offset = _seam_of(u, p, tiles, rect, ref, t, cache, f)
        planes.append(_compose(window, k, corrections=(np.full((1, 3), gain), np.full((1, 3), offset))))
    if channel is not None:
        rgba = planes[channel]
    elif len(planes) == 3:
        rgba = colour_picture(u, p, used, planes)
    elif tint is not None:
        rgba = np.dstack([(tinted(planes[0], tint, p["display_scale"]["gamma"]) + 0.5).astype(np.uint8), planes[0][..., 3]])
    else:
        rgba = planes[0]
    if p["display_scale"].get("filled"):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * k)
    # (not cut to its picture: the tiles are cut to theirs, and the canvas is where pointing_box says it is)
    return np.ascontiguousarray(rgba), (x0, y0, k)


def _seam_of(u, p, tiles, rect, ref, t, cache, f=None):
    """(gain, offset) the mosaic's compose gave tile t, as it shows in its filter's mosaic (f = LUM: in the
    luminance base, its band's gain included): fitted between the tile and that mosaic where the tile is whole
    (neighbours blend in near its edges, so the fit is trimmed); (1, 0) when too little of it is in the view."""
    window, shown = _window(u, p, [t], rect, cache)
    if not shown:
        return 1.0, 0.0
    mos = filter_mosaic(u, p, f or t["filter"], tiles, rect, cache, None if f else ref)
    tile_px = window[0][0]
    keep = (tile_px[..., 3] == 255) & (mos[..., 3] == 255)
    a, b = tile_px[..., 0][keep].astype(np.float32), mos[..., 0][keep].astype(np.float32)
    lit = (a > 3) & (a < 252) & (b > 3) & (b < 252)
    if lit.sum() < 500:
        return 1.0, 0.0
    a, b = a[lit], b[lit]
    lo, hi = np.percentile(a, [5, 95])
    if hi - lo < 4:
        return 1.0, float(np.median(b - a))
    blo, bhi = np.percentile(b, [5, 95])
    gain = (bhi - blo) / (hi - lo)
    return float(gain), float(blo - gain * lo)


REPEAT_POINTING = 600   # s: a filter's tiles at one place are one pointing when taken within this of each other


def mosaic_webp(frame_id, size, cache, slots=None, ahead=3, fmt="webp", out=OUT, force=False, tune=None):
    """(WebP, report) of the mosaic so far at frame_id when its pass is a mosaic (or force: the person asked for
    the pass as a mosaic, whatever _judge says); otherwise None. Then makes the next few tiles and the mosaics
    with them in the background, so the next frames' mosaics are ready when the window asks for them. Never
    waits for tiles beyond the first: past the tiles made so far it answers with their mosaic (report "behind":
    how many frames short of frame_id it is). size
    "full" = out px on the longest side (the full view's picture, never warmed ahead); fmt "png" for a PNG
    instead. tune: the person's changes to its tiles (parse_tune), the tuned mosaic (tuned_layout) instead of
    the pass's own; never made ahead."""
    found = unit_of(frame_id)
    if not found or not (found[0]["mosaic"] or force) or found[1] < 0:
        return None
    u, n = found
    if tune and (tune[0] or tune[1]):
        with _asking():
            made = layout(u, n, cache)
            made = tuned_layout(made, tile_map(frame_id, cache), *tune) if made else None
            return _mosaic_at(u, n, size, cache, slots, fmt, out, made=made) if made else None
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
        laid = layout(u, n, cache)
        if size == "full":
            made = _mosaic_at(u, n, size, cache, slots, fmt, out, made=laid)
        else:
            made = _mosaic_at(u, n, size, cache, slots, made=laid)
    if made:
        made = made[0], {**made[1], "behind": found[1] - n}
        # its tile map too, once the mosaic is made, so the window's first hover finds it ready (tiles made before
        # outlines were kept in their reports are measured once here); a map worked out already needs no work
        with _lock:
            mapped = (folder(u, cache), laid[5]) in _maps
        if not mapped:
            _map_later(u, n, cache)
    if made and ahead and size != "full":
        warm(u, n + ahead, cache, size, slots, start=n + 1, force=force)
    return made


_map_wanted, _map_running = {}, set()   # pass folder -> the last tile whose mosaic's map is wanted; passes mapping


def _map_later(u, n, cache):
    """Works out the tile maps of the pass's mosaics up to tile n in the background, in order and once each (the
    pass's record keeps how far it has got), one worker per pass, so the window's first hover finds its map ready
    and a pass played fast starts one thread, not one per mosaic waiting its turn."""
    rec, key = _record(u, cache), folder(u, cache)
    with _lock:
        if rec is not None and rec.get("mapped", -1) >= n:
            return   # (mapped already, then dropped from _maps: a hover works it out)
        _map_wanted[key] = max(n, _map_wanted.get(key, -1))
        if key in _map_running:
            return
        _map_running.add(key)

    def run():
        try:
            while True:
                _yield()
                rec = _record(u, cache)
                with _lock:
                    upto = _map_wanted.pop(key, None)
                    if upto is None:   # (under the lock that a later ask takes: it starts a worker of its own)
                        _map_running.discard(key)
                        return
                    first = rec.get("mapped", -1) + 1 if rec is not None else upto
                for j in range(first, upto + 1):
                    _yield()
                    try:
                        tile_map(u["frames"][j][1], cache)
                    except Exception:   # a tile not made yet: the window's own request works it out
                        pass
                    if rec is not None:
                        with _lock:
                            rec["mapped"] = max(rec.get("mapped", -1), j)
        except BaseException:
            with _lock:
                _map_running.discard(key)
            raise

    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()


_made = {}   # (pass, look) -> the last tile of the pass up to which every tile is made (or -1)


def _made_through(u, n, cache):
    """The last tile j <= n of the pass with tiles 0..j all made (their reports in the cache), -1 for none.
    Tile 0 is made here when nothing is (with the plan, seconds), so a pass's first mosaic does not wait for
    the background."""
    key = (u["key"], calibration.mode())
    with _lock:
        j = _made.get(key, -1)
    if j < 0:
        with _asking():
            tile(u, 0, cache)
    p = plan(u, cache)
    while j < n and _has_tile(u, j + 1, cache, p):
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


def _mosaic_path(u, made, size, cache, fmt="webp", out=OUT):
    """Where the mosaic of layout made is kept in the cache (named after what it is made of)."""
    return os.path.join(drawn(u, cache), f"full{out}" if size == "full" else str(size), f"{made[5]}.{fmt}")


def _mosaic_made(u, n, size, cache):
    """Whether the pass's mosaic at tile n is made at size (or holds nothing yet): nothing for warm to make."""
    made = layout(u, n, cache)
    if not made:
        return True
    path = _mosaic_path(u, made, size, cache)
    return path in _blank or os.path.exists(path)


def _mosaic_at(u, n, size, cache, slots=None, fmt="webp", out=OUT, made=None):
    """(WebP, report) of the pass's mosaic with tiles 0..n at size, made once (kept in the cache under the name
    of what it is made of, so frames that add nothing to it share it; a request that comes while it is being
    made waits for it); None before any tile is placed. made: its layout when already worked out (a tuned one)."""
    made = made or layout(u, n, cache)
    if not made:
        return None
    path = _mosaic_path(u, made, size, cache, fmt, out)
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


BLANK_LEVEL = 2   # a mosaic whose 99th percentile over its tiles is at most this many levels holds nothing yet
_blank = set()    # mosaics found blank (paths): asked again, they are blank again


def blank(im):
    """Whether a mosaic picture (RGBA) shows nothing above black over the tiles placed: a pass's first tiles of
    sky at its own noise level (Saturn's Shadow's outer E ring), drawn black. The window keeps showing its frame
    (the single picture, processed on its own scale) until a tile with something in it is placed."""
    a = np.asarray(im)
    covered = a[..., 3] > 0
    return not covered.any() or float(np.percentile(a[..., :3].max(axis=2)[covered], 99)) <= BLANK_LEVEL


def _make_mosaic(u, n, size, path, cache, slots, made, fmt="webp", out=OUT, post=None):
    """(picture, report) of the mosaic so_far draws from made, kept at path; None before anything is above black.
    post: a step applied to so_far's picture before it is kept (a mosaic movie's fade, _faded)."""
    report, full, meta = {}, size == "full", path[:-len(fmt)] + "json"
    if path in _blank:
        return None

    def make():
        with slots or contextlib.nullcontext():
            im, rep = so_far(u, n, cache, made, out if full else OUT)
        if im is None:
            raise LookupError("no tile placed yet")
        if blank(im):
            with _lock:
                _blank.add(path)
            raise LookupError("nothing above black yet")
        report.update(rep)
        if post:
            im = post(im)
        if not full and max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "png":
            im.save(buf, "PNG", compress_level=6)
        else:
            im.save(buf, "WEBP", quality=QUALITY, method=4)
        reel._cached(meta, lambda: json.dumps(rep).encode())
        reel.keep_report(meta, rep)
        return buf.getvalue()

    try:
        data = reel._cached(path, make)
    except LookupError:
        return None
    if not report:
        report = reel.report_of(meta)
    return data, report


def warm(u, upto, cache, size=None, slots=None, start=0, force=False):
    """Makes the pass's plan and its tiles up to upto in the background, and with a size the mosaics at tiles
    start..upto. One thread per pass and size: a later call while it runs moves its end on. Background work
    runs one pass at a time (_background). force: a pass _judge does not call a mosaic, asked for as one."""
    if not (u["mosaic"] or force):
        return
    mode = calibration.mode()
    key = (u["key"], size, mode)
    upto = min(upto, len(u["frames"]) - 1)
    with _lock:
        running = key in _warming
    # nothing to make (the tiles up to upto in memory, and their mosaics in the cache): no thread
    if not running:
        rec = _record(u, cache)
        if rec is not None and _all_made(u, cache, rec["plan"], 0, upto) and \
                (not size or all(_mosaic_made(u, j, size, cache) for j in range(start, upto + 1))):
            return
    with _lock:
        _upto[key] = max(_upto.get(key, -1), upto)
        _from[key] = max(_from.get(key, 0), start)
        if key in _warming:
            return
        _warming.add(key)

    def run():
        try:
            with _background, calibration.in_mode(mode):
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
                            # a window that has asked for a later frame meanwhile (a burst) has passed this one;
                            # one made already is not read again
                            if j >= _from[key] and not _mosaic_made(u, j, size, cache):
                                _mosaic_at(u, j, size, cache, slots)
                    done = last
        except Exception as e:
            print(f"observation mosaic {u['key']} failed: {type(e).__name__}: {e}", flush=True)
            with _lock:
                _warming.discard(key)
                _upto.pop(key, None)
                _from.pop(key, None)

    threading.Thread(target=run, daemon=True).start()


_ahead_passes = collections.deque(maxlen=2)   # (pass, mode) windows were in last (a NAC and a WAC window)
_ahead_running = set()   # (pass, mode) a thread is making tiles ahead for


def tiles_ahead(u, n, cache):
    """Makes the pass's tiles from the first one not made to its end in the background (n: the frame the window
    is at, kept for the callers), one thread per pass, so a playing window's
    mosaic finds its tiles made (processing a frame is the slow part of a cold mosaic) instead of waiting for
    each. Stops once windows have moved on to two other passes. Waits between tiles while a window waits for a
    mosaic (_yield), so the pass's lock goes to the request first instead of to the next tile ahead."""
    mode = calibration.mode()
    me = (u["key"], mode)
    with _lock:
        # the pass asked for in one mode only (Settings > Processing switched): the thread of its mode before stops
        for was in [a for a in _ahead_passes if a[0] == u["key"]]:
            _ahead_passes.remove(was)
        _ahead_passes.append(me)
        if me in _ahead_running:
            return
    # every tile of the pass made and in memory: nothing to make, no thread
    rec = _record(u, cache)
    if rec is not None and _all_made(u, cache, rec["plan"], 0, len(u["frames"]) - 1):
        return
    with _lock:
        if me in _ahead_running:
            return
        _ahead_running.add(me)

    def run():
        try:
            with calibration.in_mode(mode):
                p = plan(u, cache)
                # from the first tile not made: a window's mosaic is the tiles made so far in a row (mosaic_webp)
                with _lock:
                    first = _made.get((u["key"], mode), -1) + 1
                for j in range(first, len(u["frames"])):
                    _yield()
                    if me not in _ahead_passes:
                        return
                    tile(u, j, cache, p["display_scale"])
        except Exception as e:
            print(f"observation tiles {u['key']} failed: {type(e).__name__}: {e}", flush=True)
        finally:
            with _lock:
                _ahead_running.discard(me)

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
