"""A small body centred in its frames is not sharpened white (moon colour fixes, 2026-11-05).
Dione in ISS_038DI_ZEROPHASE001_PRIME sits in the middle of every frame, so pass_scale calls the pass "filled" (all
body) and every movie frame and mosaic of it ended in detail(), the local contrast step for a surface that fills the
frames. On a disk 180 px across in a 1024 px movie, detail's neighbourhood (DETAIL_SIGMA of a frame) is half sky, so
every pixel of the disk was raised by about DETAIL times its own brightness and the disk came out flat white
(N1549193148_1, N1549194210_1, N1549192171_1; Rhea in 056RH ZEROPHASE001 the same).
- pass_scale: a small body in the middle of the frames is still "filled" (its tone is unchanged) but has
  "detail" False; a body that fills the frames keeps "detail" True
- sharpens(): a scale's "detail", or its "filled" when it was made without one
- why it matters: detail() turns a mid-grey disk on black sky to white, and leaves a filled frame's level alone
Run: python web/test_small_disk_detail.py"""
import os, sys  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import numpy as np  # noqa: E402
import calibration  # noqa: E402
import stacking  # noqa: E402
import obs_mosaic as om  # noqa: E402


def frames_of(radius_px):
    """Frames of a pass with Dione's disk radius_px (full resolution) in the middle, and the stand-in load_hdr."""
    z = om.RADIUS["DIONE"] / (radius_px * om.IFOV["N"])
    fr = [(f"d{i}", f"N{1549190000 + i}_1", "CL1/CL2", 1000.0 + 20 * i, 651, 0.0, 0.0, z) for i in range(12)]
    yy, xx = np.mgrid[:1024, :1024].astype(np.float32)
    rr = np.hypot(yy - 511.5, xx - 511.5) / radius_px
    face = np.where(rr < 1, 0.8 + 0.1 * np.cos(xx / 9), 0).astype(np.float32)

    def load_hdr(path, window=120, max_frames=8, valid=False):
        noise = np.random.default_rng(int(path[1:]))
        return None, (0.0005 + 0.0002 * noise.standard_normal((1024, 1024))).astype(np.float32) + face, 1
    return fr, load_hdr


real = stacking.load_hdr
with calibration.looking("balanced"):
    for radius, want in ((90, False), (2000, True)):
        fr, stacking.load_hdr = frames_of(radius)
        u = {"key": ("DIONE", f"OBSD{radius}", "N", 0), "frames": fr, "z": fr[0][7], "movie": True}
        s = om.pass_scale(fr, u)
        assert s["filled"] and s["detail"] is want and om.sharpens(s) is want, (radius, s)
        print(f"disk {2 * radius} px across, centred: filled {s['filled']}, detail {s['detail']}")
stacking.load_hdr = real

assert om.sharpens({"filled": True}) and not om.sharpens({"filled": False}) and not om.sharpens({"filled": True, "detail": False})
print("sharpens: a scale without \"detail\" keeps its \"filled\"")

# detail() on a mid-grey disk 180 px across on black sky, as a 1024 px movie frame draws Dione, and on a frame it fills
sigma = om.DETAIL_SIGMA * om.FRAME * 1.0
yy, xx = np.mgrid[:1024, :1024]
disk = np.hypot(yy - 511.5, xx - 511.5) < 90
small = np.zeros((1024, 1024, 4), np.uint8)
small[..., 3] = 255
small[disk, :3] = 170
full = np.full((1024, 1024, 4), 170, np.uint8)
full[..., 3] = 255
with calibration.looking("balanced"):
    a, b = om.detail(small, sigma), om.detail(full, sigma)
assert np.median(a[disk, 1]) >= 250, np.median(a[disk, 1])
assert abs(int(np.median(b[..., 1])) - 170) <= 1
print(f"detail(): a 170 disk on sky -> {np.median(a[disk, 1]):.0f} (flat white, why a small disk is left out); "
      f"a frame of 170 -> {np.median(b[..., 1]):.0f}")
print("ok")
