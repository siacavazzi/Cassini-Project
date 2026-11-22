#!/usr/bin/env python3
"""Checks of colour-set derotation (PR 614) that need no archive: color_image.derotated keeps a picture's type and
passes channels without a field through; color_image._squared cuts a channel's lost edges straight and no further;
only the giant planets are derotated (obs_mosaic.DEROTATE_BODIES); obs_mosaic.derotated_tiles leaves ring mosaics,
pointings placed by matching their clouds and tiles past DEROTATE_SPAN alone; reproject.spin_field turns Saturn's
clouds and not its rings in front of them. Run: python web/frames/test_derotation.py"""
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "..")]
import color_image as ci  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reproject as rp  # noqa: E402

STEP = ci.DEROTATE_STEP


def shift_field(shape, dx, dy):
    """A field moving every place by (dx, dy), on derotation's grid, weight 1 everywhere."""
    h, w = shape
    gh, gw = h // STEP + 2, w // STEP + 2
    return (np.full((gh, gw), dx, np.float32), np.full((gh, gw), dy, np.float32), np.ones((gh, gw), np.float32), abs(dx))


def test_derotated_types_and_none():
    rgba = np.zeros((64, 64, 4), np.uint8)
    rgba[20:30, 20:30] = 200
    plane = np.zeros((64, 64), np.float32)
    plane[20:30, 20:30] = 0.25
    f = shift_field((64, 64), 3.0, 0.0)
    out = ci.derotated([None, f, f], [rgba, rgba, plane])
    assert out[0] is rgba, "a channel without a field is passed through as it is"
    assert out[1].dtype == np.uint8 and out[1].shape == rgba.shape
    assert out[2].dtype == np.float32 and out[2].shape == plane.shape, "a float plane stays a float plane"
    assert 0.2 < out[2][25, 18] and out[2][25, 28] < 0.05, "looked up 3 px to the right: the square moves 3 px left"
    assert abs(float(out[2].max()) - 0.25) < 0.02, "calibrated light is not put on 0-255"
    assert ci.derotated([f], [None]) == [None]


