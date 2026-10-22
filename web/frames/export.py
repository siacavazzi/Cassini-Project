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

Sound is made by the page, by the same synth as the live sound (sound.html, cassiniSound.render) from the plan's
picture list, and handed to the job as a WAV, which ffmpeg adds as AAC.

  CASSINI_DATA=... python web/frames/export.py 2006-09-15T14:32 2006-09-15T17:12 --cams W --out shadow.mp4
"""
import argparse
import calendar
import hashlib
import io
import json
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

# bumped whenever the way films are made changes, so older ones are not served again
VERSION = "export-v2"
FPS = 30                     # frames a second in the file
HOLD_MIN, HOLD_MAX = 1 / FPS, 0.5
TYPICAL = 1 / 8              # adaptive: how long the stretch's median gap lasts on screen
LAST = 1.5                   # seconds the last picture stays
MAX_PICTURES = int(os.environ.get("CASSINI_EXPORT_MAX", 3000))
SIZES = (512, 768, 1024)
CAPTION = 48                 # caption strip height at 1024 px panes (scaled with the pane)
SKIP_NOTE = 3 * 3600         # gaps longer than this are named in the caption
KIND = {"true": "true colour", "false": "false colour", "two": "two-filter colour"}
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


def options(q):
    """The export's options from a query (dict of lists, as parse_qs gives), checked, with defaults."""
    get = lambda k, d: (q.get(k) or [d])[0]
    t0, t1 = unix(get("from", "")), unix(get("until", ""))
    if t1 <= t0:
        raise ValueError("until must be after from")
    cams = "".join(c for c in "NW" if c in get("cams", "NW").upper()) or "NW"
    fps = get("fps", "auto")
    fps = "auto" if fps == "auto" else max(1, min(FPS, int(float(fps))))
    size = min(SIZES, key=lambda s: abs(s - int(get("size", "1024"))))
    return {"from": t0, "until": t1, "cams": cams, "fps": fps, "size": size,
            "sound": get("sound", "1") != "0", "caption": get("caption", "1") != "0"}


def job_id(opt):
    """Films are named by what they show, so the same stretch and options give the same file and link."""
    key = {k: opt[k] for k in ("from", "until", "cams", "fps", "size", "sound", "caption")}
    return hashlib.sha1(json.dumps([VERSION, key], sort_keys=True).encode()).hexdigest()[:16]


# ---------- the plan: which picture shows when ----------

def plan(opt):
    """The film's pictures in time order, each {id, cam, t, target, filters, try, kind, at (film seconds), hold,
    frames, nm, set_nm?, tile?, skipped?}, and the film's length. try = the pictures to make, best first."""
    idx, sets = reel.load_index()
    t = idx["seconds_1970"].to_numpy()
    lo, hi = np.searchsorted(t, opt["from"], "left"), np.searchsorted(t, opt["until"], "right")
    ids, insts, targets, obs = idx["id"].tolist(), idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist()
    f1s, f2s, set_of = idx["filter1"].astype(str).tolist(), idx["filter2"].astype(str).tolist(), idx["set"].to_numpy()
    cam_of = lambda q: "N" if insts[q] == "ISSNA" else "W"
    last = {}   # each camera's frame before, as movie mode looks it up (up to 64 frames back)
    for q in range(lo - 1, max(-1, lo - 65), -1):
        last.setdefault(cam_of(q), q)
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
        if tile:
            tries.append(("mosaic", ids[st["use"][0]] if comp else ids[q]))
        if comp:
            tries.append(("color", [ids[u] for u in st["use"]]))
        tries += [("processed", ids[q]), ("frame", ids[q])]
        e = {"id": ids[q], "cam": cam, "t": float(t[q]), "target": targets[q] if isinstance(targets[q], str) else "",
             "filters": f"{f1s[q]}/{f2s[q]}", "obs": obs[q] if isinstance(obs[q], str) else "", "try": tries,
             "nm": reel.wavelength(insts[q], f1s[q] + f2s[q])}
        if comp:
            e["set"] = st["kind"]
            e["set_nm"] = [reel.wavelength(insts[u], f1s[u] + f2s[u]) for u in st["use"]]
        out.append(e)
    if len(out) > MAX_PICTURES:
        raise OverflowError(f"{len(out):,} pictures: an export holds at most {MAX_PICTURES:,}; pick a shorter stretch")
    timing(out, opt["fps"])
    return {"pictures": out, "count": len(out), "seconds": round(sum(e["frames"] for e in out) / FPS, 2),
            "frames": sum(e["frames"] for e in out), "width": width(opt), "height": height(opt)}


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


def width(opt):
    return opt["size"] * len(opt["cams"])


def caption_h(opt):
    return 2 * round(CAPTION * opt["size"] / 1024 / 2) if opt["caption"] else 0


def height(opt):
    return opt["size"] + caption_h(opt)


# ---------- pictures ----------

