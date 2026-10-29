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
shift, how = ic.guided_shift(ref, flat, (20.0, 30.0))
assert shift is not None and np.hypot(shift[0] - 20, shift[1] - 30) < 2, (how, shift)
blank = cv2.cvtColor(rng.normal(20, 2, (N, N)).clip(0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
print("flat band:", how)
shift, how = ic.spice_shift(ref, blank, np.ones((N, N), bool), np.ones((N, N), bool), (40.0, -50.0))
print("blank:", how, shift)
assert shift is None
# a guess past GUESS_MAX (the frames show different parts of the scene) is no help
assert ic.guided_shift(ref, img, (5.0, 834.0)) == (None, "not aligned")
assert ic.spice_shift(ref, img, np.ones((N, N), bool), np.ones((N, N), bool), (5.0, 834.0)) == (None, "not aligned")

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

# ---------- two-filter passes play and mosaic in colour (obs_mosaic.colour_of, colour_picture) ----------
# the WAC's CB2 + MT2 Saturn movie of ISS_003SA_3X3MOVIEB001_PRIME (2005-02-05) was drawn grey: colour_of wanted three
import json  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402
NMS = {"CB2": 750, "MT2": 727, "RED": 649, "GRN": 568, "BL1": 451, "CL1/CL2": 611, "MT3": 889, "CB3": 938}
assert om.colour_of({"CB2": 9, "MT2": 9}, NMS) == ["CB2", "MT2"]
assert om.colour_of({"BL1": 4, "RED": 5}, NMS) == ["RED", "BL1"]
assert om.colour_of({"CL1/CL2": 9, "RED": 9}, NMS) is None          # a clear frame is no colour
assert om.colour_of({"CB2": 9, "MT2": 2}, NMS) is None               # one filter at most tiles: grey, as before
assert om.colour_of({"RED": 6, "GRN": 6, "BL1": 6}, NMS) == ["RED", "GRN", "BL1"]
assert om.colour_of({"MT3": 6, "CB2": 6, "MT2": 6}, NMS) == ["MT3", "CB2", "MT2"]
assert om.colour_of({"CL1/CL2": 6, "CB2": 6, "MT2": 6}, NMS) == ["CB2", "MT2", "CL1/CL2"]   # (as on main)

cache = tempfile.mkdtemp()
levels = {"CB2": 160, "MT2": 60}          # Saturn's methane band dark against its continuum, on the grey scale
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"CB2": 110 / 160, "MT2": 110 / 60}}
fr = [(f"p{i}", f"W{1486330000 + i}_1", ["MT2", "CB2"][i % 2], 1000.0 + 37 * i, 727, 0, 0, 1e6) for i in range(6)]
u = {"key": ("SATURN", "ISS_003SA_3X3MOVIEB001_PRIME", "W", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "last": 1400}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for i, (_, fid, f, t, *_r) in enumerate(fr):
    im = np.zeros((1448, 1448, 4), np.uint8)
    im[..., 3] = 255
    im[400:1000, 400:1000, :3] = levels[f]
    Image.fromarray(im).save(f"{TD}/{i}.png")
    json.dump({"n": i, "id": fid, "filter": f, "t": t, "offset": [0.0, 0.0], "box": [-724, -724, 1448, 1448]},
              open(f"{TD}/{i}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-724, -724, 724, 724], "fixed": True,
           "view": [1448, 1448], "k": 1, "colour": ["CB2", "MT2"], "grey": "CB2", "whole": False},
          open(os.path.join(d, om.PLAN_FILE), "w"))
om.movie_footprint = lambda u, cache, p=None: [-724, -724, 724, 724]
mid = lambda a: a[a.shape[0] // 3:2 * a.shape[0] // 3, a.shape[1] // 3:2 * a.shape[1] // 3, :3].reshape(-1, 3).astype(float).mean(axis=0)
with cal.looking("balanced"):
    im, rep = om.movie_frame(u, 5, cache, centre=False)
    assert rep.get("color") == ["CB2", "MT2"], rep
    r, g, b = got = mid(np.asarray(im))
    print("CB2+MT2 Saturn movie", got.round(1))
    assert r / b < 1.5 and r >= g >= b and r - b > 3, got     # toward Saturn's cream (drawn straight: 160 / 60), not grey
    p = om.plan(u, cache)
    rect = om.movie_rect(om.movie_footprint(u, cache, p), om.tile(u, 5, cache, scale))
    k = om.OUT / max(rect[2], rect[3])
    W, H = max(1, int(np.ceil(rect[2] * k))), max(1, int(np.ceil(rect[3] * k)))
    planes = [om._place(u, om.tile(u, j, cache, scale), rect, k, W, H, cache, scale) for j in (5, 4)]
    assert np.allclose(got, mid(om.colour_picture(u, p, ["CB2", "MT2"], planes)), atol=1)
    assert om._colour_recipes(u, p, cache, [4, 5], {}) is None          # the server draws it
with cal.coloring("raw"):
    # no balance in the raw look: the two bands straight, green their mean (in linear light), as a composite draws
    r, g, b = mid(om.colour_picture(u, p, ["CB2", "MT2"], planes))
    lin = lambda v: (v / 255) ** 2.2
    assert (r, b) == (160, 60) and abs(lin(g) - (lin(160) + lin(60)) / 2) < 0.005, (r, g, b)

# ---------- a pair whose one band shows no detail stays grey in the other (obs_mosaic.pair_colour, band_detail) ----------
# Titan's CB3 + MT1 maps (042TI_GLOBMAP001, 019TI_GLBMAPNLP001, 114TI_MONITORNA001): CB3 sees the surface, MT1 only
# a smooth haze; drawn in two-filter colour their tint washed the surface out
q = np.mgrid[0:256, 0:256].astype(np.float32)
lit_disk = np.hypot(q[0] - 128, q[1] - 128) < 110
surface = np.where(lit_disk, 0.10 * (1 + 0.08 * np.sin(q[0] / 2.3) * np.cos(q[1] / 3.1)), 0) + rng.normal(0, 0.0005, (256, 256))
haze = np.where(lit_disk, 0.05 * (1 - 0.3 * ((q[0] - 128) ** 2 + (q[1] - 128) ** 2) / 110 ** 2), 0) + rng.normal(0, 0.0003, (256, 256))
d = {"CB3": om.band_detail([surface], 0.0), "MT1": om.band_detail([haze], 0.0)}
print("detail CB3", round(d["CB3"], 4), "MT1", round(d["MT1"], 4))
assert d["MT1"] < 0.25 * d["CB3"], d
assert om.pair_colour(["CB3", "MT1"], d) == (None, "CB3")
assert om.pair_colour(["MT1", "CB3"], {"MT1": d["MT1"], "CB3": d["CB3"]}) == (None, "CB3")
# both bands with detail (Saturn's belts in CB2 and MT2) keep their colour; three filters and grey are as colour_of said
assert om.pair_colour(["CB2", "MT2"], {"CB2": 0.02, "MT2": 0.015}) == (["CB2", "MT2"], None)
assert om.pair_colour(["CB2", "MT2"], None) == (["CB2", "MT2"], None)
assert om.pair_colour(["RED", "GRN", "BL1"], {"RED": 0.02, "GRN": 0.0}) == (["RED", "GRN", "BL1"], None)
assert om.pair_colour(None, None) == (None, None)
assert om.band_detail([np.zeros((256, 256), np.float32)], 0.0) == 0.0
print("ok")
