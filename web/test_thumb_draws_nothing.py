#!/usr/bin/env python3
"""A Highlights thumbnail draws no pass and starts nothing.

The thumbnails are made as the server starts (frame_server.warm_thumbs), one per highlight, and a highlight's
thumbnail may be its pass's mosaic (frame_server._thumb_mosaic). Asked for as a camera window asks for it, the
mosaic route (obs_mosaic.mosaic_webp) works out the plan of a pass the cache does not hold, draws its first tile
and starts a thread that draws the others: with 15 highlight passes that was a server nobody had sent a request
taking tens of GB. So a thumbnail asks with make=False:

  - a pass with no plan in the cache: None, and no plan, tile, thread, tile map or reel mosaic is made for it
    (the thumbnail is then the highlight's colour set or frame);
  - a pass the cache holds: the mosaic of its tiles made so far, as before, with nothing started behind it;
  - a camera window's own request (make left out) still makes the first tile and the tiles ahead.

  python web/test_thumb_draws_nothing.py
"""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import frame_server as fs  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reel  # noqa: E402

U = {"key": ("SATURN", "ISS_000SA_TESTPASS001_PRIME", "W", 0), "mosaic": True, "movie": False,
     "frames": [(k, f"W140000000{k}_1", "CL1,CL2") for k in range(5)]}
FRAME, N = U["frames"][3][1], 3
calls = []


def forbidden(name):
    def f(*a, **k):
        raise AssertionError(f"{name} was called for a thumbnail")
    return f


def noted(name, answer=None):
    def f(*a, **k):
        calls.append(name)
        return answer
    return f


def check(what, ok):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        sys.exit(1)


with tempfile.TemporaryDirectory() as cache:
    plan_file = os.path.join(cache, "pass", "plan.json")
    om.unit_of = lambda frame_id: (U, N) if frame_id == FRAME else None
    om._plan_path = lambda u, c: plan_file
    om._record = lambda u, c: None
    om.folder = lambda u, c: os.path.join(cache, "pass")
    reel.target_of = lambda: {}
    threads = threading.active_count()

    # ---- a pass the cache has no plan of: nothing is made
    for name in ("plan", "tile", "tiles_ahead", "_made_through", "_map_later", "warm", "layout", "_mosaic_at"):
        setattr(om, name, forbidden("obs_mosaic." + name))
    reel.mosaic_of = forbidden("reel.mosaic_of")
    reel.shot_webp = forbidden("reel.shot_webp")
    check("a pass with no plan here is not planned", not om.planned(U, cache))
    check("mosaic_webp make=False of a pass with no plan: None, nothing made",
          om.mosaic_webp(FRAME, 256, cache, None, ahead=0, make=False) is None)
    check("the thumbnail's mosaic of a pass with no plan: None, no reel mosaic drawn in its place",
          fs._thumb_mosaic(FRAME, 256, cache) is None)
    fs.color_webp = lambda ids, size, c: (b"colour", {})
    fs.webp = lambda frame_id, size, c: b"frame"
    check("its thumbnail is then the highlight's colour set",
          fs.pick_thumb({"mosaic": FRAME, "color": ["a", "b", "c"], "frame": FRAME}, 256, cache)
          == (b"colour", {"picked": "color", "ids": ["a", "b", "c"]}))
    check("or, with no colour set, its frame",
          fs.pick_thumb({"mosaic": FRAME, "frame": FRAME}, 256, cache) == (b"frame", {"picked": "frame", "id": FRAME}))
    check("no thread was started", threading.active_count() == threads)

    # ---- a pass the cache holds (its plan file, tiles 0..2 of 0..3 made): the mosaic so far, nothing behind it
    os.makedirs(os.path.dirname(plan_file))
    open(plan_file, "w").write("{}")
    om.plan = lambda u, c: {"display_scale": 1.0}
    om._has_tile = lambda u, j, c, p: j <= 2
    om.layout = lambda u, n, c: ({}, [], None, {}, [], f"L{n + 1}")
    om._mosaic_at = lambda u, n, size, c, slots=None, fmt="webp", out=None, made=None: (
        b"mosaic", {"mosaic": n + 1, "of": 5, "filters": 1})
    check("a pass with its plan file is planned", om.planned(U, cache))
    check("_made_so_far: the last tile made in a row, the plan only read", om._made_so_far(U, N, cache) == 2)
    made = om.mosaic_webp(FRAME, 256, cache, None, ahead=0, make=False)
    check("mosaic_webp make=False of a built pass: the mosaic of its tiles so far, one frame behind",
          made == (b"mosaic", {"mosaic": 3, "of": 5, "filters": 1, "behind": 1}))
    check("the thumbnail picks that mosaic",
          fs.pick_thumb({"mosaic": FRAME, "frame": FRAME}, 256, cache) == (b"mosaic", {"picked": "mosaic", "id": FRAME, "tiles": 5}))
    check("still no thread was started", threading.active_count() == threads)

    # ---- a built pass whose mosaic route answers None (nothing above black): the reel's mosaic as before
    om._mosaic_at = lambda *a, **k: None
    reel.mosaic_of = noted("reel.mosaic_of", None)
    check("a built pass with no mosaic picture asks the reel as before",
          fs._thumb_mosaic(FRAME, 256, cache) is None and calls == ["reel.mosaic_of"])

    # ---- a camera window's request (make left out): the first tile and the tiles ahead, as before
    del calls[:]
    om._mosaic_at = lambda u, n, size, c, slots=None, fmt="webp", out=None, made=None: (
        b"mosaic", {"mosaic": n + 1, "of": 5, "filters": 1})
    om._made_through = lambda u, n, c: calls.append("_made_through") or 3
    om.tiles_ahead = noted("tiles_ahead")
    om._map_later = noted("_map_later")
    om.warm = noted("warm")
    made = om.mosaic_webp(FRAME, 256, cache, None, ahead=2)
    check("a window's mosaic_webp makes through the frame, starts the tiles ahead, the tile map and the mosaics ahead",
          made == (b"mosaic", {"mosaic": 4, "of": 5, "filters": 1, "behind": 0})
          and calls == ["_made_through", "tiles_ahead", "_map_later", "warm"])
print("all passed")
