"""Rules behind three defects the benchmark checks found on main (2026-11-19):
- natural color takes HAL in RED's place in a set with no RED (the 1999 Moon, HAL/GRN/BL1, was drawn exactly gray);
- a channel that matched nothing is placed by SPICE when it is itself flat (the 2012 north polar vortex's UV3 haze);
- in a movie playing in colour, a frame with no gray-filter frame near shows the picture before its run (127TI's P60
  and GRN frames flashed their own look).
Run: python web/test_known_defects.py"""
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web", "frames"))
os.chdir(ROOT)

import calibration  # noqa: E402
import image_correction as ic  # noqa: E402


def test_hal_stands_in_for_red():
    assert calibration.natural_mix("W", ["HAL", "GRN", "BL1"]) is not None
    assert np.allclose(calibration.natural_mix("W", ["HAL", "GRN", "BL1"]), calibration.natural_mix("W", ["RED", "GRN", "BL1"]))
    assert calibration.natural_mix("W", ["HAL", "RED", "GRN"]) is None   # (a set with RED keeps it)
    assert calibration.natural_mix("N", ["MT2", "GRN", "BL1"]) is None
    assert calibration.natural_mix("N", ["HAL", "GRN", "BL1"]) is None   # (the NAC's are night-side lightning searches)


def test_flat_channel_placed_by_spice():
    rng = np.random.default_rng(4)
    yy, xx = np.mgrid[:400, :400]
    detail = (120 + 60 * np.sin(xx / 6.0) * np.cos(yy / 9.0) + rng.normal(0, 2, (400, 400))).clip(0, 255).astype(np.uint8)
    flat = (150 + rng.normal(0, 0.6, (400, 400))).clip(0, 255).astype(np.uint8)
    detail, flat = (np.repeat(a[..., None], 3, axis=2) for a in (detail, flat))   # (the matcher takes BGR pictures)
    mask = np.ones((400, 400), bool)
    g = (6.0, -4.0)
    shift, how = ic._match(detail, flat, g, mask, mask, filled=True)
    assert shift is not None and "nothing to fringe" in how, how
    # two frames with detail that do not match stay unplaced (no fringe made up)
    other = np.repeat((120 + 60 * np.cos(xx / 4.0 + 1) * np.sin(yy / 5.0)).clip(0, 255).astype(np.uint8)[..., None], 3, axis=2)
    shift, how = ic._match(detail, other, (40.0, 40.0), mask, mask)
    assert "nothing to fringe" not in how, how


def test_lone_frame_holds_the_picture_before():
    import obs_mosaic as om
    # a pass playing in colour (CB3 its gray filter, CB3+MT1 sets), frames 4 (P60) and 6 (GRN) over HOLD_AGE from any CB3
    t = [0, 60, 120, 180, 2100, 2160, 4300, 4700, 4760]
    f = ["CB3", "MT1", "CB3", "MT1", "P60", "MT1", "GRN", "CB3", "MT1"]
    u = {"key": ("TITAN", "OBS", "N", 0), "frames": [("p", f"N{i}_1", f[i], t[i]) for i in range(len(t))]}
    p = {"colour": ["CB3", "MT1"], "grey": "CB3"}
    tiles = {j: {"offset": [0, 0], "box": [0, 0, 100, 100]} for j in range(len(t))}
    sets = [[("CB3", 0), ("MT1", 1)], [("CB3", 2), ("MT1", 3)], [("CB3", 7), ("MT1", 8)]]
    u["_sets"] = sets
    orig = (om.over_exposed, om.unit_of)
    om.over_exposed = lambda tile: False
    try:
        not_shown = lambda j: False
        tile_of = lambda j: tiles[j]
        own = om._shown_of(u, p, 4, not_shown, tile_of)
        assert own[3], own                  # P60: a held band with nothing near
        lone = om._shown_of(u, p, 6, not_shown, tile_of)
        assert lone[3], lone                # GRN: not the gray filter, no CB3 within HOLD_AGE
        for n in (4, 5, 6):
            assert om.shown_of(u, p, n, not_shown, tile_of) == om.shown_of(u, p, 3, not_shown, tile_of)[:3], n
        assert om.held_back(u, p, 4, not_shown, tile_of)
        assert not om.held_back(u, p, 2, not_shown, tile_of)
        # another body (no surface window): the lone GRN is its own moment and plays; the P60 still holds
        u2 = {**u, "key": ("TELESTO", "OBS", "N", 0), "_sets": sets}
        assert not om._shown_of(u2, p, 6, not_shown, tile_of)[3]
        assert om._shown_of(u2, p, 4, not_shown, tile_of)[3]
    finally:
        om.over_exposed, om.unit_of = orig


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
