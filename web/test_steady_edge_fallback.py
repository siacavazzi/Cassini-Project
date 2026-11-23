"""obs_mosaic._chain_links with edges (a clouded body): a link whose lit edges say nothing falls back to the picture
match, and one whose edges match takes the edge match. With edges alone (#610) every link of Titan's haze movies and
Saturn's ring movies found no edge and the frames rode SPICE's smoothed path. Run: python web/test_steady_edge_fallback.py"""
import os
import sys
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

there = tempfile.mkdtemp()
made = []
for n in range(3):
    Image.fromarray(np.full((64, 64, 4), 128, np.uint8)).save(os.path.join(there, f"{n}.png"))
    made.append({"n": n, "id": f"F{n}", "filter": "CLR", "offset": [10.0 * n, 0.0], "box": [-32, -32, 64, 64]})
pic = lambda n: np.full((64, 64, 4), 128, np.uint8)
calls = {"edges": 0, "pictures": 0}


def no_edge(*a, **k):
    calls["edges"] += 1
    return None, "no edge"


def picture_match(*a, **k):
    calls["pictures"] += 1
    return (1.0, 0.0), "phase +1.0,+0.0"


om.edge_shift, om._shift_onto = no_edge, picture_match
places, hows = om._chain_links(made, pic, there, 50.0, None, 2, None, edges=True)
print(hows)
assert calls["edges"] and calls["pictures"], calls
assert all(h.startswith(("first", "linked")) for h in hows.values()), hows
step_pictures = places[1][0] - places[0][0]
assert 8.5 < step_pictures < 10, places   # (SPICE's 10 px step less the match's 1 px, held a little to SPICE)
print("a link with no edge falls back to the picture match: ok")


def edge_match(*a, **k):
    calls["edges"] += 1
    return (2.0, 0.0), {"ncc": [0.5, 0.9]}


calls.update(edges=0, pictures=0)
om.edge_shift = edge_match
places, hows = om._chain_links(made, pic, there, 50.0, None, 2, None, edges=True)
assert calls["edges"] and not calls["pictures"], calls
assert places[1][0] - places[0][0] < step_pictures - 0.3, places   # (the edges' 2 px, further than the pictures' 1 px)
print("a link whose edges match takes the edge match: ok")
