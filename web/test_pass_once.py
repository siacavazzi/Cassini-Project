"""Synthetic check that obs_mosaic's pass pictures (so_far, movie_frame) are made once for the sizes asked for one
after another (make_pass asks for 1024, then 512), each call getting a picture of its own: a caller shrinking its
copy in place (as _make_mosaic and movie_webp do) leaves the next size whole. Another frame, layout or look, or a
picture larger than OUT, is made on its own.
Run: python web/test_pass_once.py"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(11)
made = []


def make(u, n, cache, layout_name, out=om.OUT):
    made.append((n, layout_name, out, om.calibration.style()))
    side = min(out, om.CANVAS)
    return Image.fromarray(rng.integers(0, 256, (side, side, 4), dtype=np.uint8), "RGBA"), {"n": n, "made": len(made)}


kept = om._kept_for_next_size(make, lambda u, n, cache, layout_name, out=om.OUT:
                              (om.folder(u, cache), layout_name, n, out) if out <= om.OUT else None)
cache, checks = tempfile.mkdtemp(), 0
u = {"key": ("SATURN", "ISS_000RI_TEST001_PRIME", "N", 0)}
# (frame, layout, sizes asked in turn, out, look, pictures made)
for n, name, sizes, out, look, new in ((0, "a", (1024, 512), om.OUT, "balanced", 1),
                                       (1, "a", (512, 512, 1024), om.OUT, "balanced", 1),
                                       (1, "b", (1024, 512), om.OUT, "balanced", 1),
                                       (1, "b", (1024, 512), om.OUT, "classic", 1),
                                       (1, "b", (1024, 512), 2048, "classic", 2),
                                       (1, "b", (1024, 512), om.OUT, "classic", 1)):
    with om.calibration.looking(look):
        before, got = len(made), []
        for z in sizes:   # as _make_mosaic and movie_webp: the picture, then shrunk in place to the size
            im, rep = kept(u, n, cache, name, out)
            got.append((im.copy(), rep))
            if max(im.size) > z:
                im.thumbnail((z, z), Image.LANCZOS)
        assert len(made) == before + new, (n, name, sizes, out, look, made[before:])
        for whole, rep in got:
            assert whole.size == (min(out, om.CANVAS),) * 2, (n, name, sizes, whole.size, "not whole")
            if new == 1:
                assert whole.tobytes() == got[0][0].tobytes() and rep == got[0][1], (n, name, sizes, "not the same")
            checks += 1
print(f"{checks} checks ok")
