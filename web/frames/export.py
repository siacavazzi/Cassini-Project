#!/usr/bin/env python3
"""
Movie export for the frame server: a stretch of the mission, picked on the Cassini OS timeline, made into an MP4.

Every picture in the film is one the pipeline already makes for the camera windows, chosen by the same rule as
movie mode (web/cassini-os/src/movie.html, choices): a frame that is a new tile of a mosaic pass shows the mosaic
so far (obs_mosaic.mosaic_webp, else the reel's rolling mosaic, reel.shot_webp), the frame that completes a filter
set shows the set's colour composite (color_image.load_aligned), and any other frame is processed on its own
(color_image.load_aligned with one frame: repeat exposures stacked, calibrated, on the pipeline's display scale).
Each try that the server cannot make moves on to the next; the archive frame as it is comes last. Filter sets are
reel.load_index's, the Python port of the camera windows' findSets.

The film shows one pane per camera (narrow-angle left, wide-angle right), each holding its last picture until the
next one arrives, as its window does, over a caption strip. Once a pane shows a mosaic it keeps it while that
observation goes on, so the pass builds without its other frames flashing in between tiles. Timing:
  fixed:    every new picture is one step at the chosen pictures per second
  adaptive: each picture stays for its gap to the next picture divided by one time compression C, held between
            HOLD_MIN and HOLD_MAX; C is chosen so the stretch's median gap lasts 1/8 s. Bursts flip fast, quiet
            spells linger, and longer gaps are cut (the caption says what was skipped)
The video is always FPS frames a second; holds are rounded to whole frames with the rounding carried forward.

Picture sizes 1536 and 2048 ("up to"): each mosaic and mosaic movie picture is drawn on the windows' own canvas
(obs_mosaic, CANVAS px) at the biggest of BUCKETS its pass has detail for (its native size, never more: a pass 1,400
px across stays at 1024), and the panes are the stretch's biggest such bucket; about the same work as 1024.

Picture size Full: the mosaics keep their own pixels. The panes are as big as the stretch's biggest mosaic pass at
native resolution (mosaic_native: one reference pixel a pixel, the save menu's "Full resolution mosaic"), at most
FULL_MAX px, and every mosaic and mosaic movie picture is drawn at that size from its tiles by the same layout,
seams and colour mix as the windows' (mosaic_native.movie_picture); the other pictures (a single frame is 1024 px
already) are made as at 1024 and enlarged to the pane. Pictures that big are not kept: the film is. It is extra work
made only when asked for (mosaic passes cost seconds a picture rather than a fraction of one), so it is meant for a
stretch already pre-processed (its tiles and plans made); its films are kept in the native mosaics' own cache
(mosaic_native.cache_dir, least recently used going first), not beside the 1024 px films.

Sound is made by the page, by the same synth as the live sound (sound.html, cassiniSound.render) from the plan's
picture list, and handed to the job as a WAV, which ffmpeg adds as AAC.

  CASSINI_DATA=... python web/frames/export.py 2006-09-15T14:32 2006-09-15T17:12 --cams W --out shadow.mp4
"""
import argparse
import calendar
import hashlib
from collections import Counter
import contextvars
import io
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reel  # noqa: E402  (puts the repo on the path)
import calibration  # noqa: E402
import studio_look  # noqa: E402

