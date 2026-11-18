#!/usr/bin/env python3
"""
An exported film never repeats a frame (Sam, 2026-11-17: "We should never, ever, ever, ever, ever be repeating frames
like that"). Every frame of the video is a different picture from the frame before it:
  - a fixed rate film is a video at that rate, one frame a picture (24 pictures a second was a 30 fps video in which
    every fourth picture was written twice);
  - an adaptive film is a variable frame rate video, each picture one frame lasting its hold (not the same frame
    written once for each 1/30 s of it);
  - a frame held behind a mosaic, and a picture the same as the one before it, make the frame before it last longer.
The film is made by export.py's own render (with a stand-in Pictures handing it made-up pictures), decoded frame by
frame, and checked: no frame the same as the one before, each picture's time and hold where the plan has it, the
film as long as the plan says.

  python web/test_export_no_repeats.py
"""
import atexit
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import export  # noqa: E402

SIZE = 256
T0 = 1484560000   # 2017-01-16

# ---- the plan's timing: a fixed rate is one step a picture, at that rate ----
for fps in (1, 10, 12, 24, 25, 30):
    p = [{"id": f"N{i}", "cam": "N", "t": float(T0 + 60 * i)} for i in range(50)]
    export.timing(p, fps)
    assert export.rate_of(fps) == fps
    assert all(e["frames"] == 1 for e in p), (fps, sorted({e["frames"] for e in p}))
    assert all(abs(e["at"] - i / fps) < 1e-3 for i, e in enumerate(p)), fps
p = [{"id": f"N{i}", "cam": "N", "t": float(T0 + g)} for i, g in enumerate([0, 10, 20, 400, 410, 2000, 2010, 2020])]
export.timing(p, "auto")
assert export.rate_of("auto") == export.FPS

# ---- the plan: a movie frame that plays as the picture before it (a colour movie's other filters showing the last
# complete set, a frame not fit to show) is not a picture of its own, and the timing closes over it ----
import obs_mosaic  # noqa: E402
plays = {"N1": ("set", "a"), "N2": ("set", "a"), "N3": ("set", "a"), "N4": ("frame", "N4"), "N5": None, "N6": None,
         "W1": ("set", "a"), "N7": ("frame", "N4")}
real = obs_mosaic.movie_shown
obs_mosaic.movie_shown = lambda fid, *a, **k: plays[fid]
try:
    p = [{"id": i, "cam": i[0], "t": float(T0 + 30 * n), "try": [("movie", i), ("processed", i)]}
         for n, i in enumerate(["N1", "N2", "W1", "N3", "N4", "N5", "N6", "N7"])]
    opt = {"size": 1024, "movie": {}}
    kept = [e["id"] for e in export.shown_once(p, opt, cache="cache")]
    # N2 and N3 play N1's set (W1 between is the other camera's); N5 and N6 are not made yet, so they stay; N7 plays
    # N4's picture but N5 and N6 came between
    assert kept == ["N1", "W1", "N4", "N5", "N6", "N7"], kept
    assert [e["id"] for e in export.shown_once(p, opt, cache=None)] == [e["id"] for e in p]
finally:
    obs_mosaic.movie_shown = real


def picture(seed, w=SIZE, h=SIZE):
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    disc = (x - w * r.uniform(.3, .7)) ** 2 + (y - h * r.uniform(.3, .7)) ** 2 < (min(w, h) * r.uniform(.15, .3)) ** 2
    a = x * (150 / w) + r.integers(0, 60)
    rgb = np.dstack([a + disc * 90, a * .7 + disc * 60, a * .5 + disc * 120])
    return np.dstack([np.clip(rgb, 0, 255), np.full((h, w), 255)]).astype(np.uint8)


def stretch(cams, caption):
    """Pictures of a stretch: a movie pass (whose cache gave two frames the same picture), a mosaic pass with frames
    of its observation between tiles (held behind the mosaic), frames alone, both cameras where asked."""
    pics, files, t = [], {}, T0
    for n in range(36):
        cam = "W" if "W" in cams and (n % 4 == 3 or cams == "W") else "N"
        t += [12, 40, 7, 300, 25][n % 5]
        fid = f"{cam}{T0 + n}_1"
        if 8 <= n < 16:
            kind, obs = ("mosaic" if n % 2 == 0 else "processed"), "ISS_257DA_MOSAIC"
        else:
            kind, obs = "movie", "ISS_257DA_DAPHNIS001_PIE"
        tries = [(kind, fid), ("processed", fid), ("frame", fid)] if kind != "processed" else [("processed", fid), ("frame", fid)]
        e = {"id": fid, "cam": cam, "t": float(t), "target": "DAPHNIS", "filters": "CL1/CL2", "obs": obs, "nm": 650,
             "try": tries}
        src = export.source(*tries[0])
        # the movie's 21st and 22nd frames come out of the cache as the same picture
        files[src] = picture(20 if n == 21 else n)
        pics.append(e)
    return pics, files


