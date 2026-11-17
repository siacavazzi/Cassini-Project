"""Checks of the bodies' own colors for natural color emulation (eye_colors.json, web/frames/eye_colors.py): a set's
color is read in linear light on the body's own sunlit disk, its bright disk counts (the drawn pictures' near-white
rule left an icy moon's disk out and measured its warm limb: Enceladus came out orange, taste call 17), a disk far
dimmer than its picture's white (Saturnshine on a night side) and pixels the camera saturated do not; and the table
has the icy moons near gray, Titan and Saturn warm. Run: python web/test_eye_colors.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import obs_mosaic  # noqa: E402,F401  (puts the repo on the path)
import calibration as cal  # noqa: E402
import color_image  # noqa: E402
import eye_colors  # noqa: E402

N = 200
yy, xx = np.mgrid[:N, :N]
DISK = (yy - N / 2) ** 2 + (xx - N / 2) ** 2 < (N / 3) ** 2


def fake_set(channels, saturated=None):
    """color_image.load_aligned, for one call: draws channels (RED, GRN, BL1 I/F, white 1) through calibration.tone
    with the NAC natural matrix, as the color path does, and reports a calibrated, aligned set."""
    def load_aligned(paths, *a, **k):
        cal.tone([c.astype(np.float32) for c in channels], 0.01, cal.natural_mix("N", ["RED", "GRN", "BL1"]),
                 saturated=saturated)
        return None, None, "ref", {"calibrated": True, "aligned": ["reference", "match", "match"]}
    return load_aligned


def measured(channels, saturated=None):
    keep = color_image.load_aligned, eye_colors._disk
    color_image.load_aligned, eye_colors._disk = fake_set(channels, saturated), lambda lbl, shape: DISK
    try:
        got = eye_colors.set_color(["N1", "N2", "N3"])
    finally:
        color_image.load_aligned, eye_colors._disk = keep
    return None if got is None else np.asarray(got[0])


def gray_body(level, limb=None):
    """a gray (equal I/F) disk at level, its outer ring (the limb, a terminator) in limb's color, black sky"""
    ring = DISK & ((yy - N / 2) ** 2 + (xx - N / 2) ** 2 > (N / 3.6) ** 2)
    out = []
    for c in range(3):
        x = np.where(DISK, level, 0.0)
        if limb is not None:
            x[ring] = limb[c]
        out.append(x)
    return out


# an icy moon at white, its limb warm: gray, as its disk is (the drawn pictures' rule measured the limb)
got = measured(gray_body(1.0, limb=[0.5, 0.4, 0.3]))
assert got is not None and np.allclose(got, 1, atol=0.02), got

# a gray moon a twelfth of its picture's white (a night side in Saturnshine, a speck in front of Saturn): left out
dim = gray_body(1 / 12)
for c in dim:
    c[:20, :20] = 1.0   # the picture's white is something else (Saturn in a corner)
assert measured(dim) is None

# pixels the camera saturated (a channel at the top of its range, its color lost) are left out
body = gray_body(0.9)
body[0][DISK & (xx < N / 2)] = 1.3   # half the disk saturated in RED
sat = [DISK & (xx < N / 2), np.zeros_like(DISK), np.zeros_like(DISK)]
got = measured(body, sat)
assert got is not None and np.allclose(got, 1, atol=0.02), got

# a colored body keeps its color: the natural matrix of its I/F, mean 1
orange = [np.where(DISK, v, 0.0) for v in (0.9, 0.6, 0.35)]
want = cal.natural_mix("N", ["RED", "GRN", "BL1"]) @ np.array([0.9, 0.6, 0.35])
got = measured(orange)
assert got is not None and np.allclose(got, want / want.mean(), atol=0.01), (got, want / want.mean())

# the table: icy moons near gray, Titan and Saturn warm (red over blue)
ICY = ("ENCELADUS", "MIMAS", "TETHYS", "DIONE", "RHEA")
ICY_SPREAD = 1.25   # brightest channel over dimmest, at most (Rhea, the warmest, 1.22; the drawn pictures' table had
#                     Enceladus at 1.46 and Mimas at 1.31)
for t in ICY:
    rgb = np.asarray(cal.eye_tint(t))
    assert rgb.max() / rgb.min() < ICY_SPREAD, (t, rgb)
rgb = np.asarray(cal.eye_tint("ENCELADUS"))
assert rgb.max() / rgb.min() < 1.06, rgb   # the whitest body: gray
for t, least in (("TITAN", 1.6), ("SATURN", 1.6)):
    rgb = np.asarray(cal.eye_tint(t))
    assert rgb[0] / rgb[2] > least, (t, rgb)

print("eye colors OK")