# bumped whenever the way films are made changes, so older ones are not served again
VERSION = "export-v28"   # v28: Complete color pictures only (a color set once, at its last channel) and one color mix a camera and target through the film (movie audit); v27: the batch-3 fixes (Titan color, saturated white, movie strobe, small bright bodies, line holes, pass kinds) reach exported pictures; v26: the small artifact, edge registration and two-filter color fixes (groups I, H2, F) reach exported pictures; v25: the restart's calibration and tone fixes (groups G, C) reach exported pictures; v24: Whole mosaics keep a mosaic movie's whole laps only, its drifting tiles one copy each (obs_mosaic.slots); v23: a mosaic pass is its mosaic at every frame, and stays a mosaic (or mosaic movie) in Full color only; v22: the flat fielded, dark subtracted, hot pixel repaired pictures; v21: Auto center centres the pictures shown on their own too, as the windows do
FPS = 30                     # frames a second in the file
HOLD_MIN, HOLD_MAX = 1 / FPS, 0.5
TYPICAL = 1 / 8              # adaptive: how long the stretch's median gap lasts on screen
LAST = 1.5                   # seconds the last picture stays
# pictures in a film at most, 0 for no limit (the default: a film is drawn a picture at a time, so a month of pictures
# is only a longer film); a public site sets CASSINI_EXPORT_MAX. The Movie Editor's list (list=1) has no cap either way
MAX_PICTURES = int(os.environ.get("CASSINI_EXPORT_MAX", "0") or 0)
SIZES = (512, 768, 1024)
FULL = "full"               # Picture size Full: mosaics at native resolution (module notes)
BUCKETS = (1024, 1536, 2048)   # mosaic sizes up to the canvas: a pass is drawn at the biggest its native size fills
FULL_MAX = int(os.environ.get("CASSINI_EXPORT_FULL_MAX", 4096))   # largest pane at Full, px (H.264 plays it)
FULL_WORKERS = 2            # pictures made at once at Full (each is a native mosaic, hundreds of MB while drawn)
CAPTION = 48                 # caption strip height at 1024 px panes (scaled with the pane)
SKIP_NOTE = 3 * 3600         # gaps longer than this are named in the caption
KIND = {"true": "true color", "false": "false color", "two": "two-filter color"}
FFMPEG = os.environ.get("CASSINI_FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def unix(iso):
    """Unix seconds of a UTC time like 2006-09-15T14:32 or 2006-09-15T14:32:00.5Z."""
    iso = iso.strip().rstrip("Z").replace(" ", "T").split(".")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return calendar.timegm(time.strptime(iso, fmt))
        except ValueError:
            continue
    raise ValueError(f"not a UTC time: {iso!r}")


def utc(t, seconds=True):
    return time.strftime("%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d-%H%M", time.gmtime(t))


PICTURES = ("movie", "color", "processed", "raw")
# the Movie Editor's exposure levels: a level point moves the film's exposure up to this many EV either way (the
# studio's exposure slider's range; with the look's own exposure the sum stays within it, studio_look.effective)
LEVEL_EV = 2.0
EVEN_MOST = 30               # pictures: the most Even out smooths over
LEVELS_SIDE = 160            # px: the pictures' brightness is measured on them this big (as movie mode's, obs_mosaic)
LEVELS_LIT = 0.04            # of the brightest: the pixels a brightness is measured on (the body, not the sky's noise)
LEVELS_VERSION = "levels-v4"   # v4: measured on the pictures of the batch-3 fixes; v3: measured on the pictures of the small artifact and color fixes; v2: measured on the pictures of the restart's calibration and tone fixes
# and its framing: a crop of every picture (or a start and an end crop the film glides between), and a nudge of a
# single frame (parts of the picture)
CROP_LEAST = 0.05            # of the picture: the smallest crop's side
NUDGE_MOST = 0.5
FRAME = {"crop": None, "crop2": None, "nudge": {}}
MOVIE = {"center": True, "trail": 0, "laps": 1, "fade": 0, "persist": 0}   # the movie style by default (a film named as before)


def options(q):
    """The export's options from a query (dict of lists, as parse_qs gives), checked, with defaults."""
    get = lambda k, d: (q.get(k) or [d])[0]
    t0, t1 = unix(get("from", "")), unix(get("until", ""))
    if t1 <= t0:
        raise ValueError("until must be after from")
    cams = "".join(c for c in "NW" if c in get("cams", "NW").upper()) or "NW"
    fps = get("fps", "auto")
    fps = "auto" if fps == "auto" else max(1, min(FPS, int(float(fps))))
    size = get("size", "1024")
    size = FULL if size == FULL else min(SIZES + BUCKETS[1:], key=lambda s: abs(s - int(size)))
    look, colors = get("look", calibration.LOOKS[0]), get("colors", calibration.COLORS[0])
    # how movie passes look, as the camera windows play them (Settings > Movie; the page's cassiniMovieStyle)
    movie = {"center": get("center", "1") != "0", "trail": max(0, min(12, int(get("trail", "0") or 0))),
             "laps": max(1, min(12, int(get("laps", "1") or 1)))}
    # a mosaic movie's fade (Rolling), only when on, so a film made without it keeps its name
    fade = max(0, min(120, int(get("fade", "0") or 0)))
    movie.update({"fade": fade, "persist": max(0, min(100, int(get("persist", "35") or 0))) if fade else 0})
    # Whole mosaics (Settings > Movie > Mosaic movie frames): a mosaic movie shows a picture only at the end of each
    # lap, every place new, and its older tiles do not fade; only when on, so a film made without it keeps its name
    if get("whole", "0") == "1":
        movie.update({"whole": True, "fade": 0, "persist": 0})
    # Complete mosaics only (Settings > Playback): a mosaic pass shows once, its whole mosaic at its last frame (in the
    # stretch); only when on, the same way
    if get("complete", "0") == "1":
        movie["complete"] = True
    # Complete color pictures only (Settings > Playback, movie.completeFrames, with color composites on): of a color
    # set, only the frame that completes it is a picture of the film, as movie mode steps (head-quiet.html complete());
    # sets=0 (the setting off) shows every channel on its own as well, and only then is it in the film's name
    if get("sets", "1") == "0":
        movie["sets"] = False
    # the Background (Settings > Processing, cameras.background) where a picture's frame does not reach (a centred
    # body the frame caught at its edge): black by default, and only another color is in the film's name
    bg = get("bg", "000000").lstrip("#").lower()
    if len(bg) == 6 and all(c in "0123456789abcdef" for c in bg) and bg != "000000":
        movie["bg"] = bg
    # the Movie Editor's Mosaics, over both settings: whole (every mosaic whole: a pass once, finished; a mosaic movie a
    # lap at a time) or tiles (every mosaic built tile by tile)
    if get("mos", "") == "whole":
        movie.update({"whole": True, "complete": True, "fade": 0, "persist": 0})
    elif get("mos", "") == "tiles":
        movie.pop("whole", None); movie.pop("complete", None)
    # image stabilization of movie passes (obs_mosaic.steady_places), smoothed over this many frames, only when on,
    # so a film made without it keeps its name
    steady = max(0, min(60, int(get("steady", "0") or 0)))
    if steady:
        movie["steady"] = steady
    # exposure normalization of movie passes (obs_mosaic.exposure_gains), the same way
    exposure = max(0, min(30, int(get("exposure", "0") or 0)))
    if exposure:
        movie["exposure"] = exposure
    off = ",".join(s for s in calibration.STEPS if s in get("off", "").split(","))   # Settings > Processing
    # the movie editor's cut (movieedit.html): frames taken out by hand, and only these targets and filter pairs kept
    words = lambda k: sorted({w.strip() for w in get(k, "").split(",") if w.strip()})
    kept = {"drop": words("drop"), "targets": sorted(w.upper() for w in words("targets")), "filters": words("filters")}
    # and its look on every picture: the color part of a Cassini Studio recipe
    look_edit = studio_look.parse(get("edit", ""))
    # its exposure levels: points (frame id: EV) the film's exposure goes through, straight lines between them, and
    # Even out over that many pictures (exposures)
    levels = {}
    for w in words("levels"):
        k, _, v = w.rpartition(":")
        try:
            levels[k] = round(max(-LEVEL_EV, min(LEVEL_EV, float(v))), 2)
        except ValueError:
            continue
    even = max(0, min(EVEN_MOST, int(float(get("even", "0") or 0))))
    # and single frames edited on their own (fedit=ID~ex:0.5,ct:0|ID~...): each such frame's look is the movie's with
    # these studio keys over it (studio_look.override); its level and framing still apply
    fedit = {}
    for w in get("fedit", "").split("|"):
        k, _, r = w.partition("~")
        r = studio_look.override(r)
        if k.strip() and r:
            fedit[k.strip()] = r
    # its framing: Auto center for the whole film (ctr, over the windows' setting), a crop of every picture (crop:
    # x0_y0_x1_y1, parts of the picture; crop2: the end crop the film glides to from crop), and a nudge (frame id: x, y,
    # parts of the picture) on single frames (framed)
    def box(k):
        try:
            x0, y0, x1, y1 = (max(0.0, min(1.0, round(float(v), 4))) for v in get(k, "").split("_"))
        except ValueError:
            return None
        if x1 - x0 < CROP_LEAST or y1 - y0 < CROP_LEAST or [x0, y0, x1, y1] == [0, 0, 1, 1]:
            return None
        return [x0, y0, x1, y1]
    crop, crop2 = box("crop"), box("crop2")
    if crop2 and not crop:
        crop = [0.0, 0.0, 1.0, 1.0]
    nudge = {}
    for w in words("nudge"):
        k, *xy = w.split(":")
        try:
            dx, dy = (round(max(-NUDGE_MOST, min(NUDGE_MOST, float(v))), 3) for v in xy)
        except ValueError:
            continue
        if dx or dy:
            nudge[k] = [dx, dy]
    if get("ctr", "") in ("0", "1"):
        movie["center"] = get("ctr", "") == "1"
    # which picture each frame shows (the Movie Editor's Pictures): as the camera windows show it (movie), only the
    # full color pictures (color: the frames completing a three-filter set, each its composite), every frame on its
    # own made by the pipeline (processed: stacked and calibrated, never composited) or every frame as Cassini took it
    # (raw: the archive frame, nothing stacked)
    pictures = get("pictures", "movie") if get("pictures", "movie") in PICTURES else "movie"
    return {"off": off, "cut": {k: v for k, v in kept.items() if v}, "edit": studio_look.encode(look_edit),
            "levels": levels, "even": even, "fedit": fedit, "frame": {"crop": crop, "crop2": crop2, "nudge": nudge},
            "pictures": pictures, "list": get("list", "0") == "1",
            "from": t0, "until": t1, "cams": cams, "fps": fps, "size": size,
            "sound": get("sound", "1") != "0", "caption": get("caption", "1") != "0",
            "look": look if look in calibration.LOOKS else calibration.LOOKS[0],
            "colors": colors if colors in calibration.COLORS else calibration.COLORS[0], "movie": movie}


def job_id(opt):
    """Films are named by what they show, so the same stretch and options give the same file and link."""
    key = {k: opt[k] for k in ("from", "until", "cams", "fps", "size", "sound", "caption")}
    if opt.get("look", "balanced") != "balanced":
        key["look"] = opt["look"]
    if opt.get("colors", "natural") != "natural":
        key["colors"] = opt["colors"]
    if opt.get("movie", MOVIE) != MOVIE:
        key["movie"] = opt["movie"]
    if opt.get("off"):
        key["off"] = opt["off"]
    if opt.get("cut"):
        key["cut"] = opt["cut"]
    if opt.get("edit"):
        key["edit"] = opt["edit"]
    if opt.get("levels"):
        key["levels"] = opt["levels"]
    if opt.get("even"):
        key["even"] = opt["even"]
    if opt.get("fedit"):
        key["fedit"] = opt["fedit"]
    if opt.get("frame", FRAME) != FRAME:
        key["frame"] = opt["frame"]
    if opt.get("pictures", "movie") != "movie":
        key["pictures"] = opt["pictures"]
    return hashlib.sha1(json.dumps([VERSION, key], sort_keys=True).encode()).hexdigest()[:16]


# ---------- the plan: which picture shows when ----------

def pass_kind(frame_id):
    """How the server plays frame_id's pass: "mosaic", "movie", "mosaic_movie" or None (obs_mosaic's call)."""
    import obs_mosaic
    try:
        found = obs_mosaic.unit_of(frame_id)
    except Exception:
        return None
    if not found:
        return None
    u = found[0]
    return u.get("kind") or ("movie" if u.get("movie") else "mosaic" if u.get("mosaic") else None)


def _lap_end(frame_id):
    """Whether frame_id finishes a lap of its mosaic movie (obs_mosaic.lap_end); True when that cannot be told."""
    import obs_mosaic
    try:
        return obs_mosaic.lap_end(frame_id) is not False
    except Exception:
        return True


def _pass_of(frame_id):
    """The mosaic pass frame_id is in (obs_mosaic's unit key, as text), or None."""
    import obs_mosaic
    try:
        found = obs_mosaic.unit_of(frame_id)
    except Exception:
        return None
    return "|".join(map(str, found[0]["key"])) if found else None


def complete_mosaics(pics):
    """Complete mosaics only: of each mosaic pass, only its last picture in the stretch, showing the pass's whole
    mosaic (its last frame's /frames/mosaic picture: every tile and filter), as a camera window shows a pass with
    Settings > Playback > Complete mosaics only. The film's timing then holds the picture before the pass over it."""
    last = {}
    for i, e in enumerate(pics):
        if e.get("pass"):
            last[(e["cam"], e["pass"])] = i
    out = []
    for i, e in enumerate(pics):
        if e.get("pass"):
            if last[(e["cam"], e["pass"])] != i:
                continue
            e["try"] = [("mosaic", e["id"])] + [x for x in e["try"] if x[0] != "mosaic"]
        out.append(e)
    return out


def plan(opt, cache=None, work=False):
    """The film's pictures in time order, each {id, cam, t, target, filters, try, kind, at (film seconds), hold,
    frames, nm, set_nm?, tile?, skipped?}, and the film's length. try = the pictures to make, best first. At Picture
    size Full (cache given) also the panes' size, opt["pane"], and what sets it (full_size; work: passes whose plan
    is not worked out yet are worked out now, else left out and counted)."""
    idx, sets = reel.load_index()
    t = idx["seconds_1970"].to_numpy()
    lo, hi = np.searchsorted(t, opt["from"], "left"), np.searchsorted(t, opt["until"], "right")
    ids, insts, targets, obs = idx["id"].tolist(), idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist()
    f1s, f2s, set_of = idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(), idx["set"].to_numpy()
    cam_of = lambda q: "N" if insts[q] == "ISSNA" else "W"
    last = {}   # each camera's frame before, as movie mode looks it up (up to 64 frames back)
    for q in range(lo - 1, max(-1, lo - 65), -1):
        last.setdefault(cam_of(q), q)
    # One color mix for each camera and target through the film: its most common set of three filters in the stretch.
    # The one rule (sets_passes.channels) gives a set its widest spread of filters, so a run of four (Saturn's stare
    # of 2005-07-03: MT2, CB2, MT3 and BL1 at one pointing in five) mixes MT3/MT2/BL1 where the others mix
    # MT3/CB2/MT2, and its composite came up in other colors between them (the film flickered, 2026-10-30). A set
    # that has the film's mix among its frames is made of those (the newest of each filter), in the mix's order.
    def mix_of(st):
        return tuple(st["filters"][st["rows"].index(u)] for u in st["use"])
    seen = {}
    for s in {int(v) for v in set_of[lo:hi] if v >= 0}:
        if len(sets[s]["use"]) >= 3:
            k = (cam_of(sets[s]["use"][0]), targets[sets[s]["use"][0]])
            seen.setdefault(k, Counter())[mix_of(sets[s])] += 1
    film_mix = {k: c.most_common(1)[0][0] for k, c in seen.items()}

    def mix(st):
        want = film_mix.get((cam_of(st["use"][0]), targets[st["use"][0]]))
        if not want or len(st["use"]) < 3 or mix_of(st) == want:
            return st["use"]
        newest = {f: r for f, r in sorted(zip(st["filters"], st["rows"]), key=lambda fr: t[fr[1]])}
        return [newest[f] for f in want] if all(f in newest for f in want) else st["use"]
    out = []
    for q in range(lo, hi):
        cam = cam_of(q)
        prev, last[cam] = last.get(cam), q
        if cam not in opt["cams"]:
            continue
        s = int(set_of[q])
        st = sets[s] if s >= 0 else None
        # the frame that completes its set: the set's last channel (the composite exists once it is taken)
        comp = st is not None and q in st["use"] and q == max(st["use"], key=lambda u: t[u])
        tile = prev is not None and targets[prev] == targets[q] and obs[prev] == obs[q] and (st is None or comp)
        tries = []
        # a pass the server calls a movie plays as steady movie frames, a mosaic movie as its rolling mosaic, as
        # the camera windows play them on Auto (obs_mosaic.movie_webp, rolling_webp)
        # (Full color only keeps a mosaic pass and a mosaic movie mosaics, in color; its movie passes are color
        # pictures)
        how = opt.get("pictures", "movie")
        kind = pass_kind(ids[q]) if how in ("movie", "color") else None
        if how == "color" and kind == "movie":
            kind = None
        # Complete color pictures only: a channel of a color set on the way to its last one is not a picture of its
        # own, outside a mosaic (movie mode's complete(): the black-and-white channels between the composites made a
        # film flicker from grey to color, and a color movie pass held each set for three or four frames)
        if how == "movie" and st is not None and opt["movie"].get("sets", True) and kind not in ("mosaic", "mosaic_movie") \
                and t[q] != st["ready"]:
            continue
        if kind == "movie":
            tries.append(("movie", ids[q]))
        elif kind == "mosaic_movie":
            # Whole mosaics: the frames inside a lap are left out, the lap's last frame shows the whole new mosaic
            if opt["movie"].get("whole") and not _lap_end(ids[q]):
                continue
            tries.append(("rolling", ids[q]))
        elif kind == "mosaic":
            # every frame of a mosaic pass shows the pass's mosaic so far, as the camera windows play it
            tries.append(("mosaic", ids[q]))
        elif tile:
            tries.append(("mosaic", ids[st["use"][0]] if comp else ids[q]))
        if comp:
            tries.append(("color", [ids[u] for u in mix(st)]))
        tries += [("processed", ids[q]), ("frame", ids[q])]
        if how == "color":
            # a mosaic pass stays its mosaic and a mosaic movie its rolling mosaic (in color, every tile and filter
            # so far), as in the movie, not each pointing's own color picture on its own: at each finished color set,
            # or with Whole mosaics at each lap's end (only those got here)
            full = comp and len(st["use"]) >= 3
            lap = kind == "mosaic_movie" and opt["movie"].get("whole") and st is not None
            if not full and not lap:
                continue
            lead = [tries[0]] if kind in ("mosaic", "mosaic_movie") and tries[0][0] in ("mosaic", "rolling") else []
            tries = lead + ([("color", [ids[u] for u in mix(st)])] if full else []) + [("processed", ids[q]), ("frame", ids[q])]
        elif how == "processed":
            tries = [("processed", ids[q]), ("frame", ids[q])]
        elif how == "raw":
            tries = [("frame", ids[q])]
        e = {"id": ids[q], "cam": cam, "t": float(t[q]), "target": targets[q] if isinstance(targets[q], str) else "",
             "filters": f"{f1s[q]}/{f2s[q]}", "obs": obs[q] if isinstance(obs[q], str) else "", "try": tries,
             "nm": reel.wavelength(insts[q], f1s[q] + f2s[q])}
        if comp:
            e["set"] = st["kind"]
            e["set_nm"] = [reel.wavelength(insts[u], f1s[u] + f2s[u]) for u in mix(st)]
        if kind == "mosaic":
            e["pass"] = _pass_of(ids[q])
        out.append(e)
    if opt["movie"].get("complete"):
        out = complete_mosaics(out)
    out = cut(out, opt)
    if MAX_PICTURES and len(out) > MAX_PICTURES and not opt.get("list"):
        raise OverflowError(f"{len(out):,} pictures: an export holds at most {MAX_PICTURES:,}; pick a shorter stretch")
    timing(out, opt["fps"])
    full = full_size(opt, out, cache, work) if big(opt) else None
    return dict({"pictures": out, "count": len(out), "seconds": round(sum(e["frames"] for e in out) / FPS, 2),
                 "frames": sum(e["frames"] for e in out), "width": width(opt), "height": height(opt)},
                **({"full": full} if full else {}))


NATIVE_KINDS = ("mosaic", "rolling")   # the tries drawn at native resolution at Full (Pictures.picture)


def big(opt):
    """Whether the film's mosaics are drawn bigger than 1024: Full, or an "up to" size (1536, 2048)."""
    return opt["size"] == FULL or opt["size"] > max(SIZES)


def bucket(native, cap):
    """The size a pass native px across is drawn at for an "up to cap" film: the biggest of BUCKETS it fills."""
    return max([b for b in BUCKETS if b <= max(native, BUCKETS[0]) and b <= cap] or [BUCKETS[0]])


def full_size(opt, pics, cache, work=False):
    """Picture size Full or up to 1536 / 2048: the panes' side (opt["pane"]) and what it is made of: {pane, native
    (the biggest pass's own side, px), passes [{obs, cam, side, drawn}], mosaic_pictures (pictures drawn bigger than
    1024 can hold), pending (passes whose size is not known yet: not pre-processed, work False)}. At Full the pane
    is the biggest pass at native resolution (at least 1024, at most FULL_MAX, even for the video's colour planes);
    up to a size, it is the biggest pass's bucket, each pass drawn at its own (bucket)."""
    import mosaic_native
    passes, seen, pending, count = [], set(), 0, 0
    for e in pics:
        first = e["try"][0]
        if first[0] not in NATIVE_KINDS:
            continue
        count += 1
        if (e["cam"], e["obs"]) in seen:
            continue
        seen.add((e["cam"], e["obs"]))
        try:
            side = mosaic_native.native_side(first[1], cache, work) if cache else None
        except Exception as err:   # a pass the pipeline cannot plan: drawn as at 1024
            print(f"export: native size of {first[1]}: {type(err).__name__}: {err}", flush=True)
            side = None
        if side is None:
            pending += 1
            continue
        drawn = min(FULL_MAX, max(1024, side)) if opt["size"] == FULL else bucket(side, opt["size"])
        passes.append({"obs": e["obs"], "cam": e["cam"], "side": side, "drawn": drawn})
    native = max([p["side"] for p in passes] or [1024])
    opt["pane"] = 2 * (max([p["drawn"] for p in passes] or [1024]) // 2)
    return {"pane": opt["pane"], "native": native, "passes": passes, "mosaic_pictures": count, "pending": pending}


def pane(opt):
    """A camera's pane in the film, px: the size asked for, or the one full_size worked out (Full, up to a size)."""
    return opt.get("pane", 1024) if big(opt) else opt["size"]


def cut(pics, opt):
    """The plan's pictures the movie editor keeps: not dropped by hand, of a kept target and filter pair. Taking a
    frame out never changes how the others are made (a mosaic still has every tile, a composite every channel); its
    picture is only not shown, and the film's timing closes over the gap."""
    c = opt.get("cut") or {}
    drop, targets, filters = set(c.get("drop", ())), set(c.get("targets", ())), set(c.get("filters", ()))
    if not (drop or targets or filters):
        return pics
    return [e for e in pics if e["id"] not in drop and (not targets or (e["target"] or "UNKNOWN") in targets)
            and (not filters or e["filters"] in filters)]


def timing(pics, fps):
    """Each picture's hold, start in the film and whole frames, by the fixed or adaptive rule."""
    gaps = [b["t"] - a["t"] for a, b in zip(pics, pics[1:])]
    if fps == "auto":
        c = max(1e-3, float(np.median([g for g in gaps if g > 0] or [1]))) / TYPICAL
        holds = [min(HOLD_MAX, max(HOLD_MIN, g / c)) for g in gaps]
        for e, g, h in zip(pics, gaps, holds):
            if g > SKIP_NOTE and g / c > HOLD_MAX:
                e["skipped"] = g
    else:
        holds = [1 / fps] * len(gaps)
    holds.append(LAST)
    at = carry = 0.0
    for e, h in zip(pics, holds):
        n = max(1, round(h * FPS + carry))
        carry += h * FPS - n
        e["at"], e["hold"], e["frames"] = round(at, 4), round(h, 4), n
        at += n / FPS


# ---------- the Movie Editor's exposure levels and framing ----------

def evener():
    """Movie mode's exposure normalization math (obs_mosaic.evened_gains: log brightnesses of pictures in order in,
    each one's gain out, flashes taken out and steps spread), which Even out uses as it is; None on a server
    without it."""
    import obs_mosaic
    return getattr(obs_mosaic, "evened_gains", None)


def brightness(im):
    """How bright a finished picture is (RGB, black where it has nothing): the natural log of the median gray (0..1,
    the picture's display values) of its lit pixels, as movie mode measures a movie frame's, or None when too few
    are lit. An exposure change of x EV (studio_look) moves it by x ln 2."""
    k = LEVELS_SIDE / max(im.size)
    if k < 1:
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.BILINEAR)
    v = np.asarray(im.convert("L"), np.float32).ravel() / 255
    v = v[v > 1 / 255]
    if v.size < 64:
        return None
    lit = v[v > LEVELS_LIT * max(float(np.percentile(v, 99.5)), 1e-6)]
    return float(np.log(np.median(lit))) if lit.size >= 64 else None


_measuring, _measured = {}, {}   # levels key -> the measuring under way ({done, total, logs}), the last few measured


def levels_key(opt):
    """What a stretch's measured brightnesses depend on: its pictures and how they are drawn, not the cut, look,
    levels or framing (one measuring serves every edit of the stretch)."""
    key = {k: opt.get(k) for k in ("from", "until", "pictures", "look", "colors", "off", "movie")}
    return hashlib.sha1(json.dumps([LEVELS_VERSION, key], sort_keys=True).encode()).hexdigest()[:16]


def measure(opt, cache, pictures, wait=False):
    """The brightness (brightness) of the picture every frame of opt's stretch shows, both cameras, nothing cut:
    {done, total, logs: {frame id: log or None}} so far. Measured once on a thread of its own on the pictures the
    film draws (the frame server's makers and cache, at 512 px), kept in the cache. wait: until every one is."""
    key = levels_key(opt)
    path = os.path.join(cache, LEVELS_VERSION, key + ".json")
    with _lock:
        got = _measured.get(key) or _measuring.get(key)
        if got is None and os.path.exists(path):
            try:
                with open(path) as fh:
                    logs = json.load(fh)
                got = _measured[key] = {"done": len(logs), "total": len(logs), "logs": logs}
            except (OSError, ValueError):
                got = None
        if got is None:
            got = _measuring[key] = {"done": 0, "total": None, "logs": {}}
            got["thread"] = threading.Thread(target=contextvars.copy_context().run, args=(_measure, opt, key, path, pictures, got), daemon=True)
            got["thread"].start()
    if wait and got.get("thread"):
        got["thread"].join()
    return {k: (dict(v) if k == "logs" else v) for k, v in got.items() if k != "thread"}


def _measure(opt, key, path, pictures, got):
    try:
        with calibration.looking(opt.get("look", "balanced")), calibration.coloring(opt.get("colors", "natural")), \
                calibration.stepping(opt.get("off", "")):
            pictures = Pictures(pictures.cache, pictures._color, pictures._processed, pictures._frame, pictures.slots)
            pictures.movie = {**MOVIE, **opt.get("movie", {})}
            pics = plan(dict(opt, cams="NW", cut={}, list=True))["pictures"]
            got["total"] = len(pics)

            def one(e):
                im, _ = pictures.picture(e, 512)
                return e["id"], brightness(im) if im is not None else None
            with ThreadPoolExecutor(3) as pool:
                for fid, lv in pool.map(lambda e: contextvars.copy_context().run(one, e), pics):
                    got["logs"][fid] = None if lv is None else round(lv, 5)
                    got["done"] += 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".part", "w") as fh:
            json.dump(got["logs"], fh)
        os.replace(path + ".part", path)
    except Exception as e:
        got["error"] = f"{type(e).__name__}: {e}"
        print(f"export levels {key}: {got['error']}", flush=True)
    with _lock:
        _measuring.pop(key, None)
        if "error" not in got:
            _measured[key] = {k: v for k, v in got.items() if k != "thread"}
            while len(_measured) > 8:
                _measured.pop(next(iter(_measured)))


