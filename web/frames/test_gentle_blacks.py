"""Gentler blacks on made-up pictures: the sky's grain leaves its slow glow out (calibration.sky_grain, the balanced
margin), a low-contrast close-up spreads only as far as its grain allows (calibration._flat_black), and a movie's black
follows its sky through time (obs_mosaic.sky_track / track_black).  python web/frames/test_gentle_blacks.py (or pytest)"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
import calibration  # noqa: E402
import obs_mosaic  # noqa: E402


def _titan(glow=0.002, noise=0.00016, seed=0):
    """a bright disk on sky 0.0016 I/F with a scattered-light halo round it up to glow over the sky"""
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((512, 512))
    r = np.hypot(yy - 256, xx - 256)
    iof = 0.0016 + glow * np.exp(-np.maximum(r - 60, 0) / 40.0) + rng.normal(0, noise, r.shape)
    iof[r < 60] = 0.3
    return iof.astype(np.float32), r


def test_grain_leaves_the_glow_out():
    iof, r = _titan()
    sky = r >= 60
    raw = float(np.percentile(iof[sky], 98) - np.median(iof[sky]))
    grain = calibration.sky_grain([iof], [sky])
    spread = float(np.percentile(grain, 98) - np.median(grain))
    assert spread < 0.0006 < raw, (spread, raw)
    # sky_levels' margin with a floor percentile is now the grain's
    _, margin = calibration.sky_levels([[iof]], [[sky]], floor_pct=98)
    assert spread < margin < 0.7 * raw, (margin, raw)   # the grain plus GRAIN_GLOW of the glow over it


def test_grain_of_a_plain_sky_is_its_spread():
    iof, r = _titan(glow=0.0)
    sky = r >= 60
    raw = float(np.percentile(iof[sky], 98) - np.median(iof[sky]))
    grain = calibration.sky_grain([iof], [sky])
    spread = float(np.percentile(grain, 98) - np.median(grain))
    assert abs(spread - raw) < 0.15 * raw, (spread, raw)


def _deck(contrast, noise, seed=1):
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((512, 512))
    lum = 0.5 * (1 - contrast) + 0.5 * contrast * (0.5 + 0.5 * np.sin(xx / 30.0) * np.cos(yy / 45.0))
    return (lum + rng.normal(0, noise, lum.shape)).astype(np.float32)


def test_flat_clean_deck_spreads():
    lum = _deck(0.2, 0.0005)
    lit = np.ones(lum.shape, bool)
    floor, top = (float(v) for v in np.percentile(lum, (calibration.FLOOR_PCT, calibration.WHITE_PCT)))
    old = min(calibration.FLOOR_SHARE * floor, calibration._floor_cap(top))
    new = calibration._flat_black(lum, lit, lum, top, old)
    assert new > old
    assert new <= calibration.FLAT_SHARE * float(np.percentile(lum, calibration.FLAT_PCT)) + 1e-9
    # the stretch now shows the deck's contrast: its floor well under the top on the new scale
    assert (floor - new) / (top - new) < 0.7 * (floor - old) / (top - old)


def test_flat_noisy_deck_stretches_less():
    clean, noisy = _deck(0.2, 0.0005), _deck(0.2, 0.01)
    got = []
    for lum in (clean, noisy):
        lit = np.ones(lum.shape, bool)
        floor, top = (float(v) for v in np.percentile(lum, (calibration.FLOOR_PCT, calibration.WHITE_PCT)))
        old = min(calibration.FLOOR_SHARE * floor, calibration._floor_cap(top))
        got.append(calibration._flat_black(lum, lit, lum, top, old) - old)
    assert got[1] < got[0], got


def test_contrasty_picture_unchanged():
    lum = _deck(0.9, 0.0005)
    lit = np.ones(lum.shape, bool)
    floor, top = (float(v) for v in np.percentile(lum, (calibration.FLOOR_PCT, calibration.WHITE_PCT)))
    old = min(calibration.FLOOR_SHARE * floor, calibration._floor_cap(top))
    assert calibration._flat_black(lum, lit, lum, top, old) == old


def test_sky_track_follows_the_sky_and_ignores_one_frame():
    rng = np.random.default_rng(2)
    qs, masks, ts = [], [], []
    for i in range(11):
        sky = 0.001 + 0.0001 * i + (0.01 if i == 5 else 0.0)   # rising sky, one frame of stray light
        q = (sky + rng.normal(0, 0.00005, (64, 64))).astype(np.float32)
        q[20:40, 20:40] = 0.3
        q[:, 0] = -1.0                                          # a lost column
        qs.append(q)
        masks.append(obs_mosaic._dark_sky(q))
        ts.append(100.0 * i)
    track = obs_mosaic.sky_track(qs, masks, ts, 0.0002)
    assert len(track) == 11
    b = [p[1] for p in track]
    assert b[5] < 0.002, b[5]                          # the stray-light frame does not set it
    assert b[0] < b[-1]                                # it rises with the sky
    assert abs(obs_mosaic.track_black(track, 50.0) - (b[0] + b[1]) / 2) < 1e-9
    assert obs_mosaic.track_black(track, -10.0) == b[0]


def test_tile_scale_raises_to_the_track():
    scale = {"blacks": {"CL1": 0.005}, "white": 0.3, "gamma": 3.0, "sky_track": {"CL1": [[0.0, 0.001], [10.0, 0.002]]}}
    out = obs_mosaic.tile_scale(scale, "CL1", own_sky=True, t=5.0, on_body=True)
    assert out["blacks"][0] == 0.005                   # never under the pass's black
    scale["sky_track"]["CL1"] = [[0.0, 0.006], [10.0, 0.008]]
    out = obs_mosaic.tile_scale(scale, "CL1", own_sky=True, t=5.0, on_body=True)
    assert abs(out["blacks"][0] - 0.007) < 1e-9        # over it where the frame's sky is
    assert "sky_track" not in out
    assert obs_mosaic.tile_scale(scale, "CL1", own_sky=False, t=5.0)["blacks"][0] == 0.005   # mosaics keep the pass's



if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
