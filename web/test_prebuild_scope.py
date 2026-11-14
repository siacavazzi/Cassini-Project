#!/usr/bin/env python3
"""A pre-build run cut to a stretch (--years, --from/--until) or to some frames (--only) lists only the passes of
the observations with a frame in it (prebuild.scoped, all_passes), and so takes the same items in the same order as
the whole mission's list cut down by within and only, without working out any other observation's passes.

  python web/test_prebuild_scope.py
"""
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import prebuild  # noqa: E402
import slices  # noqa: E402

# a frame a month: 0 and 1 in 2003, 2 to 13 in 2004, 14 in 2005
TIMES = [1070000000 + k * 2600000 for k in range(15)]
IDS = [f"N{t}_1" for t in TIMES]
# four observations, each cut into passes of its own rows: C runs across New Year 2004/2005, D is the WAC's
OBS = {("SATURN", "A", "ISSNA"): [[0, 1], [2, 3]], ("TITAN", "B", "ISSNA"): [[4, 5], [6, 7]],
       ("RHEA", "C", "ISSNA"): [[10, 11], [13, 14]], ("SATURN", "D", "ISSWA"): [[8, 9], [12]]}
asked = []


def fake_index():
    of = {k: key for key, parts in OBS.items() for part in parts for k in part}
    return pd.DataFrame({"id": IDS, "seconds_1970": [float(t) for t in TIMES], "TARGET_NAME": [of[k][0] for k in range(15)],
                         "OBSERVATION_ID": [of[k][1] for k in range(15)], "INSTRUMENT_ID": [of[k][2] for k in range(15)]}), []


def fake_observations():
    return fake_index()[0], {key: np.array(sorted(k for part in parts for k in part)) for key, parts in OBS.items()}


def fake_units(target, obs, cam):
    asked.append((target, obs, cam))
    parts = OBS[(target, obs, "ISSNA" if cam == "N" else "ISSWA")]
    return [{"key": (target, obs, cam, n), "mosaic": n == 0, "kind": "mosaic" if n == 0 else "movie", "movie": n == 1,
             "frames": [(0, IDS[k], 0, float(TIMES[k])) for k in part]} for n, part in enumerate(parts)]


def taken(scope, spans, path):
    """The items each pass phase takes (chosen's cuts) with the run's scope set as main sets it, and the
    observations whose passes were worked out for them."""
    prebuild._scope[0] = scope
    prebuild.all_passes.cache_clear()
    prebuild.mosaic_passes.cache_clear()
    del asked[:]
    out = {}
    for phase in ("mosaics", "movies", "strips", "chains"):
        todo = [(name, None) for name, _ in prebuild.items(phase)]
        if path:
            todo = prebuild.only(phase, todo, path)
        if spans:
            todo = prebuild.within(phase, todo, spans)
        out[phase] = [name for name, _ in todo]
    return out, sorted(set(asked))


def main():
    prebuild.reel.load_index = fake_index
    prebuild.obs_mosaic._observations = fake_observations
    prebuild.obs_mosaic.units = fake_units
    y2003, y2004, y2005 = (slices.parse_years(y) for y in ("2003", "2004", "2005"))
    with tempfile.TemporaryDirectory() as d:
        only = os.path.join(d, "ids.txt")
        with open(only, "w") as fh:
            fh.write(f"{IDS[5]}\n# a comment\n{IDS[12]},own\n")
        assert prebuild.scoped(y2003, None) == {("SATURN", "A", "N")}
        assert prebuild.scoped(y2005, None) == {("RHEA", "C", "N")}
        assert prebuild.scoped(y2004, None) == {("SATURN", "A", "N"), ("TITAN", "B", "N"), ("RHEA", "C", "N"), ("SATURN", "D", "W")}
        assert prebuild.scoped([("2004-03-01T00:00:00", "2004-05-01T00:00:00")], None) == {("TITAN", "B", "N")}
        assert prebuild.scoped(None, only) == {("TITAN", "B", "N"), ("SATURN", "D", "W")}
        assert prebuild.scoped(y2005, only) == set()        # a frame in the stretch and a frame of the list: neither has both
        whole, every = taken(None, None, None)
        assert len(every) == 4 and sum(map(len, whole.values())) == 4 + 3 * 4, (whole, every)
        cuts = [(y2003, None), (y2004, None), (y2005, None), ([("2004-03-01T00:00:00", "2004-05-01T00:00:00")], None),
                (y2003 + y2005, None), (None, only), (y2004, only), (y2005, only)]
        for spans, path in cuts:
            before, all_obs = taken(None, spans, path)          # the whole mission listed, then cut
            after, own = taken((spans, path), spans, path)      # as main runs a slice
            assert after == before, (spans, path, before, after)
            assert all_obs == every and own == sorted(prebuild.scoped(spans, path)), (spans, path, own)
            assert len(own) < len(every) or spans == y2004, (spans, path, own)
        # a pass across New Year is taken whole by both years, as before
        assert "RHEA_C_N_1" in taken((y2004, None), y2004, None)[0]["movies"]
        assert "RHEA_C_N_1" in taken((y2005, None), y2005, None)[0]["movies"]
    prebuild._scope[0] = None
    print("ok: 8 cuts take the same items scoped as cut from the whole list, from their own observations alone")


if __name__ == "__main__":
    main()
