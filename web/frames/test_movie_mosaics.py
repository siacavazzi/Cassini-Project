#!/usr/bin/env python3
"""Checks how the Movie Editor's list and the film show mosaics (web/frames/export.py): Full color only keeps a mosaic
pass and a mosaic movie mosaics, and Mosaics (mos=whole / tiles, complete=1, whole=1) shows each one whole or tile by
tile. python web/frames/test_movie_mosaics.py

The stretch is Jupiter's 2x2 color mosaics of 2000-11-15 (ISS_C23JU_6ATM2X2A001_PRIME, NAC and WAC); how the server
plays each pass (obs_mosaic's call, which needs the geometry cache) is set here, as the Mac Mini's server calls them."""
import os
import sys
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export  # noqa: E402
import obs_mosaic  # noqa: E402

STRETCH = "from=2000-11-15T05:40:00&until=2000-11-15T08:10:00&"
KIND = {}


def opts(q):
    return export.options(parse_qs(STRETCH + q))


def plan(q, kind):
    """The plan with every pass of the stretch played as kind; a mosaic movie's laps end every 8th frame."""
    export.pass_kind = lambda fid: kind
    export._lap_end = lambda fid: (obs_mosaic.unit_of(fid)[1] % 8 == 7) if kind == "mosaic_movie" else None
    return export.plan(opts(q))["pictures"]


def passes(pics):
    return {(e["cam"], e["pass"]) for e in pics if e.get("pass")}


def test_options():
    assert opts("")["movie"] == export.MOVIE
    assert opts("complete=1")["movie"]["complete"] is True
    w = opts("mos=whole")["movie"]
    assert w["whole"] and w["complete"] and w["fade"] == 0
    t = opts("whole=1&complete=1&mos=tiles")["movie"]
    assert "whole" not in t and "complete" not in t
    # the film is named by what it shows
    assert len({export.job_id(opts(q)) for q in ("", "complete=1", "mos=whole", "mos=tiles")}) == 3
    assert export.job_id(opts("mos=tiles")) == export.job_id(opts(""))


def test_color_mosaic_pass():
    before = plan("pictures=color", None)
    assert before and all(e["try"][0][0] == "color" for e in before)
    pics = plan("pictures=color", "mosaic")
    # the same color sets, now each the pass's mosaic so far (the first set of a pass: its color picture)
    assert [e["id"] for e in pics] == [e["id"] for e in before]
    assert sum(e["try"][0][0] == "mosaic" for e in pics) >= len(pics) - 2 * len(passes(pics))
    assert all(e["try"][1][0] == "color" for e in pics if e["try"][0][0] == "mosaic")
    # Complete mosaics only: a pass once, its whole mosaic at its last picture
    whole = plan("pictures=color&complete=1", "mosaic")
    assert len(whole) == len(passes(pics)) and all(e["try"][0] == ("mosaic", e["id"]) for e in whole)
    last = {}
    for e in pics:
        last[(e["cam"], e["pass"])] = e["id"]
    assert sorted(e["id"] for e in whole) == sorted(last.values())


def test_color_mosaic_movie():
    pics = plan("pictures=color", "mosaic_movie")
    assert pics and all(e["try"][0] == ("rolling", e["id"]) for e in pics)
    # Whole mosaics: only the laps' ends, every place new
    whole = plan("pictures=color&whole=1", "mosaic_movie")
    assert whole and len(whole) < len(pics) and all(obs_mosaic.unit_of(e["id"])[1] % 8 == 7 for e in whole)
    assert [e["id"] for e in plan("pictures=color&mos=whole", "mosaic_movie")] == [e["id"] for e in whole]
    assert [e["id"] for e in plan("pictures=color&whole=1&mos=tiles", "mosaic_movie")] == [e["id"] for e in pics]


def test_movie_mosaic_pass():
    pics = plan("", "mosaic")
    whole = plan("mos=whole", "mosaic")
    assert len(whole) == len(passes(pics)) < len(pics)
    assert all(e["try"][0] == ("mosaic", e["id"]) for e in whole)
    # Tile by tile: as before
    assert [e["id"] for e in plan("mos=tiles", "mosaic")] == [e["id"] for e in pics]
    # what the editor lists: the picture each entry shows, and its pass
    listed = export.public_plan({"pictures": whole})["pictures"]
    assert all(e["first"] == "mosaic" and e["src"] == f"/frames/mosaic/{e['id']}.webp" and e["pass"] for e in listed)


def test_other_pictures_untouched():
    for how in ("processed", "raw"):
        a = [e["id"] for e in plan(f"pictures={how}", None)]
        assert [e["id"] for e in plan(f"pictures={how}&mos=whole", "mosaic")] == a


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
