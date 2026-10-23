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
assert np.all(b_margin >= c_margin.max() - 0.0005)       # balanced: never below the noisiest channel's classic margin
assert np.ptp(b_margin) < 0.0005                          # balanced: one margin for every channel
assert cw > 2.5 * body[0] and cw / cal.MAX_STRETCH - 1e-6 <= bw < cw   # white below the patch, never stretched past the cap
# the shoulder: the patch rolls off below full white instead of clipping flat, the body is untouched below the knee
x = np.array([0.5, 0.79, 1.0, 3.0])
r = cal.roll_off(x, cal.SHOULDER)
assert r[0] == 0.5 and r[1] == 0.79 and 0.9 < r[2] < 0.97 and r[3] < 1 and np.all(np.diff(r) > 0)
# tone: the margin comes off the brightness, so a dim patch (a shadowed ring) keeps its color, and the sky stays black
dim = [im.copy() for im in iofs]
for c in range(3):
    dim[c][20:60, 20:60] = sky[c] + 0.04 * body[c] / body.sum() * 3 + rng.normal(0, noise[c] / 4, (40, 40))
with cal.looking("balanced"):
    levels, margin, white, _ = cal._balanced_scale(dim)
    toned = cal.tone([(im - lv) / white for im, lv in zip(dim, levels)], margin / white)
lin = np.array([cal.decode(t[20:60, 20:60, 0].mean() / 255, 2.2) for t in toned])
true = body / body[0]
per_channel = np.array([(im[20:60, 20:60].mean() - lv - margin) for im, lv in zip(dim, levels)])
print("dim patch ratios: tone", (lin / lin[0]).round(3), "per-channel black", (per_channel / per_channel[0]).round(3), "true", true.round(3))
assert np.abs(lin / lin[0] - true).max() < 0.06                          # the color the camera measured
assert np.abs(per_channel / per_channel[0] - true).max() > 0.05          # what a black per channel would draw
sky_px = (yy > 200) & (xx < 60)
assert np.mean([t[sky_px, 0] > 8 for t in toned]) < 0.01                 # the sky's noise stays dark
# a hot pixel in one channel is cleaned, a star (in every channel) stays
spiky = [im.copy() for im in iofs]
spiky[1][230, 30] += 0.2
for c in range(3):
    spiky[c][240, 40] += 0.2
with cal.looking("balanced"):
    levels, margin, white, _ = cal._balanced_scale(spiky)
    clean = cal._clean_spikes([(im - lv) / white for im, lv in zip(spiky, levels)], cal._sky(spiky))
assert clean[1][230, 30] < 0.05 and all(c[240, 40] > 0.2 for c in clean)
assert np.array_equal(clean[0][disk], ((spiky[0] - levels[0]) / white)[disk])
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
assert np.all(np.abs(offsets) <= mosaic.max_offset)
# applied on linear values: the identity changes nothing, a gain of 1.05 is 1.05 in linear brightness
f = frames[1][..., :3].astype(np.float32)
assert np.array_equal(mosaic._corrected(f, np.ones(3), gamma), f)
up = mosaic._corrected(f, np.full(3, 1.05), gamma)
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
    with cal.coloring("raw"):
        false = obs_mosaic.pass_scale(fr, u, ["RED", "GRN", "BL1"], False)
    natural_false = obs_mosaic.pass_scale(fr, u, ["RED", "GRN", "BL1"], False)
print("classic filled", {f: round(b / old["white"], 2) for f, b in old["blacks"].items()}, old["gamma"])
print("balanced filled", {f: round(b / new["white"], 2) for f, b in new["blacks"].items()}, new["gamma"])
assert old["filled"] and new["filled"] and new["gamma"] == 1.5
assert len(set(new["blacks"].values())) == 1 and all(b <= new["white"] for b in new["blacks"].values())
assert max(b / old["white"] for b in old["blacks"].values()) > 1      # the classic black sat above the white
# false colour: every filter's black its own 1st percentile, one white (the widest band's)
assert len(set(false["blacks"].values())) == 3 and np.isclose(false["white"], max(np.percentile(v[0][::4, ::4], 99.5) - np.percentile(v[0][::4, ::4], 1) for v in by.values()), rtol=1e-3)
# natural false colour: a balance toward gray
assert "balance" in natural_false and "balance" not in false

# ---- detail on luminance only: a colored patch keeps its color differences, no channel gets its own texture ----
rgba = np.zeros((64, 64, 4), np.uint8); rgba[..., 3] = 255
rgba[..., 0] = 120; rgba[..., 1] = 100; rgba[..., 2] = 80
rgba[20:40, 20:40, 0] = 160                                   # red only (as a misregistered red channel)
with cal.looking("balanced"):
    d = obs_mosaic.detail(rgba, 4).astype(int)
diff = d[..., :3] - rgba[..., :3].astype(int)
assert np.abs(diff[..., 0] - diff[..., 1]).max() <= 1 and np.abs(diff[..., 1] - diff[..., 2]).max() <= 1
# ---- natural color (phase 2b): the fitted matrix keeps gray gray and warms an orange body's hue as fitted; raw and
# classic draw the filters straight; a false color set is balanced so the body comes out gray ----
with cal.looking("balanced"):
    m = cal.color_mix("N", ["RED", "GRN", "BL1"])
    assert m is not None and np.allclose(m.sum(axis=1), 1, atol=0.01)
    assert cal.color_mix("W", ["RED", "GRN", "VIO"]) is not None and cal.color_mix("N", ["RED", "GRN", "VIO"]) is None
    orange = m @ np.array([1.0, 0.85, 0.6])
    assert orange[0] > 1.0 and orange[2] < 0.6                      # more saturated than the filters' straight mix
    with cal.coloring("raw"):
        assert cal.style() == "raw" and cal.color_mix("N", ["RED", "GRN", "BL1"]) is None
    g = cal.color_mix("N", ["CB2", "MT2", "BL1"], gains=cal.balance([0.054, 0.018, 0.036]))
    lv = np.diag(g) * [0.054, 0.018, 0.036]
    assert np.ptp(lv) < 0.5 * (0.054 - 0.018) and np.isclose(lv.sum(), 0.108)   # toward gray, brightness kept
with cal.looking("classic"):
    assert cal.style() == "classic" and cal.color_mix("N", ["RED", "GRN", "BL1"]) is None
# mixing a drawn picture with the identity changes nothing; tone with a mix keeps a gray pixel gray
rgb = np.repeat(rng.integers(0, 200, (32, 32, 1)), 3, axis=2).astype(np.uint8)
assert np.abs(cal.mix_display(rgb, m, 3.0).astype(int) - rgb).max() <= 2
# a false color mix holds a hot pink line (a ring bright in a dim band) to a pastel, and leaves a near-gray body be
pink = cal.apply_mix(np.eye(3), np.array([1.0, 0.2, 0.9], np.float32).reshape(3, 1, 1)).ravel()
near = cal.apply_mix(np.eye(3), np.array([0.5, 0.48, 0.46], np.float32).reshape(3, 1, 1)).ravel()
assert (pink.max() - pink.min()) / pink.max() < 0.6 and np.allclose(near, [0.5, 0.48, 0.46], atol=0.002)
gray = [np.full((8, 8), 0.4, np.float32)] * 3
t = cal.tone(gray, 0.01, m)
assert abs(int(t[0][0, 0, 0]) - int(t[2][0, 0, 0])) <= 2
print("ok")
