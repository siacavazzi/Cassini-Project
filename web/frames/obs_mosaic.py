#!/usr/bin/env python3
"""
Observation mosaics for the camera windows: when Cassini steps a camera across a body a tile at a
time, the window shows every tile of that pass taken so far, all filters, made like the mosaic
benchmark (web/frames/mosaic_benchmark.py), rather than the reel's rolling window of a few tiles.

A pass (a "unit") is the frames of one camera, one target and one OBSERVATION_ID, split where
the camera pauses more than GAP or the distance to the body changes by more than ZOOM since the
pass began. It is a mosaic when the geometry cache puts its frames at three or more places (at
least mosaic.min_step of a frame apart, once scaled to one distance) and its footprint is less
than MAX_FRAMES frames across. Overlap is not required: SPICE places every tile.

Every tile goes through color_image.processed_frame (repeat exposures merged in I/F, calibrated,
centred north up by SPICE) on one display scale for the pass (mosaic_benchmark.display_scale) and
is scaled to the pass's reference distance, so a flyby's tiles keep one km per pixel as Cassini
closes in. Tiles are made when first needed, oldest first, and kept in the cache.

The view: the whole footprint, worked out once from the geometry cache (so it does not move or
rescale as the mosaic grows), when the pass maps the whole body (its disk inside the footprint) or
the footprint is at most FIT frames across; otherwise a window FOLLOW frames across that follows
the newest tile in steps of one frame. The mosaic "so far" at a frame is every tile up to it, each
filter drawn by mosaic.compose (calibrated, none pinned) over its own earlier tiles; three or more
filters make false colour (longest wavelength red, middle green, shortest blue, only where all
three have the picture), otherwise the best covered filter in grey. Different filters are never
blended into one another.

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/obs_mosaic.py W1537023863_1 --cache DIR [--all]
  (makes the pass the frame is in ahead of time; the frame server makes it on first request)
"""
import argparse
import collections
import contextlib
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
VERSIONS = {"balanced": "obs-v11", "classic": "obs-v9"}
CANVAS = 2048        # longest side of the canvas the view is drawn on
OUT = 1024           # longest side of the picture sent
FRAME = 1024         # full resolution frame
HALF = 724           # half the side of a north-up frame's canvas (its diagonal)
GAP = 1800           # seconds without a frame that end a pass (mosaic.max_gap)
ZOOM = 1.4           # change in distance that ends a pass (tiles closer than this are rescaled)
MIN_PLACES = 3       # pointings a pass needs to be a mosaic
MAX_FRAMES = 16      # footprints wider than this many frames stay rolling mosaics
FIT = 8              # a footprint up to this many frames across is shown whole
FOLLOW = 4           # otherwise a window this many frames across follows the newest tile
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
_making = {}          # path of a mosaic being made -> its lock, so two requests for it make it once


def _row_of():
    idx, _ = reel.load_index()
    with _lock:
        if not hasattr(_row_of, "row"):
            _row_of.row = dict(zip(idx["id"], range(len(idx))))
    return idx, _row_of.row


def units(target, obs, cam):
    """The passes of one camera's frames of one observation: [{key, frames: [(path, id, filter, t, nm, x, y, z)],
    mosaic, whole, z, last}] in time order, from the index and the geometry cache. Repeat exposures (the same
    filter within REPEAT_GAP) are left out, as stacking.load_hdr merges them in."""
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
            cur = {"frames": [], "z": g and g[2], "last": t}
            out.append(cur)
            last = {}
        cur["last"] = t
        if not cur["z"] and g:
            cur["z"] = g[2]
        if f in last and t - last[f] <= mosaic_benchmark.REPEAT_GAP:
            continue
        last[f] = t
        cur["frames"].append((r.path, r.id, f, t, reel.wavelength(inst, f1 + f2), *(g or (None, None, None))))
    for n, u in enumerate(out):
        u["key"] = (target, obs, cam, n)
        _judge(u)
    with _lock:
        _units[(target, obs, cam)] = out
    return out


def _judge(u):
    """Sets u["mosaic"] (enough places, footprint not too big) and u["whole"] (the body's disk inside it)."""
    pts = [(-x * z / u["z"], -y * z / u["z"]) for _, _, _, _, _, x, y, z in u["frames"] if z]
    places = []
    for p in pts:
        if all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= mosaic.min_step * FRAME for q in places):
            places.append(p)
    u["mosaic"] = u["whole"] = False
    if len(places) < MIN_PLACES:
        return
    pts = np.array(pts)
    lo, hi = pts.min(0) - FRAME / 2, pts.max(0) + FRAME / 2
    if (hi - lo).max() >= MAX_FRAMES * FRAME:
        return
    u["mosaic"] = True
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


