"""Movie strobing, pumping and panel flicker (spot check round 2, 2026-10-29), on the Mini's probe of the passes
(web/frames/strobe_probe.py):
- an over-exposed frame (most of it saturated) between frames of its filter that are not is held like a partial frame
  (obs_mosaic.unfit, held_of): 201RI DRNGMOV001 alternates 2 s frames (~17% saturated) with 8.2 s ones (~75%), whose
  rings drew as a flat slab lifted 4x by exposure normalization; a run of over-exposed frames plays as it is
- a frame saturated all over is never shown, and is left out of a mosaic (101SA SPOLEDYN001 W: flat panels dark or
  bright by exposure time, flickering lap to lap)
- a frame that can't be calibrated (8LSB) among frames that can is held (Phoebe 2004-06-12: UV3/IR3 flashed grey)
- a small body's frame lit all over by stray light (no dark sky) takes its own black from everything off the disk
  (tile_scale's disk), so the veil goes (Pallene 139PL, Hati 182OT, Kiviuq 112OT); a frame with dark sky, a plume
  movie's Enceladus (64 px) and a pass without a small body keep the rule they had
Run: python web/test_movie_strobe.py"""
import json, os, sys, tempfile  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402
import color_image  # noqa: E402

placed = {"offset": [0.0, 0.0], "box": [0, 0, 8, 8]}


def fr(fs):
    return [(f"p{i}", f"N{1600000000 + i}_1", f, 1000.0 + 70 * i, 600, 0, 0, 1e6) for i, f in enumerate(fs)]


def shown(frames, tiles):
    tile_of = lambda j: tiles[j]
    return [om.held_of([f[2] for f in frames], n, lambda j: om.unfit(frames, j, tile_of),
                       lambda j: "offset" in tiles[j] and not om.unfit(frames, j, tile_of)) for n in range(len(frames))]


# ---- DRNGMOV001: short (sat ~0.17) and long (~0.75) frames of one filter, alternating
frames = fr(["CL1/CL2"] * 8)
tiles = [{**placed, "saturated": 0.17 if n % 2 == 0 else 0.75} for n in range(8)]
got = shown(frames, tiles)
assert got == [0, 0, 2, 2, 4, 4, 6, 6], got
print("alternating long exposures held:", got)

# ... a run of over-exposed frames (the camera's own view: a bright limb coming in) plays; one alone in it is held
tiles = [{**placed, "saturated": s} for s in (0.1, 0.1, 0.7, 0.7, 0.7, 0.1, 0.7, 0.1)]
got = shown(frames, tiles)
assert got == [0, 1, 2, 3, 4, 5, 5, 7], got
# ... other filters between do not count: the neighbours are the filter's own frames
frames2 = fr(["CL1/CL2", "GRN", "CL1/CL2", "GRN", "CL1/CL2"])
tiles2 = [{**placed, "saturated": s} for s in (0.1, 0.9, 0.8, 0.9, 0.1)]
got = shown(frames2, tiles2)
assert got == [0, 1, 0, 3, 4], got
# ... a pass over-exposed all through keeps its frames (nothing whole to hold)
assert shown(frames, [{**placed, "saturated": 0.8}] * 8) == list(range(8))
print("runs play, a lone over-exposed frame is held")

# ---- saturated all over: held whatever is round it
tiles = [{**placed, "saturated": s} for s in (0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0)]
got = shown(frames, tiles)
assert got == [0, 0, 0, 0, 4, 5, 5, 7], got

# ---- 8LSB among calibrated frames: held; partial frames still are; untouched frames are not
frames3 = fr(["UV3", "UV3", "UV3", "GRN", "GRN"])
tiles3 = [{**placed, "calibrated": True}, {**placed, "calibrated": False}, {**placed, "calibrated": True, "lost": 0.7},
          {**placed, "calibrated": False}, {**placed}]
got = shown(frames3, tiles3)
assert got == [0, 0, 0, 3, 4], got   # (the first GRN frame has nothing earlier to hold: shown)
assert not om.unfit(frames3, 0, lambda j: {"why": "not placed"}) and not om.unfit(frames3, 4, lambda j: tiles3[j])
print("8LSB and partial frames held")

# ---- the steady table's "partial" list (the page's heldOf) is unfit's
assert [m for m in range(8) if om.unfit(frames, m, lambda j: [{**placed, "saturated": 0.17 if n % 2 == 0 else 0.75}
                                                              for n in range(8)][j])] == [1, 3, 5, 7]

