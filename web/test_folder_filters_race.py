#!/usr/bin/env python3
"""A pass's folder never loses its colour suffix while another thread works out its filters.

obs_mosaic._filters set u["set_colour"] (and played_pair, one_pair) to False first and only then to what the pass
takes, and plan() runs it on every pass it plans. folder() reads those flags, so a thread asking a colour movie's
folder in between got the folder without _c1: right after a server start, warm_movie's plan for TITAN 259TI
COMPMAP001 was written to a folder of its own (zero-render check 2017, 11-18). _filters now works on a copy and sets
the flags on the pass once, set_colour last.

  python web/test_folder_filters_race.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

FR = [(None, f"W1864655{400 + k}_1", f, 1000.0 + k, nm) for k, (f, nm) in enumerate([("CB3", 938), ("MT1", 619)] * 4)]
U = {"key": ("TITAN", "ISS_TEST_RACE001_PRIME", "W", 0), "kind": "movie", "movie": True, "mosaic": False,
     "frames": FR, "_polarized": False, "_repointed": False}
om._aside = lambda frames, u: set()
om.colour_of = lambda count, nms: None            # its counts make it grey ...
om.colour_sets = lambda frames: []


def slow_set_colour(frames, count, nms):          # ... and its sets colour it, worked out slowly
    time.sleep(0.05)
    return ["CB3", "MT1"]


om._set_colour = slow_set_colour
om._filters(U)                                    # the first plan: the pass is a colour movie
assert U["set_colour"] is True
good = om.folder(U, "/c")
assert good.endswith(om.SET_COLOUR), good

seen, stop = set(), threading.Event()


def ask():
    while not stop.is_set():
        seen.add(om.folder(U, "/c"))


t = threading.Thread(target=ask)
t.start()
for _ in range(20):                               # plan() works the filters out again, as it does for every plan
    om._filters(U)
stop.set()
t.join()
print("folders seen while the filters were worked out again:", sorted(seen))
assert seen == {good}, seen
print("ok")
