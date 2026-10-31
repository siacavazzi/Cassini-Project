"""Synthetic check of Auto center on stills (frame_server.centred, obs_mosaic.hold_of).
Centred is centred (Sam, 2026-10-30): a still of a centred pass has the body's centre in its middle even where the
frame cuts the disk (Saturn's centre is below the WAC frame in the stares of 2005-07-03, 010SA_1X6MOVIED00*); before,
the shift stopped at the frame's data edge, so the still stayed where the frame put it and jumped with each pointing.
A north-up pass's stills hold the body where it sits on average over the pass; a pass whose frames point further
apart (a mosaic) is not held, and a still whose own SPICE place disagrees with the pass's is drawn as before.
Run: python web/test_centre_hold.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402
import frame_server as fs  # noqa: E402

om.reel.north_angles = lambda ids: {}
Z = 1.0e6
# five pointings of a stare: the frame's middle steps 100 px right each time, the body's centre 700 px below it
PLACES = [(-200 + 100 * i, -700) for i in range(5)]
U = {"z": Z, "frames": [(None, f"W{i}", "MT3", float(i), 890, float(x), float(y), Z) for i, (x, y) in enumerate(PLACES)]}


def test_hold_of():
    holds = [om.hold_of(U, n) for n in range(5)]
    assert all(h for h in holds)
    assert [h["at"] for h in holds] == [[float(x), float(y)] for x, y in PLACES]
    assert [h["hold"] for h in holds] == [[200.0 - 100 * i, 0.0] for i in range(5)]
    wide = {"z": Z, "frames": [(None, f"M{i}", "CL1", float(i), 650, 900.0 * i, 0.0, Z) for i in range(3)]}
    assert om.hold_of(wide, 0) is None            # a mosaic's frames point a frame or more apart
    assert om.hold_of(dict(U, frames=U["frames"][:4] + [U["frames"][4][:7] + (0,)]), 4) is None   # not placed


def still(n, offset):
    """processed_frame's answer for frame n: the frame on a 2048 canvas with its middle at the canvas middle, and a
    bright body whose centre is offset from it (frame_offset: the frame's middle from the body's centre)."""
    W = 2048
    img = np.zeros((W, W, 4), np.uint8)
    c = (W - 1) / 2
    img[int(c - 512):int(c + 512), int(c - 512):int(c + 512), 3] = 255
    yy, xx = np.mgrid[0:W, 0:W]
    bx, by = c - offset[0], c - offset[1]
    disk = ((xx - bx) ** 2 + (yy - by) ** 2 < 500 ** 2) & (img[..., 3] > 0)
    img[disk, :3] = 200
    return img, None, {"frame_offset": [float(offset[0]), float(offset[1])]}


def body_top(out):
    """The column and row of the body's top (its centre's column: the top of its limb) in a picture (RGBA)."""
    a = np.asarray(out)[..., 0] > 100
    rows = np.flatnonzero(a.any(1))
    return (round(float(np.flatnonzero(a[rows[0]]).mean())), int(rows[0])) if len(rows) else None


def body_x(out):
    top = body_top(out)
    return top and top[0]


def centred_all(views, offsets):
    xs = []
    for n, (v, off) in enumerate(zip(views, offsets)):
        fs.color_image.processed_frame = lambda paths, off=off, n=n: still(n, off)
        im, rep = fs.centred([f"W{n}"], v)
        xs.append((body_x(im), rep))
    return xs


def test_centred_is_centred():
    centre = {"centre": True, "side": 1024, "radius": 500}
    tops = []
    for n, off in enumerate(PLACES):
        fs.color_image.processed_frame = lambda paths, off=off, n=n: still(n, off)
        im, rep = fs.centred([f"W{n}"], centre)
        tops.append(body_top(im))
        assert "centre_shift_capped" not in rep
    # the body's centre (its top's column, its top 500 px above it) in the middle of every still
    assert all(abs(x - 511.5) <= 1 and abs(y - (511.5 - 500)) <= 1 for x, y in tops), tops


def test_centred_holds():
    offsets = PLACES
    north = {"centre": False, "north": True, "side": 1024}
    before = centred_all([north] * 5, offsets)
    after = centred_all([dict(north, **om.hold_of(U, n)) for n in range(5)], offsets)
    bx, ax = [x for x, _ in before], [x for x, _ in after]
    assert max(bx) - min(bx) >= 400, bx          # before: the body moves 100 px a pointing
    assert max(ax) - min(ax) <= 1, ax            # held: it stays put
    assert all("held" in rep for _, rep in after)
    # a still whose own SPICE place disagrees with the pass's is drawn as before
    bad = dict(north, **om.hold_of(U, 0))
    bad["at"] = [bad["at"][0] + 200, bad["at"][1]]
    (x, rep), = centred_all([bad], offsets[:1])
    assert x == bx[0] and "hold_skipped" in rep
    # held pictures are cached apart from the others
    assert fs.centre_folder("c", north) != fs.centre_folder("c", dict(north, **om.hold_of(U, 0)))


if __name__ == "__main__":
    test_hold_of()
    test_centred_is_centred()
    test_centred_holds()
    print("ok")
