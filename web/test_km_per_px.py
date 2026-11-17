#!/usr/bin/env python3
"""The catalog's km/px (export_tracks): one of the frame's own pixels at the ground in its middle.
  python web/test_km_per_px.py"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_tracks as et

W = 5.9715e-5   # the WAC's pixel as its frames are drawn (12 um at geometric_correction.F_LINEAR, 200.956 mm)


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def main():
    # the axis on the body's center: the near surface, the center's distance less the radius (Titan, 24,031 km)
    assert close(et.ground_range(24031.0, 2575.0, 0.0, W), 24031.0 - 2575.0)
    # off the center but on the disk: where the axis meets the sphere, between the near surface and the limb
    d = et.ground_range(24031.0, 2575.0, 0.05, W)
    assert 24031.0 - 2575.0 < d < math.sqrt(24031.0 ** 2 - 2575.0 ** 2), d
    side = 24031.0 * math.sin(0.05)
    assert close(d, 24031.0 * math.cos(0.05) - math.sqrt(2575.0 ** 2 - side ** 2))
    # the axis past the limb, the limb in the frame: the limb's distance
    limb = math.asin(2575.0 / 24031.0)
    assert close(et.ground_range(24031.0, 2575.0, limb + 0.01, W), math.sqrt(24031.0 ** 2 - 2575.0 ** 2))
    # the body out of the frame, or no radius: the center's distance, as before
    assert et.ground_range(24031.0, 2575.0, limb + et.FOV_HALF * W + 0.01, W) == 24031.0
    assert et.ground_range(24031.0, None, 0.0, W) == 24031.0
    # a body a quarter turn or more off the axis (N1841132267_1: Saturn 1.9 million px off, 11 "radians"): its centre
    assert et.ground_range(651889.9, 58232.0, 1883195.8 * 5.9897e-6, 5.9897e-6) == 651889.9
    # far away the ground is the center less a hair
    assert close(et.ground_range(1.2e9, 60268.0, 0.0, W), 1.2e9 - 60268.0)
    assert et.SUMMING == {"FULL": 1, "SUM2": 2, "SUM4": 4}
    assert et.summing(None, ["x/N1.png"]) == {}
    print("km/px: ground in the frame's middle, summing: ok")


if __name__ == "__main__":
    main()
