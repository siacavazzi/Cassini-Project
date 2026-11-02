"""Synthetic checks of how bright subjects and saturated color sets are drawn (fix plan PR 6, highlight shoulder and
shadow toe): a bright subject's highlights are drawn on an eased gamma (calibration.eased_gamma, encode_eased) while its
shadows keep gamma 2.2's toe, a dim picture is drawn as before; a mosaic's or movie's pass eases from gamma 3.0 no lower
than the single pictures' 2.2 (obs_mosaic.pass_scale); a color set's channel that saturated where the others did not
is filled from them (calibration.fill_saturated), so it keeps the surface and comes out the set's typical color, not
yellow or cyan, and white only where every channel saturated. Run: python web/test_tone_shoulder.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402  (puts the repo on the path)
import calibration as cal  # noqa: E402

rng = np.random.default_rng(6)
H = 256
yy, xx = np.mgrid[:H, :H].astype(np.float32)

# ---- the curve: gamma's own in the shadows, the eased gamma's in the highlights, monotonic, no step ----
x = np.linspace(0, 1, 200001, dtype=np.float32)
for eased in (1.6, 1.9, 2.2):
    v = cal.encode_eased(x, 2.2, eased)
    assert np.all(np.diff(v) > 0), eased
    below = x <= cal.EASE_TOE[0]
    assert np.array_equal(v[below], cal.encode(x[below], 2.2)), eased          # shadows exactly as before
    above = x >= cal.EASE_TOE[1]
    assert np.allclose(v[above], cal.encode(x[above], eased), atol=1e-6), eased
assert np.array_equal(cal.encode_eased(x, 2.2, 2.2), cal.encode(x, 2.2))
assert cal.eased_gamma(2.2, 0.3) == 2.2 and cal.eased_gamma(2.2, 0.95) == cal.EASE_GAMMA
assert cal.EASE_GAMMA < cal.eased_gamma(2.2, 0.7) < 2.2
assert cal.eased_gamma("srgb", 0.95) == "srgb" and cal.eased_gamma(1.5, 0.95) == 1.5
assert cal.eased_gamma(3.0, 0.95, cal.EASE_PASS) == cal.EASE_PASS and cal.eased_gamma(3.0, 0.2, cal.EASE_PASS) == 3.0
print("curve ok")

# ---- a bright icy close-up (lit median near white) on sky: fewer pixels in the top tenth, its shadows as before ----
disk = np.hypot(xx - 128, yy - 128) < 100
body = np.where(disk, 0.82 + 0.12 * np.sin(xx / 9) * np.cos(yy / 13), 0.0).astype(np.float32)
crack = disk & (np.abs(xx - yy) < 2)
body[crack] = 0.12                                             # a crack, well in the shadows
body += rng.normal(0, 0.002, body.shape).astype(np.float32)
before = cal.encode(np.clip(cal.roll_off(np.maximum(body, 0), cal.SHOULDER), 0, 1), 2.2) * 255
after = cal.tone([body], 0.0)[0][..., 0].astype(np.float32)
top_before, top_after = np.mean(before[disk] > 230), np.mean(after[disk] > 230)
print("bright disk: share above 230 of 255 %.2f -> %.2f; disk spans %d-%d -> %d-%d; crack %d -> %d" % (
    top_before, top_after, np.percentile(before[disk], 5), np.percentile(before[disk], 95),
    np.percentile(after[disk], 5), np.percentile(after[disk], 95), np.median(before[crack]), np.median(after[crack])))
assert top_after < 0.6 * top_before
assert np.percentile(after[disk], 95) - np.percentile(after[disk], 5) > \
    1.2 * (np.percentile(before[disk], 95) - np.percentile(before[disk], 5))
assert abs(np.median(after[crack]) - np.median(before[crack])) <= 1                # the shadows keep their toe

# ---- a picture whose lit part is mostly well under white (a body lit from the side, its brightness falling off to the
# terminator; a faint ring) is drawn exactly as before ----
ramp = np.where(disk, np.clip((xx - 28) / 200, 0, 1) ** 2, 0.0).astype(np.float32)
ramp += rng.normal(0, 0.002, body.shape).astype(np.float32)
dim_before = (cal.encode(np.clip(cal.roll_off(np.maximum(ramp, 0), cal.SHOULDER), 0, 1), 2.2) * 255 + 0.5).astype(np.uint8)
assert cal.lit_median(ramp) < cal.EASE_LIT[0]
assert np.array_equal(cal.tone([ramp], 0.0)[0][..., 0], dim_before)
print("side-lit body: lit median %.2f, drawn as before" % cal.lit_median(ramp))

# ---- a color set whose RED saturated over the bright side (Hyperion): filled from GRN and BL1, the surface kept ----
ratio = (1.15, 1.0, 0.85)                                       # the body's typical color, red to blue
surface = (0.55 + 0.35 * (xx / H) + 0.08 * np.sin(xx / 5) * np.sin(yy / 7)).astype(np.float32)
chans = [np.where(disk, r * surface, 0.0).astype(np.float32) for r in ratio]
clip = np.float32(0.8)
sat = [disk & (chans[0] > clip), np.zeros(disk.shape, bool), np.zeros(disk.shape, bool)]
measured = [np.where(sat[0], clip, chans[0])] + chans[1:]     # the camera's RED stops at its top
filled, every = cal.fill_saturated(measured, sat)
assert every is None and sat[0].sum() > 1000
err = np.abs(filled[0][sat[0]] - chans[0][sat[0]]) / chans[0][sat[0]]
print("RED saturated on %.0f%% of the disk: filled within %.1f%% of the true value (clipped: %.0f%% low)" % (
    100 * sat[0].sum() / disk.sum(), 100 * err.max(), 100 * np.max(1 - clip / chans[0][sat[0]])))
assert err.max() < 0.02
drawn = np.stack([c[..., 0] for c in cal.tone(measured, 0.0, saturated=sat)]).astype(int)
raw = np.stack([c[..., 0] for c in cal.tone(measured, 0.0)]).astype(int)
hue = lambda d: np.median(d[0][sat[0]] - d[2][sat[0]])             # red minus blue where RED saturated
true = np.stack([c[..., 0] for c in cal.tone(chans, 0.0)]).astype(int)
print("red minus blue on the saturated part: true %d, clipped %d, filled %d" % (hue(true), hue(raw), hue(drawn)))
assert abs(hue(drawn) - hue(true)) < 0.3 * abs(hue(raw) - hue(true))   # clipped red turns it toward cyan; filled keeps the body's tone
assert np.std(drawn[1][sat[0]]) > 5                            # and the surface the others saw

# ---- where every channel saturated: neutral white ----
both = disk & (xx > 200)
sat_all = [both] * 3
white = np.stack([c[..., 0] for c in cal.tone([np.where(both, clip, c) for c in chans], 0.0, saturated=sat_all)])
assert np.all(white[:, both] == 255)
print("every channel saturated: white")

# ---- a pass: a bright moon map eases from gamma 3.0 to no lower than 2.2, a dim one keeps 3.0 ----
def pass_gamma(frames):
    obs_mosaic.stacking.load_hdr = lambda path, gap=None: (None, frames[path], 1)
    fr = [(p, p, "CL1/CL2", n, 600, 0.0, 0.0, 0) for n, p in enumerate(frames)]
    with cal.looking("balanced"):
        return obs_mosaic.pass_scale(fr, {"key": ("TETHYS", "TEST", "N", 0)}, ["CL1/CL2"], False)["gamma"]
bright = {f"b{n}": np.where(np.hypot(xx - 128 + 20 * n, yy - 128) < 110, 0.6 + 0.05 * np.sin(xx / 7), 1e-4).astype(np.float32)
          + rng.normal(0, 1e-4, (H, H)).astype(np.float32) for n in range(3)}
dim = {f"d{n}": np.where(np.hypot(xx - 128, yy - 128 + 20 * n) < 110, 0.02 + 0.6 * (xx > 230), 1e-4).astype(np.float32)
       + rng.normal(0, 1e-4, (H, H)).astype(np.float32) for n in range(3)}
gb, gd = pass_gamma(bright), pass_gamma(dim)
print("pass gamma: bright moon %.2f, dim %.2f" % (gb, gd))
assert cal.EASE_PASS <= gb < 2.6 and gd == 3.0
print("ok")