def stretches(pics):
    """The film's pictures (indexes) Even out evens on their own, as movie mode evens a pass (exposure_gains): one
    camera's pictures in a row of one kind (mosaic, movie pass, color, processed or raw frame), in color or gray, of
    one target. A change of any of those is the picture changing, not its exposure."""
    out, last = [], {}
    for i, e in enumerate(pics):
        k = (e.get("first") or (e["try"][0][0] if e.get("try") else "frame"),
             bool(e.get("set")) or (e.get("first") or (e["try"][0][0] if e.get("try") else "")) == "color", e.get("target"))
        run = last.get(e["cam"])
        if run is None or run[0] != k:
            run = last[e["cam"]] = (k, [])
            out.append(run[1])
        run[1].append(i)
    return out


def exposures(opt, pics, logs=None):
    """Each of the film's pictures' (pics, in order) exposure change in EV, and its two parts: the levels' line
    (straight between its points, flat before the first and after the last) and Even out's (obs_mosaic.evened_gains
    over each stretch of the pictures' brightnesses logs; a stretch shorter than a flash, or a picture with too
    little lit, keeps its own). (total, line, even)."""
    n = len(pics)
    pts = [(i, opt["levels"][e["id"]]) for i, e in enumerate(pics) if e["id"] in (opt.get("levels") or {})]
    line = np.interp(np.arange(n), [i for i, _ in pts], [v for _, v in pts]) if pts else np.zeros(n)
    even = np.zeros(n)
    fn = evener() if opt.get("even") and logs else None
    if fn:
        import obs_mosaic
        flash = getattr(obs_mosaic, "EXPOSURE_FLASH", 3)
        for run in stretches(pics):
            run = [i for i in run if logs.get(pics[i]["id"]) is not None]
            if len(run) >= flash:
                for i, g in zip(run, fn([logs[pics[i]["id"]] for i in run], opt["even"])):
                    even[i] = math.log2(g)
    total = np.clip(line + even, -2 * LEVEL_EV, 2 * LEVEL_EV)
    return [round(float(v), 4) for v in total], [round(float(v), 4) for v in line], [round(float(v), 4) for v in even]


