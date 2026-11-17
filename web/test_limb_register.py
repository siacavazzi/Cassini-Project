"""obs_mosaic._limb_register (a filter's match checked on the body's limb) and _solve_misfit, on made-up tiles: a
disk SPICE puts at the canvas origin, two tiles of one pointing showing its limb, one moved by a false match."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402

R = 900.0   # px: the disk's radius on the canvas


def _disk(gx, gy, fid):
    hit = np.hypot(gx, gy) <= R
    return hit, np.where(hit, 1.0, 0.0)


def _tile(n, at, true_at=None, fid="N1_1"):
    """a 512 px tile with its middle at `at` on the canvas, its picture drawn as if its middle were at true_at (the
    body's lit disk, its limb soft over 3 px): {report}, picture"""
    true_at = at if true_at is None else true_at
    yy, xx = np.mgrid[0:512, 0:512]
    r = np.hypot(xx - 256 + true_at[0] + 0.5, yy - 256 + true_at[1] + 0.5)
    g = (200 / (1 + np.exp((r - R) / 1.0))).astype(np.uint8)
    im = np.dstack([g, g, g, np.full_like(g, 255)])
    return {"n": n, "id": fid, "filter": "CB2", "offset": list(at), "box": [-256, -256, 512, 512]}, im


def _run(monkey_at, matched_at):
    om._disk_geometry = lambda u: _disk
    u = {"key": ["SATURN", "TEST", "N", 0]}
    # the reference where SPICE (and the truth) put it; the tile SPICE puts at monkey_at, truly there too, which a
    # match moved to matched_at
    q, ref = _tile(0, (700.0, 400.0))
    out, crop = _tile(1, matched_at, true_at=monkey_at)
    if matched_at != monkey_at:
        out["spice_offset"] = list(monkey_at)
        out["registered"] = {"to": "N0_1", "how": "phase", "shift": [monkey_at[0] - matched_at[0], monkey_at[1] - matched_at[1]]}
    om._limb_register(u, q, ref, out, crop)
    return out


def test_false_match_goes_back_on_the_limb():
    out = _run((690.0, 410.0), (680.0, 395.0))   # a 18 px false match
    # (back to SPICE's place, where both limbs agree: the limb puts it within a px across the limb)
    assert np.hypot(out["offset"][0] - 690, out["offset"][1] - 410) < 1.5, out
    assert out["registered"]["limb_off"] != 0


def test_good_match_kept():
    out = _run((690.0, 410.0), (690.5, 409.6))   # a sub-px match agrees with the limb
    assert out["offset"] == [690.5, 409.6]
    assert "limb_off" not in out["registered"]


def test_raw_pointing_moved_across_limb():
    # SPICE puts the tile 6 px off across the limb (radially) from where it truly is; no match found
    true_at = (690.0, 410.0)
    nrm = np.array(true_at) / np.hypot(*true_at)
    spice = tuple(np.array(true_at) + 6 * nrm)
    out, crop = _tile(1, spice, true_at=true_at)
    out["registered"] = {"to": "N0_1", "how": "not aligned", "kept": "SPICE's place"}
    q, ref = _tile(0, (700.0, 400.0))
    om._disk_geometry = lambda u: _disk
    om._limb_register({"key": ["SATURN", "TEST", "N", 0]}, q, ref, out, crop)
    assert np.hypot(out["offset"][0] - true_at[0], out["offset"][1] - true_at[1]) < 1.5, out
    assert out["registered"]["how"].startswith("limb")


def test_solve_misfit():
    meas = [(0, 1, np.array([5.0, 0.0]), np.eye(2), 1.0), (1, 2, np.array([0.0, 5.0]), np.eye(2), 1.0),
            (None, 2, np.array([5.0, 9.0]), np.outer([0, 1], [0, 1]), 1.0), ("limb", 1, "CB2", np.array([1.0, 0]), 3.0, 0.5)]
    moves = {0: [0, 0], 1: [5, 0], 2: [5, 5]}
    m = om._solve_misfit(meas, [0, 1, 2, 3], moves)
    assert m["kept"] == 3 and m["over"] == 1 and m["worst"] == 4.0 and not m["flag"]


if __name__ == "__main__":
    import calibration  # noqa: F401  (calibration.step reads the look; the default look aligns)
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
