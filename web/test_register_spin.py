"""obs_mosaic C8 on a giant planet: between frames whose clouds turn more than REGISTER_SPIN px, the turn SPICE's spin
predicts (_turn_between) is taken off the match of the pictures; the rest is the camera's pointing, and the set is still
derotated (cloud_placed False). Taken whole, Jupiter 2000's C23JU FEATURE004 moved its CB1/CB2/CB3 frames 20 to 80 px
and its colour movie hopped. Run: python web/test_register_spin.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import obs_mosaic as om  # noqa: E402

jupiter = {"key": ("JUPITER", "x", "N", 0), "z": 9.8e6}
# (Jupiter's equator, 12.6 km/s, at 59 km a pixel: 14 px in 66 s, 1 px in 5 s)
assert 13 < om.spin_px(jupiter, 66) < 15, om.spin_px(jupiter, 66)
assert om.spin_px(jupiter, 5) < om.REGISTER_SPIN
assert om.spin_px({"key": ("PAN", "x", "N", 0), "z": 1e5}, 60) == 0.0   # (no spin known: nothing turned)

om.derotates = lambda u: True
om._shift_onto = lambda *a, **k: ((30.0, 2.0), "phase +30.0,+2.0")
om.tile = lambda u, j, cache, scale: {"id": f"F{j}", "n": j, "offset": [0.0, 0.0]}
om._tiles = lambda u, cache, scale: "/nonexistent"
om.os.path.exists = lambda p: True
om._made_pictures["/nonexistent/0.png"] = object()
om._turn_between = lambda u, q, t: (26.0, 0.0)
frames = lambda dt: [(None, "F0", "CB2", 1000.0, 0, 0, 0, 9.8e6), (None, "F1", "CB3", 1000.0 + dt, 0, 0, 0, 9.8e6)]

# a minute apart: the predicted turn taken off, the rest (4, 2 px) moves the frame, and the set is still derotated
out = {"id": "F1", "n": 1, "offset": [5.0, 5.0], "box": [-10, -10, 20, 20]}
om._register_match_to(dict(jupiter, frames=frames(66.0)), 1, 0, out, None, None, {})
assert out["offset"] == [1.0, 3.0] and out["registered"]["turn"] == [26.0, 0.0], out
assert not om.cloud_placed(dict(jupiter, frames=frames(66.0)), None, {}, out)
print("a giant planet's match a minute apart has the predicted turn taken off; the rest is the pointing: ok")

# seconds apart: the match as it is
out = {"id": "F1", "n": 1, "offset": [5.0, 5.0], "box": [-10, -10, 20, 20]}
om._register_match_to(dict(jupiter, frames=frames(4.0)), 1, 0, out, None, None, {})
assert out["offset"] == [-25.0, 3.0] and "turn" not in out["registered"], out
print("frames seconds apart matched as they are: ok")

# a match nearer none than the turn followed the limb or the rings, which do not turn: it stands as it is
om._turn_between = lambda u, q, t: (40.0, -35.0)
out = {"id": "F1", "n": 1, "offset": [5.0, 5.0], "box": [-10, -10, 20, 20]}
om._shift_onto = lambda *a, **k: ((3.0, 2.0), "edges +3.0,+2.0")
om._register_match_to(dict(jupiter, frames=frames(66.0)), 1, 0, out, None, None, {})
assert out["offset"] == [2.0, 3.0] and "turn" not in out["registered"], out
print("a match nearer none than the turn (the limb's) stands as it is: ok")
