"""obs_mosaic._solve_moves (global panel registration) and _subpixel, on made-up matches and pictures."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import obs_mosaic as om  # noqa: E402


def _meas(true, pairs, noise=0.0, rng=None):
    out = []
    for a, b in pairs:
        d = np.array(true[b]) - np.array(true[a])
        if noise:
            d = d + rng.normal(0, noise, 2)
        out.append((a, b, d, np.eye(2), 1.0))
    return out


def test_chain_recovers_relative_places():
    rng = np.random.default_rng(1)
    true = {r: tuple(rng.normal(0, 4, 2)) for r in range(6)}
    pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 2), (3, 5)]
    moves, keep = om._solve_moves(list(true), _meas(true, pairs, 0.1, rng), 2.0)
    rel = lambda m, a, b: np.array(m[b]) - np.array(m[a])
    for a, b in pairs:
        assert np.linalg.norm(rel(moves, a, b) - rel(true, a, b)) < 0.5
    assert len(keep) == len(pairs)


def test_outlier_is_dropped():
    true = {0: (0, 0), 1: (3, 0), 2: (3, 3), 3: (0, 3)}
    pairs = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2), (1, 3)]
    meas = _meas(true, pairs)
    a, b, d, P, w = meas[0]
    meas[0] = (a, b, d + np.array([15.0, -9.0]), P, w)   # a false match
    moves, keep = om._solve_moves(list(true), meas, 2.0)
    assert 0 not in keep and len(keep) == 5
    assert abs((moves[1][0] - moves[0][0]) - 3) < 0.2


def test_edge_match_constrains_only_across():
    # one straight edge: only how far across it (x) is known; along it the prior keeps SPICE's place
    meas = [(0, 1, np.array([2.0, 0.0]), np.outer([1, 0], [1, 0]), 1.0)]
    moves, _ = om._solve_moves([0, 1], meas, 3.0)
    assert abs((moves[1][0] - moves[0][0]) - 2.0) < 0.1
    assert abs(moves[0][1]) < 1e-9 and abs(moves[1][1]) < 1e-9


def test_limb_anchors_with_haze():
    # three pointings round a limb (normals 60 degrees apart), each truly off by err; one filter's haze stands 7 px out.
    # A limb says o = haze - n.err (how far the picture's limb is out of SPICE's); the solve finds -err and the haze
    err = {0: np.array([3.0, -2.0]), 1: np.array([-1.0, 4.0]), 2: np.array([2.0, 2.0])}
    normals = {r: np.array([np.cos(a), np.sin(a)]) for r, a in zip(err, np.radians([-60, 0, 60]))}
    meas = [("limb", r, "CB2", normals[r], 7.0 + float(normals[r] @ err[r]), 1.0) for r in err]
    # and the pairs between them, as matches say (pointing b sits err b - err a from a: moves undo that)
    meas += [(a, b, -(err[b] - err[a]), np.eye(2), 1.0) for a, b in ((0, 1), (1, 2))]
    haze = {}
    moves, keep = om._solve_moves([0, 1, 2], meas, 2.0, haze)
    for r in err:
        # (within a px: over a 120 degree arc a haze height and a shift along the mean normal are told apart only
        # by how the normals spread, and SPICE's prior pulls the shared part of the moves toward none)
        assert np.linalg.norm(np.array(moves[r]) + err[r]) < 1.0, (r, moves[r], err[r])
    assert abs(haze["CB2"] - 7.0) < 1.0, haze


def test_no_matches_keeps_spice():
    moves, keep = om._solve_moves([0, 1, 2], [], 2.0)
    assert all(m == (0.0, 0.0) for m in moves.values()) and keep == []


def test_subpixel_moves_a_step_by_its_fraction():
    part = np.zeros((20, 40, 4), np.uint8)
    part[..., 3] = 255
    part[:, 20:, :3] = 200
    moved = om._subpixel(part, 0.5, 0.0)
    row = moved[10, :, 0].astype(float)
    # the step from 0 to 200 now sits half a pixel right: its middle pixel is about half way
    assert 60 < row[20] < 140 and row[18] < 10 and row[22] > 190


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name}: ok")
