#!/usr/bin/env python3
"""A Highlights thumbnail draws nothing: its pass's picture is shrunk from one the cache already holds.

The thumbnails are made as the server starts (frame_server.warm_thumbs), one per highlight, in a server nobody has
asked for anything, and a highlight's thumbnail may be its pass's picture (frame_server._thumb_mosaic). Asked for
as a camera window asks, the mosaic route (obs_mosaic.mosaic_webp) composed the pass's whole mosaic from its tiles
at the thumbnail's size, which no build keeps (10 GB in 50 s for the 728-frame north polar movie, never finished,
again at every start), and for a pass the cache did not hold worked out its plan, drew its first tile and started
a thread drawing the rest. So a thumbnail asks obs_mosaic.kept_webp:

  - a pass with no plan in the cache: None, and no plan, tile, layout, mosaic, thread or reel mosaic is made for
    it; its thumbnail is the highlight's colour set, or its frame, or the frame its mosaic hint names;
  - a mosaic pass the build made: its mosaic so far as kept at 512 (or 1024), shrunk; the kept picture itself
    when the cache holds it at the thumbnail's size; nothing is composed;
  - a mosaic movie the build made: its picture at that frame (rolling_layout) as kept, shrunk; the pass's layout
    as a mosaic is not worked out;
  - a pass with a tile up to the frame not made, or with no picture kept: None;
  - a camera window's own request (mosaic_webp) still makes the first tile and the tiles ahead.

  python web/test_thumb_draws_nothing.py
"""
import io
import json
import os
import sys
import tempfile
import threading

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import frame_server as fs  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reel  # noqa: E402

