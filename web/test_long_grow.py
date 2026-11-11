"""A filter mosaic with a long exposure taken again (obs_mosaic.long_repeats, marked "long" by visit_tiles) is not
grown a tile at a time (obs_mosaic.grows): the long frame is known for one only once its filter's next frame at that
place is in, so the mosaic grown before then drew it on top, and growing never takes it under. Day the Earth Smiled,
195RI HIPHASEC001 (2013), kept its GRN repeat W1752980760 (tile 183, 5.5% saturated) on top: a lime patch by Saturn's
limb. Tile reports as filter_mosaic sees them.
Run: python web/test_long_grow.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import obs_mosaic as om  # noqa: E402

BOX = [-512, -512, 1024, 1024]
def tile(n, x, f="GRN", **kw):
    return dict({"n": n, "id": f"W{n}", "filter": f, "offset": [x, 0.0], "box": BOX, "t": 1000.0 + n}, **kw)

few = [tile(n, 700 * n) for n in range(om.GROW_FROM)]
many = [tile(n, 700 * n) for n in range(om.GROW_FROM + 4)]
assert not om.grows(few)
assert om.grows(many)
print("more than GROW_FROM tiles of a filter grow a tile at a time; ok")

# 195RI's GRN: the set's own frame, then the same filter again, longer, at the same place (5.5% saturated vs 0.1%)
grn = many + [tile(182, 700 * 7 + 5, saturated=0.001), tile(183, 700 * 7 + 3, saturated=0.055)]
longs = om.long_repeats(grn, ["GRN"])
assert longs == {183}, longs
marked = [dict(t, long=True) if t["n"] in longs else t for t in grn]
assert not om.grows(marked)
print("a filter mosaic holding a long exposure taken again is composed whole, not grown; ok")

assert not om.grows([dict(t, fill=True) if t["n"] == 3 else t for t in many])
print("nor one with a fill (as before); ok")
