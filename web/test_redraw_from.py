"""Which frame's time a registered mosaic tile is redrawn from (obs_mosaic._redraw_from): the tile C8 moved it onto,
followed back through a chain of filters each registered to the one before it (the first's surface), none for a tile
not moved (refused or the pointing's first), and none with REDRAW_AT_REFERENCE off.
Run: python web/test_redraw_from.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obs_mosaic as om

a = {"id": "A"}
b = {"id": "B", "registered": {"to": "A", "shift": [17, 3]}}
c = {"id": "C", "registered": {"to": "B", "shift": [18, 1]}}
d = {"id": "D", "registered": {"to": "A", "how": "phase", "kept": "SPICE's place"}}
loop = {"id": "E", "registered": {"to": "F", "shift": [1, 1]}}
loop2 = {"id": "F", "registered": {"to": "E", "shift": [1, 1]}}
by = {t["id"]: t for t in (a, b, c, d, loop, loop2)}
assert om._redraw_from(a, by) is None, "the pointing's first tile: its own time"
assert om._redraw_from(b, by) == "A", "registered to A"
assert om._redraw_from(c, by) == "A", "a chain lands on its first tile's time"
assert om._redraw_from(c) == "B", "without the pass's tiles: the tile it was moved onto"
assert om._redraw_from(d, by) is None, "registration refused: its own time"
assert om._redraw_from(loop, by) in ("E", "F"), "a loop ends"
om.REDRAW_AT_REFERENCE = False
assert om._redraw_from(c, by) is None, "off: its own time"
print("redraw from: ok")
