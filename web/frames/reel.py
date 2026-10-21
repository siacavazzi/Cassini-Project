#!/usr/bin/env python3
"""
Body reels for the frame server: every picture Cassini took of one body, in time order, each
made by the pipeline (color_image.processed_frame: repeat exposures stacked, lost pixels
filled, calibrated, aligned, centred on the body with north up by SPICE), drawn into the
pipeline's rolling mosaic (mosaic.compose) with the pictures just before it.

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
import color_image  # noqa: E402
import data_source  # noqa: E402
import mosaic  # noqa: E402

# bumped whenever the way reel pictures are made changes, so older ones are not served again
VERSION = "reel-v2"
SET_GAP = 300          # seconds between frames of one filter set
REPEAT_GAP = 120       # stacking.find_repeats' window
MOSAIC_GAP = 1800      # pictures more than this far apart never share a mosaic
VIEW = 1536            # full resolution pixels around the body that a picture shows
OUT = 1024             # ...kept at two thirds of full resolution
TRUE_BLUES = ("BL1", "BL2", "VIO")

_index = None
_shots = {}
_lock = threading.Lock()
_mosaic_lock = threading.Lock()   # mosaic keeps per frame work in a module level dict


def _is_polarizer(f1, f2):
    return f1.startswith("P") and f1[1:2].isdigit() or f1.startswith("IRP") or f2.startswith("IRP")


def colour_filter(f1, f2):
    """The frame's colour filter ("RED", "CB2", "BL1/GRN"...), or None for clear and polarizer frames."""
    if _is_polarizer(f1, f2):
        return None
    return "/".join(f for f in (f1, f2) if not f.startswith("CL")) or None


