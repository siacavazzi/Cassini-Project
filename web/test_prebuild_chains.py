"""prebuild.py's chains phase: every movie pass's stabilization and exposure chains (obs_mosaic.steady_chain,
exposure_chain as the window plays it by default: colour, Auto center, not stabilized) are worked out and kept with
the pass, and no picture is made; a second run finds them. Synthetic tiles on one still field, the camera creeping
across it. Run: python web/test_prebuild_chains.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, tempfile, time  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402
import prebuild  # noqa: E402

rng = np.random.default_rng(3)
field = cv2.GaussianBlur(rng.random((900, 900)).astype(np.float32), (0, 0), 5)
field = (field - field.min()) / (field.max() - field.min())
S, N = 400, 12
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0}}
filters = ["RED", "GRN"] * (N // 2)
fr = [(f"p{n}", f"N{1600000000 + 30 * n}_1", f, 30.0 * n, 600, 0, 0, 1e6) for n, f in enumerate(filters)]
u = {"key": ("MIMAS", "ISS_TEST_CHAINS", "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "track": False, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n in range(N):
    crop = cv2.warpAffine(field, np.float32([[1, 0, 100 + 5 * n], [0, 1, 100]]), (S, S), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = (crop * 200).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": fr[n][2], "t": fr[n][3], "offset": [5.0 * n, 0.0], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 400, 300], "fixed": True,
           "view": [700, 600], "k": 1, "colour": None, "grey": "RED", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))
before = {os.path.join(r, f) for r, _, fs in os.walk(cache) for f in fs}

# the phase lists the movie passes, a mosaic pass's not among them
prebuild.all_passes = lambda: [u, dict(u, key=("MIMAS", "ISS_TEST_MOSAIC", "N", 0), mosaic=True, kind="mosaic")]
todo = prebuild.items("chains")
assert [name for name, _ in todo] == ["MIMAS_ISS_TEST_CHAINS_N_0"], todo
with calibration.looking(calibration.LOOKS[0]), calibration.coloring(calibration.COLORS[0]):
    assert todo[0][1](cache) == N
    made = {os.path.join(r, f) for r, _, fs in os.walk(cache) for f in fs} - before
    names = sorted(os.path.basename(f) for f in made)
    print("made:", names)
    # the two chains (and the movie's footprint, which the exposure chain's pictures are drawn in), no picture
    assert om.STEADY_FILE in names and om._exposure_name(True, True, 0) in names and all(n.endswith(".json") for n in names), names
    assert len(json.load(open(os.path.join(d, om.STEADY_FILE)))["how"]) == N
    # a second run finds them
    t0 = time.monotonic()
    todo[0][1](cache)
    assert {os.path.join(r, f) for r, _, fs in os.walk(cache) for f in fs} - before == made
    print("second run %.3f s" % (time.monotonic() - t0))
print("ok")
