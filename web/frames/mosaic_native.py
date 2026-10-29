#!/usr/bin/env python3
"""
A pass's mosaic at native resolution, for a close look (the zoom lens: a crop of it) and for saving (the save
menu's "Full resolution mosaic": all of it). The camera windows' mosaic (obs_mosaic.so_far) is drawn on a canvas
of obs_mosaic.CANVAS px and sent at OUT, so a pass eight frames across keeps about an eighth of each frame's
pixels; its tiles (obs_mosaic.tile) are kept at full resolution, one tile pixel per full resolution pixel at the
pass's reference distance. This draws the same layout from the same tiles at that scale (k = 1, at most
NATIVE_MAX px on the longest side) instead.

Nothing here is a second way of making a mosaic. The layout (obs_mosaic.layout, tuned_layout), the tiles, their
placing on a canvas (obs_mosaic._window), the compose (obs_mosaic._compose, mosaic.compose with the soft edge at
the canvas's scale), the colour mix (colour_picture) and the local contrast (detail) are the windows' own. Only
the seam corrections are worked out apart from the drawing: the windows' mosaic solves them on its canvas, so the
same gains and offsets, tile by tile, are found again on that canvas (corrections: the first GROW_FROM tiles of a
filter solved together, each one after laid over the mosaic before it, as obs_mosaic.filter_mosaic and _grown do)
and given to the compose at native scale, and with them, with the blend step on, what it decided for each tile
there (its leveling, solved over the whole mosaic, and its seam, cut through the whole of its overlap: mosaic._blended's
kept), which a block could not work out for itself from the part of the mosaic it holds. So the native picture has
the levels, colours and seams of the one in the window, with more pixels.

The canvas is drawn in blocks of BLOCK px (each with a margin for the soft edge and the local contrast, cut off
again), so memory stays bounded whatever the mosaic's size: a block holds the tiles that reach it, one block-sized
frame each. A whole mosaic goes to a file a row of blocks at a time (a PNG written as it goes; a JPEG from one
RGB array). Between blocks the windows' mosaics go first (obs_mosaic._yield), and each block holds one of the
frame server's mosaic slots, so a big native mosaic never starves the camera windows.

The pictures are kept in a cache of their own (CASSINI_FULLRES_CACHE, by default <cache>-fullres beside the frame
server's), at most CASSINI_FULLRES_MB (5 GB) of them, the least recently used going first. They are made only
when asked for, never ahead and never by the pre-build.
"""
import base64
import hashlib
import io
import json
import math
import os
import struct
import threading
import time
import zlib

import cv2
import numpy as np
from PIL import Image

import obs_mosaic as om
import calibration
import mosaic
import reel

NATIVE_MAX = int(os.environ.get("CASSINI_NATIVE_MAX", "24000"))   # longest side of a whole native mosaic, px
CROP_MAX = int(os.environ.get("CASSINI_NATIVE_CROP", "2048"))       # longest side of a crop (the zoom lens), px
BLOCK = int(os.environ.get("CASSINI_NATIVE_BLOCK", "1024"))        # canvas px drawn at a time
KEEP_MB = int(os.environ.get("CASSINI_FULLRES_MB", "5120"))         # most the native pictures' cache holds
JPEG_QUALITY = 92
VERSION = "native-v2"   # bumped whenever the way native mosaics are made changes (with obs_mosaic.VERSIONS)
# bytes per pixel, roughly, of a saved native mosaic (sky is most of a mosaic's canvas and costs almost nothing)
EST_BYTES = {"jpg": (0.08, 0.005), "png": (2.0, 0.02)}   # (per pixel of picture, per pixel of empty canvas)

_lock = threading.Lock()
_making = {}     # path -> threading.Lock while it is made
_progress = {}   # path of a whole mosaic being made -> fraction done


def cache_dir(cache):
    return os.environ.get("CASSINI_FULLRES_CACHE") or cache.rstrip("/") + "-fullres"


