"""Synthetic check of calibration.bias_of: a frame whose bias strip was lost with its missing lines (strip mean
0 or below) takes its bias from its dark sky, leaving out the lost lines; a good strip mean is used as it is.
Run: python web/test_bias_strip.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import calibration as cal  # noqa: E402

cal.ds._lut8 = True                                     # the lean archive: stored codes, nothing guessed
rng = np.random.default_rng(5)
codes = rng.integers(16, 60, (256, 256)).astype(np.uint8)   # dark sky from code 16 up
codes[40:68] = 0                                        # 28 lines lost in transmission
sky = float(np.percentile(cal.stored_values(codes[codes > 0], {"DATA_CONVERSION_TYPE": "12BIT"}), 0.1))

for conv in ("12BIT", "TABLE"):
    good = cal.bias_of(codes, {"DATA_CONVERSION_TYPE": conv, "BIAS_STRIP_MEAN": "31.9"})
    assert good == 31.9, good                           # a good strip mean as it is
    for mean in ("-235.4", "0"):
        lost = cal.bias_of(codes, {"DATA_CONVERSION_TYPE": conv, "BIAS_STRIP_MEAN": mean})
        floor = sky if conv == "12BIT" else 16.0
        print(conv, "strip mean", mean, "-> bias", round(lost, 2))
        assert abs(lost - floor) < 1.0, (conv, mean, lost)   # the dark sky, not the lost lines (0)
print("ok")