# ---- small bodies
u = {"key": ("PALLENE", "OBS", "N", 0)}
assert om.small_body(u, ("p", "N1_1", "CL1", 0, 0, 340.0, -100.0, 36683.0)) is not None          # 10 px
assert om.small_body({"key": ("ENCELADUS", "OBS", "N", 0)}, ("p", "N1_1", "CL1", 0, 0, -9, -577, 652309.0)) is None  # 64 px
assert om.small_body({"key": ("SATURN", "OBS", "N", 0)}, ("p", "N1_1", "CL1", 0, 0, 0, 0, 1.9e6)) is None
assert om.small_body({"key": ("S_RINGS", "OBS", "N", 0)}, ("p", "N1_1", "CL1", 0, 0, 0, 0, 1e6)) is None   # no disk
assert om.small_body(u, ("p", "N1_1", "CL1", 0, 0, 0, 0, 0)) is None                                     # no place

rng = np.random.default_rng(3)


def veiled(level, x=340.0, y=-100.0):
    """A Pallene frame: stray light all over (no dark sky), a 10 px moon, a few stars."""
    iof = level * (1 + 0.1 * np.linspace(0, 1, 1024)[None, :]) + rng.normal(0, 0.004 * level, (1024, 1024))
    iof = iof.astype(np.float32)
    cy, cx = int(511.5 - y), int(511.5 - x)
    iof[cy - 8:cy + 8, cx - 8:cx + 8] = 3 * level       # the moon
    iof[rng.integers(0, 1024, 30), rng.integers(0, 1024, 30)] = 5 * level   # stars
    return iof


pal = {"blacks": {"CL1/CL2": 0.12}, "white": 0.11, "gamma": 3.0}
disk = (340.0, -100.0, 10.0)
before = om.tile_scale(pal, "CL1/CL2", True)
assert "black_of" not in before                                     # no sky_tops: the pass's black, as before
black_of = om.tile_scale(pal, "CL1/CL2", True, disk=disk)["black_of"]
for level in (0.2, 0.15):
    iof = veiled(level)
    got = black_of(iof)
    q = iof[::4, ::4]
    off = ~om._disk_mask(q.shape, iof.shape, *disk)
    assert got is not None and np.mean(q[off] > got["black"]) < 0.06, (level, got)      # the veil under black
    assert got["black"] < 3 * level                                                     # the moon over it
assert black_of(veiled(0.07)) is None                               # never lowered: a dim frame keeps the pass's
# a frame with dark sky keeps the old rule (no fallback needed)
dark = np.full((1024, 1024), 0.001, np.float32) + rng.normal(0, 0.0002, (1024, 1024)).astype(np.float32)
dark[400:600, 400:600] = 0.5        # a body bright enough for the sky test to find the dark sky
kept = om.tile_scale({**pal, "blacks": {"CL1/CL2": 0.0}, "sky_tops": {"CL1/CL2": 0.0005}}, "CL1/CL2", True)["black_of"](dark)
also = om.tile_scale({**pal, "blacks": {"CL1/CL2": 0.0}, "sky_tops": {"CL1/CL2": 0.0005}}, "CL1/CL2", True, disk=disk)["black_of"](dark)
assert kept == also, (kept, also)
# without a small body (the plume movie's Enceladus) a veiled frame keeps the pass's black, as before
assert om.tile_scale({**pal, "sky_tops": {"CL1/CL2": 0.001}}, "CL1/CL2", True)["black_of"](veiled(0.2)) is None
print("small body: the stray-light veil under black, the moon over it")

# ---- a mosaic leaves out a tile saturated all over; a movie keeps it (and holds it, unfit)
cache = tempfile.mkdtemp()
SCALE = {"blacks": {"CL1/CL2": 0.0}, "white": 1, "gamma": 3}
fm = fr(["CL1/CL2"] * 2)


def made(u, share):
    rep = {"frame_offset": [0.0, 0.0], "calibrated": True, "stacked": [1], **({"saturated_share": share} if share else {})}
    color_image.processed_frame = lambda *a, **k: (np.full((1024, 1024, 4), 200, np.uint8), None, dict(rep))
    base = os.path.join(cache, f"t{len(os.listdir(cache))}", "0")
    om._register = lambda *a, **k: None
    return om._tile_made(u, 0, cache, SCALE, base)


mos = {"key": ("SATURN", "SPOLEDYN", "W", 1), "frames": fm, "z": 1e6, "mosaic": True, "movie": False}
mov = {**mos, "mosaic": False, "movie": True}
assert "offset" not in made(mos, 1.0) and "saturated all over" in made(mos, 1.0)["why"]
assert "offset" in made(mos, 0.6) and made(mos, 0.6)["saturated"] == 0.6
t = made(mov, 1.0)
assert "offset" in t and t["saturated"] == 1.0
assert "saturated" not in made(mos, 0.0)
print("mosaic: a tile saturated all over left out; a movie keeps it (held)")
print("ok")
