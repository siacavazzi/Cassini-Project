"""/export/levels.json never keeps a level measured on a stand-in: when a frame's mosaic is not finished within
MOSAIC_WAIT, the film takes the next try (the color composite), and a measuring that used one is answered but not
written to the cache; after STAND_IN_AGAIN it is measured again, by then on the finished mosaic, and kept.

Here the plan and the pictures are stand-ins: one frame whose mosaic never finishes at first (then is finished),
one plain processed frame; the clock is the test's.

  python web/frames/test_export_stand_in.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "replay")]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import export  # noqa: E402
import obs_mosaic  # noqa: E402


def webp(level, w=200, h=200):
    a = np.zeros((h, w, 4), np.uint8)
    a[50:150, 50:150] = (level, level, level, 255)
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, "WEBP", lossless=True)
    return buf.getvalue()


MOSAIC, PART, COLOR, PROC = webp(160), webp(40), webp(70), webp(110)
M = "N1492356449_2"
PICS = [{"id": M, "try": [("mosaic", M), ("color", ["N1492356271_2", M, "N1492356166_2"]), ("processed", M)]},
        {"id": "W1492356449_1", "try": [("processed", "W1492356449_1")]}]
export.plan = lambda opt: {"pictures": [dict(e) for e in PICS]}

clock = [0.0]
export.time.monotonic = lambda: clock[0]


def sleep(s):
    clock[0] += s


export.time.sleep = sleep
finished = [False]
obs_mosaic.unit_of = lambda fid: ({"mosaic": True}, 13) if fid == M else None
obs_mosaic.mosaic_webp = lambda fid, size, cache, slots=None, ahead=3, **kw: \
    (MOSAIC, {"behind": 0}) if finished[0] else (PART, {"behind": 4})
pictures = export.Pictures(None, color=lambda ids, size, cache, centre=None: (COLOR, {}),
                           processed=lambda fid, size, cache, centre=None: (PROC, {}))
level = {k: round(export.brightness(export.Pictures(None)._on_black(Image.open(io.BytesIO(v)), 512)), 5)
         for k, v in (("mosaic", MOSAIC), ("color", COLOR), ("proc", PROC))}

cache = tempfile.mkdtemp(prefix="levels-stand-in-")
opt = export.options({"from": ["2005-04-16T15:00:00"], "until": ["2005-04-16T23:00:00"], "pictures": ["color"]})
path = os.path.join(cache, export.LEVELS_VERSION, export.levels_key(opt) + ".json")

# 1. the mosaic is never finished: the color composite stands in, answered, not kept
got = export.measure(opt, cache, pictures, wait=True)
assert got["logs"][M] == level["color"], got
assert got.get("stand_in") == [M], got
assert not os.path.exists(path), "a measuring on a stand-in was kept on disk"
print(f"mosaic not finished in {export.MOSAIC_WAIT} s: measured on the color composite, answered, not kept")

# 2. asked again soon: the same answer, not measured again yet
again = export.measure(opt, cache, pictures)
assert again["logs"][M] == level["color"] and again["done"] == 2 and "thread" not in again, again
print("asked again within STAND_IN_AGAIN: the same answer (no new measuring)")

# 3. after STAND_IN_AGAIN, with the mosaic made by then: measured again on it, and kept
finished[0] = True
clock[0] += export.STAND_IN_AGAIN + 1
export.measure(opt, cache, pictures, wait=True)
got = export.measure(opt, cache, pictures)
assert got["logs"][M] == level["mosaic"] and not got.get("stand_in"), got
assert os.path.exists(path), "the measuring on the finished mosaic was not kept"
print(f"after {export.STAND_IN_AGAIN} s: measured again on the finished mosaic and kept")
print("ok")