def layout_of(frame_id, cache, force=False, tune=None):
    """(pass, n, layout) of the mosaic the camera windows show for frame_id (obs_mosaic.mosaic_webp: the tiles made
    so far up to it, a tuned layout with the person's changes), or None when it is not a mosaic pass or nothing is
    placed yet. Nothing is waited for: a tile not made yet is not in it."""
    found = om.unit_of(frame_id)
    if not found or not (found[0]["mosaic"] or force) or found[1] < 0:
        return None
    u, n = found
    m = om._made_through(u, n, cache)
    if m < 0:
        return None
    made = om.layout(u, m, cache)
    if made and tune and (tune[0] or tune[1]):
        made = om.tuned_layout(made, om.tile_map(frame_id, cache), *tune)
    return (u, m, made) if made else None


def scale_of(made, crop=None):
    """(k, width, height) of the native picture of layout made: k canvas px per reference px (1 = native, less
    when the mosaic is wider than NATIVE_MAX, or a crop wider than CROP_MAX). crop = (x0, y0, x1, y1) fractions of
    the picture: the size of that part of it."""
    rect = made[2]
    k = min(1.0, NATIVE_MAX / max(rect[2], rect[3]))
    if crop is None:
        return k, math.ceil(rect[2] * k), math.ceil(rect[3] * k)
    w, h = (crop[2] - crop[0]) * rect[2], (crop[3] - crop[1]) * rect[3]
    k = min(k, CROP_MAX / max(w, h, 1))
    return k, max(1, round(w * k)), max(1, round(h * k))


def info(frame_id, cache, force=False, tune=None, fmts=("jpg", "png")):
    """What the save menu and the zoom lens need to know of frame_id's native mosaic, without making it: its size,
    the size of the picture the windows show, an estimate of each format's size, and which are made or being made."""
    found = layout_of(frame_id, cache, force, tune)
    if not found:
        return None
    u, n, made = found
    k, w, h = scale_of(made)
    p = made[0]
    shown = om.CANVAS / max(made[2][2], made[2][3])
    out = {"width": w, "height": h, "scale": k, "shown": [math.ceil(made[2][2] * shown), math.ceil(made[2][3] * shown)],
           "tiles": sum(made[3].get(f, 0) for f in made[4]), "filters": made[4], "observation": u["key"][1],
           "behind": om.unit_of(frame_id)[1] - n, "estimate_mb": {}, "ready": {}, "making": {}}
    cover = coverage(made)
    # prepared: its seams are worked out (the first native picture of a mosaic waits for them, tens of seconds)
    out["coverage"], out["prepared"] = round(cover, 3), os.path.exists(_seams_path(u, made, cache))
    for fmt in fmts:
        path = _path(u, made, cache, None, fmt, k)
        lit, sky = EST_BYTES[fmt]
        out["estimate_mb"][fmt] = round(w * h * (cover * lit + (1 - cover) * sky) / 1e6, 1)
        out["ready"][fmt] = os.path.exists(path)
        if out["ready"][fmt]:
            out["estimate_mb"][fmt] = round(os.path.getsize(path) / 1e6, 1)
        with _lock:
            if path in _progress:
                out["making"][fmt] = round(_progress[path], 3)
    return out


def coverage(made, side=256):
    """The share of the mosaic's canvas its placed tiles cover (their boxes drawn on a side-px grid of the view):
    what a saved mosaic's size goes by, the empty canvas around and between its tiles costing almost nothing."""
    p, tiles, rect = made[:3]
    s = side / max(rect[2], rect[3])
    grid = np.zeros((max(1, math.ceil(rect[3] * s)), max(1, math.ceil(rect[2] * s))), bool)
    for t in tiles:
        if "offset" not in t or "box" not in t:
            continue
        bx, by, bw, bh = t["box"]
        x0, y0 = (t["offset"][0] + bx - rect[0]) * s, (t["offset"][1] + by - rect[1]) * s
        grid[max(0, int(y0)):max(0, math.ceil(y0 + bh * s)), max(0, int(x0)):max(0, math.ceil(x0 + bw * s))] = True
    return float(grid.mean())


def _drawing():
    """What the names of a mosaic's pictures and seams get for how its tiles are drawn together (mosaic.drawing): ""
    with the blend step off, as they were named before it."""
    name = mosaic.drawing()
    return "-" + name if name else ""


def _seams_path(u, made, cache):
    return os.path.join(cache_dir(cache), VERSION, calibration.style(), "_".join(map(str, u["key"])),
                        f"{made[5]}{_drawing()}-seams.json")


