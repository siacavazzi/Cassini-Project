"""A movie pass plays stabilized (obs_mosaic.steady_chain, steady_places): SPICE puts each frame on its own and is a
few px off, differently from frame to frame, so a body wobbles in the movie. Each tile is registered to the one
before it with C8's alignment (_shift_onto), SPICE's step between the two as the starting guess, and the chain is held
to SPICE over the smoothing (a Gaussian of how far SPICE is from the chain), so the wobble goes and the pass stays
where SPICE puts it on average. Synthetic tiles: one textured field the camera creeps across (the real motion, 6 px a
frame), SPICE's places that motion plus up to 9 px of noise. With steady 0 the movie is SPICE's, as before.
Run: python web/test_movie_stabilize.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(5)
field = cv2.GaussianBlur(rng.random((2200, 1400)).astype(np.float32), (0, 0), 5)
field = (field - field.min()) / (field.max() - field.min())
S, N = 500, 40
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}
filters = ["RED", "GRN", "BL1", "CL1"] * (N // 4)
level = {"RED": 200, "GRN": 170, "BL1": 140, "CL1": 230}
# where frame n's crop starts in the field: the camera creeps 6 px a frame one way, 2 the other (the real motion)
truth = [(300 + 6.0 * n, 400 + 2.0 * n) for n in range(N)]
# SPICE: that motion, a few px off each time (the frame's middle round the body, which sits at the field's origin)
spice = [[x + rng.uniform(-9, 9), y + rng.uniform(-9, 9)] for x, y in truth]
fr = [(f"p{n}", f"N{1600000000 + 30 * n}_1", f, 30.0 * n, 600, 0, 0, 1e6) for n, f in enumerate(filters)]
u = {"key": ("MIMAS", "ISS_TEST_MOVIE", "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "track": False, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n, (f, (x, y)) in enumerate(zip(filters, truth)):
    M = np.float32([[1, 0, x], [0, 1, y]])
    crop = cv2.warpAffine(field, M, (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = (crop * level[f]).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": f, "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
           "view": [1800, 1100], "k": 1, "colour": None, "grey": "RED", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))


def errors(places):
    """How far each place is from the truth, after the one constant offset all of them share (px)."""
    e = np.array([np.subtract(places[n], truth[n]) for n in range(N)])
    return e - e.mean(axis=0)


with calibration.looking("balanced"):
    chain = om.steady_chain(u, cache)
    how = json.load(open(os.path.join(d, om.STEADY_FILE)))["how"]
    print("how", how)
    assert len(chain) == N and all(h == "first" or " to " in h for h in how.values()), how
    raw = np.hypot(*errors(dict(enumerate(spice))).T)
    print("SPICE's error (px): max %.1f, mean %.1f" % (raw.max(), raw.mean()))
    for smooth in (4, 12, 60):
        places = om.steady_places(u, cache, smooth=smooth)
        err = np.hypot(*errors(places).T)
        step = np.hypot(*np.diff(errors(places), axis=0).T)
        print(f"smoothing {smooth}: error max {err.max():.2f} mean {err.mean():.2f}, frame-to-frame wobble max {step.max():.2f}")
        # the wobble from one frame to the next comes out (phase correlation is good to a px or so across filters)
        assert step.max() < 2.5, step
        # and the pass stays where SPICE puts it on average: the places differ from SPICE's by no constant offset
        assert np.abs(np.mean(np.subtract([places[n] for n in range(N)], spice), axis=0)).max() < 3, smooth
    # smoothing 0: SPICE's places
    assert om.steady_places(u, cache, smooth=0) == {}
    assert om.steady_of(u, 0) == 0 and om.steady_of(u, 12) == 12 and om.steady_of(u, 999) == om.STEADY_MOST
    assert om.steady_of(dict(u, track=True), 12) == 0   # a feature track is always steady its own way
    # the movie: one view for the pass, so the field should sit still in it while the frames creep across it

    def motion(steady):
        shots = []
        for n in range(N):
            im, rep = om.movie_frame(u, n, cache, colour=False, steady=steady)
            if steady:
                assert rep["steady"] == "stabilized" and rep["stabilized"]["smooth"] == steady, rep
            else:
                assert "steady" not in rep, rep
            shots.append(np.asarray(im))
        moves = []
        for a, b in zip(shots, shots[1:]):
            # where both frames are drawn, less a margin for the edges: the field there should be the same
            ys, xs = np.nonzero((a[..., 3] > 0) & (b[..., 3] > 0))
            y0, y1, x0, x1 = ys.min() + 12, ys.max() - 12, xs.min() + 12, xs.max() - 12
            m = cv2.phaseCorrelate(a[y0:y1, x0:x1, 0].astype(np.float32), b[y0:y1, x0:x1, 0].astype(np.float32))[0]
            moves.append(np.hypot(*m))
        return np.array(moves) * max(*np.subtract(om.movie_footprint(u, cache)[2:], om.movie_footprint(u, cache)[:2])) / max(shots[0].shape[:2])
    before, after = motion(0), motion(12)
    print("frame-to-frame wobble in the movie (px), SPICE: max %.1f mean %.1f; stabilized: max %.1f mean %.1f"
          % (before.max(), before.mean(), after.max(), after.mean()))
    assert after.mean() < before.mean() / 3 and after.max() < 3, (before, after)
print("ok")
