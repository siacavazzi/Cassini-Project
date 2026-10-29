#!/usr/bin/env python3
"""
Body reels for the frame server: every picture Cassini took of one body, in time order, each
made by the pipeline (color_image.processed_frame: repeat exposures stacked, lost pixels
filled, calibrated, aligned, centred on the body with north up by SPICE), drawn into the
pipeline's rolling mosaic (mosaic.compose) over the earlier tiles of the same filter when the camera
is stepping across the body (mosaic.panels decides, from the geometry cache).

The tiles of one mosaic (pictures linked through their panels) are made alike, so they meet without
seams or colour steps: each frame's repeat exposures, short and long, merged in I/F
(stacking.load_hdr), and every tile on one display scale (calibration.tiles_scale, worked out once
per mosaic and kept in the cache), drawn with mosaic.compose's calibrated matching. A picture that
is in no mosaic is made as before, stretched on its own.

A picture is a colour composite where the frames make a filter set, otherwise one black and
white frame. Filter sets follow the camera window's rule (web/cassini-os/src/head-quiet.html,
findSets): one camera, one target and observation, each frame within 300 s of the one before,
different colour filters; clear and polarizer frames end a set and a repeated filter starts a
new one. RED, GRN and a blue make true colour; three or more other filters false colour
(longest wavelength red, middle green, shortest blue); two filters a two-filter picture.
A black and white frame within 120 s of an earlier one with the same camera, observation and
filters is left out: stacking.load_stacked already folded it into that picture.

Every picture is kept in the cache, so a body is only ever processed once. To build a body
ahead of time (the server serves what this makes):

  CASSINI_DATA=... CASSINI_KERNELS=... python web/frames/reel.py ENCELADUS [--workers 2]
"""
import argparse
import collections
import contextlib
import hashlib
import io
import json
import os
import sys
import threading
import time

import numpy as np
import pandas as pd
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
for repo in (os.path.join(HERE, "..", ".."), os.getcwd(), os.environ.get("CASSINI_REPO", "")):
    if repo and os.path.exists(os.path.join(repo, "data_source.py")):
        REPO = os.path.abspath(repo)
        sys.path.insert(0, REPO)
        break
os.environ.setdefault("MPLBACKEND", "Agg")
import calibration  # noqa: E402
import color_image  # noqa: E402
import data_source  # noqa: E402
import mosaic  # noqa: E402
import stacking  # noqa: E402
import sets_passes  # noqa: E402

# bumped whenever the way reel pictures are made changes, so older ones are not served again
VERSIONS = {"balanced": "reel-v30", "raw": "reel-v13", "classic": "reel-v7"}   # one per calibration.style(); v30/v13/v7: the restart's calibration, tone and tile fixes; v29/v12/v6: flat field


def version():
    return VERSIONS[calibration.style()] + calibration.variant() + "-q95"   # WebP quality 95 (frame_server.QUALITY)
SET_GAP = sets_passes.SET_GAP   # seconds between frames of one filter set
REPEAT_GAP = 120       # stacking.find_repeats' window
VIEW = 1536            # full resolution pixels a picture shows (a north-up frame fits in 1448)
OUT = 1024             # ...kept at two thirds of full resolution
SCALE = OUT / VIEW
FOLLOW = 300           # full resolution pixels a close-up's newest panel may sit from the middle of the view
TRUE_BLUES = sets_passes.TRUE_BLUES

_index = None
_shots = {}
_shot_of = {}
_shot_locks = {}   # target -> lock: working out one body's reel (20 s for Saturn) holds up nothing else
_lock = threading.Lock()
_mosaic_lock = threading.Lock()   # mosaic keeps per frame work in a module level dict


_is_polarizer = sets_passes.is_polarizer
colour_filter = sets_passes.colour_filter   # the frame's colour filter, or None for clear and polarizer frames


