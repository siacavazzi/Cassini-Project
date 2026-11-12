"""
The body a frame shows (bootleg_autonav.shown_body, shown_targets): a frame whose archive target is a dot (a moon a pixel
or two across) while SPICE puts a body with a real disk on it is centred, grouped and calibrated as a picture of that
body. Sam 2026-11-12: N1455663489_1 (ISS_C42OT_SATELLORB002, NAC CL1/CL2, archive target Enceladus) looked
unprocessed: Auto center put Enceladus, an invisible dot near the middle, in the middle, and Saturn stayed cut off at
the frame's left edge.
With a geometry cache whose bodies table has that frame, its label, the index, stacking.places and the camera
windows' Auto center all take Saturn.
Run: PYTHONPATH=. python web/test_shown_body.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "frames"))
import bootleg_autonav as ba

saturn = ("SATURN", -327.3, -140.3, 147.7, 65883203.9)   # (body, x, y, r, km) as bodies_in_frame gives it
dione = ("DIONE", -116.0, -404.0, 1.43, 65529546.9)
# a dot of a target, a big disk on the frame: the big disk
assert ba.shown_body(0.64, [dione, saturn]) == saturn
# a target with a disk of its own keeps it, however big the other body
assert ba.shown_body(ba.SEEN_RADIUS + 0.1, [saturn]) is None
# a target of no known size keeps it (sky, rings)
assert ba.shown_body(None, [saturn]) is None
# another dot is no picture of it
assert ba.shown_body(0.5, [dione]) is None
# a body whose centre is off the frame (a limb coming in) is not what the frame looks at, nor one the frame cuts
# (Saturn's limb across a WAC frame, W1497970864_1)
assert ba.shown_body(0.5, [("SATURN", -700.0, 0.0, 300.0, 1e6)]) is None
assert ba.shown_body(0.34, [("SATURN", 484.5, 263.8, 430.7, 1e6)]) is None
# Saturn filling the frame behind a moon whole on it (N1523942620_1, archive target Helene): no picture of the moon
assert ba.shown_body(0.4, [("SATURN", -79.0, -80.0, 2650.3, 3.67e6), ("TETHYS", 366.0, 384.0, 22.3, 3.97e6)]) is None
# the biggest of several
rhea = ("RHEA", 100.0, 50.0, 20.0, 2e6)
assert ba.shown_body(1.0, [rhea, ("MIMAS", 0.0, 0.0, 13.0, 1e6)]) == rhea
assert ba.shown_body(1.0, [("MIMAS", 0.0, 0.0, ba.SHOWN_RADIUS - 0.1, 1e6)]) is None

FRAME = "N1455663489_1"
if ba.GEOMETRY_CACHE and os.path.exists(ba.GEOMETRY_CACHE) and FRAME in ba.shown_targets():
    import stacking
    import reel
    import obs_mosaic as om
    body, x, y, z = ba.shown_targets()[FRAME]
    assert body == "SATURN", body
    assert 300 < x < 360 and 120 < y < 160, (x, y)   # Saturn's centre left of and below the frame's middle
    assert stacking.places([FRAME])[FRAME] == (x, y, z)
    idx, _ = reel.load_index()
    assert idx.loc[idx["id"] == FRAME, "TARGET_NAME"].tolist() == ["SATURN"]
    # the other bodies on it: Enceladus (the archive's target) among them, Saturn not
    others = [b[0] for b in ba.bodies_of([FRAME])[FRAME]]
    assert "ENCELADUS" in others and "SATURN" not in others, others
    view = om.centre_view(FRAME)
    assert view["centre"] and view["pass"][0] == "SATURN", view
    print("N1455663489_1 centred on Saturn:", view["pass"])
print("ok")
