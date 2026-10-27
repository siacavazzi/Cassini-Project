"""A movie pass plays with its exposure evened out (obs_mosaic.exposure_chain, exposure_gains, evened_gains): the pass
is drawn on one display scale, so a frame the calibration did not even out flashes, and a jump in brightness shows as
a step. Each tile's brightness is measured against the newest earlier tile of its filter where both are drawn; a flash
(one frame 2.5x brighter) is brought to its neighbours' level, a lasting step (1.6x) is spread over several frames,
and a slow brightening (1% a frame) stays. Synthetic tiles on one still field, filters RED and GRN in turn.
Run: python web/test_movie_exposure.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import json, math, tempfile  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402
import calibration  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(7)
field = cv2.GaussianBlur(rng.random((500, 500)).astype(np.float32), (0, 0), 5)
field = 0.05 + 0.25 * (field - field.min()) / (field.max() - field.min())   # linear brightness
S, N, FLASH, STEP = 500, 80, 14, 34
cache = tempfile.mkdtemp()
scale = {"blacks": {}, "white": 1, "gamma": 2.2, "balance": {"RED": 1.0, "GRN": 1.0}}
filters = ["RED", "GRN"] * (N // 2)
level = {"RED": 1.0, "GRN": 0.8}
# each frame's brightness: a slow brightening, a flash on frame FLASH, a lasting step from frame STEP
bright = [level[f] * (1 + 0.01 * n) * (2.5 if n == FLASH else 1) * (1.6 if n >= STEP else 1) for n, f in enumerate(filters)]
fr = [(f"p{n}", f"N{1600000000 + 30 * n}_1", f, 30.0 * n, 600, 0, 0, 1e6) for n, f in enumerate(filters)]
u = {"key": ("MIMAS", "ISS_TEST_EXPOSURE", "N", 0), "frames": fr, "z": 1e6, "movie": True, "mosaic": False,
     "track": False, "kind": "movie", "last": fr[-1][3]}
d, TD = om.folder(u, cache), om._tiles(u, cache, scale)
os.makedirs(TD, exist_ok=True)
for n, f in enumerate(filters):
    im = np.zeros((S, S, 4), np.uint8)
    im[..., 3] = 255
    im[..., :3] = (calibration.encode(np.clip(field * bright[n], 0, 1), 2.2) * 255 + 0.5).astype(np.uint8)[..., None]
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": f, "t": fr[n][3], "offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 300, 300], "fixed": True,
           "view": [600, 600], "k": 1, "colour": None, "grey": "RED", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

with calibration.looking("balanced"):
    logs = om.exposure_chain(u, cache)
    # the chain follows each filter's brightness (to the 8-bit picture's rounding)
    for n, f in enumerate(filters):
        first = filters.index(f)
        assert abs(logs[n] - math.log(bright[n] / bright[first])) < 0.03, (n, logs[n], math.log(bright[n] / bright[first]))
    gains = om.exposure_gains(u, cache, smooth=4)
    shown = [bright[n] * gains[n] for n in range(N)]
    print("gains:", [gains[n] for n in range(N)])
    # the flash is brought to its neighbours (of its filter)
    assert abs(shown[FLASH] / shown[FLASH - 2] - 1) < 0.08 and abs(shown[FLASH] / shown[FLASH + 2] - 1) < 0.08, shown[FLASH - 2:FLASH + 3]
    # the step is spread out: no frame of a filter more than 1.2x the one before it (it was 1.6x), the whole step kept
    for f in level:
        ns = [n for n in range(N) if filters[n] == f]
        steps = [shown[b] / shown[a] for a, b in zip(ns, ns[1:])]
        assert max(steps) < 1.2, (f, np.round(steps, 3).tolist())
        # and far from the flash and the step the frames keep their brightness (the slow brightening stays)
        assert abs(gains[ns[2]] - 1) < 0.03 and abs(gains[ns[-1]] - 1) < 0.03, (gains[ns[2]], gains[ns[-1]])
    assert om.exposure_gains(u, cache, smooth=0) == {}
    # the pure functions alone, as the viewer would run them
    assert om.evened_gains([0, 0, 1, 0, 0], 3)[2] == round(math.exp(-1) * 200) / 200
    assert om.held_to_spice([[0, 0], [10, 0]], [[0, 0], [10, 0]], 4) == [[0.0, 0.0], [10.0, 0.0]]
    # the movie frames: drawn with the gains (the flash frame dimmed) and named in the report
    def mean(steady_exposure):
        im, rep = om.movie_frame(u, FLASH, cache, colour=False, exposure=steady_exposure)
        return float(calibration.decode(np.asarray(im)[..., 0][np.asarray(im)[..., 3] > 0] / 255, 2.2).mean()), rep
    raw, rep0 = mean(0)
    even, rep = mean(4)
    print("the flash frame's mean linear brightness: %.3f -> %.3f" % (raw, even), rep["exposure"])
    assert "exposure" not in rep0 and rep["exposure"]["gain"] == gains[FLASH] and even < raw / 2
print("ok")
