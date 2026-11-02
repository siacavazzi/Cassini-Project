"""Natural color (emulated) on this computer (steady-local.html, the pass table's "eye" recipes) gives the server's
picture with colors=eye: the page's colour mix (cassiniSteadyMath.mix, run here in node) of a set's grey frames
(color=0, which the pre-build has, the same in every style) with the table's eye mix equals movie_frame's colour
frame drawn in the eye style (colour_picture with calibration.eye_mix), for a false colour pass (Saturn's methane
stare, WAC MT3 + CB2 + MT2) and a two-filter pass (CB2 + MT2: its longer filter's tile listed twice), so no picture
of its own is ever made or cached for it. Synthetic passes as web/test_steady_local.py.
Run: python web/test_eye_local.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(11)
field = cv2.GaussianBlur(rng.random((1600, 1400)).astype(np.float32), (0, 0), 5)
field = (field - field.min()) / (field.max() - field.min())
S, N = 400, 24
cache = tempfile.mkdtemp()
truth = [(300 + 6.0 * n, 400 + 2.0 * n) for n in range(N)]
spice = [[x + rng.uniform(-9, 9), y + rng.uniform(-9, 9)] for x, y in truth]
LEVEL = {"MT3": 40, "CB2": 220, "MT2": 110}   # as Saturn is in them: dark in the deep methane band


def make_pass(name, filters, base):
    scale = {"blacks": {}, "white": 1, "gamma": 2.2}
    fr = [(f"{name}{n}", f"W{base + 30 * n}_1", filters[n % len(filters)], 30.0 * n, 600, 0, 0, 1e6) for n in range(N)]
    u = {"key": ("SATURN", f"ISS_TEST_{name}", "W", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
         "track": False, "kind": "movie", "last": fr[-1][3]}
    # the same tiles and plan in each style's folder (the eye style keeps its own cache, as every style does)
    for style in ("natural", "eye"):
        with calibration.coloring(style):
            d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
            os.makedirs(TD, exist_ok=True)
            for n, (x, y) in enumerate(truth):
                crop = cv2.warpAffine(field, np.float32([[1, 0, x], [0, 1, y]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
                im = np.zeros((S, S, 4), np.uint8)
                im[..., 3] = 255
                f = fr[n][2]
                # each band's own structure on top of the shared one, so the mix has something to weigh
                own = np.roll(crop, 7 * filters.index(f), axis=1)
                im[..., :3] = np.clip((0.7 * crop + 0.3 * own) * LEVEL[f] * 1.1, 0, 255).astype(np.uint8)[..., None]
                Image.fromarray(im).save(f"{TD}/{n}.png")
                json.dump({"n": n, "id": fr[n][1], "filter": f, "t": fr[n][3], "offset": spice[n], "box": [-S / 2, -S / 2, S, S]},
                          open(f"{TD}/{n}.json", "w"))
            json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [0, 0, 1800, 1100], "fixed": True,
                       "view": [1800, 1100], "k": 1, "colour": filters, "grey": filters[0], "whole": False},
                      open(os.path.join(d, om.PLAN_FILE), "w"))
    return u


page = open(os.path.join(HERE, "cassini-os", "src", "steady-local.html")).read()
script = page[page.index("<script>") + 8:page.index("</script>")]


def node_mix(cases, sets):
    """The page's colour mix (cassiniSteadyMath.mix) of each case's planes, run in node on the raw bytes."""
    tmp = tempfile.mkdtemp()
    for c, planes in enumerate(cases):
        for q, pl in enumerate(planes):
            pl.tofile(f"{tmp}/{c}_{q}.bin")
    js = ("const window = {};\n" + script + "\nconst M = window.cassiniSteadyMath(), fs = require('fs'), c = " + json.dumps(sets) + ";\n"
          f"for (let i = 0; i < {len(cases)}; i++) {{ const P = [0, 1, 2].map(q => new Uint8ClampedArray(fs.readFileSync('{tmp}/' + i + '_' + q + '.bin')));"
          f" fs.writeFileSync('{tmp}/' + i + '.out', M.mix(P, c)); }}")
    with open(f"{tmp}/mix.js", "w") as fh:
        fh.write(js)
    subprocess.run(["node", f"{tmp}/mix.js"], check=True)
    return [np.fromfile(f"{tmp}/{c}.out", np.uint8).reshape(cases[c][0].shape) for c in range(len(cases))]


for name, filters, base in (("EYE3", ["MT3", "CB2", "MT2"], 1600200000), ("EYE2", ["CB2", "MT2"], 1600300000)):
    u = make_pass(name, filters, base)
    # the table as the pre-build makes it (the default style), with its eye recipes
    om.steady_chain(u, cache)
    om.exposure_chain(u, cache, None, True, True, 0)
    table = om._steady_table(u, 0, cache, True, True)
    eye = table["eye"]
    assert eye and eye["by"], table.get("eye")
    assert table["sets"] is None   # the default draws these on the server (a false colour balance)
    want_mix = calibration.eye_mix("W", filters, "SATURN")
    assert np.allclose(eye["mix"], want_mix)
    cases, wants, labels = [], [], []
    for n in range(N):
        recipe = eye["by"].get(str(n))
        if not recipe:
            continue
        if len(filters) == 2:
            assert recipe[0] == recipe[1]
        planes = []
        for j in recipe:
            grey = np.asarray(om.movie_frame(u, j, cache, colour=False, centre=True)[0])
            with calibration.coloring("eye"):
                # the grey frame the page starts from is the same in the eye style: no pictures of its own
                assert (np.asarray(om.movie_frame(u, j, cache, colour=False, centre=True)[0]) == grey).all()
            planes.append(grey)
        with calibration.coloring("eye"):
            B = np.asarray(om.movie_frame(u, n, cache, colour=True, centre=True)[0])
        cases.append(planes)
        wants.append(B)
        labels.append((n, recipe))
    off, total = 0, 0
    for out, B, lab in zip(node_mix(cases, eye), wants, labels):
        diff = np.abs(out.astype(int) - B.astype(int))
        if diff.max() > 1:
            w = np.argwhere(diff > 1)
            print("DIFF", lab, len(w), [(tuple(map(int, i)), int(out[tuple(i)]), int(B[tuple(i)])) for i in w[:4]])
        assert diff.max() <= 1, int(diff.max())
        off += int((diff > 0).sum())
        total += diff.size
    # (numpy's mix runs through BLAS, which may round a handful of sums a level apart: test_steady_local.py)
    assert off <= total * 1e-5, (off, total)
    lit = np.concatenate([w[..., :3][w[..., 3] > 0] for w in wants])
    lit = lit[lit.max(axis=1) > 40]
    print(f"{'+'.join(filters)}: {len(cases)} colour pictures, the page's eye mix equals the server's colors=eye picture "
          f"but for {off} of {total} values a level apart; median lit color {np.median(lit, axis=0).astype(int).tolist()}")
print("ok")
