"""Check that the narrow-angle camera's pixel scale (obs_mosaic.IFOV["N"]) is the instrument kernel's: its pixel size
over its focal length, the scale bootleg_autonav.pixel_scale places a body's center with (the geometry cache's
target.scale for the camera: 166,953.33 pixels per unit of tan(angle)), so a body's radius in pixels and its center
are on one scale. With the kernels unpacked (CASSINI_SPICE_CACHE) the kernel's own text is read too.
The wide-angle camera's is not the kernel's (200.77 mm) on purpose: its frames are drawn after CISSCAL's geometric
correction, a pinhole camera of geometric_correction.F_LINEAR (200.956 mm), and bootleg_autonav.linear_ratio grows
SPICE's shifts to that scale, so IFOV["W"] is the corrected frame's.
Run: python web/test_nac_pixel_scale.py"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
sys.path.insert(0, os.path.join(HERE, ".."))
import obs_mosaic  # noqa: E402

per_px = obs_mosaic.IFOV["N"]
assert abs(1 / per_px - 166953.33) < 0.01, 1 / per_px          # as bootleg_autonav.pixel_scale gives it
assert abs(per_px - 5.98970e-6) < 1e-11, per_px
# a disk 1,000 px in radius on the kernel's scale: the nominal 6.0 microradians drew it 1.7 px small
assert 1.6 < 1000 * (1 - per_px / 6.0e-6) < 1.8
import geometric_correction as gc  # noqa: E402
assert obs_mosaic.IFOV["W"] == gc.PIXEL_MM / gc.F_LINEAR, obs_mosaic.IFOV["W"]   # 59.71 microradians, as drawn
assert abs(1 / obs_mosaic.IFOV["W"] - gc.LINEAR_SCALE) < 1e-6
read = 0
cache = os.environ.get("CASSINI_SPICE_CACHE")
for path in glob.glob(os.path.join(cache, "**", "cas_iss_v*.ti"), recursive=True) if cache else []:
    text = open(path, errors="replace").read()
    focal = float(re.search(r"INS-82360_FOCAL_LENGTH\s*=\s*\(\s*([\d.]+)", text).group(1))    # mm
    pixel = float(re.search(r"INS-82360_PIXEL_SIZE\s*=\s*\(\s*([\d.]+)", text).group(1))      # microns
    assert abs(per_px - pixel / 1000 / focal) < 1e-15, (path, focal, pixel)
    read += 1
print(f"narrow-angle pixel {per_px * 1e6:.4f} microradians ok" + (f", as {read} kernel file(s) have it" if read else " (no kernel text at hand)"))
