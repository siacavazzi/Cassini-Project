"""A still mosaic's saturated pointing (obs_mosaic.clipped_still) goes under with all its filters (clipped_pointings),
but a colour set's long exposure taken again (long_repeats) goes under on its own without taking its set's other
filters with it: Day the Earth Smiled's GRN repeats (195RI HIPHASEC001) pulled eleven tiles under, and the neighbours'
edges drew a lime and purple copy of the rings.
Run: python web/test_clipped_still.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obs_mosaic as om

BOX = [-512, -512, 1024, 1024]
colour = ["RED", "GRN", "BL1"]


def pass_of(where, lap):
    """a pass whose frame n is at slot where[n] in lap lap[n] (slots and lap_of read their kept answers)"""
    return {"frames": [None] * len(where), "slots": list(where), "lap_of": list(lap)}


def tiles_of(spec):
    """spec: (filter, slot, time, saturated) per frame n"""
    return [{"n": n, "filter": f, "t": t, "offset": [900.0 * s, 0.0], "box": BOX, "saturated": sat}
            for n, (f, s, t, sat) in enumerate(spec)]


# a raster taken once: four pointings of RED, GRN, BL1; pointing 2's GRN saturated 7% (the rings' bright ansa)
once = [(f, s, 100 * s + k * 20, 0.07 if (s, f) == (2, "GRN") else 0.0002) for s in range(4) for k, f in enumerate(colour)]
u = pass_of([s for _, s, _, _ in once], [1] * len(once))
t = tiles_of(once)
assert om.clipped_under(t) == {7}, "the saturated GRN is picked"
assert om.clipped_still(u, t, colour) == {6, 7, 8}, "its pointing goes under, every filter (clipped_pointings)"

# the same raster taken in two laps, lap 2's pointing 2 saturated in GRN: lap 2's whole pointing goes under, so lap 1's
# copy shows there
twice = [(f, s, tt, 0.0002) for f, s, tt, _ in once] + [(f, s, tt + 1000, sat) for f, s, tt, sat in once]
u = pass_of([s for _, s, _, _ in twice], [1] * len(once) + [2] * len(once))
t = tiles_of(twice)
n = len(once)
assert om.clipped_still(u, t, colour) == {n + 6, n + 7, n + 8}, "retaken: the saturated lap's pointing, every filter"

# a colour set's GRN taken again for longer at its place (195RI): under on its own (long_repeats), its set's RED and
# BL1 stay on top
set_ = once + [("GRN", 2, 260, 0.069)]
set_[7] = ("GRN", 2, 220, 0.0002)
u = pass_of([s for _, s, _, _ in set_], [1] * len(set_))
t = tiles_of(set_)
assert om.long_repeats(t, colour) == {len(once)}, "the long GRN is a long repeat"
assert om.clipped_still(u, t, colour) == set(), "no pointing pulled under with it"

assert om.clipped_still(u, t, None) == set() and om.clipped_still(u, t, []) == set(), "no colour: nothing"
print("clipped still: ok")
