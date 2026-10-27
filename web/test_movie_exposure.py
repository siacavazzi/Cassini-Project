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
S, N, FLASH, STEP, SCENE = 500, 80, 14, 34, 60
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
    if n == SCENE:   # another scene: a narrow strip of the view, twice as bright (a ring arc between wide views)
        im[:, :, :3] = np.minimum(255, im[:, :, :3].astype(int) * 2).astype(np.uint8)
        im[:, 100:, 3] = 0
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[n][1], "filter": f, "t": fr[n][3], "offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]},
              open(f"{TD}/{n}.json", "w"))
json.dump({"key": list(u["key"]), "display_scale": scale, "angle": 0, "footprint": [-300, -300, 300, 300], "fixed": True,
           "view": [600, 600], "k": 1, "colour": None, "grey": "RED", "whole": False}, open(os.path.join(d, om.PLAN_FILE), "w"))

with calibration.looking("balanced"):
    logs = om.exposure_chain(u, cache)
    # the chain follows the movie's brightness frame to frame, whichever filter (to the 8-bit picture's rounding)
    # the narrow strip is a scene of its own, and the frame after it starts the next stretch: the strip left as it is
    assert logs[SCENE][1] == 1 and logs[SCENE + 1][1] == 2, (logs[SCENE], logs[SCENE + 1])
    for n in range(SCENE):
        assert abs(logs[n][0] - math.log(bright[n] / bright[0])) < 0.03 and logs[n][1] == 0, (n, logs[n], math.log(bright[n] / bright[0]))
    gains = om.exposure_gains(u, cache, smooth=4)
    assert gains[SCENE] == 1.0, gains[SCENE]
    N = SCENE   # (the rest: the stretch before the other scene)
    shown = [bright[n] * gains[n] for n in range(N)]
    print("gains:", [gains[n] for n in range(N)])
    steps = [shown[n] / shown[n - 1] for n in range(1, N)]
    print("brightness steps shown:", np.round(steps, 3).tolist())
    # the flash is brought to its neighbours, and GRN's flicker against RED (0.8x every other frame) is evened out
    assert abs(shown[FLASH] / shown[FLASH - 1] - 1) < 0.08 and abs(shown[FLASH] / shown[FLASH + 1] - 1) < 0.08, shown[FLASH - 2:FLASH + 3]
    # the step is spread out: no frame more than 1.15x the one before it (it was 1.6x), and none flickers by more than 8%
    assert max(steps) < 1.15 and min(steps) > 0.92, np.round(steps, 3).tolist()
    # the whole step is kept, and the slow brightening (1% a frame) too
    assert abs(shown[N - 2] / shown[2] / (bright[N - 2] / bright[2]) - 1) < 0.1, (shown[2], shown[-2])
    assert om.exposure_gains(u, cache, smooth=0) == {}
    # a pass that plays in colour: its grey frames before the set is complete (a filter each) keep gain 1
    real = om.exposure_chain
    om.exposure_chain = lambda *a, **k: {0: [0.0, 0, False], 1: [0.8, 0, False], 2: [-0.5, 0, False], 3: [0.0, 1, True],
                                         4: [0.0, 1, True], 5: [1.0, 1, True], 6: [0.0, 1, True], 7: [0.0, 1, True]}
    g = om.exposure_gains(u, cache, smooth=4)
    om.exposure_chain = real
    assert g[0] == g[1] == g[2] == 1.0 and g[5] < 0.5, g
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
