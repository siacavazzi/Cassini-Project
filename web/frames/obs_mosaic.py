#!/usr/bin/env python3
"""
Observation mosaics for the camera windows: when Cassini maps a whole body a tile at a time (In
Saturn's Shadow, a Titan global map), the window shows the observation's mosaic as it stood when
each frame came in, every filter, made like the mosaic benchmark (web/frames/mosaic_benchmark.py)
rather than the reel's rolling window of a few same-filter tiles.

An observation (one camera, one target, one OBSERVATION_ID) is a whole-body mosaic when the
geometry cache puts the body's disk inside the frames' footprint, the footprint is more than two
frames and less than MAX_FRAMES frames across. Its frames are made once (prepare): every picture
through color_image.processed_frame (repeat exposures merged in I/F, calibrated, centred north up
by SPICE) on one display scale for the observation (mosaic_benchmark.display_scale), shrunk onto a
canvas that fits the whole footprint (so the view does not move or rescale as the mosaic grows),
and kept in the cache with a manifest. The mosaic "so far" at a frame is then every tile up to that
frame, each filter drawn by mosaic.compose (calibrated, none pinned) over its own earlier tiles, the
filters put together like the benchmark: three or more filters make false colour (longest
wavelength red, middle green, shortest blue; only where all three have the picture), otherwise the
best covered filter in grey. Each filter's mosaic at each tile count is kept, so a new frame only
recomposes the filter it adds to.

  CASSINI_DATA=... CASSINI_GEOMETRY_CACHE=... python web/frames/obs_mosaic.py W1537023863_1 --cache DIR
  (makes the observation the frame is in ahead of time; the frame server makes it on first request)
"""
import argparse
import io
import json
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
import mosaic  # noqa: E402
import mosaic_benchmark  # noqa: E402

# bumped whenever the way observation mosaics are made changes, so older ones are not served again
VERSION = "obs-v1"
CANVAS = 2048        # longest side of the canvas the tiles are drawn on
OUT = 1024           # longest side of the picture sent
MAX_FRAMES = 16      # footprints wider than this many frames (ring scans) stay rolling mosaics
FRAME = 1024         # full resolution frame
RADIUS = {"SATURN": 60268, "JUPITER": 69911, "TITAN": 2575, "RHEA": 764, "IAPETUS": 735, "DIONE": 561,
          "TETHYS": 531, "ENCELADUS": 252, "MIMAS": 198, "HYPERION": 135, "PHOEBE": 107}
IFOV = {"N": 6.0e-6, "W": 60e-6}   # radians per full resolution pixel

_obs = {}             # (target, obs, cam) -> whole-body mosaic or not
_lock = threading.Lock()
_preparing = set()


def key_of(frame_id):
    """(target, obs, cam) of the frame."""
    idx, _ = reel.load_index()
    with _lock:
        if not hasattr(key_of, "row"):
            key_of.row = dict(zip(idx["id"], range(len(idx))))
    q = key_of.row.get(frame_id)
    if q is None:
        return None
    r = idx.iloc[q]
    return r["TARGET_NAME"], r["OBSERVATION_ID"], "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"


def rows(key):
    """The observation's frames in time order, as Image_index rows."""
    idx, _ = reel.load_index()
    target, obs, cam = key
    inst = "ISSNA" if cam == "N" else "ISSWA"
    return idx[(idx["OBSERVATION_ID"] == obs) & (idx["TARGET_NAME"] == target) & (idx["INSTRUMENT_ID"] == inst)]


def whole_body(key):
    """Whether the observation is a whole-body mosaic (see the module's docstring), from the geometry cache."""
    with _lock:
        if key in _obs:
            return _obs[key]
    r = rows(key)
    where = reel.geometry(r["id"].tolist())
    ok = False
    if key[0] in RADIUS and len(where) >= 4:
        pts = np.array(list(where.values()))
        radius = RADIUS[key[0]] / (np.median(pts[:, 2]) * IFOV[key[2]])
        lo, hi = pts[:, :2].min(0) - FRAME / 2, pts[:, :2].max(0) + FRAME / 2
        span = hi - lo
        ok = bool((lo < -radius).all() and (hi > radius).all() and span.prod() > 2 * FRAME ** 2
                  and span.max() < MAX_FRAMES * FRAME)
    with _lock:
        _obs[key] = ok
    return ok


def frames(key):
    """The observation's pictures, oldest first: [(path, filter, t, nm)], repeat exposures (the same filter
    within REPEAT_GAP) left out, as stacking.load_hdr merges them in (mosaic_benchmark.frames)."""
    out, last = [], {}
    for r in rows(key).itertuples(index=False):
        f1, f2 = str(r.filter1), str(r.filter2)
        f = "/".join(x for x in (f1, f2) if not x.startswith("CL")) or "CL1/CL2"
        if f in last and r.seconds_1970 - last[f] <= mosaic_benchmark.REPEAT_GAP:
            continue
        last[f] = r.seconds_1970
        out.append((r.path, f, float(r.seconds_1970), reel.wavelength("ISSNA" if key[2] == "N" else "ISSWA", f1 + f2)))
    return out


