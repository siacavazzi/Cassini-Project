"""Fix A (spot check 7): a clouded body's colour mosaic shows colour only where the three filters' frames on top were
taken in one visit (obs_mosaic.mixes, set_times, set_mask, unmixed). Each filter's mosaic is drawn on its own, its
newest frame on top, so where a pointing took only some of the filters, or laps an hour apart overlap, the red and
green came from one visit and the blue from another while the clouds turned: Jupiter C23 NSMAP101's green and pink
blotches in the bands, the flat green and magenta blocks on 195RI HIPHASEC001's night side of Saturn.
- a visit that took RED and GRN only, over a whole set taken an hour before: mixed where it overlaps the old set
  (its BL1 is the old one), gray there; the old set's part outside it keeps its colour
- the same overlap with a whole new set: not mixed, colour everywhere
- a seam's sliver (narrower than MIX_LEAST) keeps its colour
- a visit that took only some of the filters is left out of the colour planes (visit_frames), so the colour under it
  is a whole visit's and the gray base draws it
- a repeated mosaic's laps (each a whole set at the same places) do not mix, nor do neighbouring pointings at their
  seam
- a moon (not clouded, its surface is redrawn) and a mosaic movie's picture (rolling) never mix
Run: python web/test_colour_visits.py"""
import os
import sys
import tempfile
import atexit, shutil  # noqa: E402
# every temporary folder and file this test makes goes in one folder of its own, removed when the test ends, passed
# or failed (test runs left GBs of folders in TMPDIR, and the Mini's boot drive filled, 2026-11-13)
tempfile.tempdir = tempfile.mkdtemp(prefix="cassini-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

cache = tempfile.mkdtemp()
SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}
Z = 1e6
COLOUR = ["RED", "GRN", "BL1"]


def make(target, shots):
    """A pass of shots [(filter, x offset, time)], each tile a flat 1024 px frame, and its tiles."""
    fr = [(f"x{i}", f"N{1355690000 + i}_1", f, t, 600, -ox, 0.0, Z) for i, (f, ox, t) in enumerate(shots)]
    u = {"key": (target, f"ISS_TEST_VISITS_{len(shots)}_{shots[-1][2]:.0f}", "N", 0), "frames": fr, "z": Z,
         "movie": False, "mosaic": True, "last": shots[-1][2]}
    td = om._tiles(u, cache, SCALE)
    os.makedirs(td, exist_ok=True)
    tiles = []
    for i, (f, ox, t) in enumerate(shots):
        im = np.full((1024, 1024, 4), 255, np.uint8)
        im[..., :3] = 100 + 50 * COLOUR.index(f)
        Image.fromarray(im).save(f"{td}/{i}.png")
        tiles.append({"n": i, "id": fr[i][1], "filter": f, "t": t, "offset": [ox, 0.0], "box": [-512, -512, 1024, 1024]})
    return u, tiles


def mask_of(u, tiles):
    p = {"display_scale": SCALE, "k": 0.25}
    rect = (-512, -512, 1536, 1024)
    shape = (256, 384)
    times = [om.set_times(shape, om.placed_tiles(u, p, [t for t in tiles if t["filter"] == f], rect, cache)) for f in COLOUR]
    return om.set_mask(times, p["k"])


# an old whole set at x 0, an hour later RED and GRN only at x 512: the overlap (canvas columns 128..256) mixes
old = [("BL1", 0.0, 0.0), ("GRN", 0.0, 60.0), ("RED", 0.0, 120.0)]
u, tiles = make("JUPITER", old + [("RED", 512.0, 3600.0), ("GRN", 512.0, 3660.0)])
assert om.mixes(u, {}, tiles, COLOUR)
m = mask_of(u, tiles)
assert m is not None and m[:, 140:250].all(), "the overlap mixes an hour-old blue with new red and green"
assert not m[:, :120].any(), "the old set's own part keeps its colour"
assert not m[:, 260:].any(), "past the old set only two filters: no colour there anyway, nothing to leave out"

# the same overlap with a whole new set: one visit on top everywhere
u2, tiles2 = make("JUPITER", old + [("RED", 512.0, 3600.0), ("GRN", 512.0, 3660.0), ("BL1", 512.0, 3720.0)])
m2 = mask_of(u2, tiles2)
assert m2 is None, "every place shows one visit's three frames"

