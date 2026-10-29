#!/usr/bin/env python3
"""Cache slices (slices.py, prebuild.py --years): a phase built for some years records them in the cache's
slices.json under the picture versions; the frame server reports only records under its own versions, as the
stretches every recorded phase covers; a cache without a record, or a whole-mission run, is the whole mission.

  python web/test_prebuild_slices.py
"""
import json
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import prebuild  # noqa: E402
import slices  # noqa: E402

# a frame a month from 2003-12 to 2005-01, and two passes: one across New Year 2004/2005, one in 2003
TIMES = {f"N{1070000000 + k * 2600000}_1": 1070000000 + k * 2600000 for k in range(15)}
IDS = list(TIMES)


def fake_index():
    return pd.DataFrame({"id": IDS, "seconds_1970": [float(TIMES[i]) for i in IDS]}), []


def fake_items(phase):
    def work(cache, name):
        with open(os.path.join(cache, f"{name}.{phase}"), "w") as fh:
            fh.write("x")
    if phase in ("frames", "processed"):
        return [(i, lambda c, i=i: work(c, i)) for i in IDS]
    if phase == "composites":
        return [(f"{IDS[k]}_{IDS[k + 1]}", lambda c, k=k: work(c, IDS[k])) for k in range(0, 14, 2)]
    return [(name, lambda c, n=name: work(c, n)) for name in ("SATURN_A_N_0", "TITAN_B_N_0")]


PASSES = [{"key": ("SATURN", "A", "N", 0), "frames": [(0, IDS[13], 0, TIMES[IDS[13]]), (0, IDS[14], 0, TIMES[IDS[14]])]},
          {"key": ("TITAN", "B", "N", 0), "frames": [(0, IDS[0], 0, TIMES[IDS[0]])]}]


def year_of(i):
    return pd.Timestamp(TIMES[i], unit="s").year


def main():
    prebuild.reel.load_index = fake_index
    prebuild.items = fake_items
    prebuild.all_passes = lambda: PASSES
    ok = 0

    assert slices.parse_years("2004") == [("2004-01-01T00:00:00", "2005-01-01T00:00:00")]
    assert slices.parse_years("2004-2005,2008") == [("2004-01-01T00:00:00", "2006-01-01T00:00:00"),
                                                     ("2008-01-01T00:00:00", "2009-01-01T00:00:00")]
    assert slices.parse_years("2004,2005") == [("2004-01-01T00:00:00", "2006-01-01T00:00:00")]   # touching: one
    assert slices.utc("2004-06-30") == "2004-06-30T00:00:00" and slices.utc("2004-06-30T12:00Z") == "2004-06-30T12:00:00"
    assert slices.intersect([(None, None)], [("2004", "2005")]) == [("2004", "2005")]
    assert slices.intersect([("2004", "2006")], [("2005", "2007"), ("2003", "2004")]) == [("2005", "2006")]
    for bad in ("1996", "2018", "2005-2004"):
        try:
            slices.parse_years(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    ok += 1

    # which items a slice takes: frames by their time, a set with any frame in it, a pass with any frame in it
    y2004 = slices.parse_years("2004")
    got = prebuild.within("frames", fake_items("frames"), y2004)
    assert [n for n, _ in got] == [i for i in IDS if year_of(i) == 2004], got
    got = prebuild.within("composites", fake_items("composites"), y2004)
    assert all(any(year_of(i) == 2004 for i in ("_".join(n.split("_")[:2]), "_".join(n.split("_")[2:]))) for n, _ in got)
    assert len(got) == 6, got   # 7 sets, the first one is 2003 only (Dec 2003 + Jan 2004 counts)
    got = prebuild.within("movies", fake_items("movies"), y2004)
    assert [n for n, _ in got] == ["SATURN_A_N_0"], got   # across New Year: whole; the 2003 pass not
    ok += 1

    with tempfile.TemporaryDirectory() as d:
        os.environ["CASSINI_DATA"] = d
        cache, status = os.path.join(d, "cache"), os.path.join(d, "status")
        os.makedirs(cache)
        mine = prebuild.frame_server.picture_versions()
        assert mine and all(isinstance(v, (str, dict)) for v in mine.values())
        assert "frame_server.SERVER_VERSION" not in mine
        # no file: the whole mission
        assert slices.covered(cache, mine) == {"spans": None, "phases": {}}
        argv = sys.argv
        for phase, years in (("frames", "2004"), ("processed", "2004")):
            sys.argv = ["prebuild.py", phase, "--cache", cache, "--status", status, "--live", "", "--years", years,
                        "--pause", os.path.join(d, "pause")]
            prebuild.main()
        made = sorted(f for f in os.listdir(cache) if f.endswith(".frames"))
        assert made == sorted(f"{i}.frames" for i in IDS if year_of(i) == 2004), made
        got = slices.covered(cache, mine)
        assert got["spans"] == [["2004-01-01T00:00:00", "2005-01-01T00:00:00"]], got
        # only processed for 2005 as well: frames still 2004 only, so 2004 only
        sys.argv = ["prebuild.py", "processed", "--cache", cache, "--live", "", "--from", "2005-01-01",
                    "--until", "2005-03-01", "--pause", os.path.join(d, "pause")]
        prebuild.main()
        assert slices.covered(cache, mine)["spans"] == [["2004-01-01T00:00:00", "2005-01-01T00:00:00"]]
        assert slices.covered(cache, mine)["phases"]["processed"] == [["2004-01-01T00:00:00", "2005-03-01T00:00:00"]]
        # a server on other versions (older code, its pictures in other folders): the whole mission
        other = {**mine, "frame_server.COLOR_VERSION": "color-v0"}
        assert slices.covered(cache, other) == {"spans": None, "phases": {}}
        # --only (a remake of some frames) records nothing
        with open(os.path.join(d, "ids.txt"), "w") as fh:
            fh.write(IDS[3] + "\n")
        n = len(slices.read(cache)["records"])
        sys.argv = ["prebuild.py", "frames", "--cache", cache, "--live", "", "--only", os.path.join(d, "ids.txt"),
                    "--pause", os.path.join(d, "pause")]
        prebuild.main()
        assert len(slices.read(cache)["records"]) == n
        # a whole-mission run of both phases: the whole mission again
        for phase in ("frames", "processed"):
            sys.argv = ["prebuild.py", phase, "--cache", cache, "--live", "", "--pause", os.path.join(d, "pause")]
            prebuild.main()
        assert slices.covered(cache, mine)["spans"] is None, slices.covered(cache, mine)
        sys.argv = argv
        # a broken file reads as no records (the whole mission), never an error for the page
        with open(os.path.join(cache, slices.NAME), "w") as fh:
            fh.write("{not json")
        assert slices.covered(cache, mine) == {"spans": None, "phases": {}}
        json.dumps(slices.covered(cache, mine))
        ok += 1
    print(f"{ok} of 3 ok")


if __name__ == "__main__":
    main()
