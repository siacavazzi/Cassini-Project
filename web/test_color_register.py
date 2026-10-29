"""Colour registration and two-filter colour (group F): a colour set's channels whose own match fails are aligned near
SPICE's offset (image_correction.guided_shift, color_image.load_aligned's guess=), mosaic registration is unchanged
(no guess), two-filter sets are balanced like false colour (calibration.color_mix, two_bands) and a false colour set
with no table for its target is balanced on its own bands as fully as with one. Synthetic frames.
Run: python web/test_color_register.py"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import calibration as cal  # noqa: E402
import image_correction as ic  # noqa: E402

rng = np.random.default_rng(3)
N = 1024
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
CRATERS = [(200, 500, 30), (400, 600, 50), (600, 300, 40), (100, 800, 60), (500, 900, 35), (750, 650, 45)]


def limb(dx, dy, band):
    """A moon filling most of the frame (its lit area runs off two edges, so the centroid refuses it), its craters
    where they are in every filter but bright in one band and dark in the other, so phase correlation is weak"""
    r = np.hypot(xx - 300 - dx, yy - 700 - dy)
    tex = sum(np.exp(-((xx - cx - dx) ** 2 + (yy - cy - dy) ** 2) / (2 * s ** 2)) for cx, cy, s in CRATERS)
    img = (r < 650) * (0.6 + (0.3 if band else -0.25) * tex) * (0.8 + 0.2 * (xx / N) * (1 if band else -1))
    img = img + rng.normal(0, 0.01, img.shape)
    return cv2.cvtColor(np.clip(img * 220, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def align(ref, img, guess):
    report, found = [], []
    masks = [np.ones((N, N), bool), np.ones((N, N), bool)]
    ic.align_with_masks([ref.copy(), img.copy()], masks, 0, report, found=found, guess=guess)
    return report[1], found[1]


# ---------- the camera moved 105 px between the filters (Rhea, N1711682068_1): past phase correlation's reach ----------
true = (-0.3, 105.5)
ref, img = limb(0, 0, 0), limb(*true, 1)
how, shift = align(ref, img, None)
assert shift is None, (how, shift)                      # as before: not aligned, a quarter disk of fringes
how, shift = align(ref, img, [None, (true[0] + 5, true[1] - 6)])   # SPICE a few pixels off
assert "near SPICE" in how and np.hypot(shift[0] - true[0], shift[1] - true[1]) < 0.5, (how, shift)
print("105 px:", how)

# a match phase correlation finds alone stays as it was, whatever SPICE says
small = limb(3, 2, 1)
assert align(ref, small, None) == align(ref, small, [None, (9.0, -4.0)])
print("phase match kept:", align(ref, small, [None, (9.0, -4.0)])[0])

# nothing to match (a featureless band against a textured one): SPICE's offset stands when it lines the edges up better
# than no shift, and not otherwise
flat = cv2.cvtColor(np.clip((np.hypot(xx - 300 - 20, yy - 700 - 30) < 650) * 140 + rng.normal(0, 2, (N, N)), 0, 255)
                    .astype(np.uint8), cv2.COLOR_GRAY2BGR)
shift, how = ic.guided_shift(ref, flat, np.ones((N, N), bool), np.ones((N, N), bool), (20.0, 30.0))
assert shift is not None and np.hypot(shift[0] - 20, shift[1] - 30) < 2, (how, shift)
blank = cv2.cvtColor(rng.normal(20, 2, (N, N)).clip(0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
print("flat band:", how)
shift, how = ic.guided_shift(ref, blank, np.ones((N, N), bool), np.ones((N, N), bool), (40.0, -50.0))
print("blank:", how, shift)
assert shift is None
# a guess past GUESS_MAX (the frames show different parts of the scene) is no help
assert ic.guided_shift(ref, img, np.ones((N, N), bool), np.ones((N, N), bool), (5.0, 834.0)) == (None, "not aligned")

# ---------- without guess=, align_with_masks is the one on main, byte for byte (mosaic registration passes none) ----------
def module_from_main(name):
    src = subprocess.run(["git", "show", f"origin/main:{name}.py"], cwd=os.path.join(HERE, ".."), capture_output=True,
                         text=True)
    if src.returncode:
        return None
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, f"{name}_main.py")
    with open(path, "w") as f:
        f.write(src.stdout)
    for data in ("color_matrices.json", "false_color_bodies.json"):   # the tables it reads beside itself
        with open(os.path.join(folder, data), "w") as f:
            f.write(subprocess.run(["git", "show", f"origin/main:{data}"], cwd=os.path.join(HERE, ".."),
                                   capture_output=True, text=True).stdout)
    spec = importlib.util.spec_from_file_location(f"{name}_main", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


old_ic = module_from_main("image_correction")
if old_ic is None:
    print("(no origin/main to compare with: skipped)")
else:
    for a, b in ((ref, img), (ref, small), (ref, flat), (ref, blank)):
        got = []
        for mod in (ic, old_ic):
            masks = [np.ones((N, N), bool), (rng.random((N, N)) > 0.01)]
            masks[1] = np.ones((N, N), bool)
            rep, found = [], []
            out, ms = mod.align_with_masks([a.copy(), b.copy()], masks, 0, rep, found=found)
            got.append((rep, found, out[1].tobytes(), ms[1].tobytes()))
        assert got[0] == got[1], (got[0][0], got[1][0])
    import inspect
    sys.path.insert(0, os.path.join(HERE, "frames"))
    import obs_mosaic
    assert "guess" not in inspect.getsource(obs_mosaic._shift_onto)
    print("no guess: same as main")

# ---------- colour mixes ----------
assert cal.color_mix("N", ["RED", "BL1"], "SATURN") is None          # visible pairs stay straight (N1542600445_1)
assert cal.color_mix("W", ["RED", "VIO"], "SATURN") is None
two = cal.color_mix("W", ["IR3", "VIO"], "SATURN", own=True)
assert isinstance(two, cal.FalseMix) and two.shape == (3, 3)
assert cal.color_mix("N", ["IR3", "UV3"], "ENCELADUS", own=True).measured is False   # IR3 spread past BODY_SPREAD
assert cal.color_mix("N", ["MT3", "BL1"], "TITAN", own=True).measured
assert cal.color_mix("N", ["UV2", "UV1"], "PAN", own=True).measured is False
assert cal.two_bands([4.0, 2.0]) == [4.0, 3.0, 2.0] and cal.two_bands([1, 2, 3]) == [1, 2, 3]
with cal.coloring("raw"):
    assert cal.color_mix("W", ["IR3", "VIO"], "SATURN", own=True) is None

old_cal = module_from_main("calibration")
if old_cal is not None:
    # three-band sets (every mosaic, movie and composite of three filters) mix as they did on main
    for cam in ("N", "W"):
        for target in ("SATURN", "TITAN", "JUPITER", "ENCELADUS", "RHEA", "DIONE", "PAN"):
            for bands in (["RED", "GRN", "BL1"], ["MT3", "CB2", "MT2"], ["IR3", "GRN", "UV3"], ["CB3", "MT3", "CB2"],
                          ["IR1", "GRN", "VIO"], ["IR3", "MT2", "UV1"]):
                for gains in (None, [1.3, 0.9, 1.7]):
                    for own in (False, True):
                        a = cal.color_mix(cam, bands, target, gains, own)
                        b = old_cal.color_mix(cam, bands, target, gains, own)
                        assert (a is None) == (b is None) and (a is None or np.array_equal(np.asarray(a), np.asarray(b))), \
                            (cam, target, bands, a, b)
                        assert (a is None) or (getattr(a, "tint", None) == getattr(b, "tint", None))
    for levels in ([0.0236, 0.40, 0.135], [0.2, 0.3, 0.25], [0.01, 0.5, 0.2]):
        assert cal.balance(levels, cal.tint_of("SATURN")) == old_cal.balance(levels, old_cal.tint_of("SATURN"))
    x = rng.random((3, 64, 64)).astype(np.float32)
    m = np.diag([2.0, 1.0, 0.7]).astype(np.float32)
    a, b = m.view(cal.FalseMix), m.view(old_cal.FalseMix)
    a.tint = b.tint = cal.tint_of("SATURN")
    assert np.array_equal(cal.apply_mix(a, x), old_cal.apply_mix(b, x))
    print("three-band mixes: same as main")


# ---------- composites drawn (load_linear, tone) ----------
H = 200
disk = (np.mgrid[:H, :H][0] - 100) ** 2 + (np.mgrid[:H, :H][1] - 100) ** 2 < 70 ** 2


class Label:
    def __init__(self, band, target, cam="ISSWA"):
        self.info = {"INSTRUMENT_ID": cam, "FILTER_NAME": f"({band},CL2)", "TARGET_NAME": target}

    def get_info(self):
        return self.info


def drawn(bands, levels, target, cam="ISSWA"):
    iofs = [(np.where(disk, v, 0) + rng.normal(0, 0.0005, (H, H))).astype(np.float32) for v in levels]
    chans, margin, mix = cal.load_linear([Label(b, target, cam) for b in bands], [np.zeros((H, H, 3), np.uint8)] * len(bands), iofs)
    return [float(c[disk][:, 0].mean()) for c in cal.tone(chans, margin, mix)]


# an IR3+VIO Saturn four times brighter in IR3 (W1477675247_1): was solid orange (red 249, blue 132), now near Saturn's cream
r, g, b = drawn(["IR3", "VIO"], [0.4, 0.1], "SATURN")
print("IR3+VIO Saturn", round(r), round(g), round(b))
assert r / b < 1.35 and r >= g >= b
# a UV2+UV1 sky-blue pair comes out near gray too
r, g, b = drawn(["UV2", "UV1"], [0.05, 0.2], "SATURN", "ISSNA")
print("UV2+UV1 Saturn", round(r), round(g), round(b))
assert b / r < 1.1
# a visible pair is drawn straight, green the mean, as before
pair = drawn(["RED", "BL1"], [0.3, 0.2], "SATURN", "ISSNA")
assert len(pair) == 2
# Saturn through MT3, CB2 and MT2 with TARGET_NAME a moon that has no table (W1694956960_1, Dione): was teal
r, g, b = drawn(["MT3", "CB2", "MT2"], [0.0236, 0.40, 0.135], "DIONE")
print("methane Saturn as DIONE", round(r), round(g), round(b))
assert max(r, g, b) / min(r, g, b) < 1.06
print("ok")
