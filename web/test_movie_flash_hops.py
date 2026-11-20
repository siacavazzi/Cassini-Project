"""Four movie defects the 11-20 regression sweep found, each on made-up pictures:
- tinted_frame on a small body: Jupiter 80 px across a WAC movie, every frame tinted from its colour set. The match was
  measured over the 99th percentile of the whole overlap, which is sky, so the brightness followed the sky's noise and
  the same set and frame came out blown white, gray or yellow. Here the tinted disk's brightness is the same whatever
  noise the sky holds, and close to the frame's own.
- _lone_ends: a movie that opens on one frame of the stare before it (289SA AURSTARE001 N_3) is cut after that frame,
  one that goes back and forth between two places is not.
- _shift_onto: the square round a small target is matched only when both pictures show the target there; otherwise
  the whole of both is matched (Albiorix, never seen in its frames: its stars).
Run: python web/test_movie_flash_hops.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

om._onto_frame = lambda colour, grey: colour     # (the set already sits on the frame here)


def disk_pictures(seed, S=1024, R=30):
    """A disk under 1% of the picture on a faint sky: a level or two of glow, its own in each picture (another
    exposure, another filter), and a sprinkle of noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:S, :S]
    disk = np.hypot(xx - S / 2, yy - S / 2) < R
    sky = lambda level: np.clip(level + rng.integers(-1, 2, (S, S)), 0, 255)
    grey = np.zeros((S, S, 4), np.uint8)
    grey[..., :3] = np.where(disk, 185, sky(1 + seed % 2))[..., None].astype(np.uint8)
    grey[..., 3] = 255
    colour = np.zeros((S, S, 4), np.uint8)
    for c, v in enumerate((213, 210, 191)):
        colour[..., c] = np.where(disk, v, sky(2 + seed % 3)).astype(np.uint8)
    colour[..., 3] = 255
    return colour, grey, disk


def test_small_body_tint_steady():
    got = []
    for seed in range(4):
        colour, grey, disk = disk_pictures(seed)
        out = om.tinted_frame(colour, grey, 3.0, same=True)
        got.append(np.median(out[..., :3][disk], axis=0))
    got = np.array(got)
    assert np.ptp(got, axis=0).max() <= 2, got        # one look whatever the sky's noise
    assert got.max() < 250, got                         # not blown white
    assert got[:, 2].min() > 0.75 * got[:, 0].max(), got   # not yellow


def test_lone_ends():
    F = om.FRAME
    stare = [(6500.0, 21000.0 - 45 * k) for k in range(12)]
    xy = np.array([(60.0, 20700.0)] + stare)
    assert om._lone_ends(xy) == [1], om._lone_ends(xy)
    xy = np.array(stare + [(3800.0, 19300.0)])
    assert om._lone_ends(xy) == [12], om._lone_ends(xy)
    back_and_forth = np.array([(0.0, 0.0) if k % 2 else (3 * F, 0.0) for k in range(12)])
    assert om._lone_ends(back_and_forth) == []
    assert om._lone_ends(np.array(stare)) == []


def test_square_needs_the_target():
    S = 400
    rng = np.random.default_rng(1)

    def tile(dot):
        im = np.zeros((S, S, 4), np.uint8)
        im[..., :3] = np.clip(rng.normal(2, 3, (S, S)), 0, 255)[..., None].astype(np.uint8)
        if dot:
            im[S // 2 - 2:S // 2 + 2, S // 2 - 2:S // 2 + 2, :3] = 200
        im[..., 3] = 255
        return im
    t = {"n": 1, "offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]}
    q = {"n": 0, "offset": [0.0, 0.0], "box": [-S / 2, -S / 2, S, S]}
    kw = dict(around=(0.0, 0.0, om.STEADY_AROUND), kept=(0.0, 0.0, 2.0))
    _, how = om._shift_onto(q, tile(False), (0.0, 0.0), t, tile(False), (0.0, 0.0), **kw)
    assert str(how).startswith("target not seen"), how
    _, how = om._shift_onto(q, tile(True), (0.0, 0.0), t, tile(False), (0.0, 0.0), **kw)
    assert str(how).startswith("target not seen"), how
    _, how = om._shift_onto(q, tile(True), (0.0, 0.0), t, tile(True), (0.0, 0.0), **kw)
    assert not str(how).startswith("target not seen"), how


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