def levels(opt, cache, pictures):
    """The Movie Editor's exposure graph (/export/levels.json): each frame's brightness in EV (log2, None when it
    has too little lit), measured so far, and for the film the edit makes (its cameras and cut) each picture's Even
    out change in EV, once every picture is measured."""
    m = measure(opt, cache, pictures)
    done = m["total"] is not None and m["done"] >= m["total"]
    out = {"done": m["done"], "total": m["total"], "even_ready": evener() is not None, "error": m.get("error"),
           "level": {k: None if v is None else round(v / math.log(2), 4) for k, v in m["logs"].items()}}
    if done and opt.get("even") and evener():
        pics = plan(dict(opt, list=True))["pictures"]
        for e in pics:
            e["first"] = e["try"][0][0]
        out["even"] = {e["id"]: v for e, v in zip(pics, exposures(opt, pics, m["logs"])[2]) if v}
    return out


def crop_at(fr, n, count):
    """The crop of the film's picture n of count (x0, y0, x1, y1, parts of the picture), or None: the film's crop, or
    with an end crop the way from the start crop to it, eased in and out over the film (movieedit.html cropAt)."""
    a, b = fr.get("crop"), fr.get("crop2")
    if not b or count < 2:
        return a
    t = n / (count - 1)
    t = t * t * (3 - 2 * t)
    return [u + (v - u) * t for u, v in zip(a, b)]


