"""Synthetic check of the seam gains' kinds and limit (mosaic.overlaps' kinds, obs_mosaic.held_level, kinds_under):
a tile kept as taken and a tile redrawn as at the pass's epoch are not measured against each other, however far apart
they read; a mosaic drawn so far is measured only where the tile below is of the new tile's kind; and when every
overlap asks for more than the gain limit, the tiles that overlap nothing keep a gain of 1 instead of being brightened
by the whole limit against the rest (Rhea ISS_162RH_REGMAP001). Without kinds the gains are as before.
Run: python web/test_seam_kinds.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import cv2
import mosaic
import obs_mosaic as om

ok = True


def check(name, cond, detail=None):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail is not None and str(detail) else ""))


rng = np.random.default_rng(7)
H, W = 400, 1000
ground = cv2.GaussianBlur(rng.random((H, W)).astype(np.float32), (0, 0), 5) * 60 + 100


def tile(x0, x1, level):
    f = np.zeros((H, W, 4), np.uint8)
    f[:, x0:x1, :3] = np.clip(ground * level, 0, 255)[:, x0:x1, None]
    f[:, x0:x1, 3] = 255
    return f


# A and C redrawn (kind 1) agree to 5%; B kept as taken (kind 0) reads 70% darker over A
A, B, C = tile(0, 400, 1.0), tile(300, 700, 0.6), tile(350, 1000, 1.05)
frames = [A, B, C]
plain, _ = om.held_level(frames)
sorted_, _ = om.held_level(frames, [1, 0, 1])
check("without kinds the taken tile's 70% drags the gains to the limit",
      np.isclose(plain[:, 0].max(), mosaic.calibrated_gain) or np.isclose(plain[:, 0].min(), 1 / mosaic.calibrated_gain),
      np.round(plain[:, 0], 3))
check("with kinds the taken tile is not measured against the redrawn ones: gain 1", np.isclose(sorted_[1, 0], 1.0),
      np.round(sorted_[:, 0], 3))
ratio = sorted_[2, 0] / sorted_[0, 0]
check("the redrawn tiles still find their 5% between them", abs(ratio * 1.05 - 1) < 0.01, f"{ratio:.4f}")
check("no kinds: match_gains as before", np.array_equal(mosaic.match_gains(frames, 1.1, None, 100),
                                                      mosaic.match_gains(frames, 1.1, None, 100, kinds=None)))

# every overlap asks for more than the limit; one tile overlaps nothing
E, F = tile(0, 500, 1.0), tile(400, 1000, 1.6)
alone = tile(0, 1000, 1.0)
alone[:, :, 3] = 0
alone[:20, :20, 3] = 255   # overlaps nothing
g, _ = om.held_level([E, F, alone])
check("a tile that overlaps nothing keeps a gain of 1 when the others hit the limit", np.isclose(g[2, 0], 1.0),
      np.round(g[:, 0], 3))
check("the overlapping ones split the limit about 1", np.isclose(g[0, 0] * g[1, 0], 1.0, atol=0.02) and g[0, 0] > 1 > g[1, 0],
      np.round(g[:2, 0], 3))

# a mosaic drawn so far, half of it of each kind: the new tile is matched only where it meets its own kind
below = np.zeros((H, W, 4), np.uint8)
below[:, :, :3] = np.clip(ground, 0, 255)[..., None]
below[:, 500:, :3] = np.clip(ground * 0.6, 0, 255)[:, 500:, None]   # the right half kept as taken, darker
below[..., 3] = 255
new = tile(200, 800, 1.05)
kb = np.where(np.arange(0, W, 4) < 500, 1, 0)[None, :].repeat((H + 3) // 4, 0).astype(np.int8)
g_all = mosaic.seams([below, new], 0)[0][1, 0]
g_kind = mosaic.seams([below, new], 0, kinds=(kb, 1))[0][1, 0]
check("over a mosaic, matched only where the tile below is of its kind", abs(g_kind * 1.05 - 1) < 0.01 and abs(g_all * 1.05 - 1) > 0.02,
      f"{g_kind:.4f} (all: {g_all:.4f})")
p = {"k": 1.0}
before = [{"offset": (0, 0), "box": (0, 0, 500, H), "pic": "x"}, {"offset": (0, 0), "box": (500, 0, 500, H)}]
ku = om.kinds_under(p, before, (0, 0, W, H), 0, 0, H, W)
check("kinds_under: the last tile whose box holds each pixel", ku.shape == kb.shape and np.array_equal(ku, kb), ku.shape)
check("kinds_under: -1 where no tile is", (om.kinds_under(p, before[:1], (0, 0, W, H), 0, 0, H, W) == -1).sum() > 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
