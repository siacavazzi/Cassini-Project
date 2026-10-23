"""Synthetic check of obs_mosaic.movie_rect's Center the body rule: a body the frames look at, whose disk fits
MOVIE_FIT frames, sits in the middle of a square view that keeps the footprint round it; a body bigger than that, or out of the frames, keeps the
footprint's view. Run: python web/test_movie_center.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

F = om.FRAME
t = {"offset": (300.0, -200.0)}
fp = (-200.0, -900.0, 1300.0, 400.0)                       # a footprint 1.5 x 1.3 frames, the body off to one side
assert om.movie_rect(fp, t) == (-200.0, -900.0, 1500.0, 1300.0)                 # today's view: the whole footprint
small = (-300.0, -200.0, 350.0, 250.0)                     # a moon movie: frames round a small moon
assert om.movie_rect(small, t, radius=60, centre=True) == (-F / 2, -F / 2, F, F)   # at least a frame round it
assert om.movie_rect(small, t, radius=500, centre=True) == (-600.0, -600.0, 1200.0, 1200.0)  # its disk and a margin
S = om.MOVIE_FIT * F
assert om.movie_rect(fp, t, radius=200, centre=True) == (-S / 2, -S / 2, S, S)   # the whole footprint round it, capped
stare = (-900.0, -300.0, 700.0, 400.0)                     # a stare: the rings reach past the disk
assert om.movie_rect(stare, t, radius=300, centre=True) == (-900.0, -900.0, 1800.0, 1800.0)   # the rings stay in
assert om.movie_rect(fp, t, radius=200, centre=False) == om.movie_rect(fp, t)    # the setting off
assert om.movie_rect(fp, t, radius=5000, centre=True) == om.movie_rect(fp, t)    # bigger than the view: as today
far = (3000.0, 3000.0, 4500.0, 4300.0)                     # frames that never look at the body (a ring movie)
ft = {"offset": (3700.0, 3600.0)}
assert om.movie_rect(far, ft, radius=200, centre=True) == om.movie_rect(far, ft)
print("ok")
