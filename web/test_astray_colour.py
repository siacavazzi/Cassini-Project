"""A colour tile registration could not line up ("not aligned", kept at SPICE's place) that no other colour filter's
tile shares a pointing with, though one overlaps it, is left out of the colour (obs_mosaic.astray, visit_tiles): its
place draws gray instead of mixing bands SPICE's error apart. Iapetus' closest flyby, 049IA ORSHIRES001 pass 3, a
12-filter sweep, GRN 0.4 of a frame from BL1 and RED: a rainbow patch. A set taken at one pointing keeps its colour
even when registration found no match. Tile reports as layout() sees them.
Run: python web/test_astray_colour.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

BOX = [-540, -540, 1080, 1080]
NA = {"to": "x", "how": "not aligned", "kept": "SPICE's place"}
def tile(n, f, x, y, reg=None):
    t = {"n": n, "id": f"N{n}", "filter": f, "offset": [x, y], "box": BOX, "t": 1000.0 + 17 * n}
    return dict(t, registered=reg) if reg else t

colour = ["RED", "GRN", "BL1"]
# ORSHIRES pass 3: each filter on another patch as the camera swept
sweep = [tile(2, "GRN", 25392, 4753, NA), tile(5, "BL1", 25845, 4978, NA), tile(6, "RED", 25985, 5054, NA)]
assert om.astray(sweep, colour) == {2}, om.astray(sweep, colour)
print("a swept colour filter registration could not line up is left out of the colour; ok")

# a colour set at one pointing, not aligned (featureless or far): kept
still = [tile(1, "RED", 0, 0, NA), tile(2, "GRN", 30, 10, NA), tile(3, "BL1", -20, 15, NA)]
assert om.astray(still, colour) == set()
# a swept filter that registration did line up: kept
assert om.astray([dict(sweep[0], registered={"to": "x", "how": "phase"})] + sweep[1:], colour) == set()
# a tile overlapping no other colour filter: nothing to mismatch, kept
assert om.astray([tile(1, "RED", 0, 0, NA), tile(2, "GRN", 5000, 0, NA)], colour) == set()
print("a set at one pointing, a registered tile and a lone tile keep their colour; ok")

# the gray base always goes under a tile left out, on any body (not only clouded or kept-as-taken passes): Iapetus
# frames all redrawn, no as_taken tile, its CL1 frames the base
u = {"key": ("IAPETUS", "ISS_TEST", "N", 0), "frames": []}
p = {"display_scale": {}, "grey": "CL1/CL2", "luminance": {"filters": ["CL1/CL2"], "gains": {}}}
base = [tile(12, "CL1/CL2", 25392, 4753), tile(13, "CL1/CL2", 25845, 4978), tile(14, "CL1/CL2", 25985, 5054)]
assert om.lum_base(u, p, sweep + base, colour, base=base)
assert not om.lum_base(u, p, still + [tile(12, "CL1/CL2", 0, 0)], colour, base=[tile(12, "CL1/CL2", 0, 0)])
print("the gray base goes under a colour tile left out, on a moon whose frames were redrawn; ok")
