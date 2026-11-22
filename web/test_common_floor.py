"""obs_mosaic.common_floor: two pictures of one scene drawn with different blacks are matched alike. Each is put back to
its light and cut at the higher black, so the faint light the lower black drew is gone from both and the two match
as one. Run: python web/test_common_floor.py"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "frames"), HERE]
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

scale = {"white": 0.8, "gamma": 3.0, "blacks": {"CLR": 0.002}}
yy, xx = np.mgrid[0:200, 0:200].astype(np.float32)
light = 0.002 + 0.4 * (np.hypot(xx - 100, yy - 100) < 40) + 0.004 * np.exp(-np.hypot(xx - 150, yy - 60) / 20)   # a moon and a faint glow


def drawn(black):
    v = np.clip((light - black) / (scale["white"] - black), 0, 1) ** (1 / scale["gamma"])
    g = np.round(v * 255).astype(np.uint8)
    return np.dstack([g, g, g, np.full_like(g, 255)])


low, high = drawn(0.0018), drawn(0.0051)
ta, tb = {"filter": "CLR", "black": 0.0018}, {"filter": "CLR", "track_black": 0.0051}
assert int(np.abs(low[..., 0].astype(int) - high[..., 0]).max()) > 20, "the two blacks draw the glow differently"
a, b = om.common_floor(scale)(ta, low, tb, high)
diff = int(np.abs(a[..., 0].astype(int) - b[..., 0]).max())
print("largest difference after the common black:", diff, "levels")
mean = float(np.abs(a[..., 0].astype(int) - b[..., 0]).mean())
print("mean difference:", round(mean, 3))
# (8-bit pictures: near the cut, a level of the lower-black picture is several of light, gamma 3)
assert diff <= 8 and mean < 0.2, (diff, mean)
# (the same blacks, or a scale without a plain gamma: as they are)
a2, b2 = om.common_floor(scale)(ta, low, dict(ta), low)
assert a2 is low and b2 is low
a3, b3 = om.common_floor({"white": 0.8, "gamma": "srgb"})(ta, low, tb, high)
assert a3 is low and b3 is high
print("ok")
