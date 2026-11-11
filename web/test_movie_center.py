"""Synthetic check of obs_mosaic.movie_rect's Center the body rule (centre_half): a body whose disk fits MOVIE_FIT
frames, whose centre is on at least one frame, and round which the square view keeps CENTRE_KEEP of the frames' area,
sits in the middle of a square view as big as what the frames show round it needs (fitted_half: at least a frame,
the corners of a frame turned north up left out, the frames' wandering kept in); a body bigger than that, one no frame looks at
(frames on both ansae of the rings, a plume stare above the limb) or a pass the square would cut keeps the
footprint's view. frames_seen turns each frame north up as label_handler.middle_rotation turns the tiles.
Run: python web/test_movie_center.py"""
import math, sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402
import label_handler  # noqa: E402

F = om.FRAME
Z = 1e5
angles = {}
om.reel.north_angles = lambda ids: {i: angles[i] for i in ids if i in angles}


def frames(*places):
    """Frames (units' tuples) whose middles sit at places (find_target's shift x, y, full resolution pixels), at Z."""
    return [(None, f"F{i}", "CL1/CL2", float(i), 650, float(x), float(y), Z) for i, (x, y) in enumerate(places)]


def seen(*places):
    return om.frames_seen(frames(*places), Z)


def box(*places):
    """The geometry footprint of frames at places, as _box and plan draw it (HALF round each)."""
    xs, ys = [x for x, _ in places], [y for _, y in places]
    return (min(xs) - om.HALF, min(ys) - om.HALF, max(xs) + om.HALF, max(ys) + om.HALF)


t = {"offset": (300.0, -200.0)}
S = om.MOVIE_FIT * F

# the body on the frames: centred as before
small = [(0, 0), (60, -40), (-50, 30)]                     # a moon movie: frames on a small moon
fp = box(*small)
assert om.movie_rect(fp, t) == (fp[0], fp[1], fp[2] - fp[0], fp[3] - fp[1])                 # today's view: the whole footprint
half = om.centre_half(fp, 60, seen(*small))
wide = max(-fp[0], fp[2], -fp[1], fp[3])                   # the footprint's view (before 2026-11-03: the view drawn)
assert F / 2 <= half < F / 2 + 60 < wide                   # about a frame: the frames wander 60 px off the body
assert om.movie_rect(fp, t, radius=60, centre=True, seen=seen(*small)) == (-half, -half, 2 * half, 2 * half)
assert om.centre_half(fp, 500, seen(*small)) == 600.0      # the disk and its margin, when bigger
assert om.movie_rect(fp, t, radius=200, centre=False, seen=seen(*small)) == om.movie_rect(fp, t)    # the setting off
assert om.movie_rect(fp, t, radius=5000, centre=True, seen=seen(*small)) == om.movie_rect(fp, t)    # bigger than the view
moon = (-300.0, -200.0, 350.0, 250.0)                      # a footprint within a frame of the body
assert om.movie_rect(moon, t, radius=60, centre=True, seen=seen((0, 0))) == (-F / 2, -F / 2, F, F)   # at least a frame round it
assert om.movie_rect(moon, t, radius=500, centre=True, seen=seen((0, 0))) == (-600.0, -600.0, 1200.0, 1200.0)  # its disk and a margin
stare = [(-150, 0), (-200, 50)]                            # a stare: the body on the frames, rings past the disk
fp = box(*stare)
half = om.centre_half(fp, 300, seen(*stare))               # the rings on the frames stay in
assert F / 2 + 50 < half < max(-fp[0], fp[2], -fp[1], fp[3])
assert om.kept_share(seen(*stare), half) >= 0.9
assert om.movie_rect(fp, t, radius=300, centre=True, seen=seen(*stare)) == (-half, -half, 2 * half, 2 * half)

# (A) the body's centre on no frame, though the footprint takes it in: the footprint's view
ansae = [(-900, 0), (900, 0)]                              # a ring movie on both ansae of Saturn
fp = box(*ansae)
assert fp[0] < 0 < fp[2] and fp[1] < 0 < fp[3]           # today's rule centred it
assert om.centre_half(fp, 200, seen(*ansae)) is None
assert om.movie_rect(fp, t, radius=200, centre=True, seen=seen(*ansae)) == om.movie_rect(fp, t)
plume = [(0, 560), (10, 600)]                              # a plume stare: the frames just above the limb
assert om.centre_half(box(*plume), 252, seen(*plume)) is None

