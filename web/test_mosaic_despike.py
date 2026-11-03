"""A mosaic tile's one-frame spikes (cosmic rays) are checked against the frames at its own pointing
(obs_mosaic._same_pointing), any filter, nearest in time. Run: python web/test_mosaic_despike.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

F = om.FRAME
# (path, id, filter, t, name, x, y, z): two pointings a frame apart, three filters each, and a far later visit
frames = [("a/1.png", "1", "UV3", 0, "", 0, 0, 1.0), ("a/2.png", "2", "GRN", 60, "", 0, 0, 1.0),
          ("a/3.png", "3", "IR3", 120, "", 0.05 * F, 0, 1.0), ("a/4.png", "4", "UV3", 200, "", F, 0, 1.0),
          ("a/5.png", "5", "GRN", 260, "", F, 0, 1.0), ("a/6.png", "6", "IR3", 2000, "", 0, 0, 1.0),
          ("a/7.png", "7", "GRN", 300, "", 0, 0, 0)]
u = {"frames": frames, "z": 1.0}
assert om._same_pointing(u, 0) == ["a/2.png", "a/3.png"], om._same_pointing(u, 0)   # its pointing, nearest first
assert om._same_pointing(u, 2) == ["a/2.png", "a/1.png"]
assert om._same_pointing(u, 3) == ["a/5.png"]                     # the other pointing's
assert om._same_pointing(u, 5) is None                             # back much later: nothing near in time
assert om._same_pointing(u, 6) is None                             # SPICE has no place for it
print("mosaic despike ok")
