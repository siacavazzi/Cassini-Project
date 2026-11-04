"""Synthetic check of seams measured relit (obs_mosaic.lights, over_light, mosaic.overlaps' light): two tiles of one
surface, taken while the sun moved across it, the second also 8% too bright (its own exposure error). Measured as
drawn, the seam gains take the change of lighting in their overlap for an error of the whole tile; measured relit to
one lighting they find the 15% and nothing else. The gains still apply to the tiles as taken. The relighting (from the
Minnaert model, reproject.lighting) is 1 where the views agree and off the body, the ratio of the two Minnaert
brightnesses on it, and left out (NaN) where the sun is low; a tile without a view is not relit.
Run: python web/test_light_seams.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import cv2
import mosaic
import reproject as rp
import obs_mosaic as om

ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))


# ---- a sphere seen from -x (its sky plane: east = -y, north = +z), the sun in the x-y plane on the camera's side ----
def sunward(deg):
    a = np.radians(deg)
    return {"c": np.array([5000.0, 0, 0]), "ch": np.array([1.0, 0, 0]), "north": np.array([0, 0, 1.0]),
            "east": np.cross([0, 0, 1.0], [1.0, 0, 0]), "rot": np.eye(3), "radii": np.array([200.0] * 3),
            "sun": np.array([-np.cos(a), np.sin(a), 0])}


p = {"k": 1.0, "display_scale": {"gamma": 1.0}}
rect = (-256, -256, 512, 512)
epoch, later = sunward(60), sunward(64)
lp = {"epoch": epoch, "km_px": 1.0, "views": {"a": epoch, "b": later, "c": None}}
same, moved, none = om._relight(rp, lp, p, rect, [{"id": "a"}, {"id": "b"}, {"id": "c"}], 0, 0, 512, 512)
check("relighting has the 1/4 scale shape", same.shape == (128, 128), same.shape)
check("the epoch's own tile: 1 wherever measured", np.allclose(same[np.isfinite(same)], 1.0))
check("off the body: 1", same[0, 0] == 1.0 and moved[0, 0] == 1.0)
check("a tile with no view is not relit", none is None)
# the body's centre (sky 0, 0) is 1/4-scale pixel (64, 64); there the ground faces the camera (-x): mu0 = cos(sun angle)
want = (np.cos(np.radians(60)) / np.cos(np.radians(64))) ** rp.minnaert_k
check("on the body: the Minnaert ratio, epoch over the tile's own", abs(moved[64, 64] - want) < 1e-3,
      f"{moved[64, 64]:.4f} vs {want:.4f}")
# the terminator is where the sun is 90 degrees off the normal; there nothing is measured
check("near the terminator: left out", np.isnan(moved).sum() > 0 and np.isnan(same).sum() > 0)

# ---- the seam gains: two overlapping tiles of a textured surface under that lighting ----
rng = np.random.default_rng(5)
H = W = 512
albedo = cv2.GaussianBlur(rng.random((H, W)).astype(np.float32), (0, 0), 6) * 0.6 + 0.4
gy, gx = np.mgrid[0:H, 0:W].astype(np.float64)
pts, hit = rp.sky_to_surface(epoch, rect[0] + gx, rect[1] + gy, 1.0)
b_e, mu0_e, _ = rp.sky_lighting(epoch, pts)
b_l, mu0_l, _ = rp.sky_lighting(later, pts)


def tile(b, x0, x1, gain):
    f = np.zeros((H, W, 4), np.uint8)
    lit = np.clip(albedo * b * 200 * gain, 0, 255)
    f[:, x0:x1, :3] = np.where(hit, lit, 0)[:, x0:x1, None]
    f[:, x0:x1, 3] = 255
    return f


frames = [tile(b_e, 0, 300, 1.0), tile(b_l, 200, 512, 1.08)]
light = [om._relight(rp, lp, p, rect, [t], 0, 0, H, W)[0] for t in ({"id": "a"}, {"id": "b"})]
g0, _ = om.held_level(frames)
g1, _ = om.held_level(frames, light)
ratio0, ratio1 = g1[1, 0] / g1[0, 0], g0[1, 0] / g0[0, 0]
check("measured relit, the gains find the tile's own 8% and nothing else", abs(ratio0 * 1.08 - 1) < 0.01,
      f"gain ratio {ratio0:.4f}, want {1 / 1.08:.4f}")
check("measured as drawn, the lighting's change is taken for an error", abs(ratio1 * 1.08 - 1) > 0.02,
      f"gain ratio {ratio1:.4f}")
check("no light: as before", np.array_equal(om.held_level(frames, None)[0], g0))
pinned = mosaic.seams(frames, 0, light=light)[0][1, 0]
check("mosaic.seams takes the light too", abs(pinned * 1.08 - 1) < 0.01, f"{pinned:.4f}")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
