"""The light unsharp mask every served picture ends in (color_image.unsharp): an edge gets steeper, flat areas and the
empty canvas round a picture are left as they are (no ring at a frame's or a tile's edge), faint noise is raised far
less than an edge, colour pictures get the same change in every channel, and the server applies it to its stills and
composites (frame_server.composite) and to every tile obs_mosaic draws (_part).
Run: python web/test_sharpen.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.dirname(HERE), os.path.join(HERE, "frames")]
import tempfile  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import color_image as C  # noqa: E402


def test_edge_flat_noise():
    a = np.zeros((40, 40, 3), np.uint8)
    a[:, :20] = 60
    a[:, 20:] = 180
    b = C.unsharp(a).astype(int)
    assert b[20, 19, 0] < 60 and b[20, 20, 0] > 180, b[20, 18:22, 0]
    assert (b[:, :15] == 60).all() and (b[:, 25:] == 180).all()
    # colour: the same change in every channel
    c = a.copy(); c[..., 1] = np.clip(a[..., 1].astype(int) - 20, 0, 255); c[..., 2] = np.clip(a[..., 2].astype(int) + 30, 0, 255)
    d = C.unsharp(c).astype(int) - c.astype(int)
    assert (d[..., 0] == d[..., 1]).all() and (d[..., 0] == d[..., 2]).all()
    # faint noise (+-1 level) held to a level
    rng = np.random.default_rng(1)
    n = np.clip(80 + rng.integers(-1, 2, (60, 60)), 0, 255).astype(np.uint8)
    assert np.abs(C.unsharp(n).astype(int) - n).max() <= 1
    # the picture's own edge against the empty canvas does not ring, and the canvas stays as it is
    e = np.zeros((40, 40, 4), np.uint8)
    e[..., :3] = 120
    e[:, 20:, 3] = 255
    f = C.unsharp(e, 1.5)
    assert (f[:, 20:, :3] == 120).all() and (f[:, :20] == e[:, :20]).all()
    # grey with alpha (LA), and the frame's border in an opaque picture
    la = np.dstack([np.full((30, 30), 90, np.uint8), np.full((30, 30), 255, np.uint8)])
    assert (C.unsharp(la) == la).all()
    assert (C.unsharp(np.full((30, 30, 3), 200, np.uint8)) == 200).all()
    assert (C.unsharp(a, 0) == a).all()
    print("edges steeper; flat, borders and empty canvas untouched; faint noise held to a level; same change in every channel")


def test_tiles_sharpened():
    import obs_mosaic as om
    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    t = np.zeros((64, 64, 4), np.uint8)
    t[..., 3] = 255
    t[:, :32, :3] = 50
    t[:, 32:, :3] = 200
    Image.fromarray(t).save(f"{tmp}/0.png")
    part = om._part(f"{tmp}/0.png", 64, 64)
    assert (part == C.unsharp(t)).all() and part[10, 31, 0] < 50 and part[10, 32, 0] > 200
    print("obs_mosaic._part: every tile drawn (movies, mosaics, planes) is sharpened at the size it is drawn")


if __name__ == "__main__":
    test_edge_flat_noise()
    test_tiles_sharpened()
    print("ok")
