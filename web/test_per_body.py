"""
color_image.per_body (fix plan PR 15): a set whose bodies move against each other between the filters (a moon crossing
Titan) is aligned on each body on its own, instead of the whole set drawn grey ("moved").

A synthetic set: a big soft far disk ("TITAN") that moves 20 px a filter, and a small sharp near disk ("TETHYS") in front
of it that moves 2 px a filter, as SPICE would give them (color_image._frame_bodies stubbed, its places off by a few px
as real pointing is). Checks:
1. grey_plan calls the set "moved" when it is aligned on the near body (today's grey set).
2. per_body finds each body's own move, and in the composite both disks line up in every channel.
3. The far body that the near one hid in some filter but not in the reference is filled with its own color there
   (calibration.fill_saturated with the ratio round it), not grey.
4. A body whose match fails (the matcher places nothing) gives {"failed": ...}, so load_aligned draws the set grey as before.
5. A set with one body is not per_body's (None).
Run: python web/test_per_body.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np  # noqa: E402
import color_image as ci  # noqa: E402
import image_correction as ic  # noqa: E402

N = 1024
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
FAR = dict(x=470.0, y=650.0, r=134.0)
NEAR = dict(x=505.0, y=512.0, r=48.0)
FAR_STEP, NEAR_STEP = 20.0, 2.0   # px a filter, along x
DRIFT = (3.0, -2.0)               # the camera's own drift a filter (both bodies)
LEVEL = [0.40, 0.30, 0.15]        # the far body's brightness in each channel (an orange Titan)


def soft(x, y, r, edge):
    return np.clip((r - np.hypot(xx - x, yy - y)) / edge + 0.5, 0, 1)


def frame(j):
    """channel j (0 is the reference's -1, ...): the far body, a soft disk with a limb darkening, the near one over it"""
    k = j - 1
    fx, fy = FAR["x"] + k * (FAR_STEP + DRIFT[0]), FAR["y"] + k * DRIFT[1]
    nx, ny = NEAR["x"] + k * (NEAR_STEP + DRIFT[0]), NEAR["y"] + k * DRIFT[1]
    far = soft(fx, fy, FAR["r"], 6.0) * LEVEL[j] * (0.7 + 0.3 * np.clip(1 - np.hypot(xx - fx, yy - fy) / FAR["r"], 0, 1))
    near = soft(nx, ny, NEAR["r"], 1.0)
    # the near body's craters: detail for its match
    texture = 0.85 + 0.15 * np.sin((xx - nx) / 5.0) * np.cos((yy - ny) / 7.0)
    return (far * (1 - near) + near * 0.9 * texture).astype(np.float32)


chans = [frame(j) for j in range(3)]
guide = [np.repeat(np.clip(c / 0.9 * 255, 0, 255).astype(np.uint8)[..., None], 3, axis=2) for c in chans]
masks = [np.ones((N, N), bool) for _ in range(3)]
ref = 1


class Lbl:
    def __init__(self, j):
        self.j = j
        self.info = {"TARGET_NAME": "TETHYS", "INSTRUMENT_ID": "ISSNA"}


def stub(off=(4.0, -3.0), bodies=("TITAN", "TETHYS")):
    """_frame_bodies as SPICE gives it: each body's place without the camera's drift, the whole off by off"""
    def fb(lbl):
        k = lbl.j - 1
        out = []
        if "TITAN" in bodies:
            out.append(("TITAN", FAR["x"] + k * FAR_STEP + off[0], FAR["y"] + off[1], FAR["r"], 3.2e6))
        if "TETHYS" in bodies:
            out.append(("TETHYS", NEAR["x"] + k * NEAR_STEP + off[0], NEAR["y"] + off[1], NEAR["r"], 1.86e6))
        return out
    return fb


lbls = [Lbl(j) for j in range(3)]

# 1. aligned on the near body (as the whole-set match does: its sharp limb), the far body moved: grey
on_near = [None if j == ref else ((j - 1) * (NEAR_STEP + DRIFT[0]), (j - 1) * DRIFT[1]) for j in range(3)]
aligned_near, _ = ic.align_with_masks(list(chans), [m.copy() for m in masks], ref, use=on_near)
why, region = ci.grey_plan(["phase", "reference", "phase"], aligned_near, ref)
assert why == "moved", why
print("aligned on the near body: grey_plan says", why, "whole" if region is None else "part")

# 2. per body
ci._frame_bodies = stub()
got = ci.per_body(lbls, ref, list(guide), list(chans), [m.copy() for m in masks])
assert isinstance(got, tuple), got
out, omasks, region, rep = got
rep.pop("_full")
print("per_body:", rep)
for name, move in (("TITAN", FAR_STEP), ("TETHYS", NEAR_STEP)):
    for j in (0, 2):
        want = ((j - 1) * (move + DRIFT[0]), (j - 1) * DRIFT[1])
        s = rep["shifts"][name][j]
        assert abs(s[0] - want[0]) <= 1.0 and abs(s[1] - want[1]) <= 1.0, (name, j, s, want)


def spread(disk, inset):
    """the largest difference of each channel's shape (scaled to the reference) inside a disk, inset px from its edge"""
    d = np.hypot(xx - disk["x"], yy - disk["y"]) <= disk["r"] - inset
    r = out[ref][d]
    return max(float(np.abs(out[j][d] / max(float(np.median(out[j][d])), 1e-6) - r / float(np.median(r))).max())
               for j in (0, 2))


# both disks line up: inside the near disk, and on the far disk away from the near one and its old places
assert spread(NEAR, 3) < 0.05, spread(NEAR, 3)
d = (np.hypot(xx - FAR["x"], yy - FAR["y"]) <= FAR["r"] - 10) & (np.hypot(xx - NEAR["x"], yy - NEAR["y"]) > NEAR["r"] + 40)
for j in (0, 2):
    a, b = out[j][d] / LEVEL[j], out[ref][d] / LEVEL[ref]
    assert float(np.abs(a - b).max()) < 0.05, (j, float(np.abs(a - b).max()))
print("both bodies line up in every channel")

# 3. where the near body hid the far one in another filter (not in the reference): filled with the far body's own color
#    round it, not grey (Sam 2026-11-06: grey crescents round the transiting moon); off the far body, in the sky, a
#    filter's copy of the near body's limb may still be grey
on_far = np.hypot(xx - FAR["x"], yy - FAR["y"]) <= FAR["r"] - 30   # (the region rule's soft edge may reach its limb)
assert region is None or float(region[on_far].max()) < 0.05, float(region[on_far].max())
assert rep.get("filled", 0) > 0, rep
for j in (0, 2):
    # (just past the near disk, on the side the near body sat in channel j once it is aligned on the far body, on
    # the far disk)
    side = 1 if j == 0 else -1
    beside = (np.abs(yy - (NEAR["y"] + 36)) < 2) & (np.abs(xx - (NEAR["x"] + side * 35)) < 2)
    got_ratio = float(np.median(out[j][beside] / np.maximum(out[ref][beside], 1e-6)))
    want = LEVEL[j] / LEVEL[ref]
    assert abs(got_ratio - want) < 0.1 * want, (j, got_ratio, want)
print("the far body hidden in some filters is filled in its own color:", rep["filled"])

# 4. a match that fails (the matcher places nothing): today's grey
real = ic.align_with_masks


def nothing(imgs, masks, ref=0, report=None, found=None, use=None, guess=None, within=None):
    for i in range(len(imgs)):
        if report is not None:
            report.append("reference" if i == ref else "not aligned")
        if found is not None:
            found.append(None)
    return imgs, masks


ic.align_with_masks = nothing
failed = ci.per_body(lbls, ref, list(guide), list(chans), [m.copy() for m in masks])
ic.align_with_masks = real
assert isinstance(failed, dict) and "failed" in failed, failed
print("a failed match:", failed)

# 5. one body: not per_body's
ci._frame_bodies = stub(bodies=("TETHYS",))
assert ci.per_body(lbls, ref, list(guide), list(chans), [m.copy() for m in masks]) is None
print("ok")
