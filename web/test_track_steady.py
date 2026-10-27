"""A feature track plays steady (obs_mosaic.track_places): the camera follows a cloud the planet carries along, so
SPICE puts its frames 150 px apart one after another (and a few px off each time), while the cloud hardly moves in
the frame itself. Each tile is registered to the one before it with C8's alignment (_shift_onto), so in the movie
(movie_frame) the cloud holds still and a colour set's filters land on one another. Synthetic tiles: one cloud field,
filters RED, GRN, BL1 at three brightnesses, a methane-like frame that matches nothing (it is held where the frame before is).
Run: python web/test_track_steady.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(3)
field = cv2.GaussianBlur(rng.random((1400, 1400)).astype(np.float32), (0, 0), 6)
field = (field - field.min()) / (field.max() - field.min())
S = 600
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0, "BL1": 1.0}}
filters = ["RED", "GRN", "BL1", "MT2"] * 5
level = {"RED": 200, "GRN": 170, "BL1": 140}
# the cloud drifts a little in the frame (the camera's tracking is not perfect): where frame n's crop starts in the field
drift = [(400 + 1.5 * n + rng.uniform(-2, 2), 400 - 1.0 * n + rng.uniform(-2, 2)) for n in range(len(filters))]
fr, spice = [], []
for n, f in enumerate(filters):
    fr.append((f"p{n}", f"N{1600000000 + 40 * n}_1", f, 40.0 * n, 600, 0, 0, 1e6))
    # SPICE: the frame's middle moves 150 px a frame round the body's centre, and is a few px off each time
    spice.append([150.0 * n + rng.uniform(-6, 6), 30.0 * n + rng.uniform(-6, 6)])
u = {"key": ("SATURN", "ISS_TEST_FEATRAK", "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "track": True, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n, (f, (x, y)) in enumerate(zip(filters, drift)):
    M = np.float32([[1, 0, x], [0, 1, y]])
    crop = cv2.warpAffine(field, M, (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    if f == "MT2":   # a methane band: other clouds altogether
        im[..., :3] = (rng.random((S, S)) * 90).astype(np.uint8)[..., None]
    else:
        im[..., :3] = (crop * level[f]).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": f, "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-724, -724, 3800, 1500], "fixed": True,
           "view": [4524, 2224], "k": 1, "colour": None, "grey": "RED", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

with calibration.looking("balanced"):
    places = om.track_places(u, cache)
    how = json.load(open(os.path.join(d, om.TRACK_FILE)))["how"]
    print("how", how)
    # where each tile puts the cloud field's origin: the steady place minus where the crop starts in the field
    err = [np.subtract(places[n], np.subtract(drift[n], drift[0])) - places[0] for n in places if filters[n] != "MT2"]
    print("cloud's place, first tile = 0:", np.round(err, 2).tolist())
    # (phase correlation's sub-pixel peak is good to a px or so, across filters too)
    assert max(np.abs(e).max() for e in err) < 2.5, err
    # the methane frame is held where the frame before is, not moved by SPICE's step
    for n in places:
        if filters[n] == "MT2":
            assert how[str(n)] == f"held from {n - 1}", how[str(n)]
            assert places[n] == places[n - 1]
    # and the frame after it lands on the newest RED, the methane frame being no help
    assert how["4"].endswith("to 0"), how["4"]
    # the movie: one view for the pass, the cloud still in it from frame to frame
    fp = om.movie_footprint(u, cache)
    assert fp[2] - fp[0] < 1.5 * om.FRAME, fp   # the steady frames sit on one another, not 3000 px of SPICE steps
    shots = []
    for n in range(len(filters)):
        im, rep = om.movie_frame(u, n, cache, colour=False)
        assert rep["steady"] == "track" and not rep["centred"], rep
        if filters[n] != "MT2":
            a = np.asarray(im)[..., 0].astype(np.float32)
            h, w = a.shape
            # the middle of the view, which every frame covers: the cloud, not the frame's edges
            shots.append(a[h // 2 - 150:h // 2 + 150, w // 2 - 150:w // 2 + 150])
    moves = [cv2.phaseCorrelate(a, b)[0] for a, b in zip(shots, shots[1:])]
    print("the movie's frame-to-frame motion (px):", np.round(moves, 2).tolist())
    # (to the whole pixels the picture is drawn on) where SPICE's places step 150 px a frame
    assert max(np.hypot(*m) for m in moves) < 2.5, moves
print("ok")
