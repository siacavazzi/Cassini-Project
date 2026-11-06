"""A colour set's filter taken again for longer at the same place (obs_mosaic.long_repeats) goes under the set's own
frame in the colour picture (the 269RI HIPHASEFB001 RED repeats and 195RI HIPHASEC001 GRN repeats), while a repeat
that is not much more saturated, one at another place, one outside the visit's time, or one of a filter the colour
picture does not draw is left as it is; under_first draws it under the others.
Run: python web/test_long_repeats.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obs_mosaic as om

BOX = [-595.5, -595.5, 1191, 1191]
def tile(n, f, t, x, sat):
    return {"n": n, "filter": f, "t": t, "offset": [x, 0.0], "box": BOX, "saturated": sat}

colour = ["RED", "GRN", "BL1"]
# 269RI p32 + p33: the set (BL1, GRN, RED), then RED again 24 s later, 8% saturated against 0%
s = [tile(114, "BL1", 0, 0, 0.003), tile(115, "GRN", 17, 0, 0.005), tile(116, "RED", 34, 0, 0.0),
     tile(117, "RED", 58, 15, 0.0797)]
assert om.long_repeats(s, colour) == {117}, "the long RED goes under"
assert om.long_repeats(s[:3], colour) == set(), "a set alone: nothing"
assert om.long_repeats(s[:3] + [tile(117, "RED", 58, 15, 0.03)], colour) == set(), "under OVER_LEAST, a frame lit all over: kept"
assert om.long_repeats(s[:3] + [dict(tile(117, "RED", 58, 15, 0.049), lit=0.0555)], colour) == {117}, "most of its lit part: long"
assert om.long_repeats(s[:3] + [dict(tile(117, "RED", 58, 15, 0.005), lit=0.006)], colour) == set(), "under LONG_LEAST: kept"
assert om.long_repeats(s[:3] + [tile(117, "RED", 58, 900, 0.08)], colour) == set(), "another place: its own tile"
assert om.long_repeats(s[:3] + [tile(117, "RED", 58 + om.MIX_SPAN + 1, 15, 0.08)], colour) == set(), "another visit"
assert om.long_repeats([tile(1, "RED", 0, 0, 0.04), tile(2, "RED", 20, 0, 0.08)], colour) == set(), "only 2x: both kept"
assert om.long_repeats([tile(1, "VIO", 0, 0, 0.0), tile(2, "VIO", 20, 0, 0.2)], colour) == set(), "not a colour filter"
order = [t["n"] for t in om.under_first([dict(t, long=True) if t["n"] == 117 else t for t in s])]
assert order[0] == 117 and order[1:] == [114, 115, 116], "drawn first, under the set"
print("long repeats: ok")