def load_index():
    """Image_index.csv in time order, with each frame's filter set worked out."""
    global _index
    if _index is not None:
        return _index
    cols = ["path", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME", "filter1", "filter2", "seconds_1970"]
    idx = pd.read_csv(os.path.join(REPO, "Image_index.csv"), usecols=cols, low_memory=False)
    idx = idx[idx["path"].notna()].sort_values("seconds_1970", kind="stable").reset_index(drop=True)
    # the string steps of .str.rsplit("/", n=1).str[-1].str.replace(".png", "") on each path, without pandas' per
    # element machinery (a sixth of the time; the paths are all strings)
    idx["id"] = [p.rsplit("/", 1)[-1].replace(".png", "") for p in idx["path"].tolist()]
    cams, targets, obs = idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist()
    f1s, f2s, t = idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(), idx["seconds_1970"].to_numpy()
    # the filter sets, by the one rule (sets_passes: the camera windows', the pre-build's and the data's)
    set_of, sets = sets_passes.filter_sets(cams, targets, obs, f1s, f2s, t, lambda q: wavelength(cams[q], f1s[q] + f2s[q]))
    set_of = np.array(set_of)
    idx["set"] = set_of
    # copied whole once, which puts the columns added above into the frame's blocks (consolidates it): otherwise the
    # first selection from it (a body's reel, an observation's frames) did that, a tenth of a second on a request
    # thread, and two requests at once could both set about it
    _index = (idx.copy(), sets)
    return _index


_nm = None


def wavelength(camera, filters):
    """Effective wavelength (nm) of a filter pair ("ISSNA", "CL1RED"), from filter_calibration.csv."""
    global _nm
    if _nm is None:
        _nm = {}
        with open(os.path.join(REPO, "filter_calibration.csv")) as fh:
            next(fh)
            for line in fh:
                cam, fs, w = line.strip().split(",")[:3]
                _nm[(cam, fs)] = float(w)
    return _nm.get((camera, filters), 0)


def bodies():
    """Every target with frames: name, frame counts per camera, first and last frame time."""
    idx, _ = load_index()
    out = []
    for target, g in idx.groupby("TARGET_NAME"):
        if target in ("SKY", "UNK", "NONE", "DARK", "STAR", "PLAQUE", "CAL_LAMPS"):
            continue
        out.append({"target": target, "frames": len(g), "nac": int((g["INSTRUMENT_ID"] == "ISSNA").sum()),
                    "wac": int((g["INSTRUMENT_ID"] == "ISSWA").sum()), "first": float(g["seconds_1970"].min()),
                    "last": float(g["seconds_1970"].max())})
    return sorted(out, key=lambda b: -b["frames"])


def shots(target):
    """The body's pictures in time order, each {ids, t (unix seconds), cam, kind, filters, obs, panels, window}:
    ids longest wavelength first, kind true/false/two/bw, panels = the earlier pictures it is drawn over
    (mosaic.panels: a real mosaic tile of the same filter), window = how many, also = its other frames
    (stacked into it, or in its colour set but not used), group = the first picture of the mosaic it is a
    tile of (every picture linked to it through panels), only on mosaic tiles."""
    if target in _shots:
        return _shots[target]
    with _lock:
        lock = _shot_locks.setdefault(target, threading.Lock())
    with lock:
        if target in _shots:
            return _shots[target]
        idx, sets = load_index()
        rows = idx.index[idx["TARGET_NAME"] == target].tolist()
        out, done, last_single, last_shot = [], set(), {}, {}
        members = idx.loc[rows].query("set >= 0").groupby("set")["id"].agg(list).to_dict()
        # the columns as arrays, read by row number (the index is 0..n-1), with the values idx.loc[q] gave (the
        # strings themselves, numpy numbers): a row at a time through idx.loc took 25 s of Saturn's 26
        ids, set_of, cams, obs, filters, f1s, f2s, times = (idx[k].to_numpy() for k in (
            "id", "set", "INSTRUMENT_ID", "OBSERVATION_ID", "FILTER_NAME", "filter1", "filter2", "seconds_1970"))
        for q in rows:
            s = int(set_of[q])
            cam = "N" if cams[q] == "ISSNA" else "W"
            if s >= 0:
                if s in done:
                    continue
                done.add(s)
                st = sets[s]
                use = st["use"]
                out.append({"ids": [ids[u] for u in use], "t": float(st["ready"]), "cam": cam, "kind": st["kind"],
                            "filters": [colour_filter(str(f1s[u]), str(f2s[u])) for u in use], "obs": obs[q],
                            "also": [i for i in members.get(s, []) if i not in {ids[u] for u in use}]})
                continue
            key = (cam, obs[q], filters[q])
            if key in last_single and times[q] - last_single[key] <= REPEAT_GAP:
                last_shot[key].setdefault("also", []).append(ids[q])
                continue   # a repeat exposure, stacked into the picture before
            last_single[key] = times[q]
            last_shot[key] = {"ids": [ids[q]], "t": float(times[q]), "cam": cam, "kind": "bw",
                             "filters": [f"{f1s[q]}/{f2s[q]}"], "obs": obs[q]}
            out.append(last_shot[key])
        out.sort(key=lambda s: s["t"])
        # the mosaic: the earlier pictures of the same filter this one is a new tile next to, by the rule in
        # mosaic.panels, from where SPICE puts the body in each frame (the geometry cache)
        where = geometry([i for s in out for i in s["ids"]])
        pictures = []
        for s in out:
            g = where.get(s["ids"][len(s["ids"]) // 2])   # a set is aligned to its middle frame
            pictures.append({"t": s["t"], "cam": s["cam"], "obs": s["obs"], "filter": (s["kind"], tuple(s["filters"])),
                             "x": g and g[0], "y": g and g[1], "z": g and g[2]})
        first = list(range(len(out)))   # union-find over panels: the mosaics

        def root(n):
            while first[n] != n:
                first[n] = first[first[n]]
                n = first[n]
            return n

        for n, (s, panels) in enumerate(zip(out, mosaic.panels(pictures))):
            s["panels"] = panels
            s["window"] = len(panels)
            for p in panels:
                a, b = sorted((root(n), root(p)))
                first[b] = a
        tiles = {}
        for n in range(len(out)):
            tiles.setdefault(root(n), []).append(n)
        for r, members in tiles.items():
            if len(members) > 1:
                for n in members:
                    out[n]["group"] = r
        _shot_of[target] = {i: n for n, s in enumerate(out) for i in s["ids"] + s.get("also", [])}
        _shots[target] = out
        return out


def geometry(ids):
    """Where SPICE puts the body in each of the frames ids, from the geometry cache (bootleg_autonav,
    CASSINI_GEOMETRY_CACHE): {id: (x, y, z)}, find_target's centring shift in full resolution pixels and
    the distance in km. Frames that are not cached, or that SPICE could not place, are left out."""
    import bootleg_autonav as ba
    if not ba.GEOMETRY_CACHE or not os.path.exists(ba.GEOMETRY_CACHE):
        return {}
    db, out = ba._geometry_db(), {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        for frame, x, y, z in db.execute(f"SELECT frame, x, y, z FROM target WHERE version = ? AND error IS NULL "
                                         f"AND frame IN ({','.join('?' * len(part))})", (ba.GEOMETRY_VERSION, *part)):
            out[frame] = (x, y, z)
    return out


_target_of = None


_warming = set()


def target_of():
    """{frame id: target} for every frame in the index (the frame server makes it as it starts)."""
    global _target_of
    if _target_of is not None:
        return _target_of
    with _lock:
        if _target_of is None:
            idx, _ = load_index()
            _target_of = dict(zip(idx["id"], idx["TARGET_NAME"]))
    return _target_of


def mosaic_of(frame_id, wait=True):
    """(target, n) when frame_id is in picture n of its body's reel (stacked into it, or one of its colour
    set) and that picture is a mosaic tile drawn over earlier ones; otherwise None. wait=False answers None
    while the body's reel is still being worked out (seconds, 20 for Saturn) and works it out meanwhile."""
    target = target_of().get(frame_id)
    if not isinstance(target, str):
        return None
    if not wait and target not in _shots:
        if target not in _warming:
            _warming.add(target)
            threading.Thread(target=shots, args=(target,), daemon=True).start()
        return None
    reel = shots(target)
    n = _shot_of[target].get(frame_id)
    return (target, n) if n is not None and reel[n]["panels"] else None


def _cached(path, make):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        pass
    data = make()
    part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(part, "wb") as fh:
            fh.write(data)
        os.replace(part, path)
    except OSError as e:
        # a full disk costs the cache, never the picture (the next request makes it again)
        try:
            os.remove(part)
        except OSError:
            pass
        print(f"cannot keep {path} in the cache ({e})", flush=True)
    return data


# a made picture's report (the .json kept beside it in the cache): written once with the picture, so it is read from
# the cache once and then kept here, and a picture asked for again costs one file (the picture), not two
REPORTS_KEEP = 8192
_reports, _reports_lock, _MISSING = collections.OrderedDict(), threading.Lock(), object()


def keep_report(path, report):
    """Keeps the report just written to path (as it reads back from the file)."""
    rep = json.loads(json.dumps(report))
    with _reports_lock:
        _reports[path] = rep
        _reports.move_to_end(path)
        while len(_reports) > REPORTS_KEEP:
            _reports.popitem(last=False)


def report_of(path, default=_MISSING):
    """The report kept in path, read from the cache once: a copy, for the caller to add to. default: answered when
    there is no such file (otherwise FileNotFoundError)."""
    with _reports_lock:
        rep = _reports.get(path)
        if rep is not None:
            _reports.move_to_end(path)
            return dict(rep)
    try:
        with open(path) as fh:
            rep = json.load(fh)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default
    keep_report(path, rep)
    return dict(rep)


FOLDERS = {"N": "nac_data", "W": "wac_data"}


def group_of(target, n):
    """The ids of every picture of the mosaic picture n of the body's reel is a tile of, or None."""
    reel = shots(target)
    g = reel[n].get("group")
    return None if g is None else [s["ids"] for s in reel if s.get("group") == g]


_scale_locks = {}


def mosaic_scale(group, cache):
    """The display scale shared by the tiles of one mosaic (group = their ids), from their frames merged
    in I/F (calibration.tiles_scale: each tile's own scale, combined), worked out once and kept in the
    cache. None when no tile calibrates."""
    key = hashlib.sha1(",".join("_".join(ids) for ids in group).encode()).hexdigest()[:16]
    path = os.path.join(cache, version(), "scales", key + ".json")

    def make():
        tiles = []
        for ids in group:
            iofs = [stacking.load_hdr(f"{FOLDERS[i[0]]}/{i}.png", REPEAT_GAP)[1] for i in ids]
            if all(iof is not None for iof in iofs):
                tiles.append(iofs)
        if not tiles:
            return b"null"
        return json.dumps(calibration.tiles_scale(tiles)).encode()

    with _lock:
        lock = _scale_locks.setdefault(key, threading.Lock())
    with lock:
        return json.loads(_cached(path, make))


def picture(ids, cache, group=None):
    """The picture of frames ids as RGBA, OUT px square: VIEW full resolution pixels around the frame's
    middle, north up, and its report (frame_offset: where that middle sits relative to the body's centre).
    group = the ids of every tile of the mosaic it is a tile of (group_of): then its frames' exposures are
    merged in I/F and it is drawn on the mosaic's shared display scale (report["shared_scale"])."""
    base = os.path.join(cache, version(), "pictures", "_".join(ids))
    made = {}

    def make():
        paths = [f"{FOLDERS[i[0]]}/{i}.png" for i in ids]
        scale = mosaic_scale(group, cache) if group else None
        if scale:
            image, _, report = color_image.processed_frame(paths, hdr=True, scale=scale)
            report["shared_scale"] = bool(report.get("calibrated"))
        else:
            image, _, report = color_image.processed_frame(paths)
        if "frame_offset" in report:
            # processed_frame's canvas has the frame's middle at its middle
            c = image.shape[0] // 2
            view = image[c - VIEW // 2:c + VIEW // 2, c - VIEW // 2:c + VIEW // 2]
        else:
            pad = (VIEW - image.shape[0]) // 2
            view = np.pad(image, ((pad, pad), (pad, pad), (0, 0)))
        report["ids"] = list(ids)
        made.update(report)
        out = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(view)).resize((OUT, OUT), Image.LANCZOS).save(out, "PNG", compress_level=1)
        return out.getvalue()

    png = _cached(base + ".png", make)
    if made:
        _cached(base + ".json", lambda: json.dumps(made, default=str).encode())
    elif os.path.exists(base + ".json"):
        with open(base + ".json") as fh:
            made = json.load(fh)
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA")), made


def shot_webp(target, n, size, cache, use_mosaic=True, slots=None):
    """Picture n of the body's reel as WebP, drawn over the pictures before it in its mosaic, and its report.
    slots = a semaphore held while making it (not while serving it from the cache)"""
    reel = shots(target)
    s = reel[n]
    window = [reel[j] for j in s["panels"]] if use_mosaic else []
    window = window + [s]
    key = "_".join(s["ids"]) + ("" if len(window) == 1 else "-" + hashlib.sha1(
        ",".join("_".join(w["ids"]) for w in window).encode()).hexdigest()[:12])
    # a mosaic (more than one picture) drawn with the blend or level steps (mosaic.drawing) is another picture than
    # before them; a lone picture is the same either way
    drawn = "-" + mosaic.drawing() if len(window) > 1 and mosaic.drawing() else ""
    path = os.path.join(cache, version(), str(size), key + drawn + ".webp")
    report = {}

    def make():
        with slots or contextlib.nullcontext():
            return made()

    def made():
        group = group_of(target, n)
        frames = place([picture(w["ids"], cache, group) for w in window])
        report.update(frames[-1][1])
        if len(frames) > 1:
            # tiles on one shared scale only need small corrections at the seams
            calibrated = all(f[1].get("shared_scale") for f in frames)
            with _mosaic_lock:
                rgba = mosaic.compose([(f[0], None, None, None) for f in frames], False, calibrated=calibrated)
        else:
            rgba = frames[0][0]
        im = color_image.sharpen(Image.fromarray(rgba, "RGBA"))
        if size < OUT:
            im = im.resize((size, size), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "WEBP", quality=95, method=4)
        return out.getvalue()

    data = _cached(path, make)
    if not report:
        # served from the cache: the picture's report is kept next to it, no need to open the picture
        try:
            with open(os.path.join(cache, version(), "pictures", "_".join(s["ids"]) + ".json")) as fh:
                report = json.load(fh)
        except (OSError, ValueError):
            report = picture(s["ids"], cache, group_of(target, n))[1]
    report["mosaic"] = len(window)
    return data, report


def place(frames):
    """Puts each (image, report) of a mosaic window, oldest first, where it sits on the body, in one
    view: the body's centre in the middle when the newest picture is centred on it, otherwise (a
    close-up) the middle of the window's panels, kept within FOLLOW of the newest one. Pictures
    without SPICE stay where they are, on their own."""
    newest = frames[-1][1]
    if "frame_offset" not in newest:
        return frames[-1:]
    frames = [f for f in frames if "frame_offset" in f[1]]
    offsets = np.array([f[1]["frame_offset"] for f in frames])
    if newest.get("centred"):
        middle = np.zeros(2)
    else:
        middle = offsets.mean(axis=0)
        middle = np.clip(middle, offsets[-1] - FOLLOW, offsets[-1] + FOLLOW)
    out = []
    for (image, report), offset in zip(frames, offsets):
        dx, dy = np.round((offset - middle) * SCALE).astype(int)
        if abs(dx) >= OUT or abs(dy) >= OUT:
            continue   # a panel too far away to show
        moved = np.zeros_like(image)
        moved[max(dy, 0):OUT + min(dy, 0), max(dx, 0):OUT + min(dx, 0)] = image[max(-dy, 0):OUT - max(dy, 0), max(-dx, 0):OUT - max(dx, 0)]
        out.append((moved, report))
    return out


def build(target, cache, workers=1, first=0, count=None):
    """Makes the pictures of the body's reel (not the mosaics, which are quick), oldest first:
    count of them from number first on, or all."""
    reel = shots(target)[first:None if count is None else first + count]
    todo = [(s["ids"], group_of(target, first + k)) for k, s in enumerate(reel)
            if not os.path.exists(os.path.join(cache, version(), "pictures", "_".join(s["ids"]) + ".png"))]
    print(f"{target}: {len(reel)} pictures, {len(reel) - len(todo)} already made, {len(todo)} to make", flush=True)
    start, done = time.time(), 0

    def report():
        rate = done / max(time.time() - start, 1e-6)
        left = (len(todo) - done) / rate if rate else 0
        print(f"{done}/{len(todo)} made, {rate * 60:.0f} a minute, about {left / 60:.0f} min left", flush=True)

    if workers <= 1:
        for ids, group in todo:
            try:
                picture(ids, cache, group)
            except Exception as e:
                print(f"Failed {ids}: {e}", flush=True)
            done += 1
            if done % 25 == 0:
                report()
    else:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        # one year at a time, like export_sequence, so the workers share that year's kernels
        with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn"), initializer=_init_worker) as pool:
            for fut in [pool.submit(_build_one, ids, cache, group) for ids, group in todo]:
                fut.result()
                done += 1
                if done % 25 == 0:
                    report()
    report()


def _init_worker():
    color_image.init_worker()


def _build_one(ids, cache, group=None):
    try:
        picture(ids, cache, group)
    except Exception as e:
        print(f"Failed {ids}: {e}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="e.g. ENCELADUS")
    ap.add_argument("--cache", default=os.path.join(os.getcwd(), "frame_cache"))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--first", type=int, default=0, help="start at this picture of the reel")
    ap.add_argument("--count", type=int, help="make only this many pictures")
    ap.add_argument("--list", action="store_true", help="only print the reel")
    args = ap.parse_args()
    data_source.KEEP_SPICE_CACHE = True
    if args.list:
        for n, s in enumerate(shots(args.target.upper())):
            print(n, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(s["t"])), s["cam"], s["kind"], ",".join(s["ids"]), s["window"])
        return
    build(args.target.upper(), args.cache, args.workers, args.first, args.count)


if __name__ == "__main__":
    main()
