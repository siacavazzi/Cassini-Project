"""Polarized colour (sets_passes.polarized_as_colour, polarized_index): an observation's visible polarizer frames
count as their colour filter only when it takes all of BL2, GRN and CB1 through them and no visible colour plainly;
their three angles then make one set's channels, and the index reads them as CL1 and their filter.
Run: python web/test_polarized_colour.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames")]
import pandas as pd  # noqa: E402
import sets_passes as sp  # noqa: E402


def frames(obs, rows, cam="ISSNA", target="SATURN", t0=0.0, step=20.0):
    return [(cam, target, obs, a, b, t0 + k * step) for k, (a, b) in enumerate(rows)]


cycle = [(p, f) for f in ("CB2", "CB1", "GRN", "BL2") for p in ("P0", "P60", "P120")]
pol_only = frames("POL", cycle + [("CL1", "MT2")])                                  # 2X2PLRNC / 1X2PLRNCJ (CL1 MT2)
mixed = frames("MIX", cycle + [("CL1", "GRN")], t0=10000)                            # also a plain visible colour
two = frames("TWO", [(p, f) for f in ("GRN", "BL2") for p in ("P0", "P60", "P120")], t0=20000)   # no CB1
wac = frames("WAC", [("CB2", "IRP0"), ("CB2", "IRP90"), ("MT2", "IRP0"), ("MT2", "IRP90")], cam="ISSWA", t0=30000)
rows = pol_only + mixed + two + wac
cams, targets, obs, f1s, f2s, ts = map(list, zip(*rows))

use = sp.polarized_as_colour(cams, targets, obs, f1s, f2s)
got = {o: [f"{a}/{b}" for o2, a, b, u in zip(obs, f1s, f2s, use) if o2 == o and u] for o in ("POL", "MIX", "TWO", "WAC")}
assert got["POL"] == [f"{p}/{f}" for p, f in cycle if f != "CB2"], got["POL"]
assert got["MIX"] == [] and got["TWO"] == [], got
assert got["WAC"] == ["CB2/IRP0", "CB2/IRP90", "MT2/IRP0", "MT2/IRP90"], got["WAC"]
print("only an observation taking BL2, GRN and CB1 through polarizers, and no plain visible colour, is polarized colour")
print("a WAC observation taking two bands only through the IR polarizers is too (taste call 9)")

idx = pd.DataFrame({"INSTRUMENT_ID": cams, "TARGET_NAME": targets, "OBSERVATION_ID": obs, "filter1": f1s, "filter2": f2s,
                    "FILTER_NAME": [f"({a},{b})" for a, b in zip(f1s, f2s)]})
sp.polarized_index(idx)
pol = idx[idx["OBSERVATION_ID"] == "POL"]
assert pol["FILTER_NAME"].tolist() == ["(P0,CB2)", "(P60,CB2)", "(P120,CB2)"] + [f"(CL1,{f})" for _, f in cycle[3:]] + ["(CL1,MT2)"]
assert pol["filter1"].tolist()[3:-1] == ["CL1"] * 9 and pol["polarized"].sum() == 9
assert idx[idx["OBSERVATION_ID"] == "WAC"]["FILTER_NAME"].tolist() == ["(CB2,CL2)", "(CB2,CL2)", "(MT2,CL2)", "(MT2,CL2)"]
assert idx[idx["OBSERVATION_ID"] == "WAC"]["filter2"].tolist() == ["CL2"] * 4
assert idx[~idx["OBSERVATION_ID"].isin(["POL", "WAC"])]["FILTER_NAME"].tolist() == \
    [f"({a},{b})" for a, b, o in zip(f1s, f2s, obs) if o not in ("POL", "WAC")]
print("the index reads them as CL1 and their colour; every other frame as it was")

set_of, sets = sp.filter_sets(idx["INSTRUMENT_ID"].tolist(), targets, obs, idx["filter1"].tolist(), idx["filter2"].tolist(), ts,
                              lambda q: {"CB1": 619.0, "GRN": 568.0, "BL2": 440.0, "MT2": 727.0, "CB2": 750.0}.get(f2s[q], 600.0))
mine = [s for s in sets if all(obs[q] == "POL" for q in s["rows"])]
assert len(mine) == 1 and mine[0]["kind"] == "true", mine
assert [f2s[q] for q in mine[0]["use"]] == ["CB1", "GRN", "BL2"] and len(mine[0]["rows"]) == 10, mine
print("one true colour set: CB1, GRN, BL2, each filter's three angles in it as repeat exposures, MT2 after them")
print("ok")
