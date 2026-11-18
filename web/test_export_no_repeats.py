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

# ---- movie mode (the page's complete(), kind_of "movie_same"): the runs of a movie pass's frames in a row that play
# as one picture, read from the reports kept beside the pictures; the page stops on one frame of a run ----
root = tempfile.mkdtemp()
u = {"movie": True, "key": ("DAPHNIS", "ISS_257DA_DAPHNIS001_PIE", "N", 3),
     "frames": [[0, f"N{n}_1", "F", 0.0] for n in range(7)]}
reports = {0: {"ids": ["a", "b", "c"]}, 1: {"ids": ["a", "b", "c"]}, 2: {"ids": ["a", "b", "c"], "tint": True, "held": "N0_1"},
           3: {"ids": ["d", "e", "f"]}, 4: {"held": "N3_1"}, 5: {"held": "N3_1"}}   # frame 6: not made yet
for n, rep in reports.items():
    os.makedirs(os.path.join(root, obs_mosaic.MOVIE_DIR, "1024"), exist_ok=True)
    with open(os.path.join(root, obs_mosaic.MOVIE_DIR, "1024", f"{n}_0_1_c2_e8r3.json"), "w") as fh:
        json.dump(dict(rep, movie=True, id=f"N{n}_1"), fh)
saved = obs_mosaic.folder, obs_mosaic._plan_if_made
obs_mosaic.folder, obs_mosaic._plan_if_made = (lambda v, cache: root), (lambda v, cache: {})
try:
    runs = obs_mosaic.movie_runs(u, "cache", True)
    # 0 and 1 show one set; 2 is a tinted frame (a picture of its own); 4 and 5 hold frame 4's picture, 3 is a set
    assert runs == {"N0_1": "N0_1", "N1_1": "N0_1", "N4_1": "N4_1", "N5_1": "N4_1"}, runs
    assert obs_mosaic.movie_runs(u, "cache", False) == {}
finally:
    obs_mosaic.folder, obs_mosaic._plan_if_made = saved

# ---- a mosaic movie: frames whose tile changes nothing on screen (rolling_layout lays out the same tiles at the
# same gains: the same name, so the same picture) are one run; a frame whose tile is not made is its own ----
names = {0: "lap-1-a", 1: "lap-1-a", 2: "lap-1-a", 3: "lap-1-b", 4: None, 5: "lap-1-b", 6: "lap-1-c", 7: "lap-1-c"}
um = {"kind": "mosaic_movie", "key": ("SATURN", "ISS_257SA_NPOLMAP001_VIMS", "W", 0),
      "frames": [[0, f"W{n}_1", "F", 0.0] for n in range(8)]}
tiles_dir = tempfile.mkdtemp()
for n in names:
    if names[n] is not None:
        open(os.path.join(tiles_dir, f"{n}.json"), "w").write("{}")
saved = obs_mosaic._plan_if_made, obs_mosaic.plan, obs_mosaic._tiles, obs_mosaic.rolling_layout, obs_mosaic.unit_of
obs_mosaic._plan_if_made = lambda v, cache: {}
obs_mosaic.plan = lambda v, cache: {"display_scale": {}}
obs_mosaic._tiles = lambda v, cache, scale: tiles_dir
obs_mosaic.rolling_layout = lambda v, n, cache, laps=1, made_only=False, skipped=None, fade=(0, 0): (None,) * 5 + (names[n],)
try:
    runs = obs_mosaic.rolling_runs(um, "cache")
    assert runs == {"W0_1": "W0_1", "W1_1": "W0_1", "W2_1": "W0_1", "W6_1": "W6_1", "W7_1": "W6_1"}, runs
    # the export's plan keeps one frame of each run (and every frame of no run)
    obs_mosaic.unit_of = lambda fid: (um, int(fid[1:-2]))
    p = [{"id": f"W{n}_1", "cam": "W", "t": float(T0 + 30 * n), "try": [("rolling", f"W{n}_1"), ("processed", f"W{n}_1")]}
         for n in range(8)]
    kept = [e["id"] for e in export.shown_once(p, {"size": 1024, "movie": {}}, cache="cache")]
    assert kept == ["W0_1", "W3_1", "W4_1", "W5_1", "W6_1"], kept
