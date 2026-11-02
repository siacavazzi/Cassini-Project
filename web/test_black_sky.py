"""Synthetic checks of a color set's black sky (fix plan D, neutral black sky): a body over most of the frame with a
little sky beside it (SKY_SHARE) still has each channel's level set on that sky, so the channels' different offsets
don't tint it (Saturn in a 2013 WAC set, brown); a sky lit all over round a small moon, which the sky test can't
find, is measured off the body's disk (load_linear's off_disk, color_image.dim_off_disk) and goes black in every
channel (Phoebe 2004, violet), while light off the disk as bright as the body's own (Saturn behind Mimas, a plume)
is not taken for sky; and through the toe a pixel's color fades to gray with its brightness (tone), while a pixel
above the toe keeps its color exactly. Run: python web/test_black_sky.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image as ci  # noqa: E402

rng = np.random.default_rng(9)
H = 512
yy, xx = np.mgrid[:H, :H].astype(np.float32)


class Label:
    def __init__(self, band):
        self.info = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": f"(CL1,{band})", "TARGET_NAME": "PHOEBE"}

    def get_info(self):
        return self.info

    def export(self):
        return "nac_data/N1.png"


BANDS = ("RED", "GRN", "BL1")


def draw(iofs, off_disk=None):
    """the set drawn (H x W x 3, RGB) without its channel mix, so only the black and the toe decide the sky's color"""
    channels, margin, _ = cal.load_linear([Label(b) for b in BANDS], [None] * 3, [i.astype(np.float32) for i in iofs],
                                          off_disk=off_disk)
    return np.stack([t[..., 0] for t in cal.tone(channels, margin)], axis=-1).astype(int)


def tint(rgb, where):
    v = rgb[where].astype(float)
    return float(np.mean(v.max(axis=1) - v.min(axis=1))), v.mean(axis=0).round(1)


# 1. a body over 95% of the frame, a strip of sky with an offset per channel (stray light, a bias left over): the sky
# share is under the old tenth but over SKY_SHARE
offsets = (0.012, 0.006, 0.007)
body = (xx > 0.05 * H)
iofs = [np.where(body, 0.5 + 0.02 * np.sin(yy / 30), 0.0) + o + rng.normal(0, 0.0004, (H, H)) for o in offsets]
sky = ~body
sky[:, int(0.05 * H) - 12:] = False   # (off the body's edge)
keep = cal.SKY_SHARE
cal.SKY_SHARE = 0.1
before = draw(iofs)
cal.SKY_SHARE = keep
after = draw(iofs)
print("strip of sky beside a body: before", tint(before, sky), "after", tint(after, sky))
assert tint(before, sky)[1].max() > 15                      # the old rule left the offsets as a brown veil
assert tint(after, sky)[1].max() < 3 and tint(after, sky)[0] < 2   # black, every channel
assert abs(int(np.median(after[body][:, 0])) - int(np.median(before[body][:, 0]))) < 40   # the body still drawn

# 2. a small moon (a disk 10 px across) in a sky lit all over, a different offset per channel: the brightest
# 0.1% is about the sky, so the sky test finds no sky
disk = (xx - 300) ** 2 + (yy - 200) ** 2 < 5 ** 2
lit = [0.003, 0.0025, 0.0028]
offsets = (0.00008, 0.00003, 0.00009)
iofs = [np.where(disk, l, 0.0) + o + rng.normal(0, 0.00002, (H, H)) for l, o in zip(lit, offsets)]
assert cal._sky([i.astype(np.float32) for i in iofs]).mean() < 0.02
off = (xx - 300) ** 2 + (yy - 200) ** 2 >= (5 * 1.2 + 16) ** 2
def sky_left(off_disk=None):
    """each channel's median over the sky once its level is off (linear, white = 1)"""
    channels, _, _ = cal.load_linear([Label(b) for b in BANDS], [None] * 3, [i.astype(np.float32) for i in iofs],
                                     off_disk=off_disk)
    return np.array([float(np.median(c[off])) for c in channels])


real = ci.off_disk
before = sky_left()
try:
    ci.off_disk = lambda lbls, shape: off
    after = sky_left(lambda linear: ci.dim_off_disk([Label(b) for b in BANDS], linear))
    drawn = draw(iofs, off_disk=lambda linear: ci.dim_off_disk([Label(b) for b in BANDS], linear))
finally:
    ci.off_disk = real
print("lit sky round a small moon, each channel over its level: before", before.round(4), "after", after.round(4))
assert before.max() - before.min() > 0.01                    # one channel's offset left over the others' (a tint)
assert np.abs(after).max() < 0.005                           # every channel's sky at its level
assert tint(drawn, off)[1].max() < 3 and drawn[disk].mean() > 100   # black sky, the moon still there

# 3. light off the disk nearly as bright as the disk (Saturn behind Mimas, a plume): not sky
iofs = [np.where(disk, 0.8, 0.0) + np.where(xx < 200, 0.45, 0.0) + rng.normal(0, 0.001, (H, H)) for _ in BANDS]
try:
    ci.off_disk = lambda lbls, shape: off
    got = ci.dim_off_disk([Label(b) for b in BANDS], [i.astype(np.float32) for i in iofs])
finally:
    ci.off_disk = real
assert got is None
print("bright light off the disk is not sky")

# 4. tone: through the toe a pixel is gray, above it its color is as before
margin = 0.02
w = max(margin / 8, min(margin, cal.TOE))
start = margin - w / 2
lums = np.array([start + 0.1 * w, start + 0.5 * w, start + 2 * w, 0.5], np.float32)
color = np.array([1.3, 1.0, 0.7], np.float32)
channels = [(lums * c).reshape(1, -1) for c in color]
out = np.stack([t[..., 0] for t in cal.tone(channels, margin)], axis=-1)[0].astype(int)
print("toe pixels gray, lit pixels colored:", out.tolist())
assert out[0].max() - out[0].min() <= 1
assert out[1].max() - out[1].min() <= max(2, out[1].max() // 4)
lit_ratio = out[3] / out[3].max()
assert abs(lit_ratio[2] - lit_ratio[0] * (0.7 / 1.3) ** (1 / 2.2)) < 0.03   # (gamma encoded, the same color)
print("ok")
