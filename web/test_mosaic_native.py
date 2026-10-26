"""Synthetic check of native resolution mosaics (mosaic_native): a 6 x 4 pass in three filters (24 tiles each, so
past GROW_FROM the windows' mosaic grows a tile at a time) with fine detail and a small exposure error per tile.
The native mosaic, shrunk to the windows' canvas, is the windows' mosaic (same levels and colours, seam
corrections found again tile by tile); it holds the detail the canvas loses; a crop is the same pixels as that part
of the whole; blocks join without a seam (any block size gives the same picture); the streamed PNG reads back; and
the pictures go to their own cache, not the frame server's. Run: python web/test_mosaic_native.py"""
import os, sys, json, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om
import mosaic_native as mn
import calibration

Image.MAX_IMAGE_PIXELS = None
root = tempfile.mkdtemp()
cache = os.path.join(root, "cache")
os.environ["CASSINI_FULLRES_CACHE"] = os.path.join(root, "fullres")
rng = np.random.default_rng(5)
COLS, ROWS, STEP, F = 6, 4, 820, 1024
filters = ["RED", "GRN", "BL1"]
frames, offs = [], []
for j in range(COLS * ROWS):
    x, y = (j % COLS - (COLS - 1) / 2) * STEP, (j // COLS - (ROWS - 1) / 2) * STEP
    for f in filters:
        n = len(frames)
        frames.append((f"p{n}", f"N{1500000000 + n}_1", f, 1000.0 + 20 * n, 600, -x, -y, 1e6))
        offs.append((x, y))
u = {"key": ("RHEA", "NATIVE", "N", 0), "frames": frames, "z": 1e6, "movie": False, "mosaic": True, "last": frames[-1][3]}
SCALE = {"blacks": {}, "white": 1, "gamma": 2.2}
TD = om._tiles(u, cache, SCALE)
os.makedirs(TD, exist_ok=True)
# the body's surface: craters of every size down to a pixel or two, the same ground in every tile it is under
G = 6000
ground = np.full((G, G), 120.0, np.float32)
yy, xx = np.mgrid[0:64, 0:64]
for _ in range(9000):
    r = rng.choice([1.0, 1.5, 3, 6, 15], p=[.45, .3, .15, .07, .03])
    cx, cy = rng.integers(40, G - 40, 2)
    s = int(min(32, 4 * r))
    patch = -60 * np.exp(-(((xx[:2 * s, :2 * s] - s) ** 2 + (yy[:2 * s, :2 * s] - s) ** 2) / (r * r)))
    ground[cy - s:cy + s, cx - s:cx + s] += patch
ground = np.clip(ground + rng.normal(0, 3, ground.shape), 0, 255)
tint = {"RED": 1.0, "GRN": 0.9, "BL1": 0.75}
for n, ((x, y), fr) in enumerate(zip(offs, frames)):
    gx, gy = int(G / 2 + x - F / 2), int(G / 2 + y - F / 2)
    err = rng.uniform(0.94, 1.06)   # each frame's own exposure error, for the seams to take out
    im = np.zeros((F, F, 4), np.uint8)
    im[..., :3] = np.clip(ground[gy:gy + F, gx:gx + F] * tint[fr[2]] * err, 0, 255)[..., None]
    im[..., 3] = 255
    Image.fromarray(im).save(f"{TD}/{n}.png")
    json.dump({"n": n, "id": fr[1], "filter": fr[2], "t": fr[3], "offset": [float(x), float(y)], "box": [-F / 2, -F / 2, F, F]},
              open(f"{TD}/{n}.json", "w"))
x0, x1 = min(o[0] for o in offs) - om.HALF, max(o[0] for o in offs) + om.HALF
y0, y1 = min(o[1] for o in offs) - om.HALF, max(o[1] for o in offs) + om.HALF
view = [x1 - x0, y1 - y0]
json.dump({"key": list(u["key"]), "display_scale": SCALE, "angle": 0, "footprint": [x0, y0, x1, y1], "fixed": True,
           "view": view, "k": om.CANVAS / max(view), "colour": filters, "grey": "RED", "whole": True},
          open(om.folder(u, cache) + "/" + om.PLAN_FILE, "w"))
by_id = {fr[1]: n for n, fr in enumerate(frames)}
om.unit_of = lambda fid: (u, by_id[fid]) if fid in by_id else None
last = frames[-1][1]

with calibration.looking("balanced"):
    made = om.layout(u, len(frames) - 1, cache)
    assert made[4] == filters and made[3]["RED"] == 24 > om.GROW_FROM
    # the windows' mosaic, on its whole canvas (the window is sent this shrunk to OUT)
    shown, _ = om.so_far(u, len(frames) - 1, cache, made, out=om.CANVAS)
    shown = np.asarray(shown)
    about = mn.info(last, cache)
    print("native", about["width"], "x", about["height"], "shown", about["shown"], "estimate", about["estimate_mb"])
    assert about["width"] == int(np.ceil(view[0])) and about["shown"][0] == shown.shape[1]

    t = time.monotonic()
    path, rep = mn.picture(last, cache, None, "png")
    took = time.monotonic() - t
    assert path.startswith(os.environ["CASSINI_FULLRES_CACHE"]) and not path.startswith(cache + os.sep)
    native = np.asarray(Image.open(path).convert("RGBA"))
    print(f"whole native PNG {native.shape[1]} x {native.shape[0]}, {os.path.getsize(path) / 1e6:.1f} MB, {took:.1f} s")
    assert native.shape[:2] == (about["height"], about["width"])

    # shrunk to the canvas, the native mosaic is the windows' mosaic
    small = np.asarray(Image.fromarray(native).resize((shown.shape[1], shown.shape[0]), Image.LANCZOS)).astype(float)
    both = (shown[..., 3] == 255) & (small[..., 3] > 250)
    d = np.abs(small[..., :3] - shown[..., :3])[both]
    print(f"native shrunk vs window mosaic: mean {d.mean():.2f} levels, 99th pct {np.percentile(d, 99):.1f}")
    assert d.mean() < 1.5 and np.percentile(d, 99) < 8
    # and the level of each tile's middle agrees (the seam corrections are the windows')
    for n in range(0, len(frames), 9):
        ox, oy = offs[n]
        cx, cy = (ox - x0) * om.CANVAS / max(view), (oy - y0) * om.CANVAS / max(view)
        a = shown[int(cy) - 20:int(cy) + 20, int(cx) - 20:int(cx) + 20, :3].mean()
        b = small[int(cy) - 20:int(cy) + 20, int(cx) - 20:int(cx) + 20, :3].mean()
        assert abs(a - b) < 1.5, (n, a, b)

    # the detail the canvas loses: fine structure (high pass) at native vs the window mosaic blown up to native
    def fine(a):
        g = a[..., :3].mean(axis=2).astype(np.float32)
        import cv2
        return float(np.abs(g - cv2.GaussianBlur(g, (0, 0), 2)).mean())
    mid = native[1000:2000, 1500:2500]
    blown = np.asarray(Image.fromarray(shown).resize((native.shape[1], native.shape[0]), Image.LANCZOS))[1000:2000, 1500:2500]
    print(f"fine detail: native {fine(mid):.2f}, window mosaic blown up {fine(blown):.2f}")
    assert fine(mid) > 3 * fine(blown)

    # a crop (the zoom lens) is the same pixels as that part of the whole
    crop = (0.31, 0.27, 0.47, 0.52)
    cpath, crep = mn.picture(last, cache, crop, "png")
    part = np.asarray(Image.open(cpath).convert("RGBA")).astype(int)
    cx0, cy0 = round(crop[0] * view[0]), round(crop[1] * view[1])
    whole_part = native[cy0:cy0 + part.shape[0], cx0:cx0 + part.shape[1]].astype(int)
    print("crop", part.shape[1], "x", part.shape[0], "max diff from the whole", np.abs(part - whole_part).max())
    assert np.abs(part - whole_part).max() <= 2
    wpath, _ = mn.picture(last, cache, crop, "webp")
    assert Image.open(wpath).size == (part.shape[1], part.shape[0])
    # a wide crop is drawn at most CROP_MAX px
    _, wide = mn.picture(last, cache, (0, 0, 1, 1), "webp")
    assert max(wide["width"], wide["height"]) == mn.CROP_MAX, wide

    # any block size: the same picture (blocks join without a seam)
    mn.BLOCK = 1500
    k, w, h = mn.scale_of(made)
    corr = mn.corrections(u, made, cache)
    strips = list(mn._rows(u, made, corr, k, 0, 0, w, h, cache))
    again = np.concatenate(strips)
    print("block 1500 vs 1024: max diff", np.abs(again.astype(int) - native.astype(int)).max())
    assert np.abs(again.astype(int) - native.astype(int)).max() <= 1
    mn.BLOCK = 1024

    # the JPEG: on black, the same size
    jpath, _ = mn.picture(last, cache, None, "jpg")
    jim = Image.open(jpath)
    assert jim.size == (w, h) and jim.mode == "RGB"
    print(f"whole native JPEG {os.path.getsize(jpath) / 1e6:.1f} MB")
    after = mn.info(last, cache)
    assert after["ready"] == {"jpg": True, "png": True}

    # the cache is trimmed to its cap, least recently used first; the seams are kept
    mn._touch(jpath)
    mn.trim(os.environ["CASSINI_FULLRES_CACHE"], keep_mb=int(os.path.getsize(jpath) / 2 ** 20) + 1)
    assert os.path.exists(jpath) and not os.path.exists(path)
    print("cache trimmed; ok")