# a sliver: the new whole set's BL1 a few px short of its RED and GRN (registration), the old BL1 shows in a thin strip
u3, tiles3 = make("JUPITER", old + [("RED", 512.0, 3600.0), ("GRN", 512.0, 3660.0), ("BL1", 520.0, 3720.0)])
assert mask_of(u3, tiles3) is None, "a seam's sliver keeps its colour"

# a repeated mosaic, a whole set at the same place every lap an hour apart (Saturn 3x3): only the newest lap shows,
# nothing mixes (and so no luminance base is drawn under it)
u5, tiles5 = make("SATURN", old + [("BL1", 0.0, 3600.0), ("GRN", 0.0, 3660.0), ("RED", 0.0, 3720.0)])
assert not om.mixes(u5, {}, tiles5, COLOUR)

# neighbouring pointings of one lap, whole sets 15 min apart, overlapping only along their seam (60 px): no mix
u6, tiles6 = make("SATURN", [("BL1", 0.0, 0.0), ("GRN", 0.0, 60.0), ("RED", 0.0, 120.0),
                             ("BL1", 964.0, 900.0), ("GRN", 964.0, 960.0), ("RED", 964.0, 1020.0)])
assert not om.mixes(u6, {}, tiles6, COLOUR)

# a moon's tiles mix only where surface reprojection decided to keep them as taken ("as_taken", SURFACE_TAKEN: the
# redrawing would distort them, Phoebe's closest pass); redrawn tiles, or tiles it could not redraw for want of
# kernels, are drawn as at the pass's one moment and never mix; nor does a mosaic movie's picture
u4, tiles4 = make("RHEA", old + [("RED", 512.0, 3600.0), ("GRN", 512.0, 3660.0)])
assert not om.mixes(u4, {}, tiles4, COLOUR)
assert om.mixes(u4, {}, [dict(t, as_taken=True) for t in tiles4], COLOUR)
assert not om.mixes(u, {}, [dict(t, base=False) for t in tiles], COLOUR)
# the drawn mask too: tiles of two visits, none kept as taken, all at one moment, so set_mask finds nothing
times = [np.full((8, 8), om.drawn_time(u4, t)) for t in tiles4[:3]]
assert om.set_mask(times, 1.0) is None
times = [np.full((8, 8), om.drawn_time(u4, dict(t, as_taken=True))) for t in (tiles4[0], tiles4[1], tiles4[-1])]
assert len({float(a[0, 0]) for a in times}) > 1
# with the surface step off (Settings > Processing) a moon mosaics as it always did: no mix
import calibration  # noqa: E402
with calibration.stepping("surface"):
    assert not om.mixes(u4, {}, [dict(t, as_taken=True) for t in tiles4], COLOUR)
assert not om.mixes(u, {}, [dict(t, base=False) for t in tiles], COLOUR)

# unmixed leaves the colour out where it mixes and gray lies under it; over_grey then draws the gray there
colour = np.zeros((256, 384, 4), np.uint8)
colour[:, :256] = (200, 100, 50, 255)
grey = np.zeros((256, 384, 4), np.uint8)
grey[:, :] = (120, 120, 120, 255)
grey[::2, :, :3] = 60   # the gray's own detail: lines the flat colour does not have
out = om.over_grey(om.unmixed(colour, m, grey), grey, 0.25).astype(int)
assert abs(out[128, 200, 0] - out[129, 200, 0]) > 20, "the mixed part shows the gray's own picture"
assert abs(out[128, 20, 0] - out[129, 20, 0]) < 3 and out[128, 20, 0] > out[128, 20, 2] + 100, "the old set's own part keeps its colour"
assert om.unmixed(colour, None, grey) is colour
# visit_frames: a visit that took RED and GRN only is left out of the colour (drawn in the gray), a whole set kept
assert om.visit_frames(u, COLOUR) == frozenset({0, 1, 2}), om.visit_frames(u, COLOUR)
assert om.visit_frames(u2, COLOUR) == frozenset(range(6))
assert om.visit_tiles(u2, tiles2, COLOUR) is tiles2
assert [t["n"] for t in om.visit_tiles(u, tiles, COLOUR)] == [0, 1, 2]
assert om.visit_frames(u4, COLOUR) == frozenset(range(5)), "a moon keeps every frame"
print("ok")