def folder(u, cache):
    return os.path.join(cache, VERSIONS[calibration.look()], "_".join(map(str, u["key"])))


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
        scale = pass_scale(frames, u, colour or [max(count, key=count.get)],
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
        fixed = u["whole"] or max(x1 - x0, y1 - y0) <= FIT * FRAME
        view = [x1 - x0, y1 - y0] if fixed else [min(x1 - x0, FOLLOW * FRAME), min(y1 - y0, FOLLOW * FRAME)]
        p = {"key": list(u["key"]), "display_scale": scale, "angle": angle, "footprint": [x0, y0, x1, y1],
             "fixed": bool(fixed), "view": view, "k": CANVAS / max(view), "colour": colour,
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
        _, iof, _ = stacking.load_hdr(path, mosaic_benchmark.REPEAT_GAP)
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
    with _ulock(u):
        if os.path.exists(base + ".json"):
            with open(base + ".json") as fh:
                return json.load(fh)
        if scale is None:
            scale = plan(u, cache)["display_scale"]
        path, fid, f, t, nm, x, y, z = u["frames"][n]
        k = z / u["z"] if z else 1.0
        try:
            image, _, rep = color_image.processed_frame([path], hdr=True,
                                                        scale={**scale, "blacks": [scale["blacks"].get(f, 0.0)]})
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


def view_rect(p, tiles):
    """The view (x0, y0, w, h in reference pixels from the body's centre) for these tiles: the footprint, or a
    window following the newest placed tile in steps of one frame."""
    x0, y0, x1, y1 = p["footprint"]
    if p["fixed"]:
        return x0, y0, x1 - x0, y1 - y0
    w, h = p["view"]
    placed = [t for t in tiles if "offset" in t]
    cx, cy = placed[-1]["offset"] if placed else ((x0 + x1) / 2, (y0 + y1) / 2)
    vx = x0 + round((cx - w / 2 - x0) / FRAME) * FRAME
    vy = y0 + round((cy - h / 2 - y0) / FRAME) * FRAME
    return min(max(vx, x0), x1 - w), min(max(vy, y0), y1 - h), w, h


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


def filter_mosaic(u, p, f, tiles, rect, cache, ref=None):
    """The filter f's mosaic of these tiles in the view rect, RGBA on the view's canvas (kept in the cache).
    ref = the filter the seams are solved on (balanced look, seams)."""
    mine = [t for t in tiles if t["filter"] == f and "offset" in t]
    balanced = calibration.look() == "balanced" and SHARED_SEAMS
    ref = ref or f
    solved_on = f"-{ref.replace('/', '_')}{sum(1 for t in tiles if t['filter'] == ref and 'offset' in t)}" if balanced else ""
    name = f"{f.replace('/', '_')}-{len(mine)}{solved_on}-{'_'.join(str(round(v)) for v in rect)}.png"
    path = os.path.join(folder(u, cache), "filters", name)
    k = p["k"]
    W, H = math.ceil(rect[2] * k), math.ceil(rect[3] * k)

    def make():
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
        else:
            feather = mosaic.feather_px
            with reel._mosaic_lock:
                try:
                    # the benchmark's soft edge on its 0.5 scale canvas, at this canvas's scale
                    mosaic.feather_px = max(8, round(64 * k / 0.5))
                    mosaic.reset()
                    if corrections:
                        rgba = mosaic.compose(window, False, calibrated=True, pin=None,
                                              gamma=p["display_scale"]["gamma"], corrections=corrections)
                    else:
                        rgba = mosaic.compose(window, False, calibrated=True, pin=None)
                    mosaic.reset()
                finally:
                    mosaic.feather_px = feather
        out = io.BytesIO()
        Image.fromarray(rgba).save(out, "PNG", compress_level=1)
        return out.getvalue()

    return np.asarray(Image.open(io.BytesIO(reel._cached(path, make))).convert("RGBA"))


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
    p, tiles, rect, count, used, _ = made
    # the seams are solved on the best covered filter drawn and shared by all (balanced look)
    ref = max(used, key=lambda f: count[f])
    if len(used) == 3:
        colour = used
        acc = [filter_mosaic(u, p, f, tiles, rect, cache, ref) for f in colour]
        rgb = np.dstack([a[..., 0] for a in acc])
        # only where every filter has the picture: past one filter's edge the others alone are a coloured rim
        alpha = np.min([a[..., 3] for a in acc], axis=0)
        rgb = (rgb * (alpha[..., None] / np.float32(255)) + 0.5).astype(np.uint8)
        rgba, used = np.dstack([rgb, alpha]), colour
    else:
        rgba = filter_mosaic(u, p, used[0], tiles, rect, cache, ref)
    if p["display_scale"].get("filled"):
        rgba = detail(rgba, DETAIL_SIGMA * FRAME * p["k"])
    im = Image.fromarray(rgba, "RGBA")
    s = min(out, CANVAS) / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    return im, {"mosaic": sum(count[f] for f in used), "filters": len(used), "filter_names": used,
                "observation": u["key"][1], "pass": u["key"][3], "of": sum(1 for fr in u["frames"] if fr[2] in used),
                "fixed": p["fixed"], "width": im.width, "height": im.height}


def mosaic_webp(frame_id, size, cache, slots=None, ahead=3, fmt="webp", out=OUT):
    """(WebP, report) of the mosaic so far at frame_id when its pass is a mosaic; otherwise None. Then makes the
    next few tiles and the mosaics with them in the background, so the next frames' mosaics are ready when the
    window asks for them. size "full" = out px on the longest side (the full view's picture, never warmed
    ahead); fmt "png" for a PNG instead."""
    found = unit_of(frame_id)
    if not found or not found[0]["mosaic"] or found[1] < 0:
        return None
    u, n = found
    with _asking():
        if size == "full":
            return _mosaic_at(u, n, size, cache, slots, fmt, out)
        made = _mosaic_at(u, n, size, cache, slots)
    if made and ahead:
        warm(u, n + ahead, cache, size, slots, start=n + 1)
    return made


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


def warm(u, upto, cache, size=None, slots=None, start=0):
    """Makes the pass's plan and its tiles up to upto in the background, and with a size the mosaics at tiles
    start..upto. One thread per pass and size: a later call while it runs moves its end on. Background work
    runs one pass at a time (_background)."""
    if not u["mosaic"]:
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


def warm_frame(frame_id, cache, ahead=4):
    """A frame was asked for: when it is in a mosaic pass, start making that pass's tiles up to a few past it."""
    found = unit_of(frame_id)
    if found and found[0]["mosaic"]:
        warm(found[0], max(found[1], 0) + ahead, cache)


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
