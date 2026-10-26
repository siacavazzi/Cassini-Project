"""Synthetic check that frame_server.encode never shrinks the picture it is given (PIL's thumbnail works in place):
a composite kept for its other sizes (_recent_composite) has to come out whole at 1024, full or as PNG after a 512
view, and its channels with it.
Run: python web/test_encode_keeps_input.py"""
import io
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import frame_server as fs  # noqa: E402

rng = np.random.default_rng(5)
checks = 0
for mode, shape in (("L", (1024, 1024)), ("RGBA", (1024, 1024, 4)), ("RGBA", (700, 1300, 4)), ("L", (256, 256))):
    im = Image.fromarray(rng.integers(0, 256, shape, dtype=np.uint8), mode)
    size, pixels = im.size, im.tobytes()
    for want in (512, 128, fs.FULL, 1024, 512):
        for fmt in ("webp", "png"):
            out = Image.open(io.BytesIO(fs.encode(im, want, fmt)))
            cap = fs.FULL_MAX if want == fs.FULL else want
            assert max(out.size) == min(max(size), cap), (mode, shape, want, fmt, out.size)
            assert im.size == size and im.tobytes() == pixels, (mode, shape, want, fmt, "the input was changed")
            checks += 1
print(f"{checks} checks ok")
