"""prebuild's --max-load default: the machine's real cores (not the slots the limiter makes os.cpu_count() answer),
and no load wait under the slot limiter (HEAVY_SLOTS). Run: python web/test_prebuild_max_load.py"""
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import prebuild  # noqa: E402

cores = os.sysconf("SC_NPROCESSORS_ONLN")
saved_env, saved_count = os.environ.get("HEAVY_SLOTS"), os.cpu_count
try:
    # the limiter's view: 3 slots held, os.cpu_count() answering 3
    os.environ["HEAVY_SLOTS"] = "3"
    os.cpu_count = lambda: 3
    assert math.isinf(prebuild.default_max_load()), prebuild.default_max_load()
    # outside the limiter (or HEAVY_SLOTS=0, its own probes): the real cores, whatever os.cpu_count() says
    for v in (None, "0"):
        if v is None:
            os.environ.pop("HEAVY_SLOTS", None)
        else:
            os.environ["HEAVY_SLOTS"] = v
        assert abs(prebuild.default_max_load() - 0.8 * cores) < 1e-9, (v, prebuild.default_max_load(), cores)
finally:
    os.cpu_count = saved_count
    if saved_env is None:
        os.environ.pop("HEAVY_SLOTS", None)
    else:
        os.environ["HEAVY_SLOTS"] = saved_env
print("ok")
