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
        fs.color_image.processed_frame = lambda paths, off=off, n=n, **k: still(n, off)
        im, rep = fs.centred([f"W{n}"], v)
        xs.append((body_x(im), rep))
    return xs


def test_centred_is_centred():
    centre = {"centre": True, "side": 1024, "radius": 500}
    tops = []
    for n, off in enumerate(PLACES):
        fs.color_image.processed_frame = lambda paths, off=off, n=n, **k: still(n, off)
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


def test_pass_turn():
    """Stills are turned only to the pass's own orientation (Sam 2026-11-08: tilted pictures, corners cut): the
    circular mean of its frames' turns, a frame in no pass its own; the hold is on those turned axes."""
    angles = {"W0": 359.0, "W1": 1.0, "W2": 3.0, "W3": -1.0, "W4": 0.0}
    om.reel.north_angles = lambda ids: {i: angles[i] for i in ids if i in angles}
    try:
        assert abs(om.pass_turn(U) - 0.4) < 0.01
        assert om.pass_turn(frame_id="W2") == 3.0
        assert om.pass_turn(frame_id="X") == 0.0
        # every frame turned the same 30 degrees: the hold on the turned axes is the north-up hold seen 30 degrees off,
        # and with the pass's own turn taken out it is the hold on the camera's axes (all frames at 0)
        angles.update({f"W{i}": 30.0 for i in range(5)})
        turned = [om.hold_of(U, n, om.pass_turn(U)) for n in range(5)]
        angles.update({f"W{i}": 0.0 for i in range(5)})
        plain = [om.hold_of(U, n) for n in range(5)]
        for a, b in zip(turned, plain):
            assert np.allclose(a["hold"], b["hold"], atol=0.15) and np.allclose(a["at"], b["at"], atol=0.15)
        # movies and mosaics are drawn on the same axes: what a view keeps of the frames (frames_seen) with the pass's
        # turn taken out is the same as for a camera that had north up all along
        angles.update({f"W{i}": 30.0 for i in range(5)})
        on_t, pts_t = om.frames_seen(U["frames"], Z, 30.0)
        angles.update({f"W{i}": 0.0 for i in range(5)})
        on_0, pts_0 = om.frames_seen(U["frames"], Z, 0.0)
        assert on_t == on_0 and np.allclose(pts_t, pts_0, atol=1e-6)
    finally:
        om.reel.north_angles = lambda ids: {}


def test_quarter_snap():
    """The pass's axes are the camera's own turned the quarter that brings north closest to the top (Sam 2026-11-08:
    no tilt, but planets and moons came out sideways): never more than 45 degrees from north up, always a whole
    number of quarters from the camera's square; a pass that shows no body keeps the camera's axes."""
    angles = {}
    om.reel.north_angles = lambda ids: {i: angles[i] for i in ids if i in angles}
    # the body's centre on the frames (a Saturn stare, a moon's disk), each frame 100 px apart
    on = {"z": Z, "key": ("RHEA", "OBS", "N"),
          "frames": [(None, f"R{i}", "CL1", float(i), 650, -100.0 * i, 0.0, Z) for i in range(3)]}
    try:
        for m, want in ((0.0, 0.0), (30.0, 30.0), (44.0, 44.0), (46.0, -44.0), (100.0, 10.0), (-120.0, -30.0),
                        (155.7, -24.3), (-170.0, 10.0), (-135.5, -45.5 + 90.0)):
            angles.update({f"R{i}": m for i in range(3)})
            turn = om.pass_turn(on)
            assert abs(turn - want) < 0.01, (m, turn, want)
            assert abs(turn) <= 45.0
            # drawn turned m - turn: a whole number of quarters
            assert abs(((m - turn) / 90.0) - round((m - turn) / 90.0)) < 1e-6
            assert om.quarter_of(turn, m) == int(round((m - turn) / 90.0)) % 4
        # the body far off every frame (a star field with the body named its target): the camera's own axes
        off = dict(on, frames=[fr[:5] + (5000.0, 5000.0, Z) for fr in on["frames"]])
        angles.update({f"R{i}": 100.0 for i in range(3)})
        assert om.pass_turn(off) == 100.0
        # Saturn's rings count as Saturn in view: frames 100,000 km from its centre, off its disk
        k = 100000 / (Z * om.IFOV["N"])
        rings = {"z": Z, "key": ("SATURN", "RING", "N"), "frames": [(None, "S0", "CL1", 0.0, 650, k, 0.0, Z)]}
        angles["S0"] = 100.0
        assert om.pass_turn(rings) == 10.0
        far = dict(rings, frames=[(None, "S0", "CL1", 0.0, 650, 3 * k, 0.0, Z)])
        assert om.pass_turn(far) == 100.0
        # a frame in no pass: its own turn, snapped when its body is on it
        om.reel.geometry = lambda ids: {"R0": (0.0, 0.0, Z)}
        angles["R0"] = 100.0
        assert om.pass_turn(frame_id="R0", target="RHEA", cam="N") == 10.0
        assert om.pass_turn(frame_id="R0", target=None, cam="N") == 100.0
        assert om.view_shown({"centre": False, "quarter": 1}) and not om.view_shown({"centre": False})
        # a frame the camera rolled far from its pass: shown square on the pass's quarter while north stays within
        # 45 degrees of the top, else on its own nearest quarter
        assert om.frame_quarter(30.0, 0) == 0 and om.frame_quarter(60.0, 0) == 1 and om.frame_quarter(-170.0, 1) == 2
        assert om.frame_quarter(120.0, 1) == 1 and om.frame_quarter(-100.0, 3) == 3
    finally:
        om.reel.north_angles = lambda ids: {}


def test_surface_turn():
    """surface_field on a pass drawn turn degrees short of north up: places go onto the sky and shifts come back, so a
    field that looks the same however the sky is turned (a swell and a swirl round the body's centre) comes out the
    same on the turned canvas, and one that does not (a drift east) comes out turned."""
    class RP:
        field = None

        def sky_field(self, epoch, view, x, y, km_px):
            dx, dy = self.field(x, y)
            return dx, dy, np.ones_like(x)
    rp, t = RP(), {"offset": [100.0, -40.0], "box": [-60, -60, 120, 120]}
    rp.field = lambda x, y: (0.01 * x - 0.02 * y, 0.01 * y + 0.02 * x)
    a = om.surface_field(rp, None, None, (120, 120), t, 1.0, 0.0)
    b = om.surface_field(rp, None, None, (120, 120), t, 1.0, 37.0)
    assert all(np.allclose(p, q, atol=1e-3) for p, q in zip(a, b))
    rp.field = lambda x, y: (np.full_like(x, 5.0), np.zeros_like(y))
    dx, dy, _ = om.surface_field(rp, None, None, (120, 120), t, 1.0, 90.0)
    # (on a canvas turned a quarter, a shift along the sky's x lies along the canvas's y)
    assert np.allclose(np.hypot(dx, dy), 5.0) and np.allclose(dx, 0.0, atol=1e-5)


if __name__ == "__main__":
    test_surface_turn()
    test_hold_of()
    test_pass_turn()
    test_quarter_snap()
    test_centred_is_centred()
    test_centred_holds()
    print("ok")
