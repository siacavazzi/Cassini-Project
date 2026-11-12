"""A film's mosaic picture (export.Pictures) is the finished mosaic at its frame, never the part-built one a cold
cache answers with first, and never the next try while the mosaic is still coming.

What went wrong (Mac Mini, 2026-11-11, Titan flyby T5, frame N1492356449_2 of ISS_006TI_EUVFUV001_UVIS): on a cold
cache obs_mosaic.mosaic_webp answers at once with the tiles made so far (report "behind") or nothing at all, and
makes the rest in the background. /export/levels.json measured whatever it got and kept it: the color composite
(-2.24 EV) when no tile was made yet, a part-built mosaic (-2.17, then -3.53) a little later, while the finished
mosaic measures -0.70. Each restart stored another number.

Here mosaic_webp is replaced by one that plays a cold cache: nothing for the first calls, then part-built mosaics
(behind > 0), then the finished one. Pictures.picture must return the finished mosaic, and export.brightness on it
the finished mosaic's level, every time.

  python web/frames/test_export_finished_mosaic.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "replay")]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import export  # noqa: E402
import obs_mosaic  # noqa: E402


def webp(level, w=103, h=512):
    """A made-up mosaic picture whose lit part has gray level (0..255)"""
    a = np.zeros((h, w, 4), np.uint8)
    a[h // 4: 3 * h // 4, w // 4: 3 * w // 4] = (level, level, level, 255)
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, "WEBP", lossless=True)
    return buf.getvalue()


FINISHED, PART = webp(160), [webp(40), webp(90)]
FID = "N1492356449_2"


class Cold:
    """mosaic_webp on a cold cache: `none` calls with no tile made, then the part-built mosaics, then the finished"""

    def __init__(self, none=3):
        self.calls, self.none = 0, none

    def __call__(self, frame_id, size, cache, slots=None, ahead=3, **kw):
        assert frame_id == FID
        self.calls += 1
        k = self.calls - self.none
        if k <= 0:
            return None
        if k <= len(PART):
            return PART[k - 1], {"kind": "mosaic", "behind": len(PART) - k + 1}
        return FINISHED, {"kind": "mosaic", "behind": 0}


obs_mosaic.unit_of = lambda frame_id: ({"mosaic": True, "key": ("TITAN", "ISS_006TI_EUVFUV001_UVIS", "N", 0)}, 13) if frame_id == FID else None
COLOR = webp(70)
pictures = export.Pictures(None, color=lambda ids, size, cache, centre=None: (COLOR, {}))
e = {"id": FID, "try": [("mosaic", FID), ("color", ["N1492356271_2", FID, "N1492356166_2"]), ("processed", FID), ("frame", FID)]}
want = export.brightness(export.Pictures(None)._on_black(Image.open(io.BytesIO(FINISHED)), 512))
export.time.sleep = lambda s: None   # no real waiting here

for none in (0, 1, 5):
    obs_mosaic.mosaic_webp = cold = Cold(none)
    im, what = pictures.picture(e, 512)
    got = export.brightness(im)
    assert what == "mosaic", f"{none} cold calls: the {what} stood in for the mosaic"
    assert got == want, f"{none} cold calls: measured {got}, the finished mosaic is {want}"
    print(f"cold for {none} calls, then {len(PART)} part-built mosaics: the film took the finished mosaic "
          f"({cold.calls} asks), level {got / np.log(2):.4f} EV")

# a pass that is no mosaic: no waiting, the next try at once
obs_mosaic.mosaic_webp = lambda *a, **k: None
obs_mosaic.unit_of = lambda frame_id: None
im, what = pictures.picture(e, 512)
assert what == "colour", what
print("a frame in no mosaic pass: the color composite at once")

# a mosaic that never finishes: TimeoutError, then the next try (as any picture the pipeline cannot make)
obs_mosaic.unit_of = lambda frame_id: ({"mosaic": True}, 13)
obs_mosaic.mosaic_webp = lambda *a, **k: (PART[0], {"behind": 4})
clock = iter(range(0, 10 ** 6, 60))
export.time.monotonic = lambda: next(clock)
im, what = pictures.picture(e, 512)
assert what == "colour", what
print(f"a mosaic still behind after {export.MOSAIC_WAIT} s: given up, the color composite instead")
print("ok")
