#!/usr/bin/env python3
"""A frame's merge handed on from a pass's plan to its tile (stacking.hand_on, obs_mosaic.pass_scale): the tile's
load_hdr call takes the very answer the plan worked out, once, only in the same display model, only while there is
room, and a new pass's plan lets go of what was left; the plan's scale is the same with and without it, also where
the frames merged lost different pixels (the merge with their masks is another picture than the plain one there).
Made-up frames, as web/test_lost_lines.py makes them.
Run: python web/test_hdr_hand_on.py"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np  # noqa: E402
import calibration as cal  # noqa: E402
import obs_mosaic as om  # noqa: E402
import stacking  # noqa: E402

H = 64
rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:H, 0:H]
disk = np.hypot(xx - 32, yy - 30) < 20
base = np.where(disk, 120, 8).astype(np.uint8)
frames = {name: np.clip(base + rng.integers(-3, 4, (H, H)), 0, 255).astype(np.uint8) for name in "abcdefgh"}
whole = np.ones((H, H), bool)
lost = whole.copy()
lost[20:26, 10:50] = False      # lines a.png lost and its repeat b.png has


class Label:
    def __init__(self, path, mask):
        self.mask = mask
        self.info = {"path": path, "EXPOSURE_DURATION": 100.0, "GAIN_MODE_ID": "12", "INSTRUMENT_MODE_ID": "FULL"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return self.mask

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return pngs[self.info["path"]]


pngs = {f"{n}.png": np.dstack([f] * 3) for n, f in frames.items()}
pngs["a.png"] = np.where(lost[..., None], pngs["a.png"], 0).astype(np.uint8)
labels = {p: Label(p, lost if p == "a.png" else whole) for p in pngs}
repeats = {"a.png": ["a.png", "b.png"], "c.png": ["c.png", "d.png"]}      # a and c have a repeat, the rest are alone
calls = []
stacking.find_repeats = lambda path, window=120, max_frames=5: repeats.get(path, [path])[:max_frames]
stacking.lh.label = lambda p, as_png=True: labels[p]
stacking.ic.find_shift = lambda a, b, r: None
stacking.places = lambda ids, reach=False: {i: (0.0, 0.0, 1.0e5) for i in ids}
stacking.ds.imread = lambda path, flags=None: pngs[path][..., 0]
cal.calibrate = lambda codes, info, image=None: (calls.append(info["path"]), codes.astype(np.float32) / 1000)[1]
cal.depth_image = lambda codes, info, scale=None: np.asarray(codes, np.float32)   # (no archive here: lut8 unknown)
cal.saturated = lambda codes, info, image=None: np.zeros(codes.shape, bool)


def same(a, b):
    return len(a) == len(b) and all(x is y if not isinstance(x, np.ndarray) else
                                    (x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes()) for x, y in zip(a, b))


# ---------- the merge handed on is the one the next call would work out, and is taken once ----------
fresh = stacking.load_hdr("c.png", 120, valid=True, clipped=True)
note = {}
plan = stacking.load_hdr("c.png", 120, valid=True, clipped=True, note=note)
assert note == {"differ": False} and same(fresh, plan)
assert stacking.hand_on("c.png", 120, plan) and not stacking.hand_on("c.png", 120, plan)     # (one waits, not two)
del calls[:]
tile = stacking.load_hdr("c.png", 120, valid=True, clipped=True)
assert all(x is y for x, y in zip(tile, plan)) and not calls, "the tile worked the merge out again"
again = stacking.load_hdr("c.png", 120, valid=True, clipped=True)
assert calls == ["c.png", "d.png"] and same(again, fresh) and again[1] is not plan[1]       # (taken once)
# only the call the tile makes takes it: another window, a plain call or the plan's own (with a note) works it out
stacking.hand_on("c.png", 120, plan)
for kw in (dict(window=60, valid=True, clipped=True), dict(window=120), dict(window=120, valid=True),
           dict(window=120, clipped=True), dict(window=120, valid=True, clipped=True, note={})):
    del calls[:]
    stacking.load_hdr("c.png", **kw)
    assert calls, kw
# ... and only in the display model it was worked out in (a step turned off is another merge)
with cal.stepping(["hdr"]):
    del calls[:]
    stacking.load_hdr("c.png", 120, valid=True, clipped=True)
    assert calls
with cal.looking("classic"):
    del calls[:]
    stacking.load_hdr("c.png", 120, valid=True, clipped=True)
    assert calls
del calls[:]
assert stacking.load_hdr("c.png", 120, valid=True, clipped=True)[1] is plan[1] and not calls
print("handed on, taken once, by the same call in the same display model")

# ---------- room, and a new pass ----------
keep = stacking.HANDED_MB
one = stacking._handed_size(plan)
assert one == plan[1].nbytes + plan[3].nbytes + plan[4].nbytes
stacking.handing(("A", "obs", "N", 0))
stacking.HANDED_MB = 2 * one / (1 << 20)            # room for two
got = [stacking.hand_on(f"{n}.png", 120, stacking.load_hdr(f"{n}.png", 120, valid=True, clipped=True, note={})) for n in "efgh"]
assert got == [True, True, False, False] and not stacking.hand_room(), got
stacking.load_hdr("e.png", 120, valid=True, clipped=True)                 # a tile takes one: room again
assert stacking.hand_room() and stacking._handed_state["bytes"] == one
stacking.handing(("A", "obs", "N", 0))                                    # the same pass's plan again: kept
assert len(stacking._handed) == 1
stacking.handing(("B", "obs", "N", 0))                                    # another pass: let go
assert not stacking._handed and stacking._handed_state["bytes"] == 0 and stacking.hand_room()
stacking.HANDED_MB = keep
print("room for what fits; a new pass's plan lets go of the rest")

# ---------- frames that lost different pixels: the merge with their masks is another picture, and says so ----------
note = {}
masked = stacking.load_hdr("a.png", 120, valid=True, clipped=True, note=note)
plain = stacking.load_hdr("a.png", 120)
assert note == {"differ": True} and not np.array_equal(masked[1], plain[1])
note = {}
alone = stacking.load_hdr("e.png", 120, valid=True, clipped=True, note=note)
assert note == {"differ": False} and np.array_equal(alone[1], stacking.load_hdr("e.png", 120)[1])

# ---------- the plan's scale: the same with the merges handed on as without, and the tiles then take them ----------
u = {"key": ("TESTBODY", "ISS_TEST_HAND", "N", 0), "frames": [(f"{n}.png", f"N{k}_1", "CL1/CL2", 1000.0 + 60 * k, 600, None, None, None)
                                                              for k, n in enumerate("acefgh")]}
stacking.handing(None)
stacking.HANDED_MB = 0                      # no room: every frame merged plainly, as before
before = om.pass_scale(u["frames"], u)
assert not stacking._handed
stacking.HANDED_MB = keep
del calls[:]
after = om.pass_scale(u["frames"], u)
assert after == before, (before, after)
assert len(stacking._handed) == 6           # every frame's merge waits for its tile, a.png's too (its masked one)
assert calls.count("a.png") == 2 and calls.count("c.png") == 1, calls     # a.png's plain merge too, for the scale
del calls[:]
for n in "acefgh":
    got = stacking.load_hdr(f"{n}.png", 120, valid=True, clipped=True)
    want = masked if n == "a" else None
    assert want is None or same(got, want)
assert not calls and not stacking._handed and stacking._handed_state["bytes"] == 0

# ---------- past the memory's room a merge waits in a file, and comes back equal to the bit ----------
import glob  # noqa: E402
import tempfile  # noqa: E402

root = tempfile.mkdtemp(prefix="handed-test-")
try:
    # (a folder left by a process of this machine that is gone is removed; one of a live process or another machine stays)
    gone = os.path.join(root, f"{stacking._host()}-999999")
    mine = os.path.join(root, f"{stacking._host()}-{os.getppid()}")
    other = os.path.join(root, "anothermac-999999")
    for d in (gone, mine, other):
        os.makedirs(d)
    stacking.hand_to(root)
    assert not os.path.exists(gone) and os.path.exists(mine) and os.path.exists(other)
    stacking.handing(("C", "obs", "N", 0))
    stacking.HANDED_MB = one / (1 << 20)                # memory room for one; the rest to files
    wants = {n: stacking.load_hdr(f"{n}.png", 120, valid=True, clipped=True, note={}) for n in "aefgh"}
    assert all(stacking.hand_room() and stacking.hand_on(f"{n}.png", 120, wants[n]) for n in "aefgh")
    folder = os.path.join(root, f"{stacking._host()}-{os.getpid()}")
    assert len(glob.glob(os.path.join(folder, "*.merge"))) == 4 and stacking._handed_state["bytes"] == one
    assert stacking._handed_state["disk"] == 4 * one
    # (a bit a pixel for the masks: a file is smaller than its arrays)
    assert all(os.path.getsize(f) < one for f in glob.glob(os.path.join(folder, "*.merge")))
    del calls[:]
    for n in "aefgh":
        got = stacking.load_hdr(f"{n}.png", 120, valid=True, clipped=True)
        assert same(got, wants[n]), n                   # (the label and the count the very ones, the arrays equal to the bit)
        assert got[0] is wants[n][0] and got[1].flags.writeable and got[3].dtype == np.bool_
    assert not calls and not glob.glob(os.path.join(folder, "*.merge")) and stacking._handed_state["disk"] == 0
    # taken once, as from memory
    stacking.load_hdr("e.png", 120, valid=True, clipped=True)
    assert calls == ["e.png"]
    # room on disk too: past HANDED_DISK_MB nothing more waits
    keep_disk = stacking.HANDED_DISK_MB
    stacking.HANDED_DISK_MB = 2 * one / (1 << 20)
    got = [stacking.hand_on(f"{n}.png", 120, wants[n]) for n in "efgh"]
    assert got == [True, True, True, False] and not stacking.hand_room(), got
    stacking.HANDED_DISK_MB = keep_disk
    # another pass's plan: the files left go with the rest
    assert len(glob.glob(os.path.join(folder, "*.merge"))) == 2
    stacking.handing(("D", "obs", "N", 0))
    assert not glob.glob(os.path.join(folder, "*.merge")) and not stacking._handed and stacking._handed_state["disk"] == 0
    # a file lost or cut short costs only the hand-over: the tile merges the frame itself, the same picture
    for harm in (os.remove, lambda f: open(f, "wb").write(b"cut short")):
        stacking.HANDED_MB = 0
        assert stacking.hand_on("g.png", 120, wants["g"])
        harm(glob.glob(os.path.join(folder, "*.merge"))[0])
        del calls[:]
        assert same(stacking.load_hdr("g.png", 120, valid=True, clipped=True)[1:], wants["g"][1:]) and calls == ["g.png"]
        assert not glob.glob(os.path.join(folder, "*.merge"))
    # a folder that cannot be made: no files, as without one
    with open(os.path.join(root, "a file"), "w"):
        pass
    stacking.hand_to(os.path.join(root, "a file", "under it"))
    stacking.handing(("E", "obs", "N", 0))
    assert not stacking.hand_on("g.png", 120, wants["g"]) and not stacking.hand_room()
    # the plan's scale and the tiles' merges with every frame past the first waiting in a file: as before
    stacking.hand_to(root)
    stacking.handing(None)
    stacking.HANDED_MB = one / (1 << 20)
    del calls[:]
    filed = om.pass_scale(u["frames"], u)
    assert filed == before and len(glob.glob(os.path.join(folder, "*.merge"))) == 5
    assert calls.count("a.png") == 2 and calls.count("c.png") == 1, calls
    del calls[:]
    for n in "acefgh":
        got = stacking.load_hdr(f"{n}.png", 120, valid=True, clipped=True)
        assert n != "a" or same(got, masked)
    assert not calls and not stacking._handed and not glob.glob(os.path.join(folder, "*.merge"))
    print("past the memory's room: in a file, back equal to the bit, removed when taken or let go")
finally:
    stacking.hand_to(None)
    stacking.HANDED_MB = keep
    shutil.rmtree(root, ignore_errors=True)
print("ok")