# (B) the body on a frame, but the square (MOVIE_FIT frames at most) cuts the frames reaching further
retarget = [(0, 0), (1400, 0), (1500, 100)]
fp = box(*retarget)
assert om.kept_share(seen(*retarget), S / 2) < om.CENTRE_KEEP
assert om.centre_half(fp, 200, seen(*retarget)) is None
assert om.movie_rect(fp, t, radius=200, centre=True, seen=seen(*retarget)) == om.movie_rect(fp, t)
# ... while a little outer sky lost keeps it centred (Iapetus mosaics: the body on most frames)
most = [(0, 0)] * 30 + [(700, 0)]
assert om.CENTRE_KEEP <= om.kept_share(seen(*most), S / 2) < 1
assert om.centre_half(box(*most), 200, seen(*most)) == F / 2   # drawn a frame wide: the one frame off it keeps a part
assert om.kept(seen(*most), F / 2)[-1].any()

# ... but not when that loses a frame altogether (a stray frame of another pointing)
stray = [(0, 0)] * 60 + [(2000, 0)]
assert om.kept_share(seen(*stray), S / 2) >= om.CENTRE_KEEP
assert om.centre_half(box(*stray), 200, seen(*stray)) is None

# a frame no SPICE place: nothing to look at the body
assert om.frames_seen([(None, "X", "CL1/CL2", 0.0, 650, None, None, None)], Z) is None
assert om.centre_half(box((0, 0)), 200, None) is None

