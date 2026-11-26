"""obs_mosaic._chain_links on a clouded body (edges, no lit edge matched): the three rules for picture links across two
filters (ACROSS), which show two layers a few px apart.
  1. weighed down (STEADY_ACROSS) between tiles that keep links of their own filter, but not on a pass of the rings
     themselves (across=False), whose filters show the same ringlets;
  2. left out of the chain's agreement (res_p90, STEADY_DISAGREE);
  3. not left out of the solve for disagreeing (STEADY_AGREE).
Run: python web/test_steady_across.py"""
import os
import sys
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

LAYER = 4.0   # px: how far the second filter's layer sits from the first's
there = tempfile.mkdtemp()
made = []
for n in range(12):
    Image.fromarray(np.full((64, 64, 4), 128, np.uint8)).save(os.path.join(there, f"{n}.png"))
    made.append({"n": n, "id": f"F{n}", "filter": "RED" if n % 2 == 0 else "BL1", "offset": [10.0 * n, 0.0],
                 "box": [-32, -32, 64, 64]})
pic = lambda n: np.full((64, 64, 4), 128, np.uint8)


def match(a, pa, z, b, pb, rel, **k):
    # (same filter: SPICE's step; across filters: the other layer, LAYER px over, give or take 2 px from pair to pair,
    # the haze's look changing with each filter's exposure)
    if a["filter"] == b["filter"]:
        return (0.0, 0.0), "phase"
    noise = 2.0 if (a["n"] + b["n"]) % 4 in (1, 2) else -2.0
    return ((LAYER if b["filter"] == "BL1" else -LAYER) + noise, 0.0), "phase"


om.edge_shift = lambda *a, **k: (None, "no edge")
om._shift_onto = match


def solve(across):
    stats = {}
    places, hows = om._chain_links(made, pic, there, 50.0, None, 4, None, edges=True, stats=stats, across=across)
    own = [places[n + 2][0] - places[n][0] for n in range(10)]          # (each filter's own frame to frame)
    change = [places[n + 1][0] - places[n][0] for n in range(0, 11, 2)]  # (RED to BL1: where the filter changes)
    return own, float(np.mean(change)), stats


own_down, change_down, s_down = solve(True)
own_even, change_even, s_even = solve(False)
print("weighed down:", round(change_down, 2), s_down, "\neven (a ring pass):", round(change_even, 2), s_even)
# 1. weighed down, the links across filters barely pull: the filter change sits nearer SPICE's own 10 px step than the
#    layers' 4 px shift says (on a ring pass, across=False, they weigh as their own filter's links), and each filter's
#    own frames keep SPICE's 20 px steps
assert change_down - change_even > 0.3, (change_down, change_even)
assert max(abs(v - 20.0) for v in own_down) < 0.05, own_down
print("links across filters weighed down off the rings, as their own on a ring pass: ok")
# 2. the chain's agreement leaves them out: the pictures agree with themselves
assert s_down["res_p90"] is not None and s_down["res_p90"] < om.STEADY_DISAGREE / 4, s_down
assert s_even["res_p90"] > s_down["res_p90"] + 2, s_even   # (counted, as on a ring pass, the layers read as disagreement)
print("links across filters left out of the chain's agreement: ok")
# 3. not left out of the solve for disagreeing: every link kept
assert s_down["kept"] == s_down["links"], s_down
assert s_even["kept"] < s_even["links"], s_even   # (weighing as their own, the layers' links are left out)
print("links across filters not left out for disagreeing: ok")
