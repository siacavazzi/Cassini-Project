"""D9: the science download, /frames/<ID>.tif: the frame's I/F at the camera's resolution as a 32-bit float TIFF
with its PDS label (frame_server.science_tiff, color_image.science_frame). A synthetic lean-archive frame in a data
folder. Run: python web/test_science_tiff.py"""
import io
import os
import sys
import tempfile
import cv2
import numpy as np

data = tempfile.mkdtemp()
os.makedirs(os.path.join(data, "nac_data"))
open(os.path.join(data, "nac_data", "FORMAT.txt"), "w").write("lean archive\n")
os.environ["CASSINI_DATA"] = data
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
from PIL import Image  # noqa: E402
import frame_server  # noqa: E402
import calibration as cal  # noqa: E402

LABEL = """PDS_VERSION_ID = PDS3
PRODUCT_ID = "{id}"
INSTRUMENT_ID = "ISSNA"
TARGET_NAME = "PHOEBE"
IMAGE_TIME = 2004-163T19:00:00.000
FILTER_NAME = ("CL1","GRN")
GAIN_MODE_ID = "29 ELECTRONS PER DN"
INSTRUMENT_MODE_ID = "FULL"
EXPOSURE_DURATION = 460.0
DATA_CONVERSION_TYPE = "{conv}"
BIAS_STRIP_MEAN = 12.0
SHUTTER_STATE_ID = "ENABLED"
IMAGE_NUMBER = 1465674000
LINES = 1024
LINE_SAMPLES = 1024
MISSING_LINES = 0
END
"""
yy, xx = np.mgrid[:1024, :1024]
codes = np.full((1024, 1024), 12, np.uint8)
codes[(yy - 512) ** 2 + (xx - 512) ** 2 < 300 ** 2] = 200
for fid, conv in (("N1465674000_1", "TABLE"), ("N1465674001_1", "8LSB")):
    cv2.imwrite(os.path.join(data, "nac_data", fid + ".png"), codes)
    open(os.path.join(data, "nac_data", fid + ".lbl"), "w").write(LABEL.format(id=fid, conv=conv))

tif = frame_server.science_tiff("N1465674000_1")
im = Image.open(io.BytesIO(tif))
iof = np.asarray(im)
print("mode", im.mode, "size", im.size, "dtype", iof.dtype, "body", float(iof[512, 512]), "sky", float(iof[5, 5]))
assert im.mode == "F" and im.size == (1024, 1024) and iof.dtype == np.float32
want = cal.calibrate(codes, frame_server.color_image.lh.label("nac_data/N1465674000_1.png", as_png=True).get_info())
assert np.allclose(iof, want, rtol=1e-6, equal_nan=True)         # the pipeline's I/F, nothing done to it
assert abs(float(iof[5, 5])) < 1e-6 and float(iof[512, 512]) > 0   # sky at the bias is zero, the body above it
desc = im.tag_v2[270]
assert desc.startswith("PDS_VERSION_ID = PDS3") and "N1465674000_1" in desc and "I/F of N1465674000_1" in desc
assert frame_server.science_tiff("N1465674001_1") is None          # 8LSB: no I/F to give
print("ok")
