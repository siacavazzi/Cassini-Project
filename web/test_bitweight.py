"""CISSCAL's bit weight step (calibration.bitweighted), as cisscal main.cpp applies it: the table for the frame's camera,
gain state and front optics temperature, on 12BIT and 8LSB frames that are not lossy, not on TABLE frames or gain
state 0, before the bias. Run: python web/test_bitweight.py (with CISSCAL's files in CASSINI_CISSCAL; skipped without)"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import calibration as cal  # noqa: E402

if cal._bitweights("ISSNA", 2, "p5") is None:
    print("no CISSCAL bitweight files here: skipped")
    sys.exit(0)
info = {"INST_CMPRS_TYPE": "LOSSLESS", "DATA_CONVERSION_TYPE": "12BIT", "GAIN_MODE_ID": "29ELECTRONS_PER_DN",
        "INSTRUMENT_ID": "ISSNA", "OPTICS_TEMPERATURE": "(5.0,1.0)"}
dn = np.array([0.0, 121.0, 191.0, 4095.0])
got = cal.bitweighted(dn, info)
assert got[0] == 0 and abs(got[1] - 120.99) < 1e-9 and abs(got[2] - 190.93) < 1e-9 and got[3] == 4095
# the table by temperature (front optics), gain state and camera
assert cal._bitweights("ISSNA", 2, "p25") is not None and cal._bitweights("ISSWA", 3, "m10") is not None
assert cal.ff.temperature_name(dict(info, OPTICS_TEMPERATURE="(-8.0,1.0)")) == "m10"
# left alone: lossy, TABLE, gain state 0 (215 e/DN, no table)
for change in ({"INST_CMPRS_TYPE": "LOSSY"}, {"DATA_CONVERSION_TYPE": "TABLE"}, {"GAIN_MODE_ID": "215ELECTRONS_PER_DN"}):
    assert cal.bitweighted(dn, dict(info, **change)) is dn, change
# 8LSB frames too (as cisscal: only TABLE is excluded); their 0-255 DN sit where the table is the identity or nearly
assert cal.bitweighted(np.array([100.0]), dict(info, DATA_CONVERSION_TYPE="8LSB"))[0] == 100.0
print("ok")
