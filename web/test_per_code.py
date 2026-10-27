"""Synthetic check that the lean archive's per code steps (calibration._lookup) give exactly what the per pixel
arithmetic gives: calibrate, display_stretch, unstretch and saturated on 8-bit codes, against the same frames as
float images or 16-bit codes (which take the per pixel path), to the bit, over the label variants calibrate handles.
Run: python web/test_per_code.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
import numpy as np
import calibration as cal  # noqa: E402

cal.ds._lut8 = True                                     # the lean archive: stored codes, nothing guessed
rng = np.random.default_rng(7)
label = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": "(CL1,GRN)", "GAIN_MODE_ID": "12ELECTRONS_PER_DN",
         "INSTRUMENT_MODE_ID": "FULL", "EXPOSURE_DURATION": "460.0", "IMAGE_TIME": "2005-170T12:00:00.000",
         "TARGET_NAME": "SATURN", "BIAS_STRIP_MEAN": "31.9", "SHUTTER_STATE_ID": "ENABLED",
         "IMAGE_NUMBER": "1500045826", "DATA_CONVERSION_TYPE": "12BIT"}
variants = [{}, {"DATA_CONVERSION_TYPE": "TABLE"}, {"INSTRUMENT_MODE_ID": "SUM2"}, {"SHUTTER_STATE_ID": "DISABLED"},
            {"BIAS_STRIP_MEAN": "-235.0"}, {"GAIN_MODE_ID": "215ELECTRONS_PER_DN"}, {"EXPOSURE_DURATION": "5.0"},
            {"INSTRUMENT_ID": "ISSWA", "FILTER_NAME": "(CL1,CL2)"}, {"DATA_CONVERSION_TYPE": "8LSB"}]
frames = [rng.integers(0, 256, (64, 96), dtype=np.uint8),       # every code
          rng.integers(20, 90, (48, 48), dtype=np.uint8),       # a narrow range
          np.full((16, 16), 9, np.uint8),                       # one value
          np.where(rng.random((32, 32)) < 0.1, 255, 40).astype(np.uint8)]   # saturated pixels

def same(a, b):
    return (a is None and b is None) or (a is not None and b is not None and a.dtype == b.dtype
                                         and a.shape == b.shape and a.tobytes() == b.tobytes())

checks = 0
for change in variants:
    info = dict(label, **change)
    for codes in frames:
        stretched = cal.display_stretch(cv2.cvtColor(codes, cv2.COLOR_GRAY2BGR), info)
        gray = cv2.cvtColor(stretched, cv2.COLOR_BGR2GRAY) if stretched.ndim == 3 else stretched
        wide = codes.astype(np.uint16)                  # the same codes, not 8-bit: the per pixel path
        expect = cal.display_stretch(wide, info)
        # 8LSB frames are returned as they are; a one-valued frame's zeros keep the input's type
        expect = codes if expect is wide else expect.astype(np.uint8)
        assert same(cal.display_stretch(codes, info), expect), change
        assert same(cal.calibrate(codes, info), cal.calibrate(wide, info)), change
        for image in (gray, cv2.resize(gray, (40, 24), interpolation=cv2.INTER_AREA), gray[:, ::-1]):
            assert same(cal.calibrate(codes, info, image), cal.calibrate(codes, info, image.astype(np.float32))), change
            assert same(cal.unstretch(codes, info, image), cal.unstretch(wide, info, image)), change
            assert same(cal.saturated(codes, info, image), cal.saturated(wide, info, image)), change
            checks += 3
        checks += 2
print(checks, "checks ok")