finally:
    obs_mosaic._plan_if_made, obs_mosaic.plan, obs_mosaic._tiles, obs_mosaic.rolling_layout, obs_mosaic.unit_of = saved

# ---- the window's note (kind_of) only reads the runs the pre-build kept: never a layout on request; a pass without
# them (cold, or a style not built) gets none, and keep_rolling_runs writes what rolling_runs works out ----
um2 = dict(um, mosaic=True, movie=False, repeats=2, tossup=False, jump_frac=None)
passdir = tempfile.mkdtemp()
saved = (obs_mosaic.unit_of, obs_mosaic.units, obs_mosaic.lap_ends, obs_mosaic.folder, obs_mosaic.rolling_layout,
         obs_mosaic._plan_if_made, obs_mosaic.plan, obs_mosaic._tiles)


def no_layout(*a, **k):
    raise AssertionError("kind_of laid out a frame")


obs_mosaic.unit_of = lambda fid: (um2, int(fid[1:-2]))
obs_mosaic.units = lambda *key: [um2]
obs_mosaic.lap_ends = lambda v: []
obs_mosaic.folder = lambda v, cache: passdir
obs_mosaic.rolling_layout = no_layout
try:
    note = obs_mosaic.kind_of("W3_1", "cache")
    assert "rolling_same" not in note, note
    # the pre-build's step writes the runs (laid out from the made tiles), and the note then reads them
    obs_mosaic._plan_if_made = lambda v, cache: {}
    obs_mosaic.plan = lambda v, cache: {"display_scale": {}}
    obs_mosaic._tiles = lambda v, cache, scale: tiles_dir
    obs_mosaic.rolling_layout = lambda v, n, cache, laps=1, made_only=False, skipped=None, fade=(0, 0): (None,) * 5 + (names[n],)
    obs_mosaic._rolling_runs.clear()
    kept = obs_mosaic.keep_rolling_runs(um2, "cache")
    obs_mosaic.rolling_layout = no_layout
    note = obs_mosaic.kind_of("W3_1", "cache")
    assert note.get("rolling_same") == kept == {"W0_1": "W0_1", "W1_1": "W0_1", "W2_1": "W0_1", "W6_1": "W6_1", "W7_1": "W6_1"}, note
    # another style (laps 2) was not built: none, and still nothing laid out
    assert "rolling_same" not in obs_mosaic.kind_of("W3_1", "cache", laps=2)
finally:
    (obs_mosaic.unit_of, obs_mosaic.units, obs_mosaic.lap_ends, obs_mosaic.folder, obs_mosaic.rolling_layout,
     obs_mosaic._plan_if_made, obs_mosaic.plan, obs_mosaic._tiles) = saved


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

# ---- each frame's own time and hold, exactly, however irregular the holds (ffmpeg left to guess a frame rate from the
# first frames snapped them to it: holds 1, 15, 3, 12, 7 came out 3, 12, 3, 12, 6) ----
for rate, holds in ((30, [1, 15, 3, 12, 7]), (30, [9, 1, 1, 2, 30, 1, 4]), (24, [1, 1, 3, 1, 2]), (12, [5, 1, 7])):
    opt = {"cams": "N", "size": 64, "caption": False, "fps": "auto" if rate == 30 else rate, "movie": {}}
    path = os.path.join(tempfile.mkdtemp(), "film.mp4")
    film = export.Film(opt, path, rate)
    for n, h in enumerate(holds):
        film.canvas.paste(Image.fromarray(picture(100 + n, 64, 64)[..., :3]), (0, 0))
        film.changed = True
        film.hold(h)
    film.close()
    fr, info = decoded(path, film.w, film.h)
    got = [(round(float(f["pts_time"]) * rate), round(float(f["duration_time"]) * rate)) for f in info["frames"]]
    want = [(sum(holds[:n]), h) for n, h in enumerate(holds)]
    print(f"holds {holds} at {rate}: frames at {got}")
    assert got == want, (got, want)
    assert abs(float(info["format"]["duration"]) - sum(holds) / rate) < 0.5 / rate, info["format"]

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
