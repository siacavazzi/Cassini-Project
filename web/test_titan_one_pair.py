"""One Titan pair set (obs_mosaic._pair_colour): a pass taking its CB3 pair once is in the pair's color when it takes
fewer than STEP_FRAMES frames of its grey filter and the set's frames are shown; with STEP_FRAMES or more grey frames,
or a pair frame lost past MOVIE_HOLD_LOST, it stays grey; two sets give the pair as before.
Run: python web/test_titan_one_pair.py"""
import sys; import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, "frames"), os.path.dirname(HERE)]
import obs_mosaic as om  # noqa: E402

NMS = {"CB3": 938.0, "MT1": 619.0, "BL1": 451.0}


def pass_of(filters, sets, lost=()):
    """A synthetic pass: frames through filters (ids F0, F1...), its colour sets as lists of frame positions, and the
    ids lost past MOVIE_HOLD_LOST."""
    frames = [(f"F{j}.png", f"F{j}", f, 100.0 * j, NMS[f]) for j, f in enumerate(filters)]
    om.colour_sets = lambda fr, sets=sets: [[(fr[j][2], j) for j in run] for run in sets]
    om.lost_share = lambda i, lost=lost: 1.0 if i in lost else 0.0
    u = {"key": ("TITAN", "ISS_TEST", "N", 0), "frames": frames, "kind": "movie"}
    count = {}
    for f in filters:
        count[f] = count.get(f, 0) + 1
    return u, count


u, count = pass_of(["CB3", "CB3", "CB3", "MT1"], [[0, 1, 2, 3]])
assert om._pair_colour(u, count, NMS) == ["CB3", "MT1"] and u.get("one_pair"), u
print("one CB3, CB3, CB3, MT1 set (3 grey frames): the pair, one_pair")

u, count = pass_of(["CB3", "CB3", "CB3", "CB3", "MT1"], [[3, 4]])
assert om._pair_colour(u, count, NMS) is None and not u.get("one_pair"), u
print("one set among 4 grey frames: grey")

u, count = pass_of(["CB3", "CB3", "CB3", "MT1"], [[0, 1, 2, 3]], lost={"F3"})
assert om._pair_colour(u, count, NMS) is None, u
print("one set whose MT1 frame lost too many lines: grey")

u, count = pass_of(["CB3", "MT1", "CB3", "MT1", "CB3", "CB3", "CB3"], [[0, 1], [2, 3]])
assert om._pair_colour(u, count, NMS) == ["CB3", "MT1"] and not u.get("one_pair"), u
print("two sets: the pair, as before")
print("ok")
