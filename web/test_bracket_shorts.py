"""A grey filter's exposure bracket (obs_mosaic.bracket_shorts): the short frame at a place where the same filter took
one at least BRACKET_STEP times as long goes under it, as 036RI DRING001's 10 s frames under its 120 s ones (left to
dim_under's overlap ratio, one 10 s frame went from 0.60 to 0.74 at full depth, past DIM_UNDER, and its faint C ring
came out on top as a soft band with a hard seam). A long frame that is over-exposed, one at another place or outside
the visit's time, or a pair under BRACKET_STEP apart leaves the short one as it is; filter_mosaic marks them for a
grey filter only. Run: python web/test_bracket_shorts.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obs_mosaic as om

BOX = [-511.0, -511.0, 1022, 1022]
EXPOSURE = {}
om._tile_exposure = lambda t, paths=None: EXPOSURE.get(t["n"])


def tile(n, t, x, y, sat, s, f="CL1/CL2"):
    EXPOSURE[n] = s
    return {"n": n, "id": f"N{n}", "filter": f, "t": t, "offset": [x, y], "box": BOX, "saturated": sat}


# 036RI DRING001: 120 s then 10 s at each of four pointings (saturated shares as its tiles reported)
d = [tile(0, 0, 11337, -475, 0.0126, 120), tile(1, 70, 11336, -472, 0.0, 10),
     tile(2, 401, 11928, -474, 0.3451, 120), tile(3, 471, 11928, -478, 0.0058, 10),
     tile(4, 829, 11928, 353, 0.3303, 120), tile(5, 899, 11929, 352, 0.0353, 10),
     tile(6, 1231, 11334, 349, 0.0099, 120), tile(7, 1301, 11336, 349, 0.0, 10)]
assert om.bracket_shorts(d) == {1, 3, 5, 7}, om.bracket_shorts(d)
checks = 1
# an over-exposed long frame (OVER_EXPOSED of it saturated) does not take its short one under
assert om.bracket_shorts([tile(10, 0, 0, 0, 0.6, 120), tile(11, 70, 0, 0, 0.0, 10)]) == set()
# another place, another visit, a pair under BRACKET_STEP apart, another filter: as they are
assert om.bracket_shorts([tile(12, 0, 0, 0, 0.0, 120), tile(13, 70, 600, 0, 0.0, 10)]) == set()
assert om.bracket_shorts([tile(14, 0, 0, 0, 0.0, 120), tile(15, 70 + om.MIX_SPAN, 0, 0, 0.0, 10)]) == set()
assert om.bracket_shorts([tile(16, 0, 0, 0, 0.0, 30), tile(17, 70, 0, 0, 0.0, 10)]) == set()
assert om.bracket_shorts([tile(18, 0, 0, 0, 0.0, 120, "RED"), tile(19, 70, 0, 0, 0.0, 10)]) == set()
# a frame whose exposure is not known is left as it is
EXPOSURE[1] = None
assert 1 not in om.bracket_shorts(d)
checks += 6
# filter_mosaic marks them for a grey filter only (not a colour picture's filters, not the luminance base)
src = open(om.__file__).read().split("def filter_mosaic", 1)[1].split("\ndef ", 1)[0]
assert "bracket_shorts(mine, u)" in src and 'f != LUM and f not in (p.get("colour") or [])' in src
checks += 1
print(f"{checks} checks ok")
