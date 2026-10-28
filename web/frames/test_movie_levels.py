#!/usr/bin/env python3
"""Checks the Movie Editor's exposure levels and framing in web/frames/export.py (and the exposure the look takes in
web/frames/studio_look.py): python web/frames/test_movie_levels.py"""
import math
import os
import sys
from urllib.parse import parse_qs

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export  # noqa: E402
import obs_mosaic  # noqa: E402
import studio_look as L  # noqa: E402


def opts(q):
    return export.options(parse_qs("from=2005-02-17T05:00:00&until=2005-02-17T06:00:00&" + q))


def disk(level, side=200, r=60):
    """A gray disk on black, its lit pixels at level (0..1)."""
    y, x = np.mgrid[0:side, 0:side]
    a = np.where((x - side / 2) ** 2 + (y - side / 2) ** 2 < r * r, round(level * 255), 0).astype(np.uint8)
    return Image.fromarray(np.dstack([a] * 3), "RGB")


def test_options():
    o = opts("levels=N1_1:0.5,W2_1:-9,bad,N3_1:x&even=12&crop=0.1_0.2_0.6_0.7&crop2=x&nudge=N1_1:0.1:-0.2,N2_1:0:0,N4_1:2:1&ctr=0")
    assert o["levels"] == {"N1_1": 0.5, "W2_1": -2.0}
    assert o["even"] == 12 and o["frame"]["crop"] == [0.1, 0.2, 0.6, 0.7] and o["frame"]["crop2"] is None
    assert o["frame"]["nudge"] == {"N1_1": [0.1, -0.2], "N4_1": [0.5, 0.5]}
    assert o["movie"]["center"] is False
    # nothing asked: the film named as before the editor had levels and framing
    plain = opts("")
    assert plain["levels"] == {} and plain["even"] == 0 and plain["frame"] == export.FRAME and plain["movie"]["center"]
    assert "levels" not in str(export.job_id(plain)) and export.job_id(plain) != export.job_id(o)
    assert export.job_id(opts("levels=N1_1:0.5")) != export.job_id(plain)


def test_line():
    # straight between the points, flat before the first and after the last
    pics = [{"id": f"N{i}_1", "cam": "N", "try": [("processed", f"N{i}_1")], "target": "SATURN"} for i in range(6)]
    o = opts("levels=N1_1:1,N3_1:-1")
    total, line, even = export.exposures(o, pics)
    assert line == [1, 1, 0, -1, -1, -1] and total == line and even == [0] * 6


def test_brightness():
    a, b = export.brightness(disk(0.25)), export.brightness(disk(0.5))
    assert abs(math.exp(a) - 0.25) < 0.01 and abs((b - a) - math.log(2)) < 0.02
    assert export.brightness(Image.new("RGB", (100, 100))) is None
    # an exposure change of 1 EV through the look doubles it
    up = L.apply(disk(0.25), None, 1.0)
    assert abs(export.brightness(up) - b) < 0.02


def test_even():
    # Even out is movie mode's own math, per stretch of one camera, kind and target
    if not hasattr(obs_mosaic, "evened_gains"):
        print("skip test_even: obs_mosaic.evened_gains not on this branch")
        return
    pics = [{"id": f"N{i}_1", "cam": "N", "try": [("processed", f"N{i}_1")], "target": "SATURN"} for i in range(9)]
    logs = {e["id"]: math.log(0.3) for e in pics}
    logs["N4_1"] = math.log(0.6)   # one frame twice as bright: a flash
    total, line, even = export.exposures(opts("even=8"), pics, logs)
    assert abs(even[4] + 1) < 0.05 and max(abs(v) for i, v in enumerate(even) if i != 4) < 0.05
    want = obs_mosaic.evened_gains([logs[e["id"]] for e in pics], 8)
    assert all(abs(v - math.log2(g)) < 1e-3 for v, g in zip(even, want))
    # another target is its own stretch: a step between them is the picture changing
    for e in pics[5:]:
        e["target"] = "TITAN"
        logs[e["id"]] = math.log(0.05)
    logs["N4_1"] = math.log(0.3)
    assert max(abs(v) for v in export.exposures(opts("even=8"), pics, logs)[2]) < 0.05


