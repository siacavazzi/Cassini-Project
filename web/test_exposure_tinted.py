"""exposure_chain measures a frame drawn in its set's colour (tinted_frame) on the picture the windows show, made small.
The chain draws each frame EXPOSURE_SIDE px a side, and a tinted frame drawn that small is another picture: the tint
matches the frame to its set over LUM_MATCH_MIN lit pixels, a count, which a body that fills 7,600 px of the windows'
picture does not reach in 160 px (180 of them). There the frame fell to the match's floor, 0.25 for a set's own frame
and 0.67 for the frames between, and the chain took that for the movie: a Jupiter approach movie whose frames are all as
bright in the windows (median 190 to 192) had every fourth frame drawn at 0.43 and its last frames at up to 1.41
(C23RI RMOV001, 2026-11-16). Here a made-up pass whose tinted frames are drawn dim when drawn small: the chain is flat
and the gains are 1, and a frame that is not tinted is still drawn small, once.
Run: python web/test_exposure_tinted.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic as om  # noqa: E402

N = 16
u = {"key": ("JUPITER", "ISS_TEST_TINT", "W", 0), "frames": [(None, f"W{1355234000 + 100 * n}_1", "BL1 CB2 RED GRN".split()[n % 4], 100.0 * n) for n in range(N)]}
p = {"display_scale": {"gamma": 2.2}}
om._kept_tiles = lambda u, cache, scale: None
om._speck = lambda u: False
drawn = []


def movie_frame(u, n, cache, trail=0, colour=True, out=om.OUT, centre=True, steady=0, exposure=0, sharpen=True, per_body=True):
    """A small disk on black, as bright in every frame at the windows' size; drawn small, a tinted frame loses its match:
    a set's own frame (every fourth) to 0.25 of it and the frames between to 0.67 (tinted_frame's floors)."""
    drawn.append((n, out))
    tint = tinted(n)
    level = 0.5 if out >= om.OUT or not tint else 0.5 * (0.25 if n % 4 == 0 else 0.67)
    yy, xx = np.mgrid[:out, :out]
    disk = (xx - out / 2) ** 2 + (yy - out / 2) ** 2 < (0.12 * out) ** 2
    a = np.zeros((out, out, 4), np.uint8)
    a[..., 3] = 255
    a[..., :3][disk] = int(round(om.calibration.encode(np.float32(level), 2.2) * 255))
    return Image.fromarray(a, "RGBA"), {"color": ["RED", "GRN", "BL1"], **({"tint": True} if tint else {})}


om.movie_frame = movie_frame

# every frame tinted: each is drawn small, found tinted, and measured on the windows' picture
tinted = lambda n: True
cache = tempfile.mkdtemp(prefix="exposure-tint-")
logs = om.exposure_chain(u, cache, p)
assert sorted(logs) == list(range(N)) and {v[1] for v in logs.values()} == {0}, logs
assert max(abs(v[0]) for v in logs.values()) < 0.02, logs          # (as bright all through: no step)
assert [o for _, o in drawn] == [om.EXPOSURE_SIDE, om.OUT] * N, drawn
gains = om.exposure_gains(u, cache, p)
assert all(abs(g - 1.0) <= 0.02 for g in gains.values()), gains
assert os.path.exists(os.path.join(om.folder(u, cache), om._exposure_name(True, True, 0))) and "exposure7-" in om.EXPOSURE_FILE

# what it was: measured on the small pictures, every fourth frame read 0.67 / 0.25 = 2.7 times brighter
small = [np.asarray(movie_frame(u, n, None, out=om.EXPOSURE_SIDE)[0]) for n in (0, 1)]
was = om._lit_level(small[1], 2.2) / om._lit_level(small[0], 2.2)
assert 2.4 < was < 3.0, was

# a pass with no tinted frame is drawn small only, as before
drawn.clear()
tinted = lambda n: False
u2 = dict(u, key=("JUPITER", "ISS_TEST_PLAIN", "W", 0))
logs = om.exposure_chain(u2, tempfile.mkdtemp(prefix="exposure-plain-"), p)
assert [o for _, o in drawn] == [om.EXPOSURE_SIDE] * N and max(abs(v[0]) for v in logs.values()) < 0.02, (drawn, logs)
print("ok")
