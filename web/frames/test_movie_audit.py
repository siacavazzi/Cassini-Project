#!/usr/bin/env python3
"""Checks the movie audit's fixes to the film plan (web/frames/export.py), on Sam's Saturn stare of 2005-07-03
(ISS_010SA_1X6MOVIED00*, WAC: MT2, CB2, MT3 at each of five pointings, BL1 after the second), the stretch his
Movie Editor showed flickering: python web/frames/test_movie_audit.py

- Complete color pictures only: a color set is one picture of the film, at its last channel, as movie mode steps
  (head-quiet.html complete()); sets=0 keeps every channel.
- One color mix a camera and target through the film: the set at the second pointing (MT2, CB2, MT3, BL1) mixed
  MT3/MT2/BL1 where every other set mixed MT3/CB2/MT2, so its composite came up in other colors.
How the server plays each pass (obs_mosaic's call, which needs the geometry cache) is set here, as the Mac Mini's
server calls them (/frames/movie/W1499133136_1.json: "movie": true)."""
import os
import sys
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export  # noqa: E402
import reel  # noqa: E402

STRETCH = "from=2005-07-03T16:49:20&until=2005-07-04T06:00:00&cams=W&targets=SATURN&"
idx, sets = reel.load_index()
row = {i: q for q, i in enumerate(idx["id"].tolist())}
t = idx["seconds_1970"].to_numpy()


def plan(q, kind):
    export.pass_kind = lambda fid: kind
    export._pass_of = lambda fid: None
    return export.plan(export.options(parse_qs(STRETCH + q)))["pictures"]


def ready(fid):
    """Whether frame fid completes its color set (or is in none)."""
    s = int(idx["set"][row[fid]])
    return s < 0 or t[row[fid]] == sets[s]["ready"]


def test_movie_pass_steps_once_a_set():
    every = plan("sets=0", "movie")
    pics = plan("", "movie")
    assert len(every) > 3 * len(pics) - 10, (len(every), len(pics))
    assert pics and all(ready(e["id"]) for e in pics)
    assert all(e["try"][0] == ("movie", e["id"]) for e in pics)
    # the first two frames of each pass (MT2, CB2: no set complete yet, drawn grey) are no pictures of their own
    assert not any(e["filters"] in ("MT2/CL2", "CB2/CL2") for e in pics)


def test_stills_no_grey_channels():
    pics = plan("", None)
    # no black-and-white channel between the composites: every set's picture is its color picture (or the mosaic
    # it is a tile of, which a still pass asks the server for first)
    assert pics and all(e["try"][0][0] in ("mosaic", "color") and any(k == "color" for k, _ in e["try"]) for e in pics)
    assert any(e["try"][0][0] == "processed" for e in plan("sets=0", None))


def test_one_color_mix():
    def filters(e):
        ids = next(a for k, a in e["try"] if k == "color")
        return tuple(idx["filter1"][row[i]] + "/" + idx["filter2"][row[i]] for i in ids)
    for kind in (None, "movie"):
        pics = plan("pictures=color", kind)
        mixes = {filters(e) for e in pics}
        # every set made of MT3, CB2 and MT2 (the set at the second pointing mixed BL1 in place of CB2)
        assert mixes == {("MT3/CL2", "CB2/CL2", "MT2/CL2")}, mixes
        assert any(e["filters"] == "CL1/BL1" for e in pics)
    # a movie pass in Full color only stays the color pictures (each at full frame)
    assert all(e["try"][0][0] == "color" for e in plan("pictures=color", "movie"))


def test_mosaics_off():
    """The Movie Editor's Mosaics: Off draws no mosaic (Sam's ring scan, ISS_006RI_LPHRLFMOV001: Tile by tile was the
    windows' mosaic building up, the same pictures, so no setting took the mosaics out)."""
    q = "from=2005-04-13T02:37:00&until=2005-04-13T16:23:00&cams=NW&list=1&"
    export._pass_of = lambda fid: "P"
    export._lap_end = lambda fid: True
    for kind in ("mosaic", "mosaic_movie"):
        export.pass_kind = lambda fid, k=kind: k
        go = lambda m: export.plan(export.options(parse_qs(q + m)))["pictures"]
        assert all(e["try"][0][0] in ("mosaic", "rolling") for e in go("mos=tiles"))
        off = go("mos=off")
        assert off and not any(k in ("mosaic", "rolling") for e in off for k, _ in e["try"]), kind
    # a ring strip played as a movie (a toss-up: its mosaic the windows' other choice) is frames too; a movie is not
    export.pass_kind = lambda fid: "movie"
    for tossup in (True, False):
        export._tossup = lambda fid, v=tossup: v
        off = export.plan(export.options(parse_qs(q + "mos=off")))["pictures"]
        assert any(k == "movie" for e in off for k, _ in e["try"]) != tossup
    o = lambda m: export.options(parse_qs(STRETCH + m))
    assert export.job_id(o("mos=off")) != export.job_id(o("mos=tiles"))


def test_plan_progress():
    """A plan reports how far it is (the Movie Editor's loading window, /export/plan-progress/KEY.json)."""
    seen = []
    export.pass_kind = lambda fid: None
    ring = "from=2005-04-13T02:37:00&until=2005-04-13T16:23:00&cams=NW&list=1"
    pics = export.plan(export.options(parse_qs(ring)), progress=lambda d, n, s: seen.append((d, n, s)))
    assert pics["pictures"] and seen[0][0] == 0 and seen[-1][0] == seen[-1][1] > 1000 and len(seen) > 10, seen
    assert all(a[0] <= b[0] for a, b in zip(seen, seen[1:]))
    import frame_server as fs
    assert fs.plan_progress_key({"progress": ["ab_1"]}) == "ab_1" and fs.plan_progress_key({"progress": ["../x"]}) is None
    rep = fs.plan_progress("ab_1")
    rep(5, 10, "frames")
    assert fs._plans["ab_1"]["done"] == 5 and fs._plans["ab_1"]["total"] == 10
    rep(None, None, "done")
    assert fs._plans["ab_1"]["step"] == "done" and fs._plans["ab_1"]["done"] == 10
    assert fs.plan_progress(None) is None


def test_names():
    o = lambda q: export.options(parse_qs(STRETCH + q))
    assert o("")["movie"] == export.MOVIE and o("sets=0")["movie"]["sets"] is False
    assert export.job_id(o("")) != export.job_id(o("sets=0"))
    assert export.job_id(o("sets=1")) == export.job_id(o(""))
    # the Background: only another color than black is in the film's name, and paints its panes
    assert "bg" not in o("bg=000000")["movie"] and o("bg=%230D1A33")["movie"]["bg"] == "0d1a33" and "bg" not in o("bg=zz")["movie"]
    assert export.job_id(o("bg=0d1a33")) != export.job_id(o(""))
    assert export.background(o("bg=0d1a33")["movie"]) == (13, 26, 51) and export.background(o("")["movie"]) == (0, 0, 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
