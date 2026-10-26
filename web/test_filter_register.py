"""C8: the filters of a mosaic pointing registered to each other (obs_mosaic._register): a tile whose SPICE place is
a few pixels off lands on its pointing's first tile, through image_correction.align_with_masks. Synthetic tiles: a
disk with a sharp limb, the second filter darker and placed (3.4, -2.2) px off. Run: python web/test_filter_register.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import tempfile
import numpy as np
import cv2
from PIL import Image
import obs_mosaic  # noqa: E402

S = 900


def disk(cx, cy, level):
    yy, xx = np.mgrid[:S, :S].astype(np.float32)
    r = np.hypot(xx - cx, yy - cy)
    im = np.clip(330 - r, 0, 1) * level
    # craters, so phase correlation has texture as well as a limb
    for a, b, rad in ((420, 400, 30), (500, 520, 18), (380, 520, 24)):
        im[np.hypot(xx - a - (cx - 450), yy - b - (cy - 450)) < rad] *= 0.6
    rgba = np.zeros((S, S, 4), np.uint8)
    rgba[..., :3] = np.clip(im, 0, 255).astype(np.uint8)[..., None]
    rgba[..., 3] = 255
    return rgba


cache = tempfile.mkdtemp()
scale = {"t": 1}
u = {"key": ["DIONE", "ISS_TEST", "N", 0], "z": 100000.0,
     "frames": [("a", "N1500000000_1", "RED", 0.0, 650, 10.0, 10.0, 100000.0),
                ("b", "N1500000020_1", "GRN", 20.0, 568, 11.0, 9.0, 100000.0),
                ("c", "N1500000900_1", "GRN", 900.0, 568, 11.0, 9.0, 100000.0)]}
tiles = obs_mosaic._tiles(u, cache, scale)
os.makedirs(tiles)
ref = disk(450, 450, 220)
Image.fromarray(ref).save(os.path.join(tiles, "0.png"))
q = {"n": 0, "id": "N1500000000_1", "filter": "RED", "offset": [100.0, 50.0], "box": [-S / 2, -S / 2, S, S]}
obs_mosaic.tile = lambda u_, j, cache_, scale_=None: q
for true in ((3.4, -2.2), (-7.0, 5.5), (0.0, 0.0)):
    # the GRN frame's own picture: the body at (450 + true) in its crop, but SPICE put the crop where the body is at 450
    crop = disk(450 + true[0], 450 + true[1], 150)
    out = {"n": 1, "id": "N1500000020_1", "filter": "GRN", "offset": [100.25, 50.6], "box": [-S / 2, -S / 2, S, S]}
    obs_mosaic._register(u, 1, out, crop, cache, scale)
    # where the GRN tile now puts the body, against the RED tile's body
    body_grn = np.array(out["offset"]) + np.array(out["box"][:2]) + 450 + np.array(true)
    body_red = np.array(q["offset"]) + np.array(q["box"][:2]) + 450
    err = body_grn - body_red
    print("true", true, "registered", out.get("registered"), "left", err.round(2))
    assert np.abs(err).max() < 0.35, err
# the next pointing's frame (900 s later) is not registered to the first
out = {"n": 2, "id": "N1500000900_1", "filter": "GRN", "offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]}
obs_mosaic._register(u, 2, out, disk(460, 450, 150), cache, scale)
assert "registered" not in out and out["offset"] == [0.0, 0.0]
assert obs_mosaic._register_to(u, 0) is None and obs_mosaic._register_to(u, 1) == 0
print("ok")

# a registered pass still moves by exactly what tune= asks (Cassini Studio, tuned_layout): the move is laid over the
# registered place, and the filters of the pointing keep the registration between them
reg = {"n": 1, "id": "N1500000020_1", "filter": "GRN", "offset": [97.0, 52.0], "spice_offset": [100.25, 50.6],
       "registered": {"to": "N1500000000_1", "shift": [3.25, -1.4]}, "box": [-S / 2, -S / 2, S, S]}
rect = [-1000.0, -800.0, 2000.0, 1600.0]
made = (None, [q, reg], rect, {"RED": 1, "GRN": 1}, ["RED", "GRN"], "name")
mapped = {"pointings": [{"n": 0, "tiles": [0, 1]}]}
_, moved, _, _, _, name = obs_mosaic.tuned_layout(made, mapped, {0: (0.01, -0.02)}, set())
for before, after in zip([q, reg], moved):
    d = np.subtract(after["offset"], before["offset"])
    assert np.allclose(d, (0.01 * rect[2], -0.02 * rect[3])), d
assert np.allclose(np.subtract(moved[1]["offset"], moved[0]["offset"]), np.subtract(reg["offset"], q["offset"]))
assert name.startswith("name-tune")
print("tuned: moved by exactly the tune; ok")
