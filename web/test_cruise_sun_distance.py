"""Check the Sun distances calibration.sun_distance gives the bodies Cassini passed on its way out (the Moon and Venus
in 1999, asteroid Masursky in 2000) against SPICE's at those flybys, and that Jupiter's, Saturn's and their moons' are
as they were. Before, every target without an orbit of its own was taken to be at Jupiter until 2003: the Moon's I/F
came out 24 times too high, Venus's 47 times.
Run: python web/test_cruise_sun_distance.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calibration as cal  # noqa: E402


def au(target, time):
    return cal.sun_distance({"TARGET_NAME": target, "IMAGE_TIME": time})


# SPICE (Sun to body, the mission's kernels) at the middle of each body's frames
assert abs(au("MOON", "1999-230T03:00:00.000") - 1.01188) < 0.002
assert abs(au("EARTH", "1999-230T03:00:00.000") - 1.01236) < 0.002
assert abs(au("VENUS", "1999-175T20:00:00.000") - 0.72464) < 0.001
assert abs(au("MASURSKY", "2000-023T03:30:00.000") - 2.617) < 0.001
# unchanged: the planets, and the moons and sky frames filed under the planet Cassini was at
assert abs(au("JUPITER", "2000-350T00:00:00.000") - 5.04) < 0.02
assert abs(au("IO", "2000-350T00:00:00.000") - au("JUPITER", "2000-350T00:00:00.000")) < 1e-12
assert abs(au("SATURN", "2008-100T00:00:00.000") - 9.3) < 0.2
assert abs(au("ENCELADUS", "2008-100T00:00:00.000") - au("SATURN", "2008-100T00:00:00.000")) < 1e-12
# what it means for I/F, which goes with the distance squared
was = cal.sun_distance({"TARGET_NAME": "SOMETHING ELSE", "IMAGE_TIME": "1999-230T03:00:00.000"})   # Jupiter's, as before
print(f"Moon 1999-08-18: {au('MOON', '1999-230T03:00:00.000'):.4f} AU (was {was:.3f}: I/F {(was / au('MOON', '1999-230T03:00:00.000')) ** 2:.1f} times too high); "
      f"Venus 1999-06-24: {au('VENUS', '1999-175T20:00:00.000'):.4f} AU ok")