def framed(im, crop, nudge):
    """Picture im moved by nudge (x, y, parts of the picture) and cut to crop (x0, y0, x1, y1, parts of the picture;
    None the whole), drawn as big as the picture was on its longer side, black where it has nothing: the Movie Editor's
    framing (movieedit.html framedOf draws it the same way)."""
    dx, dy = nudge
    if not crop and not dx and not dy:
        return im
    x0, y0, x1, y1 = crop or (0, 0, 1, 1)
    W, H = im.size
    cw, ch = (x1 - x0) * W, (y1 - y0) * H
    k = max(W, H) / max(cw, ch)
    # a film pixel at (x, y) shows the picture's (x / k + x0 - d)
    return im.transform((max(1, round(cw * k)), max(1, round(ch * k))), Image.AFFINE,
                        (1 / k, 0, (x0 - dx) * W, 0, 1 / k, (y0 - dy) * H), Image.BICUBIC, fillcolor=(0, 0, 0))


def width(opt):
    return pane(opt) * len(opt["cams"])


def caption_h(opt):
    return 2 * round(CAPTION * pane(opt) / 1024 / 2) if opt["caption"] else 0


def height(opt):
    return pane(opt) + caption_h(opt)


# ---------- pictures ----------

class Pictures:
    """How the film gets each picture: the frame server's own makers (so its cache is shared), or the pipeline
    called here. Each make(...) returns WebP or PNG bytes, or None when it has no such picture."""

    def __init__(self, cache, color=None, processed=None, frame=None, slots=None):
        self.cache, self.slots, self.movie = cache, slots, dict(MOVIE)
        self._color, self._processed, self._frame = color, processed, frame

    def make(self, kind, arg, size):
        import obs_mosaic
        if kind == "mosaic":
            made = obs_mosaic.mosaic_webp(arg, size, self.cache, self.slots, ahead=0)
            if made:
                return made[0], "mosaic"
            found = reel.mosaic_of(arg, wait=True)
            return (reel.shot_webp(*found, size, self.cache, True, self.slots)[0], "mosaic") if found else None
        if kind == "movie":
            made = obs_mosaic.movie_webp(arg, size, self.cache, self.movie["trail"], wait=True, ahead=0,
                                         centre=self.movie["center"], steady=self.movie.get("steady", 0),
                                         exposure=self.movie.get("exposure", 0))
            return (made[0], "movie") if made and made[0] else None
        if kind == "rolling":
            made = obs_mosaic.rolling_webp(arg, size, self.cache, self.movie["laps"], slots=self.slots, wait=True,
                                           fade=(self.movie.get("fade", 0), self.movie.get("persist", 0)))
            return (made[0], "mosaic movie") if made and made[0] else None
        if kind == "color":
            if self._color:
                return self._centred(self._color, arg, arg[-1], size), "colour"
            return self._pipeline(arg), "colour"
        if kind == "processed":
            if self._processed:
                return self._centred(self._processed, arg, arg, size), "processed"
            return self._pipeline([arg]), "processed"
        if self._frame:
            return self._frame(arg, size, self.cache), "frame"
        return reel.data_source.read_bytes(f"{reel.FOLDERS[arg[0]]}/{arg}.png"), "frame"

    def _centred(self, maker, arg, frame_id, size):
        """A picture shown on its own (a color composite or a processed frame) made by the frame server's maker, with
        Auto center as the camera windows draw it when the film's movie style has it on (obs_mosaic.centre_view, the
        server's center=1): centred on the body or turned north up, else as it is."""
        if self.movie.get("center"):
            import obs_mosaic
            try:
                view = obs_mosaic.centre_view(frame_id)
            except Exception:
                view = {}
            if view.get("centre") or view.get("north"):
                try:
                    return maker(arg, size, self.cache, centre=view)[0]
                except LookupError:   # SPICE cannot place the frame: as it is, as in the window
                    pass
        return maker(arg, size, self.cache)[0]

    @staticmethod
    def _pipeline(ids):
        """The frames ids made by the pipeline's colour path (color_image.load_aligned), as the frame server's
        composite route makes them: one id the frame alone, two a two-filter picture, three R,G,B."""
        import color_image
        imgs, valid, _, _ = color_image.load_aligned([f"{reel.FOLDERS[i[0]]}/{i}.png" for i in ids])
        chans = [img[..., 0] if img.ndim == 3 else img for img in imgs]
        if len(chans) == 2:
            chans = [chans[0], ((chans[0].astype(np.uint16) + chans[1]) // 2).astype(np.uint8), chans[1]]
        alpha = np.where(valid, 255, 0).astype(np.uint8)
        rgba = np.dstack([chans[0]] * 3 + [alpha] if len(chans) == 1 else chans + [alpha])
        out = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(out, "PNG", compress_level=1)
        return out.getvalue()

    def native(self, kind, arg, size):
        """Picture size Full: the mosaic (kind "mosaic") or mosaic movie picture ("rolling") of arg at native
        resolution, size px at most, as an RGBA image (mosaic_native.movie_picture), or None."""
        import mosaic_native
        im = mosaic_native.movie_picture(arg, self.cache, size, rolling=kind == "rolling", laps=self.movie["laps"],
                                         fade=(self.movie.get("fade", 0), self.movie.get("persist", 0)), slots=self.slots)
        return (im, "mosaic movie" if kind == "rolling" else "mosaic") if im is not None else None

    def canvas(self, kind, arg, cap):
        """Up to a size: the mosaic or mosaic movie picture of arg on the windows' canvas, at the bucket its pass has
        detail for (at most cap), WebP bytes, as the full view's route makes it (size "full", out px)."""
        import mosaic_native
        import obs_mosaic
        out = bucket(mosaic_native.native_side(arg, self.cache) or BUCKETS[0], cap)
        if kind == "mosaic":
            made = obs_mosaic.mosaic_webp(arg, "full", self.cache, self.slots, ahead=0, out=out)
            return (made[0], "mosaic") if made and made[0] else None
        made = obs_mosaic.rolling_webp(arg, "full", self.cache, self.movie["laps"], slots=self.slots, wait=True, out=out,
                                       fade=(self.movie.get("fade", 0), self.movie.get("persist", 0)))
        return (made[0], "mosaic movie") if made and made[0] else None

    def picture(self, e, size, full=False, cap=None):
        """The picture for plan entry e as RGB over black, size px on its longest side, and what it is. full: a
        mosaic is drawn at native resolution (native); cap: up to that size, at its pass's bucket (canvas); any
        other picture made at 1024 and enlarged."""
        for kind, arg in e["try"]:
            try:
                if (full or cap) and kind in NATIVE_KINDS:
                    made = self.native(kind, arg, size) if full else self.canvas(kind, arg, cap)
                    if made:
                        return self._on_black(made[0] if full else Image.open(io.BytesIO(made[0])), size), made[1]
                    continue
                made = self.make(kind, arg, min(size, max(SIZES)))
            except FileNotFoundError:
                continue
            except Exception as err:   # a picture the pipeline cannot make: the next try stands in
                print(f"export: {kind} {arg}: {type(err).__name__}: {err}", flush=True)
                continue
            if not made or not made[0]:
                continue
            return self._on_black(Image.open(io.BytesIO(made[0])), size), made[1]
        return None, ""

    def _on_black(self, im, size):
        """im (any mode) size px on its longest side, as RGB over black (or the film's Background, bg)."""
        im = im.convert("RGBA")
        if max(im.size) != size:
            s = size / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        black = Image.new("RGB", im.size, background(self.movie))
        black.paste(im, mask=im.getchannel("A"))
        return black


# ---------- drawing and encoding ----------

def _font(px):
    for path in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    try:
        return ImageFont.load_default(px)
    except TypeError:
        return ImageFont.load_default()


def label(e, what):
    """The caption under a pane: when, what, which camera and filters, and how the picture was made."""
    kind = KIND.get(e.get("set"), "color") if what == "colour" else what if what in ("mosaic", "movie", "mosaic movie") else ""
    target = (e["target"] or "Unknown").replace("_", " ").title()
    return " · ".join(x for x in (f"{utc(e['t'])} UTC", target, f"{'NAC' if e['cam'] == 'N' else 'WAC'} {e['filters']}", kind) if x)


def background(movie):
    """The film's Background (options' bg) as an RGB tuple: black unless asked."""
    bg = (movie or {}).get("bg", "000000")
    return tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))


