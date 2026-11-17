#!/usr/bin/env python3
"""A movie picture the cache already holds under another name is found, not drawn again (obs_mosaic._movie_twin,
movie_webp): an evened frame whose exposure gain is exactly 1 is the frame with no exposure asked, its report with
the gain noted where movie_frame notes it; a plane (colour off) is the colour frame when that was drawn grey of the
same held frame. Anything else is drawn as before. The rule's every branch, on made-up reports (the pictures
themselves are compared on real passes: evidence/movie_twins).
Run: python web/test_movie_twins.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

tmp = tempfile.mkdtemp(prefix="twins-test-")
frames = [(f"p{k}.png", f"N{k}_1", "CL1/CL2", 1000.0 + 60 * k, 600, 0.0, 0.0, 1.0e5) for k in range(4)]
u = {"key": ("TESTBODY", "ISS_TEST_TWIN", "N", 0), "frames": frames}
named = lambda colour, exposure: os.path.join(tmp, f"1_0_{int(bool(colour))}_c2{f'_e{exposure}r8' if exposure else ''}.webp")
gains, tiles, partial = {1: 1.0}, {k: {"n": k, "offset": [0, 0], "filter": "CL1/CL2"} for k in range(4)}, set()
om.plan = lambda u, cache: {"display_scale": {}}
om.exposure_gains = lambda u, cache, p, exposure, colour, centre, steady: dict(gains)
om.tile = lambda u, j, cache, scale=None: tiles[j]
om.unfit = lambda frames, j, tile_of: j in partial
om.over_exposed = lambda t: False


def keep(path, report):
    with open(path, "wb") as fh:
        fh.write(b"picture")
    with open(path[:-4] + "json", "w") as fh:
        json.dump(report, fh)
    om.reel._reports.pop(path[:-4] + "json", None)


plain = {"movie": True, "n": 1, "of": 4, "filter": "CL1/CL2", "id": "N1_1", "centred": True, "view": [0, 0, 1, 1], "width": 8, "height": 8}
twin = lambda colour, exposure: om._movie_twin(u, 1, tmp, colour, True, 0, exposure, named)

# nothing kept yet, and the colour frame itself: drawn
assert twin(True, 8) is None and twin(False, 0) is None and twin(True, 0) is None
keep(named(True, 0), plain)

# ---------- evened ----------
got = twin(True, 8)
assert got[0] == named(True, 0)
assert list(got[1]) == ["movie", "n", "of", "filter", "id", "exposure", "centred", "view", "width", "height"], list(got[1])
assert got[1]["exposure"] == {"smooth": 8, "gain": 1.0} and {k: v for k, v in got[1].items() if k != "exposure"} == plain
# (as movie_frame writes it: the gain's note sits before "centred", after a held frame's name)
keep(named(True, 0), {**{k: plain[k] for k in ("movie", "n", "of", "filter", "id")}, "held": "N0_1",
                      **{k: plain[k] for k in ("centred", "view", "width", "height")}})
assert list(twin(True, 8)[1])[5:8] == ["held", "exposure", "centred"]
keep(named(True, 0), plain)
for g in (1.005, 0.995, 2.0):
    gains[1] = g
    assert twin(True, 8) is None, g                      # (any other gain is another picture)
gains.pop(1)
assert twin(True, 8) is not None                         # (a frame the chain has no gain for is drawn at 1)
gains[1] = 1.0
keep(named(True, 0), {"movie": True, "n": 1, "why": "not placed by SPICE"})
assert twin(True, 8) is None                             # (a frame with no picture: its report has no view)
keep(named(True, 0), plain)
print("an evened frame at a gain of exactly 1 is the plain frame, its report with the gain noted")

# ---------- a plane ----------
assert twin(False, 0) == (named(True, 0), plain)
for key in om.TWIN_NO:
    keep(named(True, 0), {**plain, key: ["RED", "GRN", "BL1"]})
    assert twin(False, 0) is None, key                   # (drawn of a colour set: another picture)
# held alike: the colour frame shows frame 0 for frame 1, and so does the plane only when frame 1 is not shown
keep(named(True, 0), {**plain, "held": "N0_1"})
assert twin(False, 0) is None
partial.add(1)
assert twin(False, 0) == (named(True, 0), {**plain, "held": "N0_1"})
keep(named(True, 0), plain)
assert twin(False, 0) is None                            # (the plane holds frame 0, the colour frame did not)
partial.clear()
tiles[1] = {"n": 1, "filter": "CL1/CL2", "why": "not placed by SPICE"}
assert twin(False, 0) is None                            # (a frame SPICE did not place has no picture)
tiles[1] = {"n": 1, "offset": [0, 0], "filter": "CL1/CL2"}
# an evened plane at a gain of 1 is the plane
keep(named(False, 0), plain)
assert twin(False, 8)[0] == named(False, 0)
print("a plane is the colour frame when that was drawn grey of the same held frame")
print("ok")
