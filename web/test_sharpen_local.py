"""Sharpness on this computer (Settings > Processing, sharpen.html) is color_image.unsharp: the page's arithmetic
(window.cassiniSharpen.math, run here in node on the same bytes) gives the same picture, byte for byte, for color,
grey and alpha-edged pictures at several levels. And it does its job: an edge gets steeper, flat areas and the empty
canvas round a picture are left as they are, faint noise is raised far less than an edge, and 0 changes nothing.
Optional: SHARPEN_REAL=<folder of pictures> runs the conformance check on those too.
Run: python web/test_sharpen_local.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.dirname(HERE)]
import glob, json, subprocess, tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import color_image as C  # noqa: E402

script = open(os.path.join(HERE, "cassini-os", "src", "sharpen.html")).read()
script = script[script.index("<script>") + 8:script.index("</script>")]


def scene(seed, size=160):
    """A lit disk with craters and noise on black sky, a soft edge band, RGBA (opaque)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    disk = np.hypot(x - size * 0.45, y - size * 0.5) < size * 0.33
    v = np.where(disk, 150 + 40 * np.sin(x / 5) * np.cos(y / 7), 4) + rng.normal(0, 2, (size, size))
    a = np.zeros((size, size, 4), np.uint8)
    for k, t in enumerate((1.0, 0.93, 0.8)):
        a[..., k] = np.clip(v * t + 0.5, 0, 255).astype(np.uint8)
    a[..., 3] = 255
    return a


def in_node(pictures, amount):
    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    rgba = []
    for i, a in enumerate(pictures):
        r = rgba_of(a)
        rgba.append(r)
        open(f"{tmp}/{i}.raw", "wb").write(r.tobytes())
    js = ("const fs = require('fs');\nconst window = {};\nconst performance = { now: () => 0 };\n" + script + "\nconst M = window.cassiniSharpen.math;\n"
          f"const pics = {json.dumps([[a.shape[1], a.shape[0], 1 if a.ndim == 2 or a.shape[2] == 2 else 3] for a in pictures])};\n"
          "pics.forEach(([w, h, c], i) => { const d = new Uint8ClampedArray(fs.readFileSync(`" + tmp + "/${i}.raw`));"
          f" M.unsharp(d, w, h, {amount}, c); fs.writeFileSync(`{tmp}/${{i}}.out`, d); }});\n")
    open(f"{tmp}/run.js", "w").write(js)
    subprocess.run(["node", f"{tmp}/run.js"], check=True)
    return [np.frombuffer(open(f"{tmp}/{i}.out", "rb").read(), np.uint8).reshape(r.shape) for i, r in enumerate(rgba)]


def rgba_of(a):
    """The picture as a canvas holds it: RGBA bytes (grey in all three, opaque when it has no alpha)."""
    if a.ndim == 2:
        a = a[..., None]
    n = a.shape[2]
    rgb = np.repeat(a[..., :1], 3, axis=2) if n in (1, 2) else a[..., :3]
    al = a[..., -1:] if n in (2, 4) else np.full(a.shape[:2] + (1,), 255, np.uint8)
    return np.ascontiguousarray(np.concatenate([rgb, al], axis=2))


def same(pictures, amount, name):
    js = in_node(pictures, amount)
    for i, a in enumerate(pictures):
        want = rgba_of(C.unsharp(a, amount))
        diff = np.abs(want.astype(int) - js[i].astype(int))
        assert diff.max() == 0, (name, i, int(diff.max()), int((diff > 0).sum()))
    print(f"{name}: {len(pictures)} pictures, page == python byte for byte (amount {amount})")


def test_conformance():
    color = [scene(s) for s in range(3)]
    grey = scene(7)[..., 0].copy()
    la = np.dstack([grey, np.where(np.arange(160)[None, :] < 120, 255, 0).repeat(160, 0).astype(np.uint8)])
    edged = scene(9)
    edged[:, :30, 3] = 0
    edged[:, 30:34, 3] = 128
    for amount in (0.3, 0.525, 1.5):
        same(color + [grey, la, edged], amount, "synthetic")


def test_does_its_job():
    # a step edge gets steeper; flat stays flat
    a = np.zeros((40, 40, 3), np.uint8)
    a[:, :20] = 60
    a[:, 20:] = 180
    b = C.unsharp(a, 0.525).astype(int)
    assert b[20, 19, 0] < 60 and b[20, 20, 0] > 180, (b[20, 18:22, 0])
    assert (b[:, :15] == 60).all() and (b[:, 25:] == 180).all()
    # an edge of the picture against an empty canvas does not ring (the canvas is not counted)
    c = np.zeros((40, 40, 4), np.uint8)
    c[..., :3] = 120
    c[:, 20:, 3] = 255
    d = C.unsharp(c, 1.5)
    assert (d[:, 20:, :3] == 120).all() and (d[:, :20] == c[:, :20]).all()
    # faint noise (±1 level) raised far less than the edge
    rng = np.random.default_rng(1)
    n = np.clip(80 + rng.integers(-1, 2, (60, 60, 3)), 0, 255).astype(np.uint8)
    n[..., 1] = n[..., 2] = n[..., 0]
    m = C.unsharp(n, 0.525).astype(int)
    assert np.abs(m - n).max() <= 1, np.abs(m - n).max()
    assert (C.unsharp(a, 0) == a).all()
    print("edges steeper, flat and empty canvas untouched, faint noise held to a level, 0 is off")


def test_real():
    folder = os.environ.get("SHARPEN_REAL")
    if not folder:
        return
    pics = [np.asarray(Image.open(f).convert("RGB"))[:400, :400].copy() for f in sorted(glob.glob(os.path.join(folder, "*.png")))[:8]]
    same(pics, 0.525, f"real ({folder})")


if __name__ == "__main__":
    test_conformance()
    test_does_its_job()
    test_real()
    print("ok")