class Pictures:
    """How the film gets each picture: the frame server's own makers (so its cache is shared), or the pipeline
    called here. Each make(...) returns WebP or PNG bytes, or None when it has no such picture."""

    def __init__(self, cache, color=None, processed=None, frame=None, slots=None):
        self.cache, self.slots = cache, slots
        self._color, self._processed, self._frame = color, processed, frame

    def make(self, kind, arg, size):
        import obs_mosaic
        if kind == "mosaic":
            made = obs_mosaic.mosaic_webp(arg, size, self.cache, self.slots, ahead=0)
            if made:
                return made[0], "mosaic"
            found = reel.mosaic_of(arg, wait=True)
            return (reel.shot_webp(*found, size, self.cache, True, self.slots)[0], "mosaic") if found else None
        if kind == "color":
            if self._color:
                return self._color(arg, size, self.cache)[0], "colour"
            return self._pipeline(arg), "colour"
        if kind == "processed":
            if self._processed:
                return self._processed(arg, size, self.cache)[0], "processed"
            return self._pipeline([arg]), "processed"
        if self._frame:
            return self._frame(arg, size, self.cache), "frame"
        return reel.data_source.read_bytes(f"{reel.FOLDERS[arg[0]]}/{arg}.png"), "frame"

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

    def picture(self, e, size):
        """The picture for plan entry e as RGB over black, size px on its longest side, and what it is."""
        for kind, arg in e["try"]:
            try:
                made = self.make(kind, arg, size)
            except FileNotFoundError:
                continue
            except Exception as err:   # a picture the pipeline cannot make: the next try stands in
                print(f"export: {kind} {arg}: {type(err).__name__}: {err}", flush=True)
                continue
            if not made or not made[0]:
                continue
            im = Image.open(io.BytesIO(made[0]))
            im = im.convert("RGBA")
            if max(im.size) != size:
                s = size / max(im.size)
                im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
            black = Image.new("RGB", im.size)
            black.paste(im, mask=im.getchannel("A"))
            return black, made[1]
        return None, ""


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
    kind = KIND.get(e.get("set"), "colour") if what == "colour" else what if what in ("mosaic",) else ""
    target = (e["target"] or "Unknown").replace("_", " ").title()
    return " · ".join(x for x in (f"{utc(e['t'])} UTC", target, f"{'NAC' if e['cam'] == 'N' else 'WAC'} {e['filters']}", kind) if x)


class Film:
    """Draws the panes and caption and pipes whole frames to ffmpeg."""

    def __init__(self, opt, path):
        self.opt, self.size = opt, opt["size"]
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
        pane = Image.new("RGB", (self.size, self.size))
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
    pics, ahead = p["pictures"], max(2, workers * 3)
    kinds, building = Counter(), {}
    try:
        with ThreadPoolExecutor(workers) as pool:
            todo = deque()
            nxt = 0
            for n, e in enumerate(pics):
                while nxt < len(pics) and nxt < n + ahead:
                    todo.append(pool.submit(pictures.picture, pics[nxt], opt["size"]))
                    nxt += 1
                im, what = todo.popleft().result()
                kinds[what or "none"] += 1
                # a mosaic stays up while its observation goes on: the pass's other frames (another filter, a frame
                # that is not a tile) would otherwise flash in and out between its tiles
                if what == "mosaic":
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


def folder(cache, jid):
    return os.path.join(cache, VERSION, jid)


def name(opt, p):
    """The file name a download gets: cassini-2006-09-15-1432-saturn.mp4."""
    main = Counter(e["target"] for e in p["pictures"] if e["target"]).most_common(1)
    return f"cassini-{utc(opt['from'], False)}-{(main[0][0] if main else 'mission').lower().replace('_', '-')}.mp4"


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
    try:
        with open(os.path.join(folder(cache, jid), "job.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def submit(opt, cache, pictures):
    """Starts the film (or finds it made or on its way) and says where it stands."""
    global _worker
    jid = job_id(opt)
    found = status(cache, jid)
    if found and found.get("state") != "failed":
        return found
    p = plan(opt)
    if not p["count"]:
        raise LookupError("no pictures in that stretch")
    job = {"id": jid, "state": "queued", "done": 0, "total": p["count"], "seconds": p["seconds"], "options": opt,
           "name": name(opt, p), "width": p["width"], "height": p["height"], "created": time.time(),
           "plan": p, "dir": folder(cache, jid)}
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
            job["made_as"] = render(opt, job["plan"], pictures, video + ".part.mp4", progress)
            os.replace(video + ".part.mp4", video)
            wav = os.path.join(d, "sound.wav")
            if opt["sound"]:
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
    processed), without the make-orders."""
    keep = ("id", "cam", "t", "target", "filters", "nm", "set", "set_nm", "at", "hold", "frames", "skipped")
    pics = [dict({k: e[k] for k in keep if k in e}, first=e["try"][0][0]) for e in p["pictures"]]
    return dict(p, pictures=pics)


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