class Film:
    """Draws the panes and caption and pipes whole frames to ffmpeg."""

    def __init__(self, opt, path):
        self.opt, self.size = opt, pane(opt)
        self.w, self.h, self.ch = width(opt), height(opt), caption_h(opt)
        self.canvas = Image.new("RGB", (self.w, self.h))
        self.font = _font(max(10, round(self.ch * 0.36))) if self.ch else None
        self.small = _font(max(9, round(self.ch * 0.3))) if self.ch else None
        self.captions = {c: "" for c in opt["cams"]}
        self.proc = subprocess.Popen(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.w}x{self.h}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", path], stdin=subprocess.PIPE)

    def put(self, e, im, what):
        """Picture im of entry e goes up in its camera's pane (which keeps it until the next)."""
        x0 = self.opt["cams"].index(e["cam"]) * self.size
        pane = Image.new("RGB", (self.size, self.size), background(self.opt["movie"]))
        if im is not None:
            pane.paste(im, ((self.size - im.width) // 2, (self.size - im.height) // 2))
        self.canvas.paste(pane, (x0, 0))
        self.captions[e["cam"]] = label(e, what)
        if self.ch:
            d = ImageDraw.Draw(self.canvas)
            d.rectangle((x0, self.size, x0 + self.size - 1, self.h), fill=(8, 10, 14))
            d.text((x0 + self.ch * 0.35, self.size + self.ch / 2), self.captions[e["cam"]], font=self.font,
                   fill=(222, 228, 236), anchor="lm")
            if e.get("skipped"):
                d.text((x0 + self.size - self.ch * 0.35, self.size + self.ch / 2), f"skipped {dur(e['skipped'])}",
                       font=self.small, fill=(138, 182, 255), anchor="rm")

    def hold(self, frames):
        data = self.canvas.tobytes()
        for _ in range(frames):
            self.proc.stdin.write(data)

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait():
            raise RuntimeError(f"ffmpeg failed ({self.proc.returncode})")


def dur(s):
    return f"{s / 86400:.0f} d" if s >= 2 * 86400 else f"{s / 3600:.0f} h" if s >= 3600 else f"{s / 60:.0f} min"


def render(opt, p, pictures, path, progress=lambda done, total: None, workers=3):
    """Makes the film of plan p at path: pictures made a few ahead on worker threads, drawn and encoded in order."""
    film = Film(opt, path)
    pictures.movie = {**MOVIE, **opt.get("movie", {})}   # movie passes as the windows showed them
    full = opt["size"] == FULL
    if full:
        workers = min(workers, FULL_WORKERS)
    pics, ahead = p["pictures"], max(2, workers * (2 if full else 3))
    look = studio_look.parse(opt.get("edit", ""))
    # the Movie Editor's exposure levels (Even out measures the stretch's pictures first) and framing
    logs = measure(opt, pictures.cache, pictures, wait=True)["logs"] if opt.get("even") and evener() else None
    evs = exposures(opt, pics, logs)[0]
    fr = opt.get("frame") or FRAME
    # a frame edited on its own: the movie's look with its own keys over it
    own = {k: studio_look.parse(f"{opt.get('edit', '')},{r}") for k, r in (opt.get("fedit") or {}).items()}
    kinds, building = Counter(), {}
    try:
        with ThreadPoolExecutor(workers) as pool:
            todo = deque()
            nxt = 0
            for n, e in enumerate(pics):
                while nxt < len(pics) and nxt < n + ahead:
                    # in the film's look (the pool's threads don't share the caller's)
                    todo.append(pool.submit(contextvars.copy_context().run, pictures.picture, pics[nxt], film.size, full,
                                            opt["size"] if big(opt) and not full else None))
                    nxt += 1
                im, what = todo.popleft().result()
                kinds[what or "none"] += 1
                if im is not None:
                    im = framed(im, crop_at(fr, n, len(pics)), fr["nudge"].get(e["id"], (0, 0)))
                its = own[e["id"]] if e["id"] in own else look
                if im is not None and (its or evs[n]):
                    # the movie editor's look (or the frame's own), as Cassini Studio draws it, at this picture's
                    # exposure level
                    im = studio_look.apply(im, its, evs[n])
                # a mosaic stays up while its observation goes on: the pass's other frames (another filter, a frame
                # that is not a tile) would otherwise flash in and out between its tiles
                if what in ("mosaic", "mosaic movie"):
                    building[e["cam"]] = e["obs"]
                elif building.get(e["cam"]) == e["obs"] and e["obs"]:
                    kinds["held behind mosaic"] += 1
                    film.hold(e["frames"])
                    progress(n + 1, len(pics))
                    continue
                else:
                    building.pop(e["cam"], None)
                film.put(e, im, what)
                film.hold(e["frames"])
                progress(n + 1, len(pics))
    finally:
        film.close()
    return dict(kinds)


def mux(video, wav, out):
    """The film with the soundtrack added as AAC (cut to the film's length)."""
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)


# ---------- jobs: one film made at a time, the rest wait their turn ----------

_jobs = {}
_lock = threading.Lock()
_queue = queue.Queue()
_worker = None
SOUND_WAIT = 90   # seconds a finished video waits for its soundtrack before it is kept silent
SOUND_MOST = 30 * 60   # seconds of film the page makes a soundtrack for (export.html SOUND_MOST): a longer one is silent, not waited for


def folder(cache, jid, full=None):
    """Where job jid's film is kept: beside the frame server's cache, or (full: a Picture size Full film, hundreds
    of MB) in the native mosaics' cache, which keeps its size in check (mosaic_native.trim). full None: wherever it
    is (the Full one when neither is there yet)."""
    import mosaic_native
    big = os.path.join(mosaic_native.cache_dir(cache), VERSION, jid)
    if full is None:
        return os.path.join(cache, VERSION, jid) if os.path.isdir(os.path.join(cache, VERSION, jid)) else big
    return big if full else os.path.join(cache, VERSION, jid)


def name(opt, p):
    """The file name a download gets: cassini-2006-09-15-1432-saturn.mp4."""
    main = Counter(e["target"] for e in p["pictures"] if e["target"]).most_common(1)
    full = f"-full{pane(opt)}" if opt["size"] == FULL else f"-{pane(opt)}" if big(opt) else ""
    return f"cassini-{utc(opt['from'], False)}-{(main[0][0] if main else 'mission').lower().replace('_', '-')}{full}.mp4"


def _save(job):
    os.makedirs(job["dir"], exist_ok=True)
    keep = {k: v for k, v in job.items() if k not in ("plan", "dir")}
    tmp = os.path.join(job["dir"], f"job.json.{threading.get_ident()}.part")
    with open(tmp, "w") as fh:
        json.dump(keep, fh)
    os.replace(tmp, os.path.join(job["dir"], "job.json"))


def status(cache, jid):
    """What the job is doing: {state queued|making|encoding|sound|done|failed, done, total, eta, ...}, or None."""
    with _lock:
        job = _jobs.get(jid)
        if job:
            return {k: v for k, v in job.items() if k not in ("plan", "dir")}
    d = folder(cache, jid)
    try:
        with open(os.path.join(d, "job.json")) as fh:
            job = json.load(fh)
    except (OSError, ValueError):
        return None
    # a Full film the native mosaics' cache let go of (mosaic_native.trim) is made again when asked for
    return None if job.get("state") == "done" and not os.path.exists(os.path.join(d, "film.mp4")) else job


def submit(opt, cache, pictures):
    """Starts the film (or finds it made or on its way) and says where it stands."""
    global _worker
    jid = job_id(opt)
    found = status(cache, jid)
    if found and found.get("state") != "failed":
        return found
    p = plan(opt, cache, work=True)
    if not p["count"]:
        raise LookupError("no pictures in that stretch")
    job = {"id": jid, "state": "queued", "done": 0, "total": p["count"], "seconds": p["seconds"], "options": opt,
           "name": name(opt, p), "width": p["width"], "height": p["height"], "created": time.time(),
           "plan": p, "dir": folder(cache, jid, opt["size"] == FULL)}
    with _lock:
        _jobs[jid] = job
        _save(job)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, args=(pictures,), daemon=True)
            _worker.start()
    _queue.put(jid)
    return status(cache, jid)