def _path(u, made, cache, crop, fmt, k):
    name = made[5] + _drawing() + (f"-crop{'_'.join(f'{v:.4f}' for v in crop)}" if crop else "") + f"-k{k:.4f}"
    if len(name) > 180:
        name = name[:100] + hashlib.sha1(name.encode()).hexdigest()[:16]
    return os.path.join(cache_dir(cache), VERSION, calibration.style(), "_".join(map(str, u["key"])), f"{name}.{fmt}")


# ---------- the windows' seam corrections, tile by tile ----------
def drawn(u, made):
    """What so_far draws for layout made: (the filters composed, the colour filters or None, whether the luminance
    base goes under the picture, the tag of a set of tiles with a name of its own, the filter the seams are solved on)."""
    p, tiles, rect, count, used, name = made
    plain, _, tuned = name.partition("-tune")
    tag = ("-" + plain.rsplit("-", 1)[1] if plain.startswith("lap-") else "") + ("-tune" + tuned if tuned else "")
    base = om.lum_base(u, p, tiles, used)
    colour = used if len(used) == 3 else None
    filters = (list(colour) if colour else []) + ([om.LUM] if base else [] if colour else [used[0]])
    return filters, colour, base, tag, max(used, key=lambda f: count[f])


def corrections(u, made, cache):
    """{filter: {tile n: (gains [3], offsets [3])}}: the corrections the windows' mosaic of layout made gave each
    tile, worked out again on its canvas the way obs_mosaic.filter_mosaic draws it: a filter of up to GROW_FROM tiles
    (or a set of tiles with a name of its own, a tuned layout) solved together, none pinned (held_level); past
    that, the first GROW_FROM solved together and each tile after found as _grown finds it, matched (pin 0)
    against the mosaic of the tiles before it, as _over cuts it. The luminance base (obs_mosaic.LUM, its tiles with
    their gains, _mine / _shade) is one more filter; "_grey" is over_grey's match of it to the colour, measured on the
    window's whole canvas (grey_gain), so every block lays the gray under the colour alike. With the blend step, each
    tile's (gains, offsets, what the blend step decided for it on that canvas: _packed, or None). Kept beside the
    native pictures."""
    p, tiles, rect, count, used, name = made
    path = _seams_path(u, made, cache)

    def make():
        out = {}
        filters, colour, base, tag, ref = drawn(u, made)
        tagged = bool(tag)
        blend = calibration.step("blend")
        for f in filters:
            mine = om._mine(u, p, tiles, f)
            first = mine if tagged or len(mine) <= om.GROW_FROM else mine[:om.GROW_FROM]
            got = out[f] = {}
            window, shown = om._window(u, p, first, rect, cache)
            if len(window) > 1:
                with reel._mosaic_lock:
                    gains, offsets = om.held_level([np.asarray(w[0]) for w in window])
                for t, g, o in zip(shown, gains, offsets):
                    got[t["n"]] = [list(map(float, g)), list(map(float, o))]
            if blend and len(window) > 1:
                # drawn as filter_mosaic draws them, what the blend step decides for each tile kept
                kept = []
                rgba = om._compose(window, p["k"], pin=None, kept=kept)
                for t, d in zip(shown, kept):
                    got[t["n"]].append(_packed(d))
            elif len(first) < len(mine):
                rgba = om.filter_mosaic(u, p, f, first, rect, cache).copy()
            for t in mine[len(first):]:
                pair = _pair(u, p, rgba, t, rect, cache)
                if pair is not None:
                    with reel._mosaic_lock:
                        mosaic.reset()
                        gains, offsets = mosaic.seams(pair, 0)
                        mosaic.reset()
                    got[t["n"]] = [list(map(float, gains[1])), list(map(float, offsets[1]))]
                kept = [] if blend else None
                om._over(u, p, rgba, t, rect, cache, kept=kept)
                if kept and t["n"] in got:
                    got[t["n"]].append(_packed(kept[0]))
                om._yield()
        if colour and base:
            picture = om.colour_picture(u, p, colour, [om.filter_mosaic(u, p, f, tiles, rect, cache, ref, tag) for f in colour])
            g = om.grey_gain(picture, om.filter_mosaic(u, p, om.LUM, tiles, rect, cache, None, tag), p["k"], p["display_scale"]["gamma"])
            out["_grey"] = None if g is None else list(map(float, g))
        return json.dumps(out).encode()

    # one at a time (the lens's first crop and the warm-up ask together)
    with _lock:
        lock = _making.setdefault(path, threading.Lock())
    with lock:
        solved = json.loads(reel._cached(path, make))
    grey = solved.pop("_grey", None)
    out = {f: {int(n): (np.array(v[0]), np.array(v[1]), _unpacked(v[2] if len(v) > 2 else None)) for n, v in by.items()}
           for f, by in solved.items()}
    out["_grey"] = None if grey is None else np.array(grey, np.float32)
    return out


