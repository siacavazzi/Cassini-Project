"""Synthetic check of Auto center's hold (obs_mosaic.hold_of, frame_server.centred): a still Auto center cannot
centre (the body's centre off the frame, as Saturn's is in the WAC stares of 2005-07-03, 010SA_1X6MOVIED00*) keeps
the body where it sits on average over the pass, so it holds still from picture to picture; before, it stayed where
the frame put it and jumped with each pointing. A pass whose frames point further apart (a mosaic) is not held, and
a still whose own SPICE place disagrees with the pass's is drawn as before.
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


def body_x(out):
    """The column of the body's top (its centre's column: the top of its limb) in a centred picture (RGBA)."""
    a = np.asarray(out)[..., 0] > 100
    rows = np.flatnonzero(a.any(1))
    return round(float(np.flatnonzero(a[rows[0]]).mean())) if len(rows) else None


def centred_all(views, offsets):
    xs = []
    for n, (v, off) in enumerate(zip(views, offsets)):
        fs.color_image.processed_frame = lambda paths, off=off, n=n: still(n, off)
        im, rep = fs.centred([f"W{n}"], v)
        xs.append((body_x(im), rep))
    return xs


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
    test_centred_holds()
    print("ok")
