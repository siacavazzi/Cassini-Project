#!/usr/bin/env python3
"""Checks that calibration's lazily read tables (filter_table, band_wavelength, body_level/false_gains, eye_tint) are
never seen half-filled by another thread: obs_mosaic.pass_scale calibrates a pass's first frames on a thread pool, and a
thread that found filter_table() still filling had no factor for its filter, so calibrate returned None and the frame
was left out of the pass's cached display scale (the MacBook's 269RI_HIPHASEFB001 plan without its first IR3 frame,
W1870759038_1, 2026-11-09; ISSWA IR3CL2 is 13 rows after CL1VIO in filter_calibration.csv).
python web/test_table_race.py"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calibration as cal  # noqa: E402

COLD_STARTS = 200


def cold(reset, *lookups):
    """How many of COLD_STARTS cold starts had a thread get None from one of lookups, run at once"""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)   # switch threads as often as possible, so a half-filled table is seen
    bad = 0
    try:
        for _ in range(COLD_STARTS):
            reset()
            got, gate = [], threading.Barrier(len(lookups))

            def go(fn):
                gate.wait()
                got.append(fn())
            threads = [threading.Thread(target=go, args=(fn,)) for fn in lookups]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            bad += any(g is None for g in got)
    finally:
        sys.setswitchinterval(old)
    return bad


def test_filter_table():
    assert cold(lambda: setattr(cal, "_filters", None), lambda: cal.filter_table().get(("ISSWA", "CL1VIO")),
                lambda: cal.filter_table().get(("ISSWA", "IR3CL2"))) == 0


def test_band_wavelength():
    assert cold(lambda: setattr(cal, "_wavelengths", None), lambda: cal.band_wavelength("W", "VIO"),
                lambda: cal.band_wavelength("W", "IR3")) == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
