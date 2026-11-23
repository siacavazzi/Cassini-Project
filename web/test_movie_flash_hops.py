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


def test_follow_inside_body():
    # a stare whose frames all lie inside the body's disk follows its frame (follows, filled); one showing the limb not
    S = om.FRAME
    frames = [("p", f"F{j}", "CL1/CL2", 100.0 * j, 0, 0.0, 20000.0 - 45 * j, 370000.0) for j in range(20)]
    u = {"key": ("SATURN", "OBS", "N", 0), "frames": frames, "z": 370000.0}
    assert om._inside_body(u)
    u2 = dict(u, frames=frames[:-1] + [frames[-1][:6] + (27000.0, 370000.0)])
    assert not om._inside_body(u2)
    fp = (0.0, 0.0, 2 * om.HALF + 0.5 * S, 2 * om.HALF + 0.3 * S)
    rect = (1.0, 2.0, fp[2], fp[3])
    assert om.follows(fp, rect, True) and not om.follows(fp, rect, False)


def test_veiled_frame_same_view():
    # a lone frame lit all over among its filter's dark ones at the same view is veiled (Skathi 2011); at another view
    # (101SA AURORA003's wider clear frame) it is that view's first picture, not a veil
    frames = [("p", f"F{j}", "CL1/CL2", 100.0 * j) for j in range(5)]
    tile = lambda lit, x=0.0, w=1024.0: {"offset": [x, 0.0], "box": [-w / 2, -w / 2, w, w], "lit": lit}
    tiles = [tile(0.01), tile(0.02), tile(0.8), tile(0.01), tile(0.02)]
    assert om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[2] = tile(0.8, x=900.0)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[2] = tile(0.8, w=2048.0)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[2], tiles[3] = tile(0.8), tile(0.3)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[3] = {k: v for k, v in tile(0.0).items() if k != "lit"}   # (not measured: not known dark)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    # a run of veiled frames (Skathi 2011's 48-50) between dark ones: each is veiled; a run past VEIL_RUN is not
    frames = [("p", f"F{j}", "CL1/CL2", 100.0 * j) for j in range(9)]
    tiles = [tile(0.01), tile(0.02), tile(0.8), tile(0.7), tile(0.8), tile(0.01)] + [tile(0.01)] * 3
    assert all(om.veiled_frame(frames, n, lambda j: tiles[j]) for n in (2, 3, 4))
    tiles = [tile(0.01)] + [tile(0.8)] * (om.VEIL_RUN + 1) + [tile(0.01)] * (8 - om.VEIL_RUN)
    assert not any(om.veiled_frame(frames, n, lambda j: tiles[j]) for n in range(1, om.VEIL_RUN + 2))


def test_step_frame_keeps_time_order():
    # Titan 2016 (245TI M90R1CLD288): CB3 frames, then MT1-MT3, RED, GRN, BL1, UV3, UV1, UV2, then CB3 again. On Titan
    # every other filter takes the CB3 frame; elsewhere only the held bands do, and never across a frame that plays its
    # own picture (UV3 at frame 9 does not step back to frame 2 after RED, GRN and BL1 played)
    fs = ["CB3"] * 3 + ["MT1", "MT2", "MT3", "RED", "GRN", "BL1", "UV3", "UV1", "UV2"] + ["CB3"] * 3
    times = [0, 110, 220, 314, 408, 550, 606, 661, 709, 819, 1889, 2409, 2481, 2591, 2701]
    ok = lambda j: True
    for takes, want in ((lambda i: fs[i] != "CB3", [0, 1, 2] + [2] * 7 + [12, 12, 12, 13, 14]),
                        (lambda i: om.held_band(fs[i]), [0, 1, 2, 2, 2, 2, 6, 7, 8, 12, 12, 12, 12, 13, 14])):
        got = [om.step_frame(fs, s, "CB3", ok, ok, times, om.HOLD_REACH if takes(s) else None, takes) for s in range(len(fs))]
        assert got == want, got
        assert all(a <= b for a, b in zip(got, got[1:])), got   # (never back in time)


def test_veiled_speck_by_sky():
    # a speck's frame has no lit share kept; its sky (median level) tells a gray veil: Mundilfari 2007's lone RED frame
    # between BL1 and IR2 frames with black skies, Methone 2012's 1 s frame between 10 s and 100 s ones
    tile = lambda sky, x=0.0: {"offset": [x, 0.0], "box": [-512.0, -512.0, 1024.0, 1024.0], "sky": sky}
    frames = [("p", f"F{j}", f, 100.0 * j) for j, f in enumerate(["BL1", "BL1", "RED", "IR2", "IR2"])]
    tiles = [tile(0), tile(1), tile(30), tile(0), tile(1)]
    assert om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[3] = tile(12)                     # (a neighbour neither dark nor veiled: not a veil)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    tiles[3] = tile(0)
    tiles[2] = tile(10)                     # (a sky under VEIL_SKY: what the camera saw)
    assert not om.veiled_frame(frames, 2, lambda j: tiles[j])
    # the movie's last two frames veiled after dark ones (Mundilfari 2007's clear frames); a movie all veil is not
    tiles = [tile(0), tile(1), tile(0), tile(26), tile(25)]
    assert om.veiled_frame(frames, 3, lambda j: tiles[j]) and om.veiled_frame(frames, 4, lambda j: tiles[j])
    tiles = [tile(30)] * 3
    assert not any(om.veiled_frame(frames[:3], n, lambda j: tiles[j]) for n in range(3))
    # a neighbour lost in part (partial) is passed over: Methone 2012's veiled 17 beside its 85%-lost 18
    tiles = [tile(0), tile(0), tile(35), {**tile(0), "lost": 0.85, "box": [-492.0, -492.0, 154.0, 984.0]}, tile(0)]
    frames = [("p", f"F{j}", "CL1/CL2", 100.0 * j) for j in range(5)]
    assert om.veiled_frame(frames, 2, lambda j: tiles[j])


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