def sound(cache, jid, wav):
    """The page's soundtrack for the job (WAV bytes). Added once the video is made, or now if it already is."""
    d = folder(cache, jid)
    if not os.path.isdir(d):
        raise LookupError("no such export")
    tmp = os.path.join(d, "sound.wav.part")
    with open(tmp, "wb") as fh:
        fh.write(wav)
    os.replace(tmp, os.path.join(d, "sound.wav"))
    job = status(cache, jid)
    if job and job.get("state") == "done" and not job.get("audio") and os.path.exists(os.path.join(d, "video.mp4")):
        threading.Thread(target=_add_sound, args=(cache, jid), daemon=True).start()


def _add_sound(cache, jid):
    d = folder(cache, jid)
    try:
        mux(os.path.join(d, "video.mp4"), os.path.join(d, "sound.wav"), os.path.join(d, "film.part.mp4"))
        os.replace(os.path.join(d, "film.part.mp4"), os.path.join(d, "film.mp4"))
        job = status(cache, jid)
        job.update(audio=True, dir=d)
        with _lock:
            if jid in _jobs:
                _jobs[jid]["audio"] = True
        _save(job)
    except Exception as e:
        print(f"export {jid}: adding sound failed: {e}", flush=True)


def _work(pictures):
    while True:
        jid = _queue.get()
        with _lock:
            job = _jobs.get(jid)
        if not job or job["state"] != "queued":
            continue
        d, opt, started = job["dir"], job["options"], time.time()

        def progress(done, total):
            rate = done / max(time.time() - started, 1e-6)
            with _lock:
                job.update(state="making", done=done, eta=round((total - done) / rate) if rate else None)
                if done % 25 == 0 or done == total:
                    _save(job)

        try:
            job["state"] = "making"
            video = os.path.join(d, "video.mp4")
            with calibration.looking(opt.get("look", "balanced")), calibration.coloring(opt.get("colors", "natural")), \
                    calibration.stepping(opt.get("off", "")):
                job["made_as"] = render(opt, job["plan"], pictures, video + ".part.mp4", progress)
            os.replace(video + ".part.mp4", video)
            wav = os.path.join(d, "sound.wav")
            if opt["sound"] and job["plan"]["seconds"] <= SOUND_MOST:
                with _lock:
                    job.update(state="sound", eta=None)
                waited = time.time()
                while not os.path.exists(wav) and time.time() - waited < SOUND_WAIT:
                    time.sleep(0.5)
            if opt["sound"] and os.path.exists(wav):
                mux(video, wav, os.path.join(d, "film.part.mp4"))
                os.replace(os.path.join(d, "film.part.mp4"), os.path.join(d, "film.mp4"))
                job["audio"] = True
            else:
                shutil.copyfile(video, os.path.join(d, "film.part.mp4"))
                os.replace(os.path.join(d, "film.part.mp4"), os.path.join(d, "film.mp4"))
                job["audio"] = False
            with _lock:
                job.update(state="done", done=job["total"], eta=0, took=round(time.time() - started, 1),
                           bytes=os.path.getsize(os.path.join(d, "film.mp4")))
                _save(job)
            print(f"export {jid}: {job['total']} pictures, {job['seconds']} s film, {job['took']} s, {job['made_as']}", flush=True)
            if opt["size"] == FULL:
                import mosaic_native
                mosaic_native.trim(os.path.dirname(os.path.dirname(d)))
        except Exception as e:
            with _lock:
                job.update(state="failed", error=f"{type(e).__name__}: {e}")
                _save(job)
            print(f"export {jid} failed: {type(e).__name__}: {e}", flush=True)


