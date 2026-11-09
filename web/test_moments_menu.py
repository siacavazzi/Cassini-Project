#!/usr/bin/env python3
"""
Checks for the Moments window's data (web/cassini-os/src/moments.html): every moments.csv row has a known type, and
candidates.csv (make_candidates.py) turns into data/candidates.json entries the window can sort and play.

  python web/test_moments_menu.py
"""
import csv, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "replay"))
import build_data  # noqa: E402
import make_candidates  # noqa: E402


def main():
    ok = 0
    rows = list(csv.DictReader(open(build_data.MOMENTS, newline="")))
    assert rows and all(r["type"] in build_data.MOMENT_TYPES for r in rows), {r["type"] for r in rows}
    ok += 1
    cands = list(csv.DictReader(open(build_data.CANDIDATES, newline="")))
    assert all(c["type"] in build_data.CANDIDATE_TYPES for c in cands)
    assert all(c["start_utc"] <= (c["end_utc"] or c["start_utc"]) for c in cands)
    assert sum(c["type"] == "movie" for c in cands) > 2000
    ok += 1
    # a potential transit or find is never one already in the list (by observation)
    listed = {o for r in rows for o in r["obs"].split()}
    assert not [c for c in cands if c["type"] != "movie" and set(c["obs"].split()) & listed]
    ok += 1
    # the entries: in time order, inside the asked years, times the inverse of utc_of
    args = types.SimpleNamespace(candidates=build_data.CANDIDATES)
    es = build_data.candidates(args, [2005])
    assert es and all(e["utc"].startswith("2005") for e in es) and es == sorted(es, key=lambda e: e["et"])
    assert all(e["end_et"] >= e["et"] and e["kind"] in build_data.CANDIDATE_TYPES for e in es)
    assert all(abs(build_data.et_of(build_data.utc_of(e["et"])) - e["et"]) <= 1 for e in es)   # utc_of drops the fraction
    ok += 1
    # a type the window does not know stops the build
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        w = csv.DictWriter(f, make_candidates.COLS); w.writeheader()
        w.writerow({"type": "rumor", "start_utc": "2005-01-01T00:00:00", "end_utc": "2005-01-01T01:00:00", "label": "x", "frames": "1"})
    try:
        build_data.candidates(types.SimpleNamespace(candidates=f.name), [2005])
        raise AssertionError("an unknown type passed")
    except SystemExit:
        ok += 1
    finally:
        os.unlink(f.name)
    assert make_candidates.iso("2012-127T19:58:06.091") == "2012-05-06T19:58:06"
    ok += 1
    print(f"{ok} checks ok")


if __name__ == "__main__":
    main()
