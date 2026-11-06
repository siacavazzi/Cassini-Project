"""A movie's stabilization stays on its pass's target when a second moon crosses the frame (Sam 2026-11-04: in a
mutual event, "it'll lock on one moon and then change"). obs_mosaic.steady_chain registers each tile to the one before
it; matched over the whole frame, a big bright moon moving across the picture pulls the chain along with it, and
steady_places' smoothing back to SPICE then drags the target away and back. steady_guide holds every match on the
target as SPICE puts it: only round its disk, with every other body SPICE puts in the frame (the geometry cache's
bodies table) left out, and never further than STEADY_REACH from SPICE's own place.

Synthetic tiles: a small textured moon (the target) the camera creeps past, SPICE's places that creep plus up to 4 px
of noise, and a bigger, brighter moon sweeping across the frames 9 px a frame, over the target half way through.
Checked three ways: the chain as it was (no guide: follows the other moon), held on the target with the bodies table
(masks), and with no bodies table at all (the window round the target and SPICE's reach alone).
Run: python web/test_steady_target.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

rng = np.random.default_rng(7)
S, N = 420, 36
Z = 1e6                                   # km: MIMAS at this distance is 33 px across its radius in the NAC
R = om.RADIUS["MIMAS"] / (Z * om.IFOV["N"])
R2 = 2.4 * R                              # the other moon: bigger, and brighter


def texture(r, seed):
    t = cv2.GaussianBlur(np.random.default_rng(seed).random((int(2 * r) + 9,) * 2).astype(np.float32), (0, 0), 2.5)
    return (t - t.min()) / (t.max() - t.min())


tex1, tex2 = texture(R, 1), texture(R2, 2)
# the frame's middle round the target (reference px): the camera creeps past it
truth = [(-40 + 2.5 * n, 25 - 1.0 * n) for n in range(N)]
spice = [[x + rng.uniform(-4, 4), y + rng.uniform(-4, 4)] for x, y in truth]
# the other moon from the target: sweeping across, over the target round frame N/2
other = [(-9.0 * (n - N / 2), 4.0 - 0.5 * (n - N / 2)) for n in range(N)]


def draw(n):
    im = np.zeros((S, S), np.float32)
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    for (cx, cy), r, tex, level in (((0.0, 0.0), R, tex1, 150), (other[n], R2, tex2, 250)):
        # where that body's centre is in the tile: the tile's middle sits at truth[n] from the target's centre
        px, py = S / 2 + cx - truth[n][0], S / 2 + cy - truth[n][1]
        inside = (xx - px) ** 2 + (yy - py) ** 2 <= r * r
        tx = np.clip((xx - px + r).astype(int), 0, tex.shape[1] - 1)
        ty = np.clip((yy - py + r).astype(int), 0, tex.shape[0] - 1)
        body = (0.4 + 0.6 * tex[ty, tx]) * level
        im = np.where(inside, body, im)   # (the other moon drawn last: in front)
    return im


cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}
fr = [(f"p{n}", f"N{1700000000 + 30 * n}_1", "CL1", 30.0 * n, 600, spice[n][0], spice[n][1], Z) for n in range(N)]
u = {"key": ("MIMAS", "ISS_TEST_MUTUALEVE", "N", 0), "frames": fr, "z": Z, "movie": True, "mosaic": False,
     "track": False, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n in range(N):
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = np.clip(draw(n) + rng.normal(0, 2, (S, S)), 0, 255).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": "CL1", "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 300, 300], "fixed": True,
           "view": [600, 600], "k": 1, "colour": None, "grey": "CL1", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

# the geometry cache's bodies table as bootleg_autonav.bodies_of answers it: the other moon from the CCD's centre
# (camera axes, full resolution px; north up here, angle 0), the target at -x, -y of the frame's middle
table = {fr[n][1]: [("JANUS", other[n][0] - spice[n][0], other[n][1] - spice[n][1], R2, Z * 0.98)] for n in range(N)}
om.reel.north_angles = lambda ids: {i: 0.0 for i in ids}


def run(name, guide):
    """The chain made with a guide (steady_guide(u) or none), fresh, and how far each place is from the truth (px)."""
    for f in os.listdir(d):
        if f.startswith("steady"):
            os.remove(os.path.join(d, f))
    om._passes.clear()
    made, pic, there = om._every_tile(u, cache, om.plan(u, cache))

    def step(places, j, n):
        return [places[j][0] + made[n]["offset"][0] - made[j]["offset"][0],
                places[j][1] + made[n]["offset"][1] - made[j]["offset"][1]]
    places, hows = om._chain(made, pic, there, om.STEADY_MAX * om.FRAME, step, guide)
    chain = [places[n] for n in range(N)]
    held = om.held_to_spice(spice, chain, 12)
    err = np.hypot(*np.subtract(held, truth).T)
    print(f"{name}: stabilized error from the truth max {err.max():.1f} px, mean {err.mean():.1f} px "
          f"(SPICE's own: max {np.hypot(*np.subtract(spice, truth).T).max():.1f})")
    return err, hows


with calibration.looking("balanced"):
    before, _ = run("matched over the whole frame (before)", None)
    ba.bodies_of = lambda ids: {i: table.get(i, []) for i in ids}
    masked, hows = run("held on the target, bodies table", om.steady_guide(u))
    print(" ", sorted(set(h.split(" to ")[0] for h in hows.values())))
    ba.bodies_of = lambda ids: {}
    alone, _ = run("held on the target, no bodies table", om.steady_guide(u))
    # the other moon pulls the old chain well off the target ...
    assert before.max() > 12, before.max()
    # ... and held on it, the target stays within SPICE's own few px all through
    assert masked.max() < 6, masked.max()
    # without the bodies table the window round the target and SPICE's reach alone still take most of it out
    assert alone.max() < before.max() / 4, (alone.max(), before.max())
    # and the guide's numbers for this pass: the window round a disk smaller than a frame, the other moon a hole
    g = om.steady_guide(u)({0: [0.0, 0.0]}, 0, 1, [0.0, 0.0])
    assert g["around"] is not None and g["reach"] == om.STEADY_REACH, g
    # a target bigger than a frame is not windowed (its whole limb is matched, as before)
    big = dict(u, key=("SATURN",) + u["key"][1:])
    assert om.steady_guide(big)({0: [0.0, 0.0]}, 0, 1, [0.0, 0.0])["around"] is None
print("ok")
