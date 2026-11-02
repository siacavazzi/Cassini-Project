"""Synthetic checks of the frame edge fixes (fix plan group K):

1. color_image.edge_trimmed leaves out a frame's outermost lines and columns (EDGE_PX full-resolution pixels, at
   least one of a summed frame's own pixels) and nothing else, and load_aligned's mask (the alpha of every picture
   made of a frame) no longer has them: a frame whose first and last columns and first line are bright, as the
   camera's are, shows none of that brightness once drawn with its alpha.
2. reel.save_webp keeps black under every fully transparent (and nearly transparent) pixel of a lossy WebP (left to itself the encoder copies
   the picture's nearest blocks there: the staircase of grey blocks along a turned frame's edge), changes nothing a
   reader drawing the alpha sees, and leaves a picture without transparency as the plain save makes it.
3. frame_server.encode goes through it.
Run: python web/test_edge_trim.py"""
import io
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "frames"))
sys.path.insert(0, os.path.dirname(HERE))
import numpy as np
from PIL import Image
import color_image  # noqa: E402
import reel  # noqa: E402
import frame_server as fs  # noqa: E402


class Lbl:
    def __init__(self, lines):
        self.info = {"LINES": lines}


# 1. the trim
full = np.ones((1024, 1024), bool)
t = color_image.edge_trimmed(full, Lbl(1024))
n = color_image.EDGE_PX
assert not t[:n].any() and not t[-n:].any() and not t[:, :n].any() and not t[:, -n:].any()
assert t[n:-n, n:-n].all(), "only the outermost lines and columns go"
assert full.all(), "the mask given is not changed"
for lines, want in ((512, max(n, 2)), (256, max(n, 4))):
    t = color_image.edge_trimmed(full, Lbl(lines))
    assert not t[:, :want].any() and t[want:-want, want:-want].all(), (lines, want)
assert color_image.edge_trimmed(full, Lbl("N/A"))[n:-n, n:-n].all()
lost = full.copy()
lost[500:510] = False    # lost lines stay lost
t = color_image.edge_trimmed(lost, Lbl(1024))
assert not t[500:510].any() and t[n:500, n:-n].all()
print(f"trim: {n} px of a full frame, one pixel of a summed frame (2 or 4 px), nothing else")

# a frame whose first and last columns and first line are bright (the camera's own, in nearly every frame of the
# archive), drawn as processed_frame draws it: alpha = mask.png where the frame has pixels
sky = np.full((1024, 1024), 10, np.uint8)
sky[:, 0] = sky[:, -1] = 220
sky[0] = 200
soft = np.asarray(Image.open(os.path.join(os.path.dirname(HERE), "mask.png")).convert("L"))
for name, valid in (("before", full), ("after", color_image.edge_trimmed(full, Lbl(1024)))):
    alpha = np.where(valid, soft, 0).astype(np.float32) / 255
    shown = sky * alpha
    rim = max(shown[:, 0].max(), shown[:, -1].max(), shown[0].max())
    print(f"{name}: brightest edge pixel over black {rim:.1f} of 255 (sky inside {sky[512, 512]})")
    if name == "after":
        assert rim == 0, "no edge pixel is drawn"
        assert shown[n:-n, n:-n].max() <= 10, "the rest of the frame as it was"

# 2. the WebP save
side = 256
yy, xx = np.mgrid[:side, :side]
inside = ((xx + yy) > 180) & ((xx - yy) < 90) & ((xx + yy) < 400) & ((yy - xx) < 120)   # a turned frame
rgba = np.zeros((side, side, 4), np.uint8)
rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = np.where(inside, 120 + (xx % 37), 0)
rgba[..., 3] = np.where(inside, 255, 0)
im = Image.fromarray(rgba, "RGBA")


def decoded(save):
    b = io.BytesIO()
    save(b)
    return np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGBA")).astype(int), len(b.getvalue())


plain, plain_n = decoded(lambda b: im.save(b, "WEBP", quality=95, method=4))
clean, clean_n = decoded(lambda b: reel.save_webp(im, b, quality=95, method=4))
under = clean[..., 3] == 0
print(f"under transparent pixels: plain save up to {plain[..., :3][plain[..., 3] == 0].max()}, "
      f"save_webp up to {clean[..., :3][under].max()} ({clean_n} bytes against {plain_n})")
assert plain[..., :3][plain[..., 3] == 0].max() > 60, "the encoder's own fill (the staircase) is there to clean"
assert clean[..., :3][under].max() <= 12, "black (up to the lossy encoder's ringing) under what is transparent"
assert np.array_equal(clean[..., 3], plain[..., 3]), "alpha as it was"
over = lambda a: a[..., :3] * a[..., 3:] / 255
err = lambda a: np.abs(over(a) - over(rgba.astype(int))).max()
print(f"shown with its alpha, off the picture by up to {err(clean):.0f} levels (the plain save {err(plain):.0f})")
assert err(clean) <= max(err(plain), 6), "the same picture shown with its alpha, up to the lossy encoder's error"
# a faint pixel's colour (rounded far off by an 8-bit premultiplied resize: a white speck where the alpha is
# dropped) is saved black, which changes what the page shows by under WEBP_FAINT levels
speck = rgba.copy()
speck[10:14, 10:14] = (255, 255, 255, reel.WEBP_FAINT - 1)
s_, _ = decoded(lambda b: reel.save_webp(Image.fromarray(speck, "RGBA"), b, quality=95, method=4))
assert s_[10:14, 10:14, :3].max() <= 12, s_[10:14, 10:14]
# the picture given is not changed
assert np.array_equal(np.asarray(im), rgba)
# no transparency: the plain save
rgb = Image.fromarray(rgba[..., :3], "RGB")
a, _ = decoded(lambda b: rgb.save(b, "WEBP", quality=95, method=4))
c, _ = decoded(lambda b: reel.save_webp(rgb, b, quality=95, method=4))
assert np.array_equal(a, c)

# 3. the frame server's encode
e = np.asarray(Image.open(io.BytesIO(fs.encode(im, 1024))).convert("RGBA")).astype(int)
assert e[..., :3][e[..., 3] == 0].max() <= 12
print("ok")