def _packed(decision):
    """What the blend step decided for a tile on the windows' canvas (mosaic._blended's kept), for the seams' JSON:
    its leveling's cells (log gains, as half floats) and its seam's cut (bits), deflated, each with where it lies on
    the canvas."""
    if decision is None:
        return None
    out = {}
    if decision["field"] is not None:
        grid, c, y, x = decision["field"]
        out["field"] = {"grid": _deflated(grid.astype(np.float16)), "shape": list(grid.shape), "c": int(c), "at": [int(y), int(x)]}
    if decision["cut"] is not None:
        cut, y, x = decision["cut"]
        out["cut"] = {"bits": _deflated(np.packbits(cut.astype(bool))), "shape": list(cut.shape), "at": [int(y), int(x)]}
    return out or None


def _deflated(a):
    return base64.b64encode(zlib.compress(a.tobytes(), 9)).decode()


def _inflated(text, dtype):
    return np.frombuffer(zlib.decompress(base64.b64decode(text)), dtype)


def _unpacked(packed):
    """_packed's decisions again: {"field": (log gains (rows, columns, bands), cell size, y, x) or None, "cut": (bool
    (h, w), y, x) or None}, or None."""
    if not packed:
        return None
    field = cut = None
    if "field" in packed:
        f = packed["field"]
        field = (_inflated(f["grid"], np.float16).reshape(f["shape"]).astype(np.float32), f["c"], f["at"][0], f["at"][1])
    if "cut" in packed:
        c = packed["cut"]
        h, w = c["shape"]
        bits = np.unpackbits(_inflated(c["bits"], np.uint8))[:h * w]
        cut = (bits.reshape(h, w).astype(bool), c["at"][0], c["at"][1])
    return {"field": field, "cut": cut}


