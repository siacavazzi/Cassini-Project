"""Finding 21: on a summed frame one camera pixel is a 2x2 or 4x4 block of the 1024 px picture, so guards built on a 3x3
median there (the white's brightest-pixel guard, _clean_spikes, image_correction.spikes/unspike) kept a hot pixel or a
cosmic ray whole. They now work at the camera's own pixel size (summing_of); a picture of lit sky keeps the white guard
as it was. Run: python web/test_summed_white.py"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import calibration as cal  # noqa: E402
import image_correction as ic  # noqa: E402

assert cal.summing_of({"LINES": "256"}) == 4 and cal.summing_of({"LINES": "512"}) == 2 and cal.summing_of({"LINES": "1024"}) == 1
rng = np.random.default_rng(5)
# a sunlit summed frame (rings at I/F ~0.1) with one hot camera pixel, a 4x4 block 20 times brighter
ring = (0.1 + 0.01 * rng.standard_normal((1024, 1024))).astype(np.float32)
hot = ring.copy(); hot[500:504, 500:504] = 2.0
assert cal._despeckled(hot, 4).max() < 0.2 and cal._despeckled(hot, 1).max() > 1.9
_, _, white4, _ = cal._balanced_scale([hot], summing=[4])
_, _, white1, _ = cal._balanced_scale([hot], summing=[1])
assert white1 > 1.0 and white4 < 0.3, (white1, white4)        # (white1: the hot block set it, as before)
# lit sky (median under GLOW_IOF[0]): the guard as it was
sky = (2e-5 + 2e-6 * rng.standard_normal((1024, 1024))).astype(np.float32); sky[500:504, 500:504] = 4e-4
_, _, w4, _ = cal._balanced_scale([sky], summing=[4])
_, _, w1, _ = cal._balanced_scale([sky], summing=[1])
assert abs(w4 - w1) < 1e-12, (w4, w1)
# the classic look's white and a reel mosaic's tiles_scale, the same
with cal.looking("classic"):
    assert cal.picture_scale([hot], summing=[4])[1] < 0.3 and cal.picture_scale([hot], summing=[1])[1] > 1.0
    assert abs(cal.picture_scale([sky], summing=[4])[1] - cal.picture_scale([sky], summing=[1])[1]) < 1e-12
assert cal.tiles_scale([[hot]], summing=[[4]])["white"] < cal.tiles_scale([[hot]])["white"]
# a 4x4 cosmic ray in a summed movie frame is found and taken out (its neighbours do not have it)
frame = (100 + rng.standard_normal((1024, 1024))).astype(np.float32)
before, after = frame + rng.standard_normal(frame.shape).astype(np.float32), frame + rng.standard_normal(frame.shape).astype(np.float32)
hit = frame.copy(); hit[200:204, 300:304] += 400
ic.find_shift = lambda a, b, *k, **kw: (0.0, 0.0)
found = ic.spikes(hit, [before, after], 4)
assert found[200:204, 300:304].all() and found.sum() < 200
assert abs(float(ic.unspike(hit, found, 4)[201, 301]) - 100) < 10
# (at the picture's size the block's edges are found, but its median there is the block itself: it stayed)
assert float(ic.unspike(hit, ic.spikes(hit, [before, after], 1), 1)[201, 301]) > 400
print("ok")
