"""Synthetic check of obs_mosaic.movie_rect's Center the body rule (centre_half): a body whose disk fits MOVIE_FIT
frames, whose centre is on at least one frame, and round which the square view keeps CENTRE_KEEP of the frames' area,
sits in the middle of a square view that keeps the footprint round it; a body bigger than that, one no frame looks at
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
half = max(-fp[0], fp[2], -fp[1], fp[3])
assert om.movie_rect(fp, t, radius=60, centre=True, seen=seen(*small)) == (-half, -half, 2 * half, 2 * half)
assert om.movie_rect(fp, t, radius=500, centre=True, seen=seen(*small)) == (-half, -half, 2 * half, 2 * half)
assert om.movie_rect(fp, t, radius=200, centre=False, seen=seen(*small)) == om.movie_rect(fp, t)    # the setting off
assert om.movie_rect(fp, t, radius=5000, centre=True, seen=seen(*small)) == om.movie_rect(fp, t)    # bigger than the view
moon = (-300.0, -200.0, 350.0, 250.0)                      # a footprint within a frame of the body
assert om.movie_rect(moon, t, radius=60, centre=True, seen=seen((0, 0))) == (-F / 2, -F / 2, F, F)   # at least a frame round it
assert om.movie_rect(moon, t, radius=500, centre=True, seen=seen((0, 0))) == (-600.0, -600.0, 1200.0, 1200.0)  # its disk and a margin
stare = [(-150, 0), (-200, 50)]                            # a stare: the body on the frames, rings past the disk
fp = box(*stare)
half = max(-fp[0], fp[2], -fp[1], fp[3])                   # the rings stay in
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
assert om.centre_half(box(*most), 200, seen(*most)) == S / 2

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
angles.clear()
assert om.kept_share(seen((0, 0)), F / 2) == 1.0
print("ok")
