"""The flat field step (flat_field.py, calibration.calibrate's "flat" step): a synthetic CISSCAL folder with a flat that
has a dark dust ring, dust ring maps for two epochs and a mottle map. A frame of an evenly lit scene, taken through
that flat, comes out even again; with the step off, or without the maps, the ring stays. Also the choice of maps by
image number (the dust ring maps hold from their epoch on) and the mottle strength by filter.
Run: python web/test_flat_field.py"""
import os
import sys
import tempfile
import numpy as np

root = tempfile.mkdtemp()
os.environ["CASSINI_CISSCAL"] = root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibration as cal  # noqa: E402
import flat_field as ff  # noqa: E402

cal.ds._lut8 = True                                     # the lean archive: stored codes, nothing guessed


def write_cube(path, a, tile=128):
    """An ISIS 3 cube of floats, tiled, as the USGS mirror has them."""
    lines, samples = a.shape
    head = (f"Object = IsisCube\n  Object = Core\n    StartByte   = 65537\n    Format      = Tile\n"
            f"    TileSamples = {tile}\n    TileLines   = {tile}\n    Group = Dimensions\n      Samples = {samples}\n"
            f"      Lines   = {lines}\n      Bands   = 1\n    End_Group\n    Group = Pixels\n      Type       = Real\n"
            f"      ByteOrder  = Lsb\n      Base       = 0.0\n      Multiplier = 1.0\n    End_Group\n  End_Object\n"
            f"End_Object\nEnd\n").encode().ljust(65536, b" ")
    tiles = a.astype("<f4").reshape(lines // tile, tile, samples // tile, tile).transpose(0, 2, 1, 3)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(head + tiles.tobytes())


yy, xx = np.mgrid[:1024, :1024]
ring = np.abs(np.hypot(yy - 388, xx - 887) - 12) < 5            # a dust ring
slope_flat = np.where(ring, 0.88, 1.0).astype(np.float32)        # a pixel in the ring sees 12% less light
slope_flat[:, ::2] *= 1.01                                        # and a column pattern
write_cube(f"{root}/slope/flat/flat113.full.cub", slope_flat)
write_cube(f"{root}/slope/flat/flat113.sum2.cub", slope_flat.reshape(512, 2, 512, 2).mean(axis=(1, 3)))
os.makedirs(f"{root}/slope", exist_ok=True)
open(f"{root}/slope/slope_db_2.tab", "w").write("""PDS_VERSION_ID = PDS3
END
\\begindata
'ISSNA' m10     'CL1'   'CB3'       2     ON     285     SLOPE189.IMG
'ISSNA' p5      'CL1'   'CB3'       2     ON     378     SLOPE113.IMG
""")
late_ring = np.where(np.hypot(yy - 700, xx - 300) < 30, 1.05, 1.0)  # a ring that settled on in 2005
write_cube(f"{root}/dustring/nac_dustring_venus.full.cub", np.ones((1024, 1024)))
write_cube(f"{root}/dustring/nac_dustring_1308947228.full.cub", np.ones((1024, 1024)))
write_cube(f"{root}/dustring/nac_dustring_1502443470.full.cub", late_ring)
write_cube(f"{root}/dustring/nac_mottle_1444733393.full.cub", np.zeros((1024, 1024)))

INFO = {"INSTRUMENT_ID": "ISSNA", "FILTER_NAME": '("CL1","CB3")', "GAIN_MODE_ID": "29 ELECTRONS PER DN",
        "INSTRUMENT_MODE_ID": "FULL", "EXPOSURE_DURATION": "320.0", "DATA_CONVERSION_TYPE": "12BIT",
        "BIAS_STRIP_MEAN": "12.0", "SHUTTER_STATE_ID": "ENABLED", "OPTICS_TEMPERATURE": "(0.627,1.9)",
        "ANTIBLOOMING_STATE_FLAG": "ON", "TARGET_NAME": "TITAN", "IMAGE_TIME": "2005-298T03:00:00.000",
        "IMAGE_NUMBER": "1508671907"}

# the maps a frame takes
assert ff.temperature_name(INFO) == "p5" and ff.flat_name(INFO) == "flat113"
assert ff.dust_name({**INFO, "IMAGE_NUMBER": "1290000000"}) == "nac_dustring_venus"        # before the first epoch
assert ff.dust_name({**INFO, "IMAGE_NUMBER": "1400000000"}) == "nac_dustring_1308947228"
assert ff.dust_name(INFO) == "nac_dustring_1502443470"                                     # the latest before it
assert ff.flat_name({**INFO, "OPTICS_TEMPERATURE": "(-12.0,1.9)"}) == "flat189"
assert ff.flat_name({**INFO, "FILTER_NAME": '("UV1","UV3")'}) is None
assert abs(ff.mottle_strength(INFO) - 0.608) < 1e-9                                        # CB3: cisscal's table
assert abs(ff.mottle_strength({**INFO, "FILTER_NAME": '("CL1","CL2")'}) - 0.763) < 1e-9
assert abs(ff.mottle_strength({**INFO, "FILTER_NAME": '("RED","CL2")'}) - 0.843) < 1e-9
assert ff.correction({**INFO, "SHUTTER_STATE_ID": "DISABLED"}) is None
print("maps ok")

# an evenly lit Titan through the flat (and the late ring): the camera's DN, stored as the nearest LUT code
dn = 1800.0 * slope_flat / late_ring + 12.0
mids = (cal.LUT[:-1] + cal.LUT[1:]) / 2
codes = np.searchsorted(mids, dn).astype(np.uint8)


def ring_contrast(iof):
    inside = iof[ring & (xx > 880)].mean()
    around = iof[(np.abs(np.hypot(yy - 388, xx - 887) - 40) < 5)].mean()
    return inside / around - 1


raw = cal.calibrate(codes, INFO)
with cal.stepping("flat"):
    off = cal.calibrate(codes, INFO)
print("ring contrast: flat on", round(ring_contrast(raw), 4), "flat off", round(ring_contrast(off), 4))
assert abs(ring_contrast(off) + 0.12) < 0.02                      # off: the ring is 12% dark
assert abs(ring_contrast(raw)) < 0.01                             # on: gone, to the 8-bit codes' step
late = np.hypot(yy - 700, xx - 300) < 25
assert abs(raw[late].mean() / raw[300:400, 100:200].mean() - 1) < 0.01   # the 2005 ring too
assert raw[:, 200:600:2].mean() / raw[:, 201:601:2].mean() - 1 < 0.003   # and the columns
assert cal.variant() == "" and "flat" in cal.STEPS
with cal.stepping("flat"):
    assert cal.variant() == "-off-flat"

# a resized image (label.resize_image) gets the map resized to it; a summed frame its own map
half = cal.calibrate(codes[::2, ::2], {**INFO, "INSTRUMENT_MODE_ID": "SUM2"})
r2 = ring[::2, ::2] & (xx[::2, ::2] > 880)
assert half.shape == (512, 512) and abs(half[r2].mean() / half[180:200, 400:420].mean() - 1) < 0.02
resized = cal.calibrate(codes, {**INFO, "INSTRUMENT_MODE_ID": "SUM2"})   # a summed frame shown at 1024
assert resized.shape == (1024, 1024) and abs(ring_contrast(resized)) < 0.03

# a flat map that is not one (CISSCAL's own flat129, the NAC UV2 flat: 20 everywhere at full size, 1e-11 to 4e12
# summed) is left out with a warning instead of turning the frame into blobs on black
assert ff.usable_flat(slope_flat) and not ff.usable_flat(np.full((256, 256), 20.0, np.float32))
broken = np.exp(np.random.default_rng(1).normal(0, 8, (256, 256))).astype(np.float32)
assert not ff.usable_flat(broken)
write_cube(f"{root}/slope/flat/flat113.sum4.cub", broken)
quarter = {**INFO, "INSTRUMENT_MODE_ID": "SUM4"}
assert ff.correction(quarter) is None                              # its dust ring map isn't there either: nothing
with cal.stepping("flat"):
    plain = cal.calibrate(codes[::4, ::4], quarter)
assert np.allclose(cal.calibrate(codes[::4, ::4], quarter), plain)

# without the maps nothing changes but the nonlinearity, and calibrate still works
ff.ROOT = os.path.join(root, "missing")
ff._slope_db.cache_clear()
ff._correction.cache_clear()
ff._map.cache_clear()
none = cal.calibrate(codes, INFO)
assert np.allclose(none, off) and ff.correction(INFO) is None
print("ok")
