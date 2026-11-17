"""A mosaic movie played as a movie (the Mosaic / Movie switch on Movie) finishes working out its pass.

obs_mosaic.movie_webp answers "working out the pass" (503) until the pass's movie footprint is made, and starts
warm_movie to make it. warm_movie left the footprint out for a mosaic movie (its rolling picture does without one),
so the footprint was never made and the window asked for ever (spot check: Jupiter ATMOS02D 2001, 00ASA 2006).
Synthetic 2 x 2 pass, two laps, tiles and plan on disk (as test_rolling_base makes them): the first ask is 503, the
footprint is then made in the background, and the next ask is the movie frame; its rolling picture still does
without the footprint; and steady movie frames of it finish too (their stabilization chain).
Run: python web/test_mosaic_movie_footprint.py"""
import json
import os
import sys
import tempfile
import atexit, shutil  # noqa: E402
# every temporary folder and file this test makes goes in one folder of its own, removed when the test ends, passed
# or failed (test runs left GBs of folders in TMPDIR, and the Mini's boot drive filled, 2026-11-13)
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}
OFFS = [(-380, -380), (380, -380), (-380, 380), (380, 380)]
yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)


def make_pass(name):
    """A gray 2 x 2 mosaic movie (kind mosaic_movie), two laps, its tiles and plan on disk and no footprint."""
    cache = tempfile.mkdtemp()
    seq = [q for q in (0, 1, 2, 3)] * 2
    fr = [(f"p{i}", f"N{1500000000 + i}_1", "CL1/CL2", 1000.0 + 20 * i, 600, -OFFS[q][0], -OFFS[q][1], 1e6) for i, q in enumerate(seq)]
    u = {"key": ("JUPITER", name, "N", 0), "frames": fr, "z": 1e6, "movie": False, "mosaic": True, "last": fr[-1][3],
         "place": seq, "kind": "mosaic_movie", "repeats": 2}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    for i, q in enumerate(seq):
        gx, gy = xx - 512 + OFFS[q][0], yy - 512 + OFFS[q][1]
        im = np.zeros((1024, 1024, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = (160 * (0.75 + 0.2 * np.sin(gx / 37.0) * np.cos(gy / 53.0))).astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{td}/{i}.png")
        t = {"n": i, "id": fr[i][1], "filter": "CL1/CL2", "t": fr[i][3], "offset": list(map(float, OFFS[q])), "box": [-512, -512, 1024, 1024]}
        json.dump(t, open(f"{td}/{i}.json", "w"))
    plan = {"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [-900, -900, 900, 900], "fixed": True,
            "view": [1800, 1800], "k": 1024 / 1800, "colour": False, "grey": "CL1/CL2", "whole": False,
            "luminance": {"filters": ["CL1/CL2"], "gains": {}}}
    json.dump(plan, open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
    return u, cache


def setup(name):
    u, cache = make_pass(name)
    ids = {fr[1]: (u, i) for i, fr in enumerate(u["frames"])}
    om.unit_of = lambda fid: ids.get(fid)
    return u, cache


def ask(fid, cache, secs=20, **kw):
    """movie_webp of fid until it stops answering "working out the pass" (every 0.2 s, as the page's retry does);
    (answer, number of 503s)."""
    tries, t0 = 0, time.time()
    while time.time() - t0 < secs:
        made = om.movie_webp(fid, 512, cache, ahead=2, **kw)
        if made is None or made[0] is not None or made[1].get("why") != "working out the pass":
            return made, tries
        tries += 1
        time.sleep(0.2)
    return None, tries


def test_movie_of_mosaic_movie():
    u, cache = setup("FOOTPRINT_MOVIE")
    fp = os.path.join(om.folder(u, cache), om.FOOTPRINT_FILE)
    assert not os.path.exists(fp)
    fid = u["frames"][5][1]
    made, tries = ask(fid, cache)
    assert made is not None and made[0] is not None, f"still working out the pass after {tries} asks"
    assert tries >= 1, "the first ask should start the pass (503) and not wait"
    assert os.path.exists(fp), "the movie footprint is kept with the pass"
    print(f"movie frame of a mosaic movie: {len(made[0])} bytes after {tries} x 503")


def test_rolling_keeps_without_footprint():
    u, cache = setup("FOOTPRINT_ROLLING")
    made = om.rolling_webp(u["frames"][5][1], 512, cache)
    assert made is not None and made[0] is not None, made
    time.sleep(1.0)
    assert not os.path.exists(os.path.join(om.folder(u, cache), om.FOOTPRINT_FILE)), \
        "the rolling picture should not make a footprint it does not use"
    print("rolling picture of a mosaic movie: made without a footprint")


def test_steady_movie_of_mosaic_movie():
    u, cache = setup("FOOTPRINT_STEADY")
    made, tries = ask(u["frames"][6][1], cache, secs=60, steady=2)
    assert made is not None and made[0] is not None, f"steady movie still working out the pass after {tries} asks"
    print(f"steady movie frame of a mosaic movie: {len(made[0])} bytes after {tries} x 503")


if __name__ == "__main__":
    test_movie_of_mosaic_movie()
    test_rolling_keeps_without_footprint()
    test_steady_movie_of_mosaic_movie()
    print("ok")
