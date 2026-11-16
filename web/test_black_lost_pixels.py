"""A narrow-angle movie frame's own black (obs_mosaic.tile_scale's black_of, clean_lost) is measured without the
frame's lost pixels. Pixels lost in downlink that nothing filled are border columns that are never drawn, and hold junk
of either sign: up to 5 times the pass's white in 133TI CLOUD002. The black is measured on every 4th pixel, which meets
some of those columns: negative junk was already taken out as far under the sky, positive junk was not, and one such
column is 0.39% of that picture, over the 0.1% that sets the frame's brightest (the 99.9th percentile its sky is under
5% of). Most of the body then counted as sky and the frame's black went far over its neighbours', whichever frames
met positive junk: one channel of every second or third picture of the movie on another black, the movie flickering
between two colours. A wide-angle frame is measured as it was (a stand-in until its look has a rule of its own: its
black has always been set by such junk). Synthetic I/F. Run: python web/test_black_lost_pixels.py"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import obs_mosaic as om  # noqa: E402

rng = np.random.default_rng(11)
scale = {"blacks": {"CB3": 0.002}, "sky_tops": {"CB3": 0.001}, "toe": 0.002, "white": 0.3, "gamma": 1.5}


def frame():
    """A hazy body: a disk whose brightness falls away slowly past its limb into the sky, on a sky in whole codes."""
    y, x = np.mgrid[:1024, :1024].astype(np.float32)
    r = np.hypot(x - 600, y - 500)
    body = np.where(r < 330, 0.3, 0.3 * np.exp(-(r - 330) / 60))
    sky = 0.004 + 0.0004 * np.round(rng.normal(0, 1, (1024, 1024)))
    return (body + sky).astype(np.float32)


clean = frame()
lost = clean.copy()
valid = np.ones(clean.shape, bool)
valid[:, :2] = valid[:, -2:] = False                      # its outermost columns lost, and junk left in them
lost[~valid] = rng.uniform(-3.5, 5.0, int((~valid).sum())).astype(np.float32) * scale["white"]


def black(iof, valid=None, **how):
    seen = {}
    of = om.tile_scale(scale, "CB3", True, seen, **how)["black_of"]
    got = of(iof) if valid is None else of(iof, valid)
    return got["black"] if got else None


whole = black(clean)
fooled = black(lost)
steady = black(lost, valid, clean_lost=True)
print("whole frame", whole, "lost columns counted", fooled, "lost columns left out", steady)
assert whole is not None and fooled is not None and steady is not None
assert fooled > whole + 0.01 * scale["white"], "the junk is what moved the black (the fault this test is about)"
assert abs(steady - whole) < 0.002 * scale["white"], "without its lost pixels the frame's black is its neighbours'"
# a frame that lost nothing is measured on every pixel, the same to the last digit, with a mask or without
assert black(clean, np.ones(clean.shape, bool), clean_lost=True) == whole
# negative junk never fooled it (the rule that takes out pixels far under the sky): the same black either way
under = clean.copy()
under[~valid] = -rng.uniform(1.0, 3.5, int((~valid).sum())).astype(np.float32) * scale["white"]
assert abs(black(under) - whole) < 0.002 * scale["white"] and abs(black(under, valid, clean_lost=True) - whole) < 0.002 * scale["white"]
# a wide-angle frame (clean_lost off, as tile_scale is called for it) is measured as it was, lost pixels and all
assert black(lost, valid) == fooled and black(lost, valid, clean_lost=False) == fooled
# load_channels hands the mask on: the picture drawn with it is the clean frame's where both are valid
import calibration  # noqa: E402


class L:
    pass


def drawn(iof, valid):
    sc = om.tile_scale(scale, "CB3", True, clean_lost=True)
    return calibration.load_channels([L()], [np.zeros(iof.shape, np.uint8)], iofs=[iof], scale=sc, valid=valid)[0]


a, b = drawn(clean, None), drawn(lost, [valid])
inside = valid if a.ndim == 2 else valid[..., None] & np.ones(a.shape, bool)
assert np.abs(a.astype(int) - b.astype(int))[inside].max() <= 1, "the frame that lost its edge columns is drawn as the whole one"
print("ok")