class Stand(export.Pictures):
    """export.py's Pictures with made-up pictures in place of the frame server's makers."""

    def __init__(self, files):
        super().__init__(None)
        self.files = files

    def make(self, kind, arg, size):
        src = export.source(kind, arg)
        if src not in self.files:
            return None
        out = io.BytesIO()
        Image.fromarray(self.files[src], "RGBA").save(out, "PNG")
        return out.getvalue(), {"movie": "movie", "mosaic": "mosaic", "processed": "processed", "frame": "frame"}[kind]


def decoded(path, w, h):
    """Every frame of the video once, as stored (no resampling to a fixed rate), and each one's time and duration."""
    raw = subprocess.run([export.FFMPEG, "-v", "error", "-i", path, "-fps_mode", "passthrough", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    probe = export.FFMPEG.replace("ffmpeg", "ffprobe")
    info = json.loads(subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "frame=pts_time,duration_time:stream=r_frame_rate,avg_frame_rate:format=duration",
                                      "-of", "json", path], capture_output=True, text=True, check=True).stdout)
    return fr, info


def repeats(fr):
    """The frames (by number) that look the same as the frame before them, as decoded: their mean difference under
    one code value (two different pictures differ by tens)."""
    return [k for k in range(1, len(fr)) if np.abs(fr[k].astype(np.int16) - fr[k - 1]).mean() < 1.0]


if not (os.path.exists(export.FFMPEG) or shutil.which(export.FFMPEG)):
    print(f"skipped the films: no ffmpeg at {export.FFMPEG} (CASSINI_FFMPEG); the plan's timing passed")
    sys.exit(0)

for cams, fps, caption in (("N", 24, True), ("N", "auto", False), ("NW", 24, True), ("NW", "auto", True),
                           ("N", 12, False)):
    pics, files = stretch(cams, caption)
    export.timing(pics, fps)
    rate = export.rate_of(fps)
    opt = {"cams": cams, "size": SIZE, "caption": caption, "fps": fps, "movie": {}, "sound": False}
    plan = {"pictures": pics, "count": len(pics), "seconds": round(sum(e["frames"] for e in pics) / rate, 2),
            "frames": sum(e["frames"] for e in pics), "rate": rate, "width": export.width(opt), "height": export.height(opt)}
    path = os.path.join(tempfile.mkdtemp(), "film.mp4")
    made = export.render(opt, plan, Stand(files), path, workers=2)
    W, H = plan["width"], plan["height"]
    fr, info = decoded(path, W, H)
    same = repeats(fr)
    times = [float(f["pts_time"]) for f in info["frames"]]
    length = float(info["format"]["duration"])
    # what the screen shows changes at each picture, except a narrow-angle frame held behind its mosaic and the
    # movie's frame whose picture is the one before's: the picture up stays
    changes = [e["at"] for n, e in enumerate(pics)
               if not (e["cam"] == "N" and e["obs"] == "ISS_257DA_MOSAIC" and e["try"][0][0] == "processed")
               and n != 21]
    print(f"cams {cams} fps {fps} caption {caption}: {len(pics)} pictures, {len(fr)} frames in the video, "
          f"{length:.3f} s (plan {plan['seconds']:.3f} s), {len(same)} repeated, made as {made}")
    assert not same, f"frames the same as the one before: {same}"
    assert made.get("same picture as before") == 1, made
    assert len(fr) == len(changes), (len(fr), len(changes))
    assert all(abs(a - b) < 0.5 / rate for a, b in zip(times, changes)), list(zip(times, changes))
    assert abs(length - sum(e["frames"] for e in pics) / rate) < 0.5 / rate, (length, plan["seconds"])
    if fps != "auto" and len(changes) == len(pics):
        assert info["streams"][0]["r_frame_rate"] == f"{fps}/1", info["streams"][0]
print("ok")
