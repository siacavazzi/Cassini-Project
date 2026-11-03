"""PR12 (tile placement): a mosaic's tiles redrawn as at the pass's epoch (obs_mosaic.surface_pictures) keep the
ground the redrawing moves past their own box (surface_field, surface_redrawn), so two neighboring panels whose
frames overlap on the sky still overlap on the surface. Drawn inside the box as taken (the form replaced), that
ground was cut off and the strip it left lay empty: the curved black slots inside the disks of Enceladus
ISS_004EN_REGEO002 and Rhea ISS_162RH_REGMAP001. Made-up SPICE: a moon turning a degree a minute (test_sky_field's
view); two panels side by side on its disk, taken 2 and 3 minutes after the epoch, their frames overlapping by
OVERLAP px on the sky. Run: python web/test_surface_reach.py"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402
import reproject as rp  # noqa: E402

R, D, KM = 500.0, 100000.0, 0.5   # the moon's radius and distance (km), km per reference pixel: its disk 1000 px across
SIDE = 400                        # a tile's side, px
OVERLAP = 8                       # px the two frames share on the sky


def view(turn):
    c = np.array([D, 0.0, 0.0])
    a = math.radians(turn)
    rot = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1.0]])
    s = np.array([-1.0, 0.0, 0.0])
    return {"c": c, "ch": c / D, "north": np.array([0.0, 0.0, 1.0]), "east": np.cross([0.0, 0.0, 1.0], c / D),
            "rot": rot, "radii": np.array([R, R, R]), "sun": rot @ s}


def tile(x):
    """A panel whose frame's middle is x px east of the disk's middle, a whole opaque frame (alpha 255)."""
    picture = np.full((SIDE, SIDE, 4), 180, np.uint8)
    picture[..., 3] = 255
    return {"offset": [float(x), 0.0], "box": [-SIDE / 2, -SIDE / 2, SIDE, SIDE]}, picture


def before(t, picture, ep, vw):
    """The form replaced: the field over the tile's own box, the picture redrawn inside it."""
    h, w = picture.shape[:2]
    gy, gx = np.mgrid[0:h + om.SURFACE_STEP:om.SURFACE_STEP, 0:w + om.SURFACE_STEP:om.SURFACE_STEP].astype(np.float64)
    x0, y0 = t["offset"][0] + t["box"][0], t["offset"][1] + t["box"][1]
    dx, dy, wt = rp.sky_field(ep, vw, gx + x0, gy + y0, KM)
    return rp.warp_sky(picture, dx, dy, wt, om.SURFACE_STEP), list(t["box"])


def after(t, picture, ep, vw):
    dx, dy, wt = om.surface_field(rp, ep, vw, picture.shape[:2], t, KM)
    return om.surface_redrawn(rp, picture, t, dx, dy, wt)


def cover(drawn):
    """The sky (reference px about the disk's middle, 1400 px square) every drawn tile [(t, picture, box)] covers."""
    canvas = np.zeros((1400, 1400), bool)
    for t, picture, box in drawn:
        left = int(round(t["offset"][0] + box[0])) + 700
        top = int(round(t["offset"][1] + box[1])) + 700
        h, w = picture.shape[:2]
        canvas[top:top + h, left:left + w] |= picture[..., 3] > 128
    return canvas


ep = view(0.0)
a, pa = tile(-(SIDE - OVERLAP) / 2)
b, pb = tile((SIDE - OVERLAP) / 2)
yy, xx = np.mgrid[-700:700, -700:700]
# the disk well inside its limb, round where the two panels meet (the shift fades out toward the limb; past the
# panels' outer edges lies ground neither saw)
inner = (np.hypot(xx, yy) < 0.6 * R / KM) & (np.abs(yy) < SIDE / 2 - 40) & (np.abs(xx) < SIDE / 4)
ok = True
for name, draw in (("before", before), ("after", after)):
    drawn = [(a, *draw(a, pa, ep, view(2.0))), (b, *draw(b, pb, ep, view(3.0)))]
    hole = inner & ~cover(drawn)
    cols = np.flatnonzero(hole.any(axis=0))
    print(f"{name}: {int(hole.sum())} px of the disk left empty between the panels"
          + (f", columns {cols.min() - 700} to {cols.max() - 700}" if len(cols) else ""))
    if name == "before":
        assert hole.sum() > 1000, "the made-up pass shows the slot (the form replaced cut the moved ground off)"
    else:
        assert hole.sum() == 0, "the ground each panel moves past its box is kept, so the panels still meet"
        # and the picture grew only as far as its ground moved, its box still about the frame's middle
        for t, picture, box in drawn:
            assert picture.shape[:2] == (box[3], box[2]) and box[2] <= SIDE + 2 * om.SURFACE_REACH, (box, picture.shape)
            assert box[0] < t["box"][0] or box[0] + box[2] > t["box"][0] + t["box"][2], box
        # a tile nothing on it moves (the epoch's own) comes back as it was
        same, box = after(a, pa, ep, ep)
        assert box == a["box"] and np.array_equal(same, pa), box
print("surface reach: ok")
