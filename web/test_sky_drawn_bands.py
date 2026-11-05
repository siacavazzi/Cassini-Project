"""A pass whose drawn bands have dark sky keeps their sky step when a band it takes but does not draw has lit sky
(the 2006 ring movie 032RI: IR2's sky is lit beside the rings, RED, GRN and BL1 have 80% dark sky, and their sky
came out a brown veil). Run: python web/test_sky_drawn_bands.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402  (puts the repo on the path)
import calibration as cal  # noqa: E402

rng = np.random.default_rng(5)
yy, xx = np.mgrid[:256, :256]
rings = (yy > 100) & (yy < 140)                       # a bright band across the frames
stripes = 0.004 * rng.random((256, 1)) * np.ones((1, 256))
def band(sky, lit=0.08):
    return [(np.where(rings, lit, sky + stripes) + 0.0005 * rng.standard_normal((256, 256))).astype(np.float32)]
drawn = {"RED": band(0.0012), "GRN": band(0.0007), "BL1": band(0.0004)}
lit_ir2 = band(0.0070)                                # sky above 5% of the 99.9th percentile: no dark sky
U = {"key": ("SATURN", "TEST", "W", 0), "z": 1e5}

def scale(by):
    obs_mosaic.stacking.load_hdr = lambda path, gap=None: (None, by[path][0], 1)
    fr = [(f, f"W{i}", f, i, 600, 0.0, 0.0, 1e5) for i, f in enumerate(by)]
    with cal.looking("balanced"):
        return obs_mosaic.pass_scale(fr, U, ["RED", "GRN", "BL1"], True)

alone = scale(drawn)
both = scale({**drawn, "IR2": lit_ir2})
print("drawn bands alone", {f: round(alone["blacks"][f], 5) for f in drawn}, "toe", alone.get("toe"))
print("with a lit IR2   ", {f: round(both["blacks"][f], 5) for f in drawn}, "toe", both.get("toe"),
      "IR2", round(both["blacks"]["IR2"], 5))
assert alone.get("toe") and both.get("toe")
for f, v in drawn.items():
    sky = v[0][~rings]
    assert both["blacks"][f] > np.median(sky), f                # the drawn bands' black is over their sky
    assert abs(both["blacks"][f] - alone["blacks"][f]) < 2e-4, f
assert "IR2" not in both["sky_tops"]                            # the lit band keeps its own black
print("a band not drawn, with lit sky, leaves the drawn bands' sky step; ok")
