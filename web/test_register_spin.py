"""obs_mosaic C8 on a giant planet: frames whose clouds turn more than REGISTER_SPIN px between them are not matched
on their pictures (the match would be the turn, not the camera's pointing); SPICE's place stands. Jupiter 2000's C23JU
FEATURE004 moved its CB1/CB2/CB3 frames 20 to 80 px by such matches and its colour movie hopped.
Run: python web/test_register_spin.py"""
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

# _register_match_to keeps SPICE's place between frames a minute apart on a derotating body, without matching
calls = []
om.derotates = lambda u: True
om._shift_onto = lambda *a, **k: calls.append(1) or ((30.0, 0.0), "phase +30.0,+0.0")
om.tile = lambda u, j, cache, scale: {"id": f"F{j}", "n": j, "offset": [0.0, 0.0]}
om._tiles = lambda u, cache, scale: "/nonexistent"
om.os.path.exists = lambda p: True
om._made_pictures["/nonexistent/0.png"] = object()
u = dict(jupiter, frames=[(None, "F0", "CB2", 1000.0, 0, 0, 0, 9.8e6), (None, "F1", "CB3", 1066.0, 0, 0, 0, 9.8e6)])
out = {"id": "F1", "n": 1, "offset": [5.0, 5.0]}
om._register_match_to(u, 1, 0, out, None, None, {})
assert not calls and out["offset"] == [5.0, 5.0] and out["registered"]["kept"] == "SPICE's place", out
print("a giant planet's frames a minute apart keep SPICE's place, not matched on their turning clouds: ok")