def test_squared_straight():
    old = np.ones((200, 300), bool)
    old[:, :2] = False                       # the frame's own trimmed edge
    past = np.zeros_like(old)
    for x in range(300):                     # a slanted strip along the top, 10 to 19 rows deep, drawn from past the edge
        past[:10 + x // 30, x] = True
    new = old & ~past
    new[5, 40:200] = True                    # a ring's line across it, not moved: it pokes into the strip
    new[120, 50:250] = False                 # a lost line inside the frame, moved: not the edge's
    new[190, :] = False                      # and one near the bottom, across the whole frame: no strip either
    out = ci._squared(new, old, past)
    rows = np.nonzero(out.any(axis=1))[0]
    assert rows[0] == 19, rows[0]           # cut straight, just past the strip's deepest line (row 18)
    assert out[19:, 2:].sum() == new[19:, 2:].sum(), "nothing else is cut: the lost lines stay holes as they were"
    assert not out[:19].any(), "the ring's line is cut with the strip"
    assert ci._squared(old, old, np.zeros_like(old)) is old, "nothing looked past, nothing cut"


def test_squared_corners_belong_to_their_strip():
    old = np.ones((300, 300), bool)
    past = np.zeros_like(old)
    past[:40, :] = True                      # a 40 px strip along the top, its corners too
    out = ci._squared(old & ~past, old, past)
    assert out[40:, :].all(), "the sides beside it are not cut for the strip's corners"


def test_looked_past():
    old = np.ones((64, 64), bool)
    f = shift_field((64, 64), 5.0, 0.0)     # every place looks 5 px right
    past = ci._looked_past(f, old)
    assert past[:, -5:].all() and not past[:, :-5].any(), past.sum()


def test_derotation_helps():
    rng = np.random.default_rng(3)
    clouds = cv2.GaussianBlur(rng.random((256, 256)).astype(np.float32), (0, 0), 2)
    f = shift_field((256, 256), 9.0, 0.0)
    tracked = [clouds, clouds.copy()]                     # the camera followed the clouds: the same at the same pixels
    assert ci.derotation_helps([None, f], tracked, 0) is None, "redrawn they come apart: kept as taken"
    turned = [clouds, np.roll(clouds, 9, axis=1)]         # the clouds 9 px on in the second frame, where the field looks
    assert ci.derotation_helps([None, f], turned, 0)[1] is f, "redrawn they meet: derotated"


def test_eased_at_edges():
    h, w = 400, 600
    gy, gx = np.mgrid[0:h + STEP:STEP, 0:w + STEP:STEP].astype(np.float64)
    dx = np.full(gx.shape, 12.0, np.float32)            # every place looks 12 px right ...
    dy = np.where(gy < h / 2, -0.05, 0.05).astype(np.float32)   # ... and a hair up or down
    ex, ey = ci._eased_at_edges(dx, dy, gx, gy, h, w)
    inside = gx <= w - 1
    assert np.all(gx[inside] + ex[inside] <= w - 1 + 1e-6), "never looks past the right edge"
    assert np.all(ex[gx < w - 1 - 3 * 12] == 12), "the move is whole away from the edge it looks toward"
    assert np.all(ex[gx < 50] == 12), "the left edge, looked away from, leaves the move whole"
    assert np.all(np.abs(np.diff(ex, axis=0)) < 1e-6), "a tiny move across the bands does not cut the move along them"
    assert rp.field_stretch(ex, ey, np.ones_like(ex), STEP) <= om.SURFACE_STRETCH


class Label:
    def __init__(self, target):
        self.info = {"TARGET_NAME": target, "IMAGE_TIME": "2011-057T15:45:45"}


def test_only_giant_planets():
    assert {"SATURN", "JUPITER"} <= om.DEROTATE_BODIES
    for body in ("TITAN", "ENCELADUS", "RHEA", "MIMAS"):
        assert body not in om.DEROTATE_BODIES, body
        assert not om.derotates({"key": [body, "x", "N"]}), body
        assert ci.derotation_fields([Label(body), Label(body)], 0, (64, 64)) is None, body


def test_missing_kernels_stop():
    import data_source as ds
    a, b = Label("SATURN"), Label("SATURN")
    for lbl, et in ((a, 1.0), (b, 90.0)):
        lbl.geometry = {"et": et, "target": "SATURN", "camera": "CASSINI_ISS_NAC", "center": 511.5, "scale": 5000.0}
    keep = ci._spice_locs, ci._year_kernels
    try:
        ci._spice_locs = lambda lbls: [[0, 0, 1e6, 0]] * len(lbls)
        ci._year_kernels = lambda lbl: False
        try:
            ci.derotation_fields([a, b], 0, (64, 64))
        except ds.KernelsMissing:
            pass
        else:
            raise AssertionError("a giant planet's set without its year's kernels must stop the work, not come out undrotated")
    finally:
        ci._spice_locs, ci._year_kernels = keep


def test_derotated_tiles_skips():
    tiles = [{"n": 0, "id": "N1", "t": 0.0, "offset": [0, 0], "box": [0, 0, 8, 8]},
             {"n": 1, "id": "N2", "t": 90.0, "offset": [0, 0], "box": [0, 0, 8, 8]},
             {"n": 2, "id": "N3", "t": 700.0, "offset": [0, 0], "box": [0, 0, 8, 8]}]
    keep = {k: getattr(om, k) for k in ("derotates", "ring_redraw", "cloud_placed", "derotated", "_pointing_root")}
    asked = []
    try:
        om.derotates = lambda u: True
        om._pointing_root = lambda u, n, roots: 0
        om.derotated = lambda u, cache, p, t, ref: asked.append((t["n"], ref)) or dict(t, src=f"d{t['n']}.png", box=[1, 1, 8, 8])
        om.cloud_placed = lambda u, cache, p, t: False
        om.ring_redraw = lambda u: True
        assert om.derotated_tiles({}, None, {}, tiles) is tiles, "a ring mosaic is left as it is"
        om.ring_redraw = lambda u: False
        got = om.derotated_tiles({}, None, {}, tiles)
        assert asked == [(1, "N1")], asked      # tile 2 is 700 s after its pointing's first: a repeat, not its set
        assert got[1]["pic"] == "d1.png" and "pic" not in got[0] and "pic" not in got[2]
        asked.clear()
        om.cloud_placed = lambda u, cache, p, t: t["n"] == 0
        got = om.derotated_tiles({}, None, {}, tiles)
        assert not asked and all("pic" not in t for t in got), "a pointing placed by its clouds is left as it is"
    finally:
        for k, v in keep.items():
            setattr(om, k, v)


def saturn_frame(turn_deg=0.0):
    """A synthetic Saturn frame: Cassini 1e6 km off, 12 degrees above the ring plane, looking at the centre; the
    body turned turn_deg about its pole (spin_field's spun view when not 0). (geometry, view)."""
    radii = np.array([60268.0, 60268.0, 54364.0])
    i = math.radians(12)
    obs = np.array([0.0, -1e6 * math.cos(i), 1e6 * math.sin(i)])
    z = -obs / np.linalg.norm(obs)
    x = np.cross([0.0, 0.0, 1.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    cam_to_body = np.stack([x, y, z], axis=1)
    sun = np.array([0.3, -1.0, 0.2])
    sun /= np.linalg.norm(sun)
    a = math.radians(turn_deg)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.0]])
    view = {"cam_to_body": rz @ cam_to_body, "observer": rz @ obs, "radii": radii, "sun": rz @ sun}
    return {"center": 511.5, "scale": 5000.0, "target": "SATURN"}, view


def test_spin_field_turns_clouds_not_rings():
    g, view = saturn_frame()
    _, spun = saturn_frame(0.5)
    gy, gx = np.mgrid[0:1024:4, 0:1024:4].astype(np.float64)
    dx, dy, w = rp.spin_field(g, view, spun, gx, gy)
    # the rings in front of the disk, worked out here on their own
    ray = rp.pixel_to_ray(g, gx, gy) @ view["cam_to_body"].T
    o = view["observer"]
    t = -o[2] / ray[..., 2]
    p = o + t[..., None] * ray
    radius = np.hypot(p[..., 0], p[..., 1])
    pts, hit = rp.surface_points(g, view, np.eye(3), gx, gy)
    t_disk = ((pts - o) * ray).sum(-1) / (ray * ray).sum(-1)
    rings = hit & (t > 0) & (t < t_disk) & (radius >= rp.RING_INNER) & (radius <= rp.RING_OUTER)
    assert rings.sum() > 50, "the synthetic view has rings over the disk"
    assert np.all(dx[rings] == 0) and np.all(dy[rings] == 0) and np.all(w[rings] == 0), "rings over the disk stay"
    clouds = hit & ~rings & (w > 0)
    move = np.hypot(dx, dy)[clouds]
    want = 60268.0 * math.radians(0.5) / 1e6 * 5000.0     # the sub-Cassini point's move, px
    assert 0.5 * want < move.max() < 1.5 * want, (move.max(), want)
    assert np.all(dx[~hit] == 0) and np.all(dy[~hit] == 0), "the sky stays"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
