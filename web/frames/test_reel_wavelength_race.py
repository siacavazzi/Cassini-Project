#!/usr/bin/env python3
"""Checks that reel.wavelength's table (filter_calibration.csv) is never seen half-filled by another thread, as
calibration.filter_table (#388): a thread that found it still filling got 0 nm for its filter.
python web/frames/test_reel_wavelength_race.py"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import reel  # noqa: E402

COLD_STARTS = 200


def test_wavelength():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)   # switch threads as often as possible, so a half-filled table is seen
    bad = 0
    try:
        for _ in range(COLD_STARTS):
            reel._nm = None
            got, gate = [], threading.Barrier(2)

            def go(fs):
                gate.wait()
                got.append(reel.wavelength("ISSWA", fs))
            threads = [threading.Thread(target=go, args=(fs,)) for fs in ("CL1VIO", "IR3CL2")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            bad += any(not g for g in got)
    finally:
        sys.setswitchinterval(old)
    assert bad == 0, f"{bad} of {COLD_STARTS} cold starts: a thread got no wavelength"


if __name__ == "__main__":
    test_wavelength()
    print("ok test_wavelength")
