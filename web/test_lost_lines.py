"""Lines lost in downlink (truncated lines, zeros in the file; label.valid_mask): repeat exposures fill each other's lost
pixels in the stack (image_correction.stack_frames, stacking.load_hdr), short runs of lost lines are filled from the
rows above and below (image_correction.fill_lines), taller blocks stay lost, and frames that lost nothing come out
byte for byte as before. Synthetic frames. Run: python web/test_lost_lines.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import cv2
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import image_correction as ic  # noqa: E402
import stacking  # noqa: E402

H = 256
rng = np.random.default_rng(7)
yy, xx = np.mgrid[:H, :H]
disk = (yy - 128) ** 2 + (xx - 128) ** 2 < 90 ** 2
scene = np.where(disk, 120 + 40 * np.sin(xx / 9.0) * np.cos(yy / 13.0), 3).astype(np.float32)


def shot(seed):
    noise = np.random.default_rng(seed).normal(0, 3, (H, H))
    gray = np.clip(scene + noise + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def wedge():
    """Rhea's pattern: lines whose ends never arrived, every one cut at its own place, zeros to the right edge."""
    m = np.ones((H, H), bool)
    for y in range(60, 200):
        m[y, int(rng.integers(150, 250)):] = False
    return m


def lose(frame, mask):
    out = frame.copy()
    out[~mask] = 0
    return out


frames = [shot(s) for s in range(3)]
clean = [np.ones((H, H), bool)] * 3

# ---------- nothing lost: byte for byte the plain stack ----------
plain = ic.stack_frames(frames)
same, valid = ic.stack_frames(frames, masks=clean)
assert np.array_equal(plain, same) and valid.all()
one, valid = ic.stack_frames(frames[:1], masks=clean[:1])
assert one is frames[0] and valid.all()
print("clean frames: byte-identical ok")

# ---------- the reference lost a wedge, a repeat has it: the stack fills it ----------
m = wedge()
stacked, valid = ic.stack_frames([lose(frames[0], m), frames[1]], masks=[m, clean[1]])
gap = ~m & disk
# (the repeat's sub-pixel shift uncovers the frame's last column, as alignment does for any frame)
assert valid[gap].all() and valid[:, :-1].all(), (~valid).sum()
assert np.abs(stacked[gap, 0].astype(int) - scene[gap]).mean() < 6, np.abs(stacked[gap, 0].astype(int) - scene[gap]).mean()
# without the masks (as before): the pair rule keeps the darker value, the zeros
old = ic.stack_frames([lose(frames[0], m), frames[1]])
assert (old[gap, 0] == 0).mean() > 0.9
print("reference's gap filled from a repeat ok")

# ---------- a repeat lost a wedge, the reference didn't: no streak ----------
stacked, valid = ic.stack_frames([frames[0], lose(frames[1], m), frames[2]], masks=[clean[0], m, clean[2]])
assert valid.all()   # the reference has every pixel
# as the stack of the frames that do have those pixels (the limb's half-pixel blur is alignment's, not a streak)
d = np.abs(stacked[gap, 0].astype(int) - ic.stack_frames([frames[0], frames[2]])[gap, 0])
assert d.max() <= 12 and d.mean() < 2, (d.max(), d.mean())
print("repeat's gap left out ok")

# ---------- every frame lost the same pixels: they stay lost ----------
stacked, valid = ic.stack_frames([lose(f, m) for f in frames[:2]], masks=[m, m])
assert np.array_equal(valid[:, :-1], m[:, :-1])
print("lost everywhere stays lost ok")

# ---------- fill_lines: short runs from the rows above and below, tall blocks and edges left ----------
img = np.tile(np.arange(H, dtype=np.uint8)[:, None], (1, H))   # each row its own value
m = np.ones((H, H), bool)
m[100:104, 50:] = False   # four lines lost from x = 50
m[150:170, 80:] = False   # a block twenty lines tall
m[:3, 10:20] = False      # at the top edge: nothing above
filled, mask = ic.fill_lines(img, m)
assert mask[100:104, 50:].all() and np.array_equal(filled[100:104, 60], np.arange(100, 104))
assert not mask[150:170, 80:].any() and not mask[:3, 10:20].any()
assert np.array_equal(filled[m], img[m])
f3, m3 = ic.fill_lines(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), m)
assert np.array_equal(f3[..., 0], filled) and np.array_equal(m3, mask)
ff, mf = ic.fill_lines(img.astype(np.float32) / 255, m)
assert np.array_equal(mf, mask) and np.allclose(ff[101, 60], 101 / 255)
same, sm = ic.fill_lines(img, np.ones((H, H), bool))
assert same is img
print("fill_lines ok")

# ---------- load_hdr: a repeat fills the reference's lost pixels in I/F ----------
m = wedge()
gap = ~m & disk


class Label:
    def __init__(self, path, mask):
        self.mask = mask
        self.info = {"path": path, "EXPOSURE_DURATION": 100.0, "GAIN_MODE_ID": "12", "INSTRUMENT_MODE_ID": "FULL"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return self.mask

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return pngs[self.info["path"]]


pngs = {"a.png": lose(frames[0], m), "b.png": frames[1]}
labels = {"a.png": Label("a.png", m), "b.png": Label("b.png", clean[1])}
stacking.find_repeats = lambda path, window=120, max_frames=5: ["a.png", "b.png"][:max_frames]
stacking.lh.label = lambda p, as_png=True: labels[p]
stacking.ic.find_shift = lambda a, b, r: None
stacking.ds.imread = lambda path, flags=None: pngs[path][..., 0]
cal.calibrate = lambda codes, info, image=None: codes.astype(np.float32) / 1000
cal.saturated = lambda codes, info, image=None: np.zeros(codes.shape, bool)
_, iof, n, valid = stacking.load_hdr("a.png", valid=True)
assert n == 2 and valid.all()
assert iof[gap].min() > 0.05, iof[gap].min()
_, plain_iof, _ = stacking.load_hdr("a.png")   # without valid: as before, the zeros averaged in
assert plain_iof[gap].mean() < iof[gap].mean() * 0.7
labels["a.png"].mask = clean[0]
pngs["a.png"] = frames[0]
_, a, _ = stacking.load_hdr("a.png")
_, b, _, valid = stacking.load_hdr("a.png", valid=True)
assert np.array_equal(a, b) and valid.all()
print("load_hdr ok")
print("ok")
