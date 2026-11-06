"""
Auto center on the cruise's bodies: Io and Europa in eclipse, Himalia (2000-2001) and the Moon (1999) had no radius,
so obs_mosaic.centre_view answered "no disk of a known body" and left the picture where the camera had it. They are in
RADIUS now (obs_mosaic.CRUISE_RADIUS), and, as the small moons, not in FILL_RADIUS (far off, a disk of a few dozen
pixels the filled scale would blow out). With a geometry cache that places N1356777593_1 (Io), centre_view centers it.
Run: PYTHONPATH=. python web/test_cruise_centre.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om

for body in ("IO", "EUROPA", "GANYMEDE", "CALLISTO", "HIMALIA", "MOON"):
    assert om.RADIUS.get(body, 0) > 0, body
    assert body not in om.FILL_RADIUS, body
# Io 10.1 million km off: a disk of about 30 NAC pixels
r = om.RADIUS["IO"] / (10102581 * om.IFOV["N"])
assert 25 < r < 35, r
if os.environ.get("CASSINI_GEOMETRY_CACHE") and os.path.exists(os.path.join(om.REPO if hasattr(om, "REPO") else ".", "Image_index.csv")):
    import reel
    if reel.geometry(["N1356777593_1"]).get("N1356777593_1"):
        view = om.centre_view("N1356777593_1")
        assert view["centre"], view
        print("Io centered:", view)
print("ok")
