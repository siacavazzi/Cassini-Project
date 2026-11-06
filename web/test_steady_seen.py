"""A small moon's movie stabilization takes the pictures' place of the moon when SPICE's jumps about (Sam 2026-11-04:
"see variance between frames that are close together and then if it's a certain amount then we like just use visual
frame alignment"). obs_mosaic.steady_chain is held on the target as SPICE puts it (steady_guide: a window round
SPICE's place, never further than STEADY_REACH from it), and steady_places smooths back to SPICE: where SPICE is tens
of px off and jumps from frame to frame, the moon wanders out of the window and the movie jumps with SPICE.
seen_places finds the moon in each tile (color_image.find_small_body) and, when SPICE's error jumps between
neighbouring frames or is past the reach, puts SPICE's places where the pictures show the moon.

Synthetic tiles: a textured moon (MIMAS, 33 px radius) the camera creeps past. Case 1: SPICE 45 px off and jumping up
to 30 px between frames: before (SPICE's places) the stabilized moon is far off; after, within a few px. Case 2: SPICE
3 px off at random (its usual noise): nothing changes (seen_places leaves SPICE's places). Case 4: a bigger, brighter
moon touching it on ten of the tiles (a transit, Rhea over Titan in 154RH MUTUALEVE002, whose movie swung from one
moon to the other): those tiles are not looked at, so the hold stays on the target.
Run: python web/test_steady_seen.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

rng = np.random.default_rng(3)
S, N = 420, 30
Z = 1e6
R = om.RADIUS["MIMAS"] / (Z * om.IFOV["N"])
tex = cv2.GaussianBlur(np.random.default_rng(1).random((int(2 * R) + 9,) * 2).astype(np.float32), (0, 0), 2.5)
tex = (tex - tex.min()) / (tex.max() - tex.min())
truth = [(-40 + 2.5 * n, 25 - 1.0 * n) for n in range(N)]
ba.bodies_of = lambda ids: {}
om.reel.north_angles = lambda ids: {i: 0.0 for i in ids}
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}


TOUCH = range(10, 20)     # case 4: the tiles another moon touches the target on
OTHER = (1.9 * R, 0.0, 1.4 * R)   # its place from the target and radius
other_on = [False]


def draw(n):
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    px, py = S / 2 - truth[n][0], S / 2 - truth[n][1]
    inside = (xx - px) ** 2 + (yy - py) ** 2 <= R * R
    tx = np.clip((xx - px + R).astype(int), 0, tex.shape[1] - 1)
    ty = np.clip((yy - py + R).astype(int), 0, tex.shape[0] - 1)
    out = np.where(inside, (0.4 + 0.6 * tex[ty, tx]) * 160, 0)
    if other_on[0] and n in TOUCH:
        # (behind the target: a big soft bright disk)
        d = np.hypot(xx - px - OTHER[0], yy - py - OTHER[1])
        out = np.where(inside, out, np.clip((OTHER[2] - d) / 4 + 0.5, 0, 1) * 230)
    return out


def make(name, spice):
    cache = tempfile.mkdtemp()
    fr = [(f"p{n}", f"N{1700000000 + 30 * n}_1", "CL1", 30.0 * n, 600, spice[n][0], spice[n][1], Z) for n in range(N)]
    u = {"key": ("MIMAS", f"ISS_TEST_{name}", "N", 0), "frames": fr, "z": Z, "movie": True, "mosaic": False,
         "track": False, "kind": "movie", "last": fr[-1][3]}
    d, td = om.folder(u, cache), om._tiles(u, cache, scale)
    os.makedirs(td, exist_ok=True)
    for n in range(N):
        im = np.zeros((S, S, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = np.clip(draw(n) + rng.normal(0, 2, (S, S)), 0, 255).astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{td}/{n}.png")
        json.dump({"n": n, "id": fr[n][1], "filter": "CL1", "t": fr[n][3], "offset": list(spice[n]),
                   "box": [-S / 2, -S / 2, S, S]}, open(f"{td}/{n}.json", "w"))
    json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 300, 300],
               "fixed": True, "view": [600, 600], "k": 1, "colour": None, "grey": "CL1", "whole": False},
              open(os.path.join(d, om.PLAN_FILE), "w"))
    return u, cache


def error(u, cache, spice):
    """How far the moon is from where the stabilized movie draws it (its place is where the target is drawn from)."""
    placed = om.steady_places(u, cache, smooth=12)
    held = [placed[n] for n in range(N)]
    with open(os.path.join(om.folder(u, cache), om.STEADY_FILE)) as fh:
        seen = json.load(fh).get("seen")
    return np.hypot(*np.subtract(held, truth).T), np.hypot(*np.subtract(spice, truth).T), seen


with calibration.looking("balanced"):
    # 1. SPICE 45 px off, jumping: a third of its places 30 px further one way or the other
    bad = [[x + 45 + (30 if n % 3 == 1 else -25 if n % 5 == 2 else 0), y - 10] for n, (x, y) in enumerate(truth)]
    u, cache = make("JUMPY", bad)
    after, spice_err, seen = error(u, cache, bad)
    print(f"jumpy SPICE (off {spice_err.mean():.0f} px, up to {spice_err.max():.0f}): stabilized off the moon max "
          f"{after.max():.1f} px, mean {after.mean():.1f}", seen)
    assert seen["jumpy"] > om.STEADY_JUMPS and after.max() < 6, (after.max(), seen)
    # (before: seen_places switched off, SPICE's places held)
    keep = om.seen_places
    om.seen_places = lambda *a: ({}, None)
    u0, cache0 = make("JUMPY0", bad)
    before, _, _ = error(u0, cache0, bad)
    om.seen_places = keep
    print(f"  before (SPICE's places): max {before.max():.1f} px, mean {before.mean():.1f}")
    assert before.mean() > 20, before.mean()
    # 2. SPICE's usual few px: its places stand
    good = [[x + rng.uniform(-3, 3), y + rng.uniform(-3, 3)] for x, y in truth]
    u2, cache2 = make("STEADY", good)
    calm, spice_err, seen = error(u2, cache2, good)
    with open(os.path.join(om.folder(u2, cache2), om.STEADY_FILE)) as fh:
        assert not json.load(fh).get("held"), "SPICE's places stand"
    print(f"usual SPICE: stabilized max {calm.max():.1f} px", seen)
    assert calm.max() < 6
# 4. a bigger moon touching the target on ten tiles, SPICE 45 px off all the way (154RH's 18): those tiles take the moon's place from the
#    tiles either side, so the hold stays on the target; without the rule it swings onto the other moon
with calibration.looking("balanced"):
    other_on[0] = True
    off = [[x + 45 + rng.uniform(-2, 2), y - 10 + rng.uniform(-2, 2)] for x, y in truth]
    def bodies(ids, spice=off):
        n_of = {f"N{1700000000 + 30 * n}_1": n for n in range(N)}
        return {i: [("TITAN", OTHER[0] - spice[n_of[i]][0], OTHER[1] - spice[n_of[i]][1], OTHER[2], 2 * Z)]
                for i in ids if n_of.get(i) in TOUCH}
    ba.bodies_of = bodies
    u4, cache4 = make("TOUCH", off)
    touch, _, seen = error(u4, cache4, off)
    print(f"another moon touching it: stabilized off the moon max {touch.max():.1f} px", seen)
    assert seen["touching"] == len(TOUCH) and touch.max() < 6, (touch.max(), seen)
    keep = om.other_bodies
    om.other_bodies = lambda u: {}
    u5, cache5 = make("TOUCH0", off)
    swung, _, _ = error(u5, cache5, off)
    om.other_bodies = keep
    print(f"  before (the touching tiles looked at): max {swung.max():.1f} px")
    assert swung.max() > 10, swung.max()
    other_on[0] = False
    ba.bodies_of = lambda ids: {}
# 3. a bright blob the moon's size against a tile's edge (a cut corner's wedge) is not taken for the moon
u3, cache3 = make("EDGE", bad)
p3 = om.plan(u3, cache3)
made, pic, there = om._every_tile(u3, cache3, p3)
edge = dict(made[5]); im = pic(5).copy()
im[..., :3] = 0
im[180:250, 0:60, :3] = 220   # (the moon gone, a wedge at the left edge)
pics = {5: im}
held, why = om.seen_places(u3, [edge], lambda n: pics[n], there)
assert held == {} and why["found"] == 0, (held, why)
print("ok")
