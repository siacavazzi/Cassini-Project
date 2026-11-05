"""A colour set's channel is registered when SPICE's pointing jumps past REGISTER_MAX between its frames
(obs_mosaic._register, moon colour fixes 2026-11-05). In Dione's 038DI ZEROPHASE001 SPICE puts consecutive frames 19 s
apart 20 to 45 px apart (N1549196942_1 sits 42 px from the frames either side of it): UV3's 38 px match was believed,
GRN's 44 px match was not (REGISTER_MAX, 41 px), so one set's channels were drawn at two places, three Diones in a
column (N1549197025_1). A match past REGISTER_MAX, up to REGISTER_BODY_MAX, is believed when the lit area's centroid
of the two tiles moves with it (within REGISTER_AGREE); otherwise SPICE's place is kept, as before.
Synthetic tiles: a cratered disk 180 px across, the whole body inside both tiles.
Run: python web/test_register_far.py"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import obs_mosaic  # noqa: E402

S = 900


def disk(cx, cy, level, other=None):
    """The body at (cx, cy) in an S px tile; other: (x, y) of a second lit body of the same size in this tile only."""
    yy, xx = np.mgrid[:S, :S].astype(np.float32)
    im = np.clip(90 - np.hypot(xx - cx, yy - cy), 0, 1) * level
    for a, b, rad in ((-20, -15, 14), (25, 10, 9), (-5, 30, 11)):
        im[np.hypot(xx - cx - a, yy - cy - b) < rad] *= 0.6
    if other:
        im += np.clip(90 - np.hypot(xx - other[0], yy - other[1]), 0, 1) * level
    rgba = np.zeros((S, S, 4), np.uint8)
    rgba[..., :3] = np.clip(im, 0, 255).astype(np.uint8)[..., None]
    rgba[..., 3] = 255
    return rgba


cache = tempfile.mkdtemp()
scale = {"t": 1}
u = {"key": ["DIONE", "ISS_TEST", "N", 0], "z": 100000.0,
     "frames": [("a", "N1549196968_1", "UV3", 0.0, 338, 10.0, 10.0, 100000.0),
                ("b", "N1549196987_1", "GRN", 19.0, 568, 11.0, 9.0, 100000.0)]}
tiles = obs_mosaic._tiles(u, cache, scale)
os.makedirs(tiles)
Image.fromarray(disk(450, 450, 200)).save(os.path.join(tiles, "0.png"))
q = {"n": 0, "id": "N1549196968_1", "filter": "UV3", "offset": [100.0, 50.0], "box": [-S / 2, -S / 2, S, S]}
obs_mosaic.tile = lambda u_, j, cache_, scale_=None: q
assert obs_mosaic.REGISTER_MAX * obs_mosaic.FRAME < 44 < obs_mosaic.REGISTER_BODY_MAX * obs_mosaic.FRAME


def register(true, other=None):
    """The GRN tile, its body (true) px from where SPICE's place puts it on the UV3 tile's: (out, what is left)."""
    crop = disk(450 + true[0], 450 + true[1], 230, other)
    out = {"n": 1, "id": "N1549196987_1", "filter": "GRN", "offset": [100.0, 50.0], "box": [-S / 2, -S / 2, S, S]}
    obs_mosaic._register(u, 1, out, crop, cache, scale)
    return out, np.array(out["offset"]) + true - np.array(q["offset"])


# SPICE 44 px off (past REGISTER_MAX): believed, the centroid moves with the match
out, left = register((1.6, -43.9))
print("44 px off:", out["registered"], "left", left.round(2))
assert "kept" not in out["registered"] and "centroid agrees" in out["registered"]["how"] and np.abs(left).max() < 0.5, out
# 3.4 px off (under REGISTER_MAX): as before, no centroid asked for
out, left = register((3.4, -2.2))
assert "centroid" not in out["registered"]["how"] and np.abs(left).max() < 0.5, out
# 44 px off, but another lit body in the GRN tile pulls its centroid away: SPICE's place kept, as before
out, left = register((1.6, -43.9), other=(150, 150))
print("44 px off, a second body in one tile:", out["registered"])
assert out["registered"].get("kept") == "SPICE's place" and out["offset"] == [100.0, 50.0], out
# 130 px off: past REGISTER_BODY_MAX, kept
out, left = register((0.0, 130.0))
print("130 px off:", out.get("registered"))
assert out["offset"] == [100.0, 50.0], out
print("ok")
