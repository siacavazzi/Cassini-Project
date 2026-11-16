"""A frame with no colour set to show, in a movie that plays in colour, is drawn in gray at the brightness its filter's
frames take in the pass's colour pictures (obs_mosaic.grey_match). Such a frame (its own set never complete, the sets
either side not covering its place) was drawn at its filter's own brightness, 20 to 28% above the colour pictures round
it (257DA DAPHNIS001 frames 7 to 9, 2026-11-16). The factor is measured once per pass, on its complete sets, as the
ratio of a set frame drawn in colour to the same frame drawn on its own, the median over the sets, within TINT_MATCH,
and kept with the pass. Here the measuring on a made-up pass whose drawing is stood in for.
Run: python web/test_grey_match.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import json  # noqa: E402
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

G = 2.2
want = ["IR3", "GRN", "UV3"]
# four sets of IR3, GRN, UV3, then a clear frame; the second set's UV3 lost its lines (never complete)
filters = (["GRN", "UV3", "IR3"] * 4) + ["CL1/CL2"]
u = {"key": ("DAPHNIS", "ISS_TEST_GREYMATCH", "N", 0), "frames": [(None, f"N{1863267000 + 60 * n}_1", f, 60.0 * n) for n, f in enumerate(filters)]}
p = {"display_scale": {"gamma": G}, "colour": want, "grey": "GRN"}
lost = {4}
om._kept_tiles = lambda u, cache, scale: None
om.tile = lambda u, j, cache, scale: {"n": j, "offset": [0.0, 0.0], "filter": filters[j]}
om.unfit = lambda frames, j, tile_of: j in lost
om._pass_sets = lambda u: [[(filters[j], j) for j in range(k, k + 3)] for k in range(0, 12, 3)]
om.plays_colour = lambda u, w, grey, shown=None: True
own = {"GRN": 0.50, "UV3": 0.10, "IR3": 0.60}       # each filter's frame on its own, linear
in_colour = [0.40, 0.42, 0.38, 0.40]                 # the colour picture's level, set by set
drawn = []


def movie_frame(u, n, cache, trail=0, colour=True, out=om.OUT, centre=True, steady=0, exposure=0, sharpen=True, per_body=True):
    drawn.append((n, colour, out))
    level = in_colour[n // 3] if colour else own[filters[n]]
    a = np.zeros((64, 64, 4), np.uint8)
    a[..., 3] = 255
    a[8:56, 8:56, :3] = int(round(om.calibration.encode(np.float32(level), G) * 255))
    return Image.fromarray(a, "RGBA"), ({"color": want} if colour else {})


om.movie_frame = movie_frame
cache = tempfile.mkdtemp(prefix="grey-match-")
got = om.grey_match(u, cache, p)
# the three complete sets (the second is not: a frame of it lost), every frame of each drawn in colour and on its own,
# at the windows' size
assert sorted({n for n, _, _ in drawn}) == [0, 1, 2, 6, 7, 8, 9, 10, 11] and {o for _, _, o in drawn} == {om.OUT}, drawn
assert len(drawn) == 18
med = float(np.median([0.40, 0.38, 0.40]))
assert abs(got["GRN"] - med / 0.50) < 0.02 and abs(got["IR3"] - max(om.TINT_MATCH[0], med / 0.60)) < 0.02, got
assert got["UV3"] == om.TINT_MATCH[1], got            # (0.40 / 0.10: held to the furthest a tint is matched)
assert "CL1/CL2" not in got                           # (a filter no set holds: none)
# kept with the pass, and read from there
kept = json.load(open(os.path.join(om.folder(u, cache), om.GREY_MATCH_FILE)))
assert kept["factors"] == got and kept["sets"] == 3
drawn.clear()
assert om.grey_match(u, cache, p) == got and not drawn
# a pass that does not play in colour has none, and nothing is drawn or kept for it
om.plays_colour = lambda u, w, grey, shown=None: False
u2 = dict(u, key=("DAPHNIS", "ISS_TEST_GREYPLAYS", "N", 0))
assert om.grey_match(u2, cache, p) == {} and not drawn and not os.path.exists(os.path.join(om.folder(u2, cache), om.GREY_MATCH_FILE))
assert om.grey_match(u, cache, dict(p, colour=None)) == {}
print("ok")