def test_stretches():
    e = lambda cam, kind, t="SATURN", **k: dict({"id": "x", "cam": cam, "try": [(kind, "x")], "target": t}, **k)
    pics = [e("N", "movie"), e("W", "processed"), e("N", "movie"), e("N", "color", set="true"), e("N", "movie", t="TITAN")]
    assert export.stretches(pics) == [[0, 2], [1], [3], [4]]


def test_look_ev():
    # the level is the look's exposure moved: the same as a look with that exposure, within the slider's range
    im = disk(0.3)
    assert np.array_equal(np.asarray(L.apply(im, None, 0.5)), np.asarray(L.apply(im, L.parse("ex:0.5"))))
    assert np.array_equal(np.asarray(L.apply(im, L.parse("ex:0.5,sa:20"), 0.25)), np.asarray(L.apply(im, L.parse("ex:0.75,sa:20"))))
    assert np.array_equal(np.asarray(L.apply(im, L.parse("ex:1.5"), 1)), np.asarray(L.apply(im, L.parse("ex:2.5"))))
    assert np.array_equal(np.asarray(L.apply(im, L.parse("ex:3.5"), 1)), np.asarray(L.apply(im, L.parse("ex:4"))))
    assert L.apply(im, None, 0) is im


def test_framed():
    im = disk(0.5, 100, 10)
    assert export.framed(im, None, (0, 0)) is im
    # moved right by a tenth: the disk's middle 10 px right
    a = np.asarray(export.framed(im, None, (0.1, 0)))[..., 0]
    cols = np.flatnonzero(a.any(0))
    assert abs((cols[0] + cols[-1]) / 2 - 59.5) <= 1
    # cut to its middle half: the disk twice as wide, the picture as big as before
    z = export.framed(im, [0.25, 0.25, 0.75, 0.75], (0, 0))
    cols = np.flatnonzero(np.asarray(z)[..., 0].any(0))
    assert z.size == im.size and abs((cols[-1] - cols[0] + 1) - 40) <= 2 and abs((cols[0] + cols[-1]) / 2 - 49.5) <= 1
    # a wide crop keeps its shape, as wide as the picture
    assert export.framed(im, [0, 0.25, 1, 0.75], (0, 0)).size == (100, 50)


def test_glide():
    fr = {"crop": [0, 0, 1, 1], "crop2": [0.5, 0.5, 1, 1], "nudge": {}}
    assert export.crop_at(fr, 0, 5) == [0, 0, 1, 1] and export.crop_at(fr, 4, 5) == [0.5, 0.5, 1, 1]
    mid = export.crop_at(fr, 2, 5)
    assert abs(mid[0] - 0.25) < 1e-9 and export.crop_at(fr, 1, 5)[0] < 0.125   # eased: slow at the start
    assert export.crop_at({"crop": [0.1, 0.1, 0.9, 0.9], "crop2": None}, 3, 5) == [0.1, 0.1, 0.9, 0.9]
    o = opts("crop2=0.5_0.5_1_1")
    assert o["frame"]["crop"] == [0, 0, 1, 1] and o["frame"]["crop2"] == [0.5, 0.5, 1, 1]


def test_frame_edit():
    # a frame's own look: the studio keys it sets over the movie's, kept even at rest, the last of a key winning
    assert L.override("ct:0,ex:9,zz:1,fi:warm,ex:0.5,cr:0.1_0.1_0.5_0.5") == "ex:0.5,ct:0,fi:warm"
    assert L.override("bad") == ""
    o = opts("edit=ct:20,sa:30&fedit=N1_1~ct:0,ex:0.5|N2_1~nonsense|~ex:1|W3_1~fi:mono")
    assert o["fedit"] == {"N1_1": "ex:0.5,ct:0", "W3_1": "fi:mono"}
    assert export.job_id(o) != export.job_id(opts("edit=ct:20,sa:30")) and opts("")["fedit"] == {}
    # drawn as the movie's look with the frame's keys over it: contrast back at rest, saturation the movie's
    im = disk(0.3)
    own = L.parse(f"{o['edit']},{o['fedit']['N1_1']}")
    assert np.array_equal(np.asarray(L.apply(im, own)), np.asarray(L.apply(im, L.parse("ex:0.5,sa:30"))))

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
