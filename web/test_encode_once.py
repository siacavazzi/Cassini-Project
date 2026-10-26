"""Synthetic check that a picture asked for at sizes it is encoded the same way for is encoded once, and that those
sizes get the bytes encode gives each of them: a composite's 1024 and full at quality 95 (color_webp), a summed frame's
1024 and 512 (webp, asked in turn as the pre-build does). Sizes encoded differently are encoded each.
Run: python web/test_encode_once.py"""
import io
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import frame_server as fs  # noqa: E402

rng = np.random.default_rng(5)
calls = []
real_encode = fs.encode


def counting(im, size, fmt="webp", quality=fs.QUALITY):
    calls.append((im.mode, im.size, size, fmt))
    return real_encode(im, size, fmt, quality)


def picture(mode, side):
    bands = len(mode)
    a = rng.integers(0, 256, (side, side, bands), dtype=np.uint8)
    yy, xx = np.mgrid[:side, :side]
    a[..., 0] = (xx * 255 // side + yy) % 256   # some structure, so the WebP encoder has work to do
    if mode.endswith("A"):
        a[..., -1] = np.where((xx - side / 2) ** 2 + (yy - side / 2) ** 2 < (side / 2.2) ** 2, 255, 0)
    return Image.fromarray(a[..., 0] if bands == 1 else a, mode)


checks = 0
# every size of every picture: the same bytes as encode, and sizes encoded the same way share them
for mode in ("L", "LA", "RGB", "RGBA"):
    for side in (256, 512, 1024, 1500):
        im = picture(mode, side)
        for quality in (80, 95):
            enc = fs.encoder(im, quality)
            by_way = {}
            for size in (128, 512, 1024, fs.FULL):
                for fmt in ("webp", "png") if side == 512 and quality == 95 else ("webp",):
                    data = enc(size, fmt)
                    assert data == real_encode(im, size, fmt, quality), (mode, side, quality, size, fmt)
                    by_way.setdefault(fs._encoding(im, size, fmt, quality), set()).add(data)
                    checks += 1
            assert all(len(v) == 1 for v in by_way.values()), (mode, side, quality)
        # at quality 95 a picture no larger than 1024 is the same bytes at 1024 and full (not grey: full is lossless)
        same = fs._encoding(im, 1024, "webp", 95) == fs._encoding(im, fs.FULL, "webp", 95)
        assert same == (side <= 1024 and mode != "L"), (mode, side)
        checks += 1

fs.encode = counting
cache = tempfile.mkdtemp()

# composites: color_webp at 1024 then 512, as the pre-build asks (the 1024 also writes full)
for side, encodes in ((1024, (1, 1)), (1500, (2, 1))):
    im = picture("RGBA", side)
    fs._recent_composite = lambda ids, centre=None, im=im: (im, {"ids": list(ids)})
    ids = [f"N15000{side}_2", "N1500000002_2", "N1500000003_2"]
    for size, n in zip((1024, 512), encodes):
        before = len(calls)
        data, _ = fs.color_webp(ids, size, cache)
        assert len(calls) - before == n, (side, size, calls[before:])
        assert data == real_encode(im, size), (side, size)
        checks += 1
    folder = os.path.join(cache, fs.COLOR_VERSIONS[fs.calibration.style()] + fs.QSUFFIX)
    for size in (1024, 512, fs.FULL):
        with open(os.path.join(folder, str(size), "_".join(ids) + ".webp"), "rb") as fh:
            assert fh.read() == real_encode(im, size), (side, size, "file")
        checks += 1

# frames: webp at 1024, 512 and 128 in turn, as the pre-build asks; a summed frame's 1024 and 512 are one encode
for side, mode, encodes in ((1024, "L", 3), (512, "L", 2), (256, "L", 2), (512, "RGB", 2)):
    fid = f"N1500{side}{mode}_1"
    im = picture(mode, side)
    png = io.BytesIO()
    im.save(png, "PNG")
    fs.archive_png = lambda frame_id, png=png.getvalue(): png
    before = len(calls)
    got = [fs.webp(fid, size, cache) for size in (1024, 512, 128)]
    assert len(calls) - before == encodes, (side, mode, calls[before:])
    for size, data in zip((1024, 512, 128), got):
        assert data == real_encode(im, size, "webp", fs.FRAME_QUALITY), (side, mode, size)
        with open(os.path.join(cache, fs.FRAME_VERSION, str(size), f"{fid}.webp"), "rb") as fh:
            assert fh.read() == data, (side, mode, size, "file")
        checks += 1
print(f"{checks} checks ok")
