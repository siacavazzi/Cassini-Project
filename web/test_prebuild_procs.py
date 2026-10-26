#!/usr/bin/env python3
"""prebuild.py's sharing of the Mini: a phase split over processes (--procs) makes every item once, each process
its own stretch, and their status files add up to the phase's; the holds are asked off the thread that hands out
the work (a slow check no longer holds the workers back); --min-free waits while the cache's disk is short.

  python web/test_prebuild_procs.py
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import prebuild  # noqa: E402

N = 200


def fake_items(phase):
    def work(cache, i):
        with open(os.path.join(cache, f"{i}.{os.getpid()}"), "w") as fh:
            fh.write("x")
    return [(str(i), lambda c, i=i: work(c, i)) for i in range(N)]


def main():
    prebuild.items = fake_items
    if "--shard" in sys.argv or "--procs" in sys.argv:   # a run: the test below starts these, children start themselves
        prebuild.main()
        return
    ok = 0
    with tempfile.TemporaryDirectory() as d:
        cache, status = os.path.join(d, "cache"), os.path.join(d, "status")
        os.makedirs(cache)
        os.environ["CASSINI_DATA"] = d   # a folder, so no archive index is read
        t0 = time.monotonic()
        rc = os.spawnv(os.P_WAIT, sys.executable, [sys.executable, __file__, "frames", "--cache", cache, "--status", status,
                                                 "--procs", "4", "--live", "", "--pause", os.path.join(d, "pause")])
        assert rc == 0, rc
        made = sorted(f.split(".") for f in os.listdir(cache) if not f.startswith("errors-"))
        assert sorted(int(i) for i, _ in made) == list(range(N)), made          # every item, once
        assert len({pid for _, pid in made}) == 4, made                          # by four processes
        with open(os.path.join(status, "status-frames.json")) as fh:
            s = json.load(fh)
        assert s["done"] == N and s["total"] == N and s["errors"] == 0 and s["state"] == "done", s
        ok += 1
        assert time.monotonic() - t0 < 60
        # the holds: a check taking 1 s, asked off the dispatch thread, costs the run nothing per item
        calls = []

        def slow_busy(args):
            calls.append(1)
            time.sleep(1)
            return None
        prebuild.busy, real = slow_busy, prebuild.busy
        cache2 = os.path.join(d, "cache2")
        os.makedirs(cache2)
        a = prebuild.argparse.Namespace(phase="frames", cache=cache2, status=None, threads=2, first=0, shard=None)
        t0 = time.monotonic()
        prebuild.run(a)
        took = time.monotonic() - t0
        assert len([f for f in os.listdir(cache2) if not f.startswith("errors-")]) == N
        assert took < 1 + 3, took   # the first answer only (asked once when the holds start), not one per 20 items
        ok += 1
        prebuild.busy = real
        # --min-free: waits while the disk has less free than asked
        a = prebuild.argparse.Namespace(pause="", max_load=1e9, live="", watch="", disk=None, cache=cache2, min_free=1e12)
        assert real(a).startswith("disk "), real(a)
        a.min_free = 0.001
        assert real(a) is None
        ok += 1
        # --only: the items using a listed frame
        listed = os.path.join(d, "only.txt")
        with open(listed, "w") as fh:
            fh.write("# lost lines\nN2_1\nW5_1 extra\n")
        todo = [("N1_1", None), ("N2_1", None), ("W5_1", None)]
        assert [t[0] for t in prebuild.only("frames", todo, listed)] == ["N2_1", "W5_1"]
        sets = [("N1_1_N3_1", None), ("N3_1_N2_1", None), ("W4_1_W5_1_W6_1", None), ("N2_11_N7_1", None)]
        assert [t[0] for t in prebuild.only("composites", sets, listed)] == ["N3_1_N2_1", "W4_1_W5_1_W6_1"]
        ok += 1
    print(f"{ok} checks ok")


if __name__ == "__main__":
    main()
