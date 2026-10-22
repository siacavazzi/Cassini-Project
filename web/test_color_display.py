"""Synthetic checks of the balanced display model (color plan steps C1-C5) against the classic one: composite
black and white (calibration.picture_scale), anchored mosaic gains and linear offsets (mosaic.seams), the
filled-pass scale (obs_mosaic.pass_scale) and luminance-only detail. Run: python web/test_color_display.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402  (puts the repo on the path)
import calibration as cal  # noqa: E402
import mosaic  # noqa: E402

rng = np.random.default_rng(3)

# ---- composite: a body with a bright limb patch, on a sky whose offset and noise differ per channel ----
H = 256
yy, xx = np.mgrid[:H, :H]
disk = (yy - 128) ** 2 + (xx - 128) ** 2 < 70 ** 2
body = np.array([0.30, 0.27, 0.19])            # red, green, blue I/F of the body
sky = np.array([0.002, 0.003, 0.001])          # real sky offsets
noise = np.array([0.004, 0.002, 0.0015])       # red is the noisiest
iofs = []
for c in range(3):
    im = sky[c] + rng.normal(0, noise[c], (H, H))
    im[disk] += body[c] * (0.8 + 0.2 * np.cos(np.radians(xx[disk] - 128)))
    im[120:126, 196:202] += 2 * body[c]        # a bright limb patch: 36 pixels, past a 3x3 median
    iofs.append(im.astype(np.float32))
with cal.looking("classic"):
    cb, cw, _ = cal.picture_scale(iofs)
with cal.looking("balanced"):
    bb, bw, _ = cal.picture_scale(iofs)
c_margin = np.array(cb) - sky
b_margin = np.array(bb) - sky
print("classic blacks above sky", c_margin.round(4), "white", round(float(cw), 3))
print("balanced blacks above sky", b_margin.round(4), "white", round(float(bw), 3))
assert c_margin[0] > 2 * c_margin[2]                      # classic takes more off red than blue
assert np.ptp(b_margin) < 0.0005                          # balanced: one margin for every channel
assert cw > 2.5 * body[0] and 0.8 * body[0] < bw < 1.15 * body[0]   # white from the body, not the patch
# the shoulder: the patch rolls off below full white instead of clipping flat, the body is untouched below the knee
x = np.array([0.5, 0.79, 1.0, 3.0])
r = cal.roll_off(x, cal.SHOULDER)
assert r[0] == 0.5 and r[1] == 0.79 and 0.9 < r[2] < 0.97 and r[3] < 1 and np.all(np.diff(r) > 0)
# encode and decode are inverses, for a power and for sRGB
v = np.linspace(0, 1, 101)
for g in (2.2, 3.0, "srgb"):
    assert np.abs(cal.decode(cal.encode(v, g), g) - v).max() < 1e-9

# ---- mosaic seams: a row of overlapping tiles of one smooth scene, each with a small gain error and sky offset ----
W, T, STEP = 1600, 512, 300
scene = 0.05 + 0.4 * np.exp(-((np.mgrid[:T, :W][1] - 800) / 500.0) ** 2)    # linear brightness, white = 1
true_gain = np.exp(rng.normal(0, 0.03, 4))
true_off = rng.normal(0, 0.003, 4)
gamma = 3.0
frames = []
for i in range(4):
    lin = np.zeros((T, W)); alpha = np.zeros((T, W), np.uint8)
    sl = slice(i * STEP, i * STEP + T)
    lin[:, sl] = np.clip(scene[:, sl] * true_gain[i] + true_off[i], 0, 1)
    alpha[:, sl] = 255
    lev = (cal.encode(lin, gamma) * 255 + 0.5).astype(np.uint8)
    frames.append(np.dstack([lev, lev, lev, alpha]))
classic = mosaic.match_gains(frames, mosaic.calibrated_gain, None, mosaic.calibrated_overlap)[:, 0]
gains, offsets = mosaic.seams(frames, None, gamma)
gains, offsets = gains[:, 0], offsets[:, 0]
corrected = true_gain * gains
print("classic gains (pin none)", classic.round(3))
print("anchored gains", gains.round(3), "mean log", round(float(np.log(gains).mean()), 4))
print("true gain x solved gain", corrected.round(3), "offsets", offsets.round(4))
assert abs(np.log(gains).mean()) < 0.01                   # the mosaic keeps its level
assert np.ptp(corrected) < 0.03                          # the tiles agree after the correction
assert not np.any(np.isclose(gains, 1 / mosaic.calibrated_gain))   # none at the clip
assert np.all(np.abs(offsets) <= mosaic.max_linear_offset)
# applied on linear values: the identity changes nothing, a gain of 1.05 is 1.05 in linear brightness
f = frames[1][..., :3].astype(np.float32)
assert np.array_equal(mosaic._corrected(f, np.ones(3), np.zeros(3), gamma), f)
up = mosaic._corrected(f, np.full(3, 1.05), np.zeros(3), gamma)
lin_in, lin_out = cal.decode(f / 255, gamma), cal.decode(up / 255, gamma)
lit = (f > 120) & (f < 200)
assert np.abs(lin_out[lit] / lin_in[lit] - 1.05).max() < 0.02
out = mosaic.compose([(fr, None, None, None) for fr in frames], False, calibrated=True, pin=None, gamma=gamma)
# another filter pulled toward these seams keeps their overall level and still evens out its own tiles
shared = (np.full((4, 3), 1.02), np.zeros((4, 3)))
g2, _ = mosaic.seams(frames, None, gamma, shared)
assert abs(np.log(g2[:, 0]).mean() - np.log(1.02)) < 0.01 and np.ptp(true_gain * g2[:, 0]) < 0.03
assert out.shape == (T, W, 4) and out[..., 3].max() == 255

# ---- a filled pass (a bright moon filling every frame): one black and white for every filter, black below white ----
by = {"RED": [0.95 + 0.25 * rng.random((64, 64))], "GRN": [0.90 + 0.25 * rng.random((64, 64))],
      "BL1": [0.60 + 0.25 * rng.random((64, 64))]}
obs_mosaic.stacking.load_hdr = lambda path, gap=None: (None, by[path][0], 1)
u = {"key": ("RHEA", "TEST", "N", 0), "z": 1e5}
fr = [(f, f"N{i}", f, i, 600, 0.0, 0.0, 1e5) for i, f in enumerate(by)]
with cal.looking("classic"):
    old = obs_mosaic.pass_scale(fr, u)
with cal.looking("balanced"):
    new = obs_mosaic.pass_scale(fr, u, ["RED", "GRN", "BL1"], True)
    false = obs_mosaic.pass_scale(fr, u, ["RED", "GRN", "BL1"], False)
print("classic filled", {f: round(b / old["white"], 2) for f, b in old["blacks"].items()}, old["gamma"])
print("balanced filled", {f: round(b / new["white"], 2) for f, b in new["blacks"].items()}, new["gamma"])
assert old["filled"] and new["filled"] and new["gamma"] == "srgb"
assert len(set(new["blacks"].values())) == 1 and all(b <= new["white"] for b in new["blacks"].values())
assert max(b / old["white"] for b in old["blacks"].values()) > 1      # the classic black sat above the white
# false colour: every filter's black its own 1st percentile, one white (the widest band's)
assert len(set(false["blacks"].values())) == 3 and np.isclose(false["white"], max(np.percentile(v[0], 99.5) - np.percentile(v[0], 1) for v in by.values()), rtol=1e-3)

# ---- detail on luminance only: a colored patch keeps its color differences, no channel gets its own texture ----
rgba = np.zeros((64, 64, 4), np.uint8); rgba[..., 3] = 255
rgba[..., 0] = 120; rgba[..., 1] = 100; rgba[..., 2] = 80
rgba[20:40, 20:40, 0] = 160                                   # red only (as a misregistered red channel)
with cal.looking("balanced"):
    d = obs_mosaic.detail(rgba, 4).astype(int)
diff = d[..., :3] - rgba[..., :3].astype(int)
assert np.abs(diff[..., 0] - diff[..., 1]).max() <= 1 and np.abs(diff[..., 1] - diff[..., 2]).max() <= 1
print("ok")
