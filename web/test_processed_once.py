"""Synthetic check that frame_server.processed_webp makes a frame once for the sizes asked for one after another (the
segment pre-render asks for 512, then 1024), and that each size is what encode makes of that one picture; another
look or a centred view is made on its own.
Run: python web/test_processed_once.py"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import frame_server as fs  # noqa: E402

rng = np.random.default_rng(3)
made = []


def composite(ids, channel=None, centre=None):
    made.append((tuple(ids), fs.calibration.style(), centre and centre["side"]))
    im = Image.fromarray(rng.integers(0, 256, (1024, 1024, 2), dtype=np.uint8), "LA")
    return im, {"ids": list(ids), "n": len(made)}


fs.composite = composite
cache, checks = tempfile.mkdtemp(), 0
for look, centre in (("balanced", None), ("classic", None), ("balanced", {"side": 800})):
    with fs.calibration.looking(look):
        before = len(made)
        out = [fs.processed_webp("N1500000000_1", z, cache, centre=centre) for z in (512, 1024, fs.FULL, 512)]
        assert len(made) == before + 1, (look, centre, made[before:])
        im, _ = fs._recent_composite(["N1500000000_1"], centre)
        assert len(made) == before + 1, (look, centre, "made again")
        for (data, report), z in zip(out, (512, 1024, fs.FULL, 512)):
            assert data == fs.encode(im, z), (look, centre, z)
            assert report["n"] == len(made), (look, centre, z, report)
            checks += 1
print(f"{checks} checks ok")