U = {"key": ("SATURN", "ISS_000SA_TESTPASS001_PRIME", "W", 0), "mosaic": True, "movie": False, "kind": "mosaic",
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


def keep(path, size, report):
    """a picture of a given size kept at path, with its report beside it; its bytes"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 60, 30)).save(buf, "WEBP", quality=95)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())
    with open(path[:-len("webp")] + "json", "w") as fh:
        json.dump(report, fh)
    return buf.getvalue()


with tempfile.TemporaryDirectory() as cache:
    plan_file = os.path.join(cache, "pass", "plan.json")
    om.unit_of = lambda frame_id: (U, N) if frame_id == FRAME else None
    om._plan_path = lambda u, c: plan_file
    om._record = lambda u, c: None
    om.folder = lambda u, c: os.path.join(cache, "pass")
    reel.target_of = lambda: {}
    threads = threading.active_count()
    # what a thumbnail must never reach: the makers of tiles and mosaics, and everything started in the background
    for name in ("tile", "tiles_ahead", "_made_through", "_map_later", "warm", "so_far", "_make_mosaic", "_mosaic_at",
                 "mosaic_webp", "rolling_webp", "_rolling_picture", "filter_mosaic"):
        setattr(om, "_real_" + name, getattr(om, name))
        setattr(om, name, forbidden("obs_mosaic." + name))

    # ---- a pass the cache has no plan of: nothing is made
    for name in ("plan", "layout", "rolling_layout"):
        setattr(om, name, forbidden("obs_mosaic." + name))
    reel.mosaic_of = forbidden("reel.mosaic_of")
    reel.shot_webp = forbidden("reel.shot_webp")
    check("a pass with no plan here is not planned", not om.planned(U, cache))
    check("kept_webp of a pass with no plan: None, nothing made", om.kept_webp(FRAME, 256, cache) is None)
    check("the thumbnail's pass picture: None, no reel mosaic drawn in its place", fs._thumb_mosaic(FRAME, 256, cache) is None)
    fs.color_webp = lambda ids, size, c: (b"colour", {})
    fs.webp = lambda frame_id, size, c: b"frame " + frame_id.encode()
    check("its thumbnail is then the highlight's colour set",
          fs.pick_thumb({"mosaic": FRAME, "color": ["a", "b", "c"], "frame": "N1_1"}, 256, cache)
          == (b"colour", {"picked": "color", "ids": ["a", "b", "c"]}))
    check("or, with no colour set, its frame",
          fs.pick_thumb({"mosaic": FRAME, "frame": "N1_1"}, 256, cache) == (b"frame N1_1", {"picked": "frame", "id": "N1_1"}))
    check("or, with a mosaic hint alone, the frame that hint names",
          fs.pick_thumb({"mosaic": FRAME}, 256, cache) == (b"frame " + FRAME.encode(), {"picked": "frame", "id": FRAME}))
    check("no thread was started", threading.active_count() == threads)

    # ---- a mosaic pass the build made: its mosaic so far kept at 512 and 1024, not at 256
    os.makedirs(os.path.dirname(plan_file))
    open(plan_file, "w").write("{}")
    made_tiles = [5]
    om.plan = lambda u, c: {"display_scale": 1.0}
    om._has_tile = lambda u, j, c, p: j < made_tiles[0]
    om.layout = lambda u, n, c: calls.append("layout") or ({}, [], None, {}, [], f"CL1-CL2{n + 1}")
    report = {"kind": "mosaic", "mosaic": 4, "of": 5, "filters": 1}
    k512 = keep(om._mosaic_path(U, om.layout(U, N, cache), 512, cache), (512, 400), report)
    keep(om._mosaic_path(U, om.layout(U, N, cache), 1024, cache), (1024, 800), report)
    del calls[:]
    data, rep = om.kept_webp(FRAME, 256, cache)
    im = Image.open(io.BytesIO(data))
    check("kept_webp of a built mosaic pass: the kept 512 shrunk to 256, with its report, nothing composed",
          im.format == "WEBP" and im.size == (256, 200) and rep == report and calls == ["layout"])
    check("the thumbnail picks that mosaic",
          fs.pick_thumb({"mosaic": FRAME, "frame": "N1_1"}, 256, cache) == (data, {"picked": "mosaic", "id": FRAME, "tiles": 5}))
    check("asked at a size the cache holds, the kept picture itself", om.kept_webp(FRAME, 512, cache) == (k512, report))
    k256 = keep(om._mosaic_path(U, om.layout(U, N, cache), 256, cache), (256, 200), report)
    check("a picture kept at the thumbnail's size (made before) is the thumbnail as it was", om.kept_webp(FRAME, 256, cache) == (k256, report))
    check("still no thread was started", threading.active_count() == threads)

    # ---- a tile up to the frame not made, or no picture kept: None, and the layout is not worked out
    made_tiles[0] = 3
    del calls[:]
    check("a pass with a tile up to the frame not made: None, no layout", om.kept_webp(FRAME, 256, cache) is None and not calls)
    made_tiles[0] = 5
    om.layout = lambda u, n, c: ({}, [], None, {}, [], "another-name")
    check("a pass whose picture is kept at no size: None", om.kept_webp(FRAME, 256, cache) is None)
    om.layout = lambda u, n, c: None
    check("a pass with nothing placed yet: None", om.kept_webp(FRAME, 256, cache) is None)

    # ---- a mosaic movie the build made: its picture at that frame, kept at 512; never its layout as a mosaic
    U["kind"] = "mosaic_movie"
    om.layout = forbidden("obs_mosaic.layout")
    om.rolling_layout = lambda u, n, c, laps=1, made_only=False, skipped=None, fade=(0, 0): (
        calls.append(("rolling_layout", laps, made_only)) or ({}, [], None, {}, [], f"lap-1-{n}"))
    rolled = {"kind": "mosaic_movie", "mosaic": 12, "of": 312, "filters": 3}
    keep(om._rolling_path(U, om.rolling_layout(U, N, cache), 512, cache), (500, 512), rolled)
    del calls[:]
    data, rep = om.kept_webp(FRAME, 256, cache)
    check("kept_webp of a built mosaic movie: its kept picture at that frame shrunk, made-only, a time-lapse",
          Image.open(io.BytesIO(data)).size == (250, 256) and rep == rolled and calls == [("rolling_layout", 1, True)])
    check("the thumbnail picks it, over the colour set too (three filters)",
          fs.pick_thumb({"mosaic": FRAME, "color": ["a", "b", "c"]}, 256, cache)
          == (data, {"picked": "mosaic", "id": FRAME, "tiles": 312}))
    U["kind"] = "mosaic"

    # ---- a camera window's request: the first tile and the tiles ahead, as before
    del calls[:]
    om.mosaic_webp = om._real_mosaic_webp
    om.layout = lambda u, n, c: ({}, [], None, {}, [], f"CL1-CL2{n + 1}")
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