def load_index():
    """Image_index.csv in time order, with each frame's filter set worked out."""
    global _index
    if _index is not None:
        return _index
    cols = ["path", "INSTRUMENT_ID", "TARGET_NAME", "OBSERVATION_ID", "FILTER_NAME", "filter1", "filter2", "seconds_1970"]
    idx = pd.read_csv(os.path.join(REPO, "Image_index.csv"), usecols=cols, low_memory=False)
    idx = idx[idx["path"].notna()].sort_values("seconds_1970", kind="stable").reset_index(drop=True)
    idx["id"] = idx["path"].str.rsplit("/", n=1).str[-1].str.replace(".png", "", regex=False)
    cams, targets, obs = idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist()
    f1s, f2s, t = idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(), idx["seconds_1970"].to_numpy()
    set_of = np.full(len(idx), -1)
    sets, run = [], {}

    def close(cam):
        r = run.pop(cam, None)
        if not r or len(r["rows"]) < 2:
            return
        by = dict(zip(r["filters"], r["rows"]))
        blue = next((f for f in TRUE_BLUES if f in by), None)
        if "RED" in by and "GRN" in by and blue:
            kind, use = "true", [by["RED"], by["GRN"], by[blue]]
        else:
            w = sorted(r["rows"], key=lambda q: -wavelength(cams[q], f1s[q] + f2s[q]))
            kind, use = ("false", [w[0], w[len(w) // 2], w[-1]]) if len(w) >= 3 else ("two", w)
        for q in r["rows"]:
            set_of[q] = len(sets)
        sets.append({"kind": kind, "use": use, "ready": max(t[q] for q in use)})

    for q in range(len(idx)):
        cam, f = cams[q], colour_filter(f1s[q], f2s[q])
        r = run.get(cam)
        if not f:
            close(cam)
            continue
        if r and targets[q] == r["target"] and obs[q] == r["obs"] and t[q] - r["last"] <= SET_GAP and f not in r["filters"]:
            r["rows"].append(q); r["filters"].append(f); r["last"] = t[q]
        else:
            close(cam)
            run[cam] = {"target": targets[q], "obs": obs[q], "rows": [q], "filters": [f], "last": t[q]}
    for cam in list(run):
        close(cam)
    idx["set"] = set_of
    _index = (idx, sets)
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
    """The body's pictures in time order, each {ids, t (unix seconds), cam, kind, filters, obs, window}:
    ids longest wavelength first, kind true/false/two/bw, window = how many of the pictures just
    before it share its mosaic."""
    with _lock:
        if target in _shots:
            return _shots[target]
        idx, sets = load_index()
        rows = idx.index[idx["TARGET_NAME"] == target].tolist()
        out, done, last_single = [], set(), {}
        for q in rows:
            r = idx.loc[q]
            s = int(r["set"])
            cam = "N" if r["INSTRUMENT_ID"] == "ISSNA" else "W"
            if s >= 0:
                if s in done:
                    continue
                done.add(s)
                st = sets[s]
                use = [idx.loc[u] for u in st["use"]]
                out.append({"ids": [u["id"] for u in use], "t": float(st["ready"]), "cam": cam, "kind": st["kind"],
                            "filters": [colour_filter(str(u["filter1"]), str(u["filter2"])) for u in use], "obs": r["OBSERVATION_ID"]})
                continue
            key = (cam, r["OBSERVATION_ID"], r["FILTER_NAME"])
            if key in last_single and r["seconds_1970"] - last_single[key] <= REPEAT_GAP:
                continue   # a repeat exposure, stacked into the picture before
            last_single[key] = r["seconds_1970"]
            out.append({"ids": [r["id"]], "t": float(r["seconds_1970"]), "cam": cam, "kind": "bw",
                        "filters": [f"{r['filter1']}/{r['filter2']}"], "obs": r["OBSERVATION_ID"]})
        out.sort(key=lambda s: s["t"])
        # the rolling mosaic, like export_sequence's: the pictures before this one from the same camera,
        # observation and colour, back to a gap of MOSAIC_GAP
        for n, s in enumerate(out):
            window, j, t = 0, n - 1, s["t"]
            while j >= 0 and window < mosaic.buffer_size - 1:
                p = out[j]
                j -= 1
                if p["cam"] != s["cam"]:
                    continue
                if p["obs"] != s["obs"] or (p["kind"] == "bw") != (s["kind"] == "bw") or t - p["t"] > MOSAIC_GAP:
                    break
                window, t = window + 1, p["t"]
            s["window"] = window
        _shots[target] = out
        return out


def _cached(path, make):
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    data = make()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, path)
    return data


def picture(ids, cache):
    """The picture of frames ids as RGBA, OUT px square with the body at the centre, and its report."""
    base = os.path.join(cache, VERSION, "pictures", "_".join(ids))
    made = {}

    def make():
        folders = {"N": "nac_data", "W": "wac_data"}
        image, _, report = color_image.processed_frame([f"{folders[i[0]]}/{i}.png" for i in ids])
        if report["centred"]:
            # auto_center's canvas has the body at its centre
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
    window = [reel[j] for j in range(n - 1, -1, -1) if reel[j]["cam"] == s["cam"]][:s["window"]] if use_mosaic else []
    window = window[::-1] + [s]
    key = "_".join(s["ids"]) + ("" if len(window) == 1 else "-" + hashlib.sha1(
        ",".join("_".join(w["ids"]) for w in window).encode()).hexdigest()[:12])
    path = os.path.join(cache, VERSION, str(size), key + ".webp")
    report = {}

    def make():
        with slots or contextlib.nullcontext():
            return made()

    def made():
        frames = [picture(w["ids"], cache) for w in window]
        report.update(frames[-1][1])
        if len(frames) > 1:
            with _mosaic_lock:
                rgba = mosaic.compose([(f[0], None, None, None) for f in frames], False)
        else:
            rgba = frames[0][0]
        im = color_image.sharpen(Image.fromarray(rgba, "RGBA"))
        if size < OUT:
            im = im.resize((size, size), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "WEBP", quality=82, method=4)
        return out.getvalue()

    data = _cached(path, make)
    if not report:
        # served from the cache: the picture's report is kept next to it, no need to open the picture
        try:
            with open(os.path.join(cache, VERSION, "pictures", "_".join(s["ids"]) + ".json")) as fh:
                report = json.load(fh)
        except (OSError, ValueError):
            report = picture(s["ids"], cache)[1]
    report["mosaic"] = len(window)
    return data, report


def build(target, cache, workers=1, first=0, count=None):
    """Makes the pictures of the body's reel (not the mosaics, which are quick), oldest first:
    count of them from number first on, or all."""
    reel = shots(target)[first:None if count is None else first + count]
    todo = [s["ids"] for s in reel if not os.path.exists(os.path.join(cache, VERSION, "pictures", "_".join(s["ids"]) + ".png"))]
    print(f"{target}: {len(reel)} pictures, {len(reel) - len(todo)} already made, {len(todo)} to make", flush=True)
    start, done = time.time(), 0

    def report():
        rate = done / max(time.time() - start, 1e-6)
        left = (len(todo) - done) / rate if rate else 0
        print(f"{done}/{len(todo)} made, {rate * 60:.0f} a minute, about {left / 60:.0f} min left", flush=True)

    if workers <= 1:
        for ids in todo:
            try:
                picture(ids, cache)
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
            for fut in [pool.submit(_build_one, ids, cache) for ids in todo]:
                fut.result()
                done += 1
                if done % 25 == 0:
                    report()
    report()


def _init_worker():
    color_image.init_worker()


def _build_one(ids, cache):
    try:
        picture(ids, cache)
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
