"""Synthetic checks of the full-depth calibration input (calibration.depth_image, full_values, data_source.original_dn):
a frame calibrated from depth_image gives what its stored codes give (the per code path, image=None) to float
precision, where its display copy (resize_image, 255 levels) merged the dark codes; a summed frame's depth image is its
values resized without rounding; a stack of repeats at full depth (stacking.load_stacked's deep, image_correction.
stack_frames) keeps the same pixels as the display copies' stack; and an original 12-bit IMG in CASSINI_ORIGINALS
(a zip of xz-compressed IMG files, as the re-download stores them) is read in place of the codes, also for 8LSB frames.
Run: python web/test_full_depth.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lzma
import tempfile
import zipfile
import numpy as np
import calibration as cal  # noqa: E402
import data_source as ds  # noqa: E402
import image_correction as ic  # noqa: E402

cal.ds._lut8 = True
label = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": "(CL1,CL2)", "GAIN_MODE_ID": "12ELECTRONS_PER_DN",
         "INSTRUMENT_MODE_ID": "FULL", "EXPOSURE_DURATION": "2000.0", "IMAGE_TIME": "2017-100T12:00:00.000",
         "TARGET_NAME": "ENCELADUS", "BIAS_STRIP_MEAN": "12.0", "SHUTTER_STATE_ID": "ENABLED", "LINES": "1024",
         "LINE_SAMPLES": "1024", "IMAGE_NUMBER": "1876460140", "DATA_CONVERSION_TYPE": "12BIT", "path": "nac_data/N1876460140_1.png"}
rng = np.random.default_rng(3)
# a faint glow a few codes over a dark sky, and one bright patch that sets the display copy's range
codes = (6 + 4 * np.exp(-((np.arange(64)[:, None] - 32) ** 2 + (np.arange(64)[None] - 32) ** 2) / 300)
         + rng.integers(0, 2, (64, 64))).astype(np.uint8)
codes[:4, :4] = 250
checks = 0

# 1. depth_image calibrates to what the codes give, the display copy does not
info = dict(label)
deep = cal.depth_image(codes, info)
assert deep.dtype == np.float32 and deep.shape == codes.shape
exact = cal.calibrate(codes, info, None, smooth=False)
full = cal.calibrate(codes, info, deep, smooth=False)
gray = cal.display_stretch(codes, info)
old = cal.calibrate(codes, info, gray, smooth=False)
assert np.allclose(full, exact, rtol=1e-5, atol=1e-9 * float(np.abs(exact).max())), np.abs(full - exact).max()
dark = codes < 20
# (the DN each is calibrated from: the display copy merged the dark codes into fewer levels)
merged, kept = (len(np.unique(np.round(cal.unstretch(codes, info, im)[dark], 6))) for im in (gray, deep))
assert kept == len(np.unique(codes[dark])) > merged, (kept, merged)
assert np.abs(old - exact)[dark].max() > 100 * np.abs(full - exact)[dark].max()
print(f"12BIT: full depth = codes; dark levels {merged} (display copy) -> {kept}")
checks += 2

# 2. TABLE frames: the same as the codes too
info_t = dict(label, DATA_CONVERSION_TYPE="TABLE")
assert np.allclose(cal.calibrate(codes, info_t, cal.depth_image(codes, info_t), smooth=False),
                   cal.calibrate(codes, info_t, None, smooth=False), rtol=1e-5)
checks += 1

# 3. a summed frame: resized to 1024 as a float, not rounded
info_s = dict(label, LINES="512", LINE_SAMPLES="512", INSTRUMENT_MODE_ID="SUM2")
big = np.kron(codes, np.ones((8, 8), np.uint8))
deep_s = cal.depth_image(big, info_s)
assert deep_s.shape == (1024, 1024) and deep_s.dtype == np.float32
assert len(np.unique(deep_s)) >= len(np.unique(cal.stored_values(big, info_s)))
checks += 1

# 4. stacking at full depth: two identical repeats give the frame itself, a cosmic ray in one is left out of both stacks
frame = np.dstack([gray] * 3)
hit = frame.copy(); hit[40, 40] = 254
deep_hit = deep.copy(); deep_hit[40, 40] = 254.0
ic.find_shift = lambda a, b, m, *x: (0.0, 0.0)
out, deep_out = ic.stack_frames([frame, frame, hit], deep=[deep, deep, deep_hit])
assert np.allclose(deep_out, deep, atol=1e-4), np.abs(deep_out - deep).max()
assert out[40, 40, 0] == frame[40, 40, 0]
out_m, mask_m, deep_m = ic.stack_frames([frame, hit], masks=[np.ones(codes.shape, bool)] * 2, deep=[deep, deep_hit])
assert deep_m[40, 40] <= deep[40, 40] + 1e-4   # (two frames: the darker one)
assert ic.stack_frames([frame]) is frame and ic.stack_frames([frame], deep=[deep])[1] is deep
checks += 3


# 5. originals: a 12-bit IMG (VICAR label, 24-byte line prefixes, big-endian halfwords), xz-compressed in a zip
def img_bytes(dn, half=True):
    lines, samples = dn.shape
    prefix, size = 24, 2 if half else 1
    record = prefix + samples * size
    head = f"LBLSIZE={record * 4} FORMAT='{'HALF' if half else 'BYTE'}' RECSIZE={record} NL={lines} NS={samples} NBB={prefix} NLB=0 "
    head = head.encode().ljust(record * 4, b" ")
    body = np.zeros((lines, record), np.uint8)
    body[:, prefix:] = np.frombuffer(dn.astype(">i2" if half else "u1").tobytes(), np.uint8).reshape(lines, -1)
    return head + body.tobytes()


true = np.clip(cal.LUT[codes] + rng.normal(0, 1.0, codes.shape), 0, 4095).round().astype(np.int32)
eight = rng.integers(10, 30, codes.shape).astype(np.int32)
with tempfile.TemporaryDirectory() as folder:
    with zipfile.ZipFile(os.path.join(folder, "COISS_2111.zip"), "w") as z:
        z.writestr("COISS_2111/data/1876/N1876460140_1.IMG.xz", lzma.compress(img_bytes(true)))
        z.writestr("COISS_2111/data/1876/N1876460141_1.IMG.xz", lzma.compress(img_bytes(eight, half=False)))
    ds.ORIGINALS, ds._originals = folder, None
    got = ds.original_dn("nac_data/N1876460140_1.png", codes.shape)
    assert got is not None and np.array_equal(got, true)
    assert ds.original_dn("nac_data/N1876460140_1.png", (32, 32)) is None   # another shape: not the frame's
    assert ds.original_dn("nac_data/N1000000000_1.png") is None
    assert np.array_equal(cal.full_values(codes, info), true)
    from_original = cal.calibrate(codes, info, cal.depth_image(codes, info), smooth=False)
    direct = cal.calibrate(codes, info, None, smooth=False)
    assert np.allclose(from_original, direct, rtol=1e-5, atol=1e-9 * float(np.abs(direct).max()))
    assert not np.allclose(from_original, exact, rtol=1e-3)   # the true DN, not the squeezed codes
    # a TABLE frame keeps its codes whatever is in the folder
    assert np.array_equal(cal.full_values(codes, info_t), codes.astype(np.float64))
    # an 8LSB frame: nothing without its original, calibrated from it with one
    info_8 = dict(label, DATA_CONVERSION_TYPE="8LSB", path="nac_data/N1876460141_1.png")
    stretched = cal.display_stretch(eight.astype(np.uint8), dict(info_8, DATA_CONVERSION_TYPE="TABLE"))
    assert cal.calibrate(stretched, dict(info_8, path="nac_data/N1999999999_1.png"), None) is None
    iof8 = cal.calibrate(stretched, info_8, cal.depth_image(stretched, info_8), smooth=False)
    assert iof8 is not None and np.isfinite(iof8).all()
    # ... but not one whose DN wrapped past 255 (only their low 8 bits were sent)
    wrapped = eight.copy(); wrapped[20:40, 20:40] = 3; wrapped[20:40, 40:44] = 250
    with zipfile.ZipFile(os.path.join(folder, "COISS_2112.zip"), "w") as z:
        z.writestr("COISS_2112/data/N1876460142_1.IMG.xz", lzma.compress(img_bytes(wrapped, half=False)))
    ds._originals = None
    assert cal.calibrate(stretched, dict(info_8, path="nac_data/N1876460142_1.png"), None) is None
    ds.ORIGINALS, ds._originals = None, None
    checks += 8
print(f"{checks} checks ok")