def _decided(d, r, top, left):
    """A tile's decisions on the windows' canvas (corrections) as a block's compose takes them (mosaic._blended's
    decided): functions of a box of the block's frame pixels, the frame's first pixel at (top, left) of the native
    canvas, r of the windows' canvas pixels to a native one. Each pixel's middle is looked up on the windows' canvas,
    linear in between: the same values for a native pixel whatever block it is drawn in."""
    if d is None:
        return None

    def at(box, y, x):
        # the box's pixel middles on the windows' canvas, as pixels of what starts at (y, x) there
        ys = (np.arange(box[0], box[1]) + top + 0.5) * r - 0.5 - y
        xs = (np.arange(box[2], box[3]) + left + 0.5) * r - 0.5 - x
        return ys.astype(np.float32), xs.astype(np.float32)

    def look(a, ys, xs):
        mx, my = np.meshgrid(xs, ys)
        return cv2.remap(a, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    field = cut = None
    if d["field"] is not None:
        grid, c, gy, gx = d["field"]

        def field(box):
            # a cell's middle is its gain (mosaic._field): cell i's middle lies at (i + 0.5) * c - 0.5
            ys, xs = at(box, gy, gx)
            return np.exp(look(grid, (ys + 0.5) / c - 0.5, (xs + 0.5) / c - 0.5).reshape(len(ys), len(xs), grid.shape[2]))
    if d["cut"] is not None:
        bits, cy, cx = d["cut"]
        h, w = bits.shape
        bits = bits.astype(np.float32)

        def cut(box):
            ys, xs = at(box, cy, cx)
            out = look(bits, ys, xs)
            out[~(((ys >= -0.5) & (ys <= h - 0.5))[:, None] & ((xs >= -0.5) & (xs <= w - 0.5))[None, :])] = -1
            return out
    return field, cut


def _pair(u, p, rgba, t, rect, cache):
    """The two frames obs_mosaic._over composes when tile t is laid over the mosaic rgba (the mosaic under the
    tile's part of the canvas and a margin for its soft edge, and the tile on it), or None when it is off the canvas."""
    k = p["k"]
    H, W = rgba.shape[:2]
    pad = max(8, round(64 * k / 0.5)) + 1
    bx, by, bw, bh = t["box"]
    left = round((t["offset"][0] + bx - rect[0]) * k)
    top = round((t["offset"][1] + by - rect[1]) * k)
    sw, sh = max(1, round(bw * k)), max(1, round(bh * k))
    x0, y0 = max(left - pad, 0), max(top - pad, 0)
    x1, y1 = min(left + sw + pad, W), min(top + sh + pad, H)
    a0, b0 = max(left, 0), max(top, 0)
    a1, b1 = min(left + sw, W), min(top + sh, H)
    if not (x1 > x0 and y1 > y0 and a1 > a0 and b1 > b0):
        return None
    part = om._shade(om._part(om._pic(u, cache, p["display_scale"], t), sw, sh), t)
    frame = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
    frame[b0 - y0:b1 - y0, a0 - x0:a1 - x0] = part[b0 - top:b1 - top, a0 - left:a1 - left]
    return [np.ascontiguousarray(rgba[y0:y1, x0:x1]), frame]


# ---------- drawing ----------
def block(u, made, corr, k, x0, y0, w, h, cache):
    """RGBA of canvas pixels x0..x0+w, y0..y0+h of the mosaic of layout made drawn k canvas px per reference px:
    each filter's tiles that reach it composed with the windows' corrections (corr), the colour mix and the local
    contrast, as obs_mosaic.so_far does, on a margin wide enough for the soft edge and the contrast's blur that is
    cut off again, so blocks side by side join without a seam."""
    p, tiles, rect, count, used, name = made
    filters, colour, base, _, _ = drawn(u, made)
    blend = calibration.step("blend")
    filled = p["display_scale"].get("filled")
    sigma = om.DETAIL_SIGMA * om.FRAME * k
    pad = max(8, round(64 * k / 0.5)) + 2 + (math.ceil(4 * sigma) + 2 if filled else 0)
    # the block's frames start on the blend step's grid (mosaic.GRID) of the whole canvas, so blocks side by side lay
    # their pyramids and blurs on the same pixels
    px, py = pad + (x0 - pad) % mosaic.GRID, pad + (y0 - pad) % mosaic.GRID
    sub = (rect[0] + (x0 - px) / k, rect[1] + (y0 - py) / k, (w + px + pad) / k, (h + py + pad) / k)
    pk = dict(p, k=k)
    planes = {}
    for f in filters:
        mine = om._mine(u, pk, tiles, f)
        window, shown = om._window(u, pk, mine, sub, cache)
        if not window:
            planes[f] = np.zeros((math.ceil(sub[3] * k), math.ceil(sub[2] * k), 4), np.uint8)
            continue
        one = (np.ones(3), np.zeros(3), None)
        got = [corr.get(f, {}).get(t["n"], one) for t in shown]
        # with the blend step, each tile's leveling and seam as decided on the windows' canvas (corrections)
        decided = [_decided(g[2], p["k"] / k, y0 - py, x0 - px) for g in got] if blend else None
        planes[f] = om._compose(window, k, corrections=(np.array([g[0] for g in got]), np.array([g[1] for g in got])),
                                decided=decided)
    # as so_far: the colour picture over the luminance base where it has one, the base alone, or the one filter
    if colour:
        rgba = om.colour_picture(u, p, colour, [planes[f] for f in colour])
        if base:
            rgba = om.over_grey(rgba, planes[om.LUM], k, p["display_scale"]["gamma"], gain=corr.get("_grey"))
    else:
        rgba = planes[filters[0]]
    if filled:
        rgba = om.detail(rgba, sigma)
    return np.ascontiguousarray(rgba[py:py + h, px:px + w])


def _rows(u, made, corr, k, x0, y0, w, h, cache, slots=None, done=None):
    """The picture of canvas pixels x0..x0+w, y0..y0+h a row of blocks at a time (RGBA, BLOCK px high, the last
    less), each block drawn holding a mosaic slot, the windows' own mosaics going first between blocks."""
    rows = math.ceil(h / BLOCK)
    cols = math.ceil(w / BLOCK)
    for r in range(rows):
        bh = min(BLOCK, h - r * BLOCK)
        strip = np.zeros((bh, w, 4), np.uint8)
        for c in range(cols):
            bw = min(BLOCK, w - c * BLOCK)
            om._yield()
            if slots is not None:
                slots.acquire()
            try:
                strip[:, c * BLOCK:c * BLOCK + bw] = block(u, made, corr, k, x0 + c * BLOCK, y0 + r * BLOCK, bw, bh, cache)
            finally:
                if slots is not None:
                    slots.release()
            if done:
                done((r * cols + c + 1) / (rows * cols))
        yield strip


def _png_chunk(fh, kind, data):
    fh.write(struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def write_png(fh, w, h, strips):
    """A PNG (RGBA, 8 bit) written a strip of rows at a time, so a mosaic of any size never sits whole in memory;
    each row filtered by its left neighbour (PNG filter 1), which is what a mosaic's smooth sky and body like."""
    fh.write(b"\x89PNG\r\n\x1a\n")
    _png_chunk(fh, b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    z = zlib.compressobj(6)
    for strip in strips:
        a = strip.reshape(strip.shape[0], w * 4)
        sub = a.copy()
        sub[:, 4:] -= a[:, :-4]   # uint8: wraps modulo 256, as the filter does
        raw = np.empty((a.shape[0], w * 4 + 1), np.uint8)
        raw[:, 0] = 1
        raw[:, 1:] = sub
        data = z.compress(raw.tobytes())
        if data:
            _png_chunk(fh, b"IDAT", data)
    _png_chunk(fh, b"IDAT", z.flush())
    _png_chunk(fh, b"IEND", b"")


def _on_black(rgba):
    a = rgba[..., 3:4].astype(np.uint16)
    return ((rgba[..., :3].astype(np.uint16) * a + 127) // 255).astype(np.uint8)


def _write(path, fmt, w, h, strips):
    part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(part, "wb") as fh:
            if fmt == "png":
                write_png(fh, w, h, strips)
            else:
                rgb = np.empty((h, w, 3), np.uint8)
                y = 0
                for s in strips:
                    rgb[y:y + s.shape[0]] = _on_black(s)
                    y += s.shape[0]
                im = Image.fromarray(rgb)
                if fmt == "webp":
                    im.save(fh, "WEBP", quality=90, method=4)
                else:
                    im.save(fh, "JPEG", quality=JPEG_QUALITY, optimize=True, subsampling=0)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    trim(cache_root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(path)))))


def picture(frame_id, cache, crop=None, fmt="jpg", slots=None, force=False, tune=None):
    """(path of the picture, report) of frame_id's mosaic at native resolution, made once and kept: crop = (x0, y0,
    x1, y1) fractions of the picture for that part of it only (the zoom lens; at most CROP_MAX px), else all of it;
    fmt "jpg" (on black), "png" (with its transparency) or "webp" (a crop for the lens). None when frame_id shows
    no mosaic."""
    found = layout_of(frame_id, cache, force, tune)
    if not found:
        return None
    u, n, made = found
    k, w, h = scale_of(made, crop)
    path = _path(u, made, cache, crop, fmt, k)
    rect = made[2]
    report = {"observation": u["key"][1], "width": w, "height": h, "scale": k, "crop": crop,
              "native": list(scale_of(made)[1:]), "behind": om.unit_of(frame_id)[1] - n}
    if os.path.exists(path):
        _touch(path)
        return path, report
    whole = crop is None
    with _lock:
        lock = _making.setdefault(path, threading.Lock())
        if whole:
            _progress.setdefault(path, 0.0)
    try:
        with lock:
            if os.path.exists(path):
                return path, report
            started = time.monotonic()
            corr = corrections(u, made, cache)
            x0 = round(crop[0] * rect[2] * k) if crop else 0
            y0 = round(crop[1] * rect[3] * k) if crop else 0

            def done(f):
                if whole:
                    with _lock:
                        _progress[path] = f

            _write(path, fmt, w, h, _rows(u, made, corr, k, x0, y0, w, h, cache, slots, done))
            report["took"] = round(time.monotonic() - started, 2)
    finally:
        with _lock:
            _progress.pop(path, None)
            _making.pop(path, None)
    return path, report


def warm(frame_id, cache, force=False, tune=None):
    """Works out frame_id's mosaic's seam corrections ahead (the slow part of its first native picture: the window's
    mosaic grown again tile by tile), when the lens or the save menu first asks about it."""
    def run():
        # one at a time, and only for a mosaic whose tiles are all made up to frame_id: a pass still building
        # changes its layout with every tile, so its seams would be worked out again and again for nothing
        if not _warming.acquire(blocking=False):
            return
        try:
            found = layout_of(frame_id, cache, force, tune)
            if found and om.unit_of(frame_id)[1] == found[1]:
                corrections(*found[::2], cache)
        except Exception as e:
            print(f"native mosaic {frame_id} seams: {type(e).__name__}: {e}", flush=True)
        finally:
            _warming.release()
    return run


_warming = threading.Semaphore(1)


def start(frame_id, cache, fmt, force=False, tune=None, slots=None):
    """Makes frame_id's whole native mosaic in fmt in the background (the save menu asks, then waits for it)."""
    def run():
        try:
            picture(frame_id, cache, None, fmt, slots, force, tune)
        except Exception as e:   # the save menu's next look says it is not being made; the log says why
            print(f"native mosaic {frame_id} {fmt}: {type(e).__name__}: {e}", flush=True)
    return run


def movie_picture(frame_id, cache, side, rolling=False, laps=1, fade=(0, 0), slots=None):
    """frame_id's mosaic as an exported film shows it (export.py, Picture size: Full), RGBA, the layout at side px
    on its longest side (native, k = 1, when the pass is no bigger; less when it is): the pass's mosaic so far
    (obs_mosaic.layout, as mosaic_webp draws it) or, rolling, its mosaic movie picture at that frame
    (obs_mosaic.rolling_layout, as rolling_webp draws it with wait), with the fade (fade_style) after compose as
    _faded does it. The same blocks, seam corrections and colour mix as the save menu's native mosaic; kept nowhere
    (the film is what is kept). None when the frame is in no pass or nothing is placed yet."""
    found = om.unit_of(frame_id)
    if not found or found[1] < 0:
        return None
    u, n = found
    fade = om.fade_style(*fade)
    made = om.rolling_layout(u, n, cache, laps, fade=fade) if rolling else om.layout(u, n, cache)
    if not made:
        return None
    rect = made[2]
    k = min(1.0, side / max(rect[2], rect[3]))
    w, h = max(1, math.ceil(rect[2] * k)), max(1, math.ceil(rect[3] * k))
    corr = corrections(u, made, cache)
    rgba = np.empty((h, w, 4), np.uint8)
    y = 0
    for strip in _rows(u, made, corr, k, 0, 0, w, h, cache, slots):
        rgba[y:y + strip.shape[0]] = strip
        y += strip.shape[0]
    im = Image.fromarray(rgba, "RGBA")
    if om.blank(im):
        return None
    return om._faded(u, made, cache)(im) if fade[0] else im


def native_side(frame_id, cache, work=True):
    """The longest side, px, of frame_id's pass at native resolution (its view, one reference px a pixel), or None
    when it is in no pass, or its plan is not worked out yet and work is False (a stretch not pre-processed)."""
    found = om.unit_of(frame_id)
    if not found:
        return None
    u = found[0]
    if not work and not os.path.exists(om._plan_path(u, cache)) and om._record(u, cache) is None:
        return None
    v = om.plan(u, cache)["view"]
    return math.ceil(max(v))


def _touch(path):
    try:
        os.utime(path)
    except OSError:
        pass


def trim(cache_root=None, keep_mb=None):
    """Keeps the native pictures' cache under KEEP_MB: the least recently used (made or sent) go first."""
    root = cache_root
    if not root or not os.path.isdir(root):
        return
    keep = (keep_mb if keep_mb is not None else KEEP_MB) << 20
    files = []
    for d, _, names in os.walk(root):
        for nm in names:
            if nm.endswith(".part"):
                continue
            fp = os.path.join(d, nm)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, fp))
    total = sum(s for _, s, _ in files)
    for _, s, fp in sorted(files):
        if total <= keep:
            break
        if fp.endswith("-seams.json"):
            continue
        try:
            os.remove(fp)
            total -= s
        except OSError:
            pass