def folder(key, cache):
    return os.path.join(cache, VERSION, "_".join(key))


def prepare(key, cache):
    """Makes the observation's tiles and manifest (the display scale, the canvas, each tile's filter, time and
    place), once; returns the manifest."""
    base = folder(key, cache)
    path = os.path.join(base, "manifest.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    start = time.time()
    todo = frames(key)
    scale = mosaic_benchmark.display_scale([t[:3] for t in todo], 99.9, 3.0)
    made, failed = [], []
    for n, (p, f, t, nm) in enumerate(todo):
        try:
            image, _, rep = color_image.processed_frame([p], hdr=True,
                                                        scale={**scale, "blacks": [scale["blacks"].get(f, 0.0)]})
        except Exception as e:
            failed.append({"path": p, "why": f"{type(e).__name__}: {e}"[:200]})
            continue
        if "frame_offset" not in rep:
            failed.append({"path": p, "why": rep.get("why", "not placed by SPICE")})
            continue
        made.append((p, f, t, nm, image, rep))
    if not made:
        manifest = {"tiles": [], "failed": failed}
    else:
        # the canvas: every frame on it, the longest side CANVAS pixels
        half = [m[4].shape[0] / 2 for m in made]
        xs, ys = [m[5]["frame_offset"][0] for m in made], [m[5]["frame_offset"][1] for m in made]
        x0, x1 = min(x - r for x, r in zip(xs, half)), max(x + r for x, r in zip(xs, half))
        y0, y1 = min(y - r for y, r in zip(ys, half)), max(y + r for y, r in zip(ys, half))
        k = CANVAS / max(x1 - x0, y1 - y0)
        W, H = int(np.ceil((x1 - x0) * k)) + 2, int(np.ceil((y1 - y0) * k)) + 2
        tiles = []
        os.makedirs(os.path.join(base, "tiles"), exist_ok=True)
        for n, (p, f, t, nm, image, rep) in enumerate(made):
            side = round(image.shape[0] * k)
            small = np.asarray(Image.fromarray(image).resize((side, side), Image.LANCZOS))
            left = round((rep["frame_offset"][0] - x0) * k) - side // 2 + 1
            top = round((rep["frame_offset"][1] - y0) * k) - side // 2 + 1
            # kept cropped to the frame's pixels
            used = np.flatnonzero(small[..., 3].any(1)), np.flatnonzero(small[..., 3].any(0))
            if not len(used[0]):
                continue
            a, b, c, d = used[0][0], used[0][-1] + 1, used[1][0], used[1][-1] + 1
            Image.fromarray(np.ascontiguousarray(small[a:b, c:d])).save(os.path.join(base, "tiles", f"{n}.png"), compress_level=1)
            tiles.append({"n": n, "path": p, "id": os.path.basename(p)[:-4], "filter": f, "t": t, "nm": nm,
                          "left": int(left + c), "top": int(top + a), "stacked": rep.get("stacked"), "calibrated": rep.get("calibrated")})
        # the filters drawn: three or more with tiles make false colour, longest wavelength red
        count = {}
        for tile in tiles:
            count[tile["filter"]] = count.get(tile["filter"], 0) + 1
        nms = {tile["filter"]: tile["nm"] for tile in tiles}
        common = [f for f in count if count[f] >= max(count.values()) / 2]
        by_nm = sorted(common, key=lambda f: -nms[f])
        colour = [by_nm[0], by_nm[len(by_nm) // 2], by_nm[-1]] if len(by_nm) >= 3 else None
        manifest = {"key": list(key), "canvas": [W, H], "scale": k, "display_scale": scale, "colour": colour,
                    "grey": max(count, key=count.get), "tiles": tiles, "failed": failed}
    manifest["seconds"] = round(time.time() - start, 1)
    os.makedirs(base, exist_ok=True)
    reel._cached(path, lambda: json.dumps(manifest, default=str).encode())
    print(f"observation mosaic {'_'.join(key)}: {len(manifest['tiles'])} tiles, {len(failed)} failed, "
          f"{manifest['seconds']} s", flush=True)
    return manifest


def ready(key, cache, start=True):
    """The manifest when the observation's tiles are made; otherwise None, and (start) makes them in the
    background."""
    path = os.path.join(folder(key, cache), "manifest.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    with _lock:
        if start and key not in _preparing:
            _preparing.add(key)
            threading.Thread(target=_prepare, args=(key, cache), daemon=True).start()
    return None


def _prepare(key, cache):
    try:
        prepare(key, cache)
    except Exception as e:
        print(f"observation mosaic {'_'.join(key)} failed: {type(e).__name__}: {e}", flush=True)


def _tile(base, tile, W, H):
    part = np.asarray(Image.open(os.path.join(base, "tiles", f"{tile['n']}.png")).convert("RGBA"))
    frame = np.zeros((H, W, 4), np.uint8)
    x0, y0 = max(tile["left"], 0), max(tile["top"], 0)
    x1, y1 = min(tile["left"] + part.shape[1], W), min(tile["top"] + part.shape[0], H)
    frame[y0:y1, x0:x1] = part[y0 - tile["top"]:y1 - tile["top"], x0 - tile["left"]:x1 - tile["left"]]
    return frame


def filter_mosaic(manifest, f, count, cache):
    """The filter f's mosaic of its first count tiles, RGBA on the canvas (kept in the cache)."""
    base = folder(manifest["key"], cache)
    path = os.path.join(base, "filters", f"{f.replace('/', '_')}-{count}.png")

    def make():
        W, H = manifest["canvas"]
        window = [(_tile(base, t, W, H), None, None, None) for t in [t for t in manifest["tiles"] if t["filter"] == f][:count]]
        feather = mosaic.feather_px
        with reel._mosaic_lock:
            try:
                # the benchmark's soft edge on its 0.5 scale canvas, at this canvas's scale
                mosaic.feather_px = max(8, round(64 * manifest["scale"] / 0.5))
                mosaic.reset()
                rgba = mosaic.compose(window, False, calibrated=True, pin=None)
                mosaic.reset()
            finally:
                mosaic.feather_px = feather
        out = io.BytesIO()
        Image.fromarray(rgba).save(out, "PNG", compress_level=1)
        return out.getvalue()

    return np.asarray(Image.open(io.BytesIO(reel._cached(path, make))).convert("RGBA"))


def so_far(manifest, t, cache):
    """The observation's mosaic with every tile taken by time t, RGBA OUT px on its longest side, and how
    many tiles and filters are in it."""
    tiles = [x for x in manifest["tiles"] if x["t"] <= t + 1]
    count = {}
    for x in tiles:
        count[x["filter"]] = count.get(x["filter"], 0) + 1
    colour = manifest["colour"]
    if colour and all(count.get(f) for f in colour):
        acc = [filter_mosaic(manifest, f, count[f], cache) for f in colour]
        rgb = np.dstack([a[..., 0] for a in acc])
        # only where every filter has the picture: past one filter's edge the others alone are a coloured rim
        alpha = np.min([a[..., 3] for a in acc], axis=0)
        rgb = (rgb * (alpha[..., None] / np.float32(255)) + 0.5).astype(np.uint8)
        rgba, used = np.dstack([rgb, alpha]), colour
    else:
        f = manifest["grey"] if count.get(manifest["grey"]) else max(count, key=count.get)
        rgba, used = filter_mosaic(manifest, f, count[f], cache), [f]
    im = Image.fromarray(rgba, "RGBA")
    W, H = manifest["canvas"]
    k = OUT / max(W, H)
    im = im.resize((round(W * k), round(H * k)), Image.LANCZOS)
    return im, {"mosaic": len(tiles), "filters": len(used), "filter_names": used, "observation": manifest["key"][1],
                "of": len(manifest["tiles"]), "width": im.width, "height": im.height}


def mosaic_webp(frame_id, size, cache, slots=None):
    """(WebP, report) of the observation mosaic so far at frame_id, when its observation is a whole-body
    mosaic whose tiles are made; otherwise None (and the tiles are started in the background)."""
    key = key_of(frame_id)
    if key is None or not whole_body(key):
        return None
    manifest = ready(key, cache)
    if not manifest or not manifest["tiles"]:
        return None
    idx, _ = reel.load_index()
    t = float(idx.iloc[key_of.row[frame_id]]["seconds_1970"])
    n = sum(1 for x in manifest["tiles"] if x["t"] <= t + 1)
    if not n:
        return None
    path = os.path.join(folder(key, cache), str(size), f"{n}.webp")
    report = {}

    def make():
        with slots or __import__("contextlib").nullcontext():
            im, rep = so_far(manifest, t, cache)
        report.update(rep)
        if max(im.size) > size:
            im.thumbnail((size, size), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "WEBP", quality=85, method=4)
        reel._cached(path[:-5] + ".json", lambda: json.dumps(rep).encode())
        return out.getvalue()

    data = reel._cached(path, make)
    if not report:
        with open(path[:-5] + ".json") as fh:
            report = json.load(fh)
    return data, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frame", help="a frame of the observation, e.g. W1537023863_1")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--all", action="store_true", help="also make the mosaic at every frame (1024 px)")
    args = ap.parse_args()
    key = key_of(args.frame)
    print(key, "whole-body mosaic" if whole_body(key) else "not a whole-body mosaic")
    manifest = prepare(key, args.cache)
    if args.all:
        for tile in manifest["tiles"]:
            t0 = time.time()
            _, rep = mosaic_webp(tile["id"], 1024, args.cache)
            print(tile["id"], tile["filter"], rep["mosaic"], f"{time.time() - t0:.2f} s", flush=True)


if __name__ == "__main__":
    main()
