"""Synthetic checks of a single picture's own black (calibration._balanced_scale with _floor and _dark_sky, then
load_linear and tone): an even bright surface with no sky (Titan's haze) spreads over the range instead of sitting at
near-white; a lit sky that fails the sky test goes dark; an even body beside sky (a moon close-up) gets its floor taken
off, a body with a terminator or a ring shadow does not; a night side the sky test counts as sky keeps its glow while
the real sky stays black; one black for every channel keeps the colour; saturated pixels draw white (draw_saturated);
and a reel's shared scale (tiles_scale) still fits every tile's white. Run: python web/test_tone_floor.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402

rng = np.random.default_rng(29)
H = 512
yy, xx = np.mgrid[:H, :H].astype(np.float32)


class Label:
    def __init__(self, info=None):
        self.info = dict(info or {}, INSTRUMENT_ID="ISSNA", FILTER_NAME="(CL1,CL2)", TARGET_NAME="TITAN")

    def get_info(self):
        return self.info

    def export(self):
        return "nac_data/N1.png"


"""
The picture drawn (one uint8 image per channel); floor=False: without the floor black, dark=False: the sky's level and
noise floor over the whole sky mask (both as before)
"""
def draw(iofs, floor=True, dark=True):
    keep = cal.FLOOR_SHARE, cal._dark_sky
    if not floor:
        cal.FLOOR_SHARE = 0.0
    if not dark:
        cal._dark_sky = lambda iofs, sky: sky
    try:
        channels, margin, mix = cal.load_linear([Label() for _ in iofs], [None] * len(iofs), [i.astype(np.float32) for i in iofs])
        return [t[..., 0] for t in cal.tone(channels, margin, mix)]
    finally:
        cal.FLOOR_SHARE, cal._dark_sky = keep


def pct(p, *q):
    return [int(v) for v in np.percentile(p, q)]


smooth = (np.sin(xx / 70) * np.cos(yy / 90) + 1) / 2         # slow structure, 0..1

# ---- an even bright surface, no sky (a Titan haze close-up): I/F 0.17-0.19 ----
haze = 0.17 + 0.02 * smooth + rng.normal(0, 0.0003, (H, H))
before, after = draw([haze], floor=False)[0], draw([haze])[0]
print("haze p1/p10/p50/p99: before", pct(before, 1, 10, 50, 99), "after", pct(after, 1, 10, 50, 99))
assert np.percentile(before, 10) > 230                        # today: near-white
assert np.percentile(after, 50) < 215 and np.percentile(after, 1) > 60   # spread out, nothing crushed to black
assert np.percentile(after, 99) > 225                         # the brightest stays near white

# ---- a lit sky that fails the sky test (a plume's forward-scattered light): a glow over the whole frame ----
glow = 0.0005 + 0.0004 * (yy / H) + rng.normal(0, 0.00002, (H, H))
glow[440:, 200:320] += 0.004 * np.exp(-((xx[440:, 200:320] - 260) / 25) ** 2)   # the plume
before, after = draw([glow], floor=False)[0], draw([glow])[0]
print("lit sky top rows p50: before", int(np.median(before[:40])), "after", int(np.median(after[:40])))
assert np.median(after[:40]) < np.median(before[:40]) - 40   # the sky's darkest part much darker
assert after[:440].max() > after[:40].max()                  # the glow's gradient is kept

# ---- with sky: an even moon close-up (one edge of the frame is sky) gets its floor off ----
moon = np.where(xx + yy > 380, 0.6 + 0.08 * smooth, 0.0) + rng.normal(0, 0.0005, (H, H))
before, after = draw([moon], floor=False)[0], draw([moon])[0]
body = (xx + yy) > 420
print("moon body p10/p50: before", pct(before[body], 10, 50), "after", pct(after[body], 10, 50))
assert np.percentile(before[body], 10) > 225 and np.percentile(after[body], 50) < 225
assert np.percentile(after[(xx + yy) < 340], 99) < 10        # the sky stays black

# ---- with sky: a lit disc with a terminator, and a ring shadow: no floor taken off, the same as before ----
r = np.hypot(xx - 256, yy - 256)
disc = np.where(r < 200, 0.5 * np.clip(np.cos(np.radians((xx - 156) * 0.9)), 0, 1) + 0.002, 0.0)
disc[(np.abs(yy - 300) < 12) & (r < 200)] *= 0.05             # a dark band across it
disc += rng.normal(0, 0.0005, (H, H))
before, after = draw([disc], floor=False)[0], draw([disc])[0]
print("terminator disc: largest change", int(np.abs(before.astype(int) - after).max()))
assert np.abs(before.astype(int) - after).max() <= 1

# ---- a crescent whose dim night side the sky test counts as sky: the glow stays, the real sky stays black ----
crescent = np.where((r < 180) & (xx < 200), 0.3 * np.clip((215 - xx) / 120, 0.02, 1), 0.0)
night = (r < 180) & (xx >= 200)
crescent[night] = 0.006 * np.exp(-(xx[night] - 200) / 60)     # twilight fading into the night side, < 5% of the limb
crescent += 0.0005 + rng.normal(0, 0.0004, (H, H))
before, after = draw([crescent], dark=False)[0], draw([crescent])[0]
twilight = night & (xx < 260)
real_sky = r > 200
print("night side twilight p50: before", int(np.median(before[twilight])), "after", int(np.median(after[twilight])),
      "| real sky p99:", int(np.percentile(after[real_sky], 99)))
assert np.median(before[twilight]) < 15 and np.median(after[twilight]) > 20   # was cut off hard, now shows
assert np.percentile(after[real_sky], 99) < 12                # the real sky's noise stays dark

# ---- color: one black for every channel, taken off the brightness, keeps an even surface's color ----
ratios = np.array([1.0, 0.8, 0.6])
cols = [(haze * k).astype(np.float32) for k in ratios]
channels, margin, _ = cal.load_linear([Label() for _ in cols], [None] * 3, cols)
toned = [t[..., 0] for t in cal.tone(channels, margin)]       # without the channel mix, which changes color on purpose
lin = np.array([cal.decode(np.median(t) / 255, 2.2) for t in toned])
print("even surface channel ratios after:", (lin / lin[0]).round(3), "true", ratios)
assert np.abs(lin / lin[0] - ratios).max() < 0.03

# ---- saturated pixels draw white, also on a frame saturated all over (flat field pattern otherwise) ----
flat = (0.2 * (1 + 0.01 * smooth)).astype(np.float32)
codes = np.full((H, H), 255, np.uint8)
real_imread, real_lut8 = cal.ds.imread, cal.ds.lut8
cal.ds.imread, cal.ds.lut8 = (lambda path, flags=None: codes.copy()), (lambda: False)
try:
    channels, margin, mix = cal.load_linear([Label()], [None], [flat])
    share = cal.draw_saturated([Label()], channels, margin)
    toned = cal.tone(channels, margin, mix)[0][..., 0]
finally:
    cal.ds.imread, cal.ds.lut8 = real_imread, real_lut8
print("saturated frame: share", share, "output p1/p99", pct(toned, 1, 99))
assert share == 1.0 and np.percentile(toned, 1) >= 254

# ---- a reel's shared scale: tiles without sky on their lowest floor black, every tile's white under one white; a reel
# with sky in a tile keeps the sky's black ----
tiles = [[haze], [haze * 1.3]]
scale = cal.tiles_scale(tiles)
for t in tiles:
    blacks, white, _ = cal.picture_scale([t[0].astype(np.float32)])
    assert scale["blacks"][0] <= blacks[0] + 1e-9 and blacks[0] + white <= scale["blacks"][0] + scale["white"] + 1e-6
print("tiles_scale, no sky: blacks", [round(b, 4) for b in scale["blacks"]], "white", round(scale["white"], 4))
scale = cal.tiles_scale(tiles + [[moon]])
assert scale["blacks"][0] < 0.01                              # the moon tile's sky, not its floor
print("tiles_scale, with sky: blacks", [round(b, 4) for b in scale["blacks"]], "white", round(scale["white"], 4))
print("ok")
