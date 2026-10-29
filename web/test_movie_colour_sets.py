"""A movie's colour set drawn on one another (obs_mosaic.set_places): the filters of a set are taken minutes apart and
a planet's clouds move between them, so drawn where SPICE puts each one the set is a smeared, fringed overlay of three
pictures (the 2011 storm movie, quality check 10-29). Synthetic colour pass: RED, GRN, BL1 over and over, the field
(the clouds) drifting 5 px a frame against where SPICE puts the frames. Each set's filters land on its newest within
half a pixel; its colour frame holds the detail of a single filter's frame, which drawn at SPICE's places it loses;
a match past SET_MAX and Settings > Processing's alignment off keep SPICE's places; the frames are named apart.
Run: python web/test_movie_colour_sets.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(11)
field = cv2.GaussianBlur(rng.random((1600, 1600)).astype(np.float32), (0, 0), 2)
field = (field - field.min()) / (field.max() - field.min())
S, N, DRIFT = 500, 18, 5.0
FILTERS = ["RED", "GRN", "BL1"]
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {f: 1.0 for f in FILTERS}}
# SPICE follows the camera (the frames' places); the clouds drift DRIFT px a frame across the view on top of that
spice = [[200 + 3.0 * n, 300 + 1.0 * n] for n in range(N)]
truth = [[x - DRIFT * n, y] for n, (x, y) in enumerate(spice)]


def make(cache, name):
    fr = [(f"c{n}", f"N{1600200000 + 40 * n}_1", FILTERS[n % 3], 40.0 * n, 600, 0, 0, 1e6) for n in range(N)]
    u = {"key": ("SATURN", name, "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
         "track": False, "kind": "movie", "last": fr[-1][3]}
    d, td = om.folder(u, cache), om._tiles(u, cache, scale)
    os.makedirs(td, exist_ok=True)
    for n, (x, y) in enumerate(truth):
        crop = cv2.warpAffine(field, np.float32([[1, 0, x], [0, 1, y]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
        im = np.zeros((S, S, 4), np.uint8)
        im[..., 3] = 255
        im[..., :3] = np.clip(crop * {"RED": 220, "GRN": 180, "BL1": 140}[FILTERS[n % 3]], 0, 255).astype(np.uint8)[..., None]
        Image.fromarray(im).save(f"{td}/{n}.png")
        json.dump({"n": n, "id": fr[n][1], "filter": FILTERS[n % 3], "t": fr[n][3], "offset": spice[n],
                   "box": [-S / 2, -S / 2, S, S]}, open(f"{td}/{n}.json", "w"))
    json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
               "view": [1800, 1100], "k": 1, "colour": FILTERS, "grey": "RED", "whole": False},
              open(os.path.join(d, om.PLAN_FILE), "w"))
    return u


def detail(im):
    """The picture's fine detail where it is whole: the variance of the Laplacian of its luminance."""
    a = np.asarray(im)
    inside = cv2.erode((a[..., 3] == 255).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    return float(cv2.Laplacian(a[..., :3].astype(np.float32).mean(axis=2), cv2.CV_32F)[inside].var())


with calibration.looking("balanced"):
    cache = tempfile.mkdtemp()
    u = make(cache, "ISS_TEST_SETS")
    p = om.plan(u, cache)
    worst, sharp, alone = 0.0, [], []
    # (the sets are RED, GRN, BL1 runs, each frame between them showing the newest complete one)
    for n in range(2, N, 3):
        js = [n - 2, n - 1, n]
        rel = om.set_places(u, cache, p, js)
        # where each filter's picture lands from the newest's: the truth's step, not SPICE's
        for j, (dx, dy) in zip(js, rel):
            want = (truth[j][0] - truth[n][0], truth[j][1] - truth[n][1])
            worst = max(worst, abs(dx - want[0]), abs(dy - want[1]))
        im, rep = om.movie_frame(u, n, cache, colour=True, centre=False)
        assert rep.get("color") == FILTERS and rep.get("set_places") == rel, rep
        sharp.append(detail(im))
        alone.append(detail(om.movie_frame(u, n, cache, colour=False, centre=False)[0]))
    assert worst <= 0.5, worst
    # the set kept with the pass's tiles, worked out once
    kept = json.load(open(os.path.join(om._tiles(u, cache, scale), om.SET_FILE)))
    assert len(kept) == 2 * (N // 3) and all(v["shift"] for v in kept.values()), kept

    # before: each filter where SPICE puts it (a match past SET_MAX keeps SPICE's place)
    om.SET_MAX, keep = 0.0, om.SET_MAX
    cache0 = tempfile.mkdtemp()
    u0 = make(cache0, "ISS_TEST_SETS")
    p0 = om.plan(u0, cache0)
    soft = []
    for n in range(2, N, 3):
        rel = om.set_places(u0, cache0, p0, [n - 2, n - 1, n])
        assert rel == [[round(spice[j][0] - spice[n][0], 2), round(spice[j][1] - spice[n][1], 2)] for j in (n - 2, n - 1, n)], rel
        soft.append(detail(om.movie_frame(u0, n, cache0, colour=True, centre=False)[0]))
    om.SET_MAX = keep
    # drawn on one another the colour frame keeps a single frame's detail; at SPICE's places it is a blur of three
    assert min(sharp) > 0.8 * np.median(alone), (sharp, alone)
    assert max(soft) < 0.6 * min(sharp), (soft, sharp)

    # Settings > Processing's alignment off: SPICE's places, and no registration worked out
    cache2 = tempfile.mkdtemp()
    with calibration.stepping("align"):
        u2 = make(cache2, "ISS_TEST_SETS")
        p2 = om.plan(u2, cache2)
        assert om.set_places(u2, cache2, p2, [0, 1, 2]) == [[round(spice[j][0] - spice[2][0], 2), round(spice[j][1] - spice[2][1], 2)] for j in (0, 1, 2)]
        assert not os.path.exists(os.path.join(om._tiles(u2, cache2, scale), om.SET_FILE))

    # the colour frames are named apart from the ones drawn before (SET_TAG); grey frames keep their names
    om.unit_of = lambda fid: (u, [q[1] for q in u["frames"]].index(fid)) if fid in [q[1] for q in u["frames"]] else None
    om.movie_webp(u["frames"][5][1], 128, cache, colour=True, wait=True, ahead=0, centre=False)
    om.movie_webp(u["frames"][5][1], 128, cache, colour=False, wait=True, ahead=0, centre=False)
    names = sorted(os.listdir(os.path.join(om.folder(u, cache), om.MOVIE_DIR, "128")))
    assert names == ["5_0_0.json", "5_0_0.webp", f"5_0_1{om.SET_TAG}.json", f"5_0_1{om.SET_TAG}.webp"], names

print(f"colour sets: each set's filters land on its newest within {worst:.2f} px (clouds drifting {DRIFT:.0f} px a frame "
      f"against SPICE); colour frames' detail {np.median(sharp):.1f} on one another vs {np.median(soft):.1f} at SPICE's "
      f"places ({np.median(alone):.1f} for a single filter's frame); alignment off keeps SPICE's places")
print("ok")