# frames_seen turns each frame by its own angle as the tiles are turned (label_handler.middle_rotation)
angles.update(F0=37.0)
pts = seen((300, -120))[1]
shape = (3000, 3000)
R = label_handler.middle_rotation(shape, 37.0)
mid = (np.array(shape[::-1]) - 1) / 2
corner = (R @ [mid[0] + 300 + F / 2, mid[1] - 120 + F / 2, 1]) - mid   # the frame's corner, after the turn
far = pts[np.argmax(pts @ (corner / np.hypot(*corner)))]
assert np.hypot(*(far - corner)) < F / om.SEEN_GRID, (far, corner)
assert np.allclose(pts.mean(0), (R[:, :2] @ [300, -120]), atol=1e-6)
# ... so a frame turned 45 degrees on the body's centre spills out of a frame-wide square at its corners
angles.update(F0=45.0)
assert 0.8 < om.kept_share(seen((0, 0)), F / 2) < 0.86
# ... which does not widen a centred view: a moon movie whose frames are turned is drawn a frame wide, as its single
# pictures are (centre_view), not 1.41 frames and more (Hyperion 141HY, 2010-11-28: 1.9 frames)
assert om.centre_half(box((0, 0)), 60, seen((0, 0))) == F / 2
angles.update({f"F{i}": 124.0 for i in range(6)})
flyby = [(66, 80), (62, 88), (67, 86), (63, 84), (67, 87), (66, 80)]
assert om.centre_half(box(*flyby), 250, seen(*flyby)) < 0.53 * F
angles.clear()
assert om.kept_share(seen((0, 0)), F / 2) == 1.0
# the view of a pass that is not centred (Sam 2026-11-08: a 271SA close-up sweep drawn in a window two frames across,
# the frame a quarter of it): each frame's own box on the pass's axes (frames_boxes, the corners frames_seen turns) ...
b = om.frames_boxes(frames((0, 0), (300, -120)), Z)
assert np.allclose(b, [(-F / 2, -F / 2, F / 2, F / 2), (300 - F / 2, -120 - F / 2, 300 + F / 2, -120 + F / 2)])
angles.update(F0=45.0)
assert np.allclose(om.frames_boxes(frames((0, 0)), Z)[0], [-F / 2 ** 0.5, -F / 2 ** 0.5, F / 2 ** 0.5, F / 2 ** 0.5])
assert np.allclose(om.frames_boxes(frames((0, 0)), Z, 45.0)[0], [-F / 2, -F / 2, F / 2, F / 2])   # on its pass's axes: square
angles.clear()
# ... a pass sweeping further than MOVIE_FIT frames follows the frame (follows), and draws it as Cassini took it:
# the square round the frame turned by its own angle less the pass's (follow_view), turned back and cut to the frame
sweep = [(i * 400.0, 0.0) for i in range(12)]
fp = (-F / 2, -F / 2, 4400 + F / 2, F / 2)
t5 = {"offset": (2000.0, 0.0), "id": "F5"}
assert om.movie_rect(fp, t5) == (2000 - S / 2, -F / 2, S, F)            # the window MOVIE_FIT frames across ...
assert om.follows(fp, om.movie_rect(fp, t5))                           # ... which follows the frame
assert not om.follows((-F, -F, F, F), om.movie_rect((-F, -F, F, F), t5))  # a footprint within MOVIE_FIT frames holds still
U5 = {"key": ("SATURN", "X", "W", 5), "frames": frames(*sweep), "z": Z}
angles.update({f"F{i}": 10.0 * i for i in range(12)})                  # the spacecraft rolling through the pass
turn = om.view_turn(U5)
n = 512
rect, k, got = om.follow_view(U5, 5, t5, n)
# (turned back by its roll only: it keeps the pass's quarter, square_turn, so north stays near the top)
want = om.wrapped(om.square_turn(50.0, om.quarter_of(turn, om.view_axes(U5))) - turn)
assert abs(k * F - (n + om.FOLLOW_SLACK)) < 1e-9 and abs(got - want) < 1e-9
# the frame ends up turned a whole number of quarters from the camera's frame (drawn 50 - turn, turned back got)
assert abs(((50.0 - turn - got) / 90.0) - round((50.0 - turn - got) / 90.0)) < 1e-9 and abs(om.wrapped(50.0 - (50.0 - turn - got))) <= 45.0
a = math.radians(got)
assert np.allclose(rect, (2000 - F * (abs(math.cos(a)) + abs(math.sin(a))) / 2, -rect[2] / 2, rect[2], rect[2]))
# the tile as processed_frame draws it (the frame turned by got about its middle, its box round it) and _place puts
# it comes back the whole frame, every edge row and column drawn (no part-transparent seam for detail() to darken)
for got in (got, 10.0, -33.0, 0.0):
    a = math.radians(got)
    big = F * (abs(math.cos(a)) + abs(math.sin(a)))
    rect = (2000 - big / 2, -big / 2, big, big)
    tb = math.ceil(big)                                     # the tile: the frame turned on a canvas its box wide
    sq = np.zeros((tb, tb), np.uint8)
    o0 = (tb - F) / 2
    sq[math.floor(o0):math.floor(o0) + F, math.floor(o0):math.floor(o0) + F] = 255
    tile_pic = cv2.warpAffine(sq, label_handler.middle_rotation(sq.shape, got), (tb, tb), flags=cv2.INTER_LINEAR)
    t6 = {"offset": (2000.0, 0.0), "box": [-tb / 2, -tb / 2, tb, tb]}
    W = math.ceil(big * k)
    sw = max(1, round(tb * k))
    left = round((t6["offset"][0] + t6["box"][0] - rect[0]) * k)
    canvas = np.zeros((W + 2, W + 2), np.uint8)
    part = cv2.resize(tile_pic, (sw, sw), interpolation=cv2.INTER_AREA)
    canvas[left:left + sw, left:left + sw] = part[:W + 2 - left, :W + 2 - left]
    back = om._unturn(canvas, got, om.follow_middle(t6, rect, k), n, n)
    assert back.shape == (n, n) and back.min() > 200, (got, back.min(), (back < 200).mean())
    # ... and the turn a tile shows is found from its picture when the geometry cache has none (_drawn_turn)
    import tempfile
    from PIL import Image
    with tempfile.NamedTemporaryFile(suffix=".png") as fh:
        rgba = np.zeros((tb, tb, 4), np.uint8)
        rgba[..., 3] = tile_pic
        Image.fromarray(rgba, "RGBA").save(fh.name)
        assert abs(om._drawn_turn(fh.name) - got) < 0.6, (om._drawn_turn(fh.name), got)
angles.clear()
# ... and a stare's footprint is its frames' own boxes, a frame across, so the whole footprint is the view
stare_fp = om.frames_boxes(frames((0, 0), (10, -5)), Z)
fp = (*stare_fp[:, :2].min(0), *stare_fp[:, 2:].max(0))
assert max(fp[2] - fp[0], fp[3] - fp[1]) == F + 10
print("ok")