def film_path(cache, jid):
    path = os.path.join(folder(cache, jid), "film.mp4")
    return path if os.path.exists(path) else None


def public_plan(p):
    """The plan as the page gets it: what shows when, and the best picture each may be (mosaic, color or
    processed); tries: every picture to make, best first, as [kind, address], which the page follows when it makes
    the film itself (export.html: a film made on this computer)."""
    keep = ("id", "cam", "t", "target", "filters", "obs", "nm", "set", "set_nm", "at", "hold", "frames", "skipped", "pass")
    pics = [dict({k: e[k] for k in keep if k in e}, first=e["try"][0][0], src=source(*e["try"][0]),
                 tries=[[k, source(k, a)] for k, a in e["try"]]) for e in p["pictures"]]
    return dict(p, pictures=pics)


def source(kind, arg):
    """The frame server's address of a plan entry's best picture (its first try), without size or look: what the
    movie editor shows and downloads for that frame."""
    if kind == "movie":
        return f"/frames/movie/{arg}.webp"
    if kind == "rolling":
        return f"/frames/movie/{arg}.webp?mode=rolling"
    if kind == "mosaic":
        return f"/frames/mosaic/{arg}.webp"
    if kind == "color":
        return f"/frames/color.webp?ids={','.join(arg)}"
    if kind == "processed":
        return f"/frames/processed/{arg}.webp"
    return f"/frames/{arg}.webp"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", help="UTC, e.g. 2006-09-15T14:32")
    ap.add_argument("end")
    ap.add_argument("--cams", default="NW")
    ap.add_argument("--fps", default="auto")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--no-caption", action="store_true")
    ap.add_argument("--cache", default=os.path.join(os.getcwd(), "frame_cache"))
    ap.add_argument("--plan", action="store_true", help="only print the plan")
    ap.add_argument("--out", default="export.mp4")
    a = ap.parse_args()
    opt = options({"from": [a.start], "until": [a.end], "cams": [a.cams], "fps": [a.fps], "size": [str(a.size)],
                   "caption": ["0" if a.no_caption else "1"], "sound": ["0"]})
    p = plan(opt)
    print(f"{p['count']} pictures, {p['seconds']} s of film, {p['width']}x{p['height']}", flush=True)
    if a.plan:
        for e in p["pictures"]:
            print(f"{e['at']:8.3f} {e['frames']:3d}f {utc(e['t'])} {e['cam']} {e['id']} {e['target']} {e['filters']} {e['try'][0][0]}")
        return
    reel.data_source.KEEP_SPICE_CACHE = True
    started = time.time()
    made = render(opt, p, Pictures(a.cache), a.out,
                  lambda d, t: print(f"{d}/{t} pictures, {time.time() - started:.0f} s", flush=True) if d % 50 == 0 or d == t else None)
    print(f"{a.out}: {made}, {time.time() - started:.0f} s", flush=True)


if __name__ == "__main__":
    main()
