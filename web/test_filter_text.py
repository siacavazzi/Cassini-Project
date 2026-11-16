"""Filter columns read as text (sets_passes.as_text, reel.load_index): a missing filter1/filter2 reads as "nan", as
pandas 1 and 2's astype(str) gave it, also under pandas 3 (whose astype(str) keeps NaN, a float, which colour_filter
could not read: AttributeError in the cloud's pandas 3.0.5). Run: python web/test_filter_text.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames")]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sets_passes as sp  # noqa: E402

col = pd.Series(["CL1", np.nan, "P0", 12.0], dtype=object)
assert sp.as_text(col) == ["CL1", "nan", "P0", "12.0"], sp.as_text(col)
assert sp.as_text(pd.Series(["CL1", np.nan], dtype=object)) == ["CL1", "nan"]
# the same as pandas 1/2's astype(str), where that keeps NaN as "nan"
if pd.__version__.split(".")[0] in ("1", "2"):
    assert sp.as_text(col) == col.astype(str).tolist()
# colour_filter reads a missing filter's text (it raised on NaN), and sets work out round it
assert sp.colour_filter("nan", "nan") == "nan/nan"
idx = pd.DataFrame({"INSTRUMENT_ID": ["ISSNA"] * 3, "TARGET_NAME": ["SATURN"] * 3, "OBSERVATION_ID": ["O"] * 3,
                    "filter1": ["CL1", "CL1", np.nan], "filter2": ["RED", "GRN", np.nan], "seconds_1970": [0.0, 20.0, 40.0]})
f1s, f2s = sp.as_text(idx["filter1"]), sp.as_text(idx["filter2"])
set_of, sets = sp.filter_sets(idx["INSTRUMENT_ID"].tolist(), idx["TARGET_NAME"].tolist(), idx["OBSERVATION_ID"].tolist(),
                              f1s, f2s, idx["seconds_1970"].to_numpy(), lambda q: 600.0)
assert len(sets) >= 1 and set_of[0] == set_of[1] >= 0, (set_of, sets)
print("filter columns with a missing value read as text, as pandas 2 did; sets work out on them")
print("ok")
