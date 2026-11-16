"""A repeat exposure taken from nearer or further is brought to the frame's range before it is merged
(stacking.grown, REPEAT_GROW, to_range). On a close flyby the frames of an exposure bracket seconds apart are taken
from tens or hundreds of km nearer: Phoebe's closest approach (2004-06-11, N1465674377_2) merged a 2 s frame with
0.82 s ones 18 and 35 s later from 100 and 200 km nearer, the body 4% bigger, and its crater shadows got three edges.
Fails on the code before it (the nearer frame merged at its own size: the merged disk's edge doubled).
Run: python web/test_repeat_range.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import cv2
import stacking

# ---------- the measure ----------
# a body reaching 700 px from its centre, 0.1% nearer, moves its limb 0.7 px; 4% nearer, 28 px
assert stacking.grown((0, 0, 2400.0, 700.0), (0, 0, 2397.6, 700.7)) < 1
assert abs(stacking.grown((0, 0, 2400.0, 724.0), (0, 0, 2304.0, 754.0)) - 754 * 96 / 2400) < 1e-9
# a small body far off grows a fraction of a pixel; no reach (a body of no known size) or no place: 0
assert stacking.grown((0, 0, 1.0e6, 20.0), (0, 0, 0.97e6, 20.6)) < 1
assert stacking.grown((0, 0, 2400.0), (0, 0, 2300.0)) == 0 and stacking.grown(None, (0, 0, 1.0, 5.0)) == 0
# same_place asks the pointing only, as before
assert stacking.same_place((0, 0, 2400.0, 724.0), (0, 0, 2300.0, 724.0))
# reach: the body's radius in px, no further than the frame's farthest corner from its centre, 0 wholly off the frame
stacking._radii.update({"PHOEBE": 107.0, "NOWHERE": None})
NAC = 1 / 6.0e-6
assert abs(stacking._reach("PHOEBE", (0, 0, 1.0e5), NAC) - 107 / 1e5 * NAC) < 1e-6
assert abs(stacking._reach("PHOEBE", (0, 0, 2400.0), NAC) - 512 * 2 ** 0.5) < 1e-6
assert stacking._reach("PHOEBE", (5000.0, 0, 1.0e5), NAC) == 0.0
assert stacking._reach("NOWHERE", (0, 0, 1.0e5), NAC) is None
print("grown, reach ok")

# ---------- to_range: about the body's centre ----------
C = stacking.ba.CCD_CENTER


def disk(r, at=(0.0, 0.0), value=200):
    im = np.zeros((1024, 1024), np.uint8)
    cv2.circle(im, (int(round(C - at[0])), int(round(C - at[1]))), int(r), value, -1)
    return im


near = disk(208, (40.0, -30.0))
back = stacking.to_range(near, (40.0, -30.0, 2300.0), (40.0, -30.0, 2392.0))
rows = np.nonzero(back[:, int(C - 40)] > 100)[0]
assert abs((rows.max() - rows.min() + 1) / 2 - 200) <= 1.5, (rows.min(), rows.max())
ones = stacking.to_range(np.ones((1024, 1024), np.float32), (0.0, 0.0, 2300.0), (0.0, 0.0, 2392.0), cv2.INTER_LINEAR)
assert ones[512, 512] > 0.99 and ones[2, 512] < 0.5   # a shrunk frame no longer covers its edge
print("to_range ok")

# ---------- load_hdr: the nearer repeat merged at the frame's size ----------
places = {"far": (40.0, -30.0, 2392.0, 724.0), "near": (40.0, -30.0, 2300.0, 724.0)}
pngs = {"far.png": disk(200, (40.0, -30.0)), "near.png": disk(208, (40.0, -30.0))}


class Label:
    def __init__(self, p):
        self.info = {"path": p, "EXPOSURE_DURATION": 100.0, "GAIN_MODE_ID": "12", "INSTRUMENT_MODE_ID": "FULL"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return np.ones((1024, 1024), bool)

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return cv2.cvtColor(pngs[self.info["path"]], cv2.COLOR_GRAY2BGR)


stacking.lh.label = lambda p, as_png=True: Label(p)
stacking.ds.imread = lambda p, flags=None: pngs[p]
stacking.cal.calibrate = lambda codes, info, image=None: codes.astype(np.float32) / 1000
stacking.cal.saturated = lambda codes, info, image=None: np.zeros(codes.shape, bool)
stacking.find_repeats = lambda p, window=120, max_frames=5: ["far.png", "near.png"]
stacking.places = lambda ids, reach=False: {i.split(".")[0]: places[i.split(".")[0]][:4 if reach else 3] for i in ids}
stacking.frame_id = lambda p: os.path.basename(p).split(".")[0]
_, merged, n = stacking.load_hdr("far.png")
assert n == 2, n
col = merged[:, int(C - 40)]
# one edge: the disk is 0.2 inside 200 px, nothing at half value between 200 and 208 px (two disks laid over each other)
half = ((col > 0.05) & (col < 0.15)).sum()
assert half <= 4, half
lit = np.nonzero(col > 0.1)[0]
assert abs((lit.max() - lit.min() + 1) / 2 - 200) <= 1.5, (lit.min(), lit.max())
# ... and with valid, the edge the shrunk frame doesn't cover is the frame's own
_, merged_v, n, valid = stacking.load_hdr("far.png", valid=True)
assert n == 2 and valid.all() and np.abs(merged_v - merged).max() < 1e-6
# ... a repeat with lost lines: the cubic resize's spread round them is left out too (a pixel round the resized mask)
lost = np.ones((1024, 1024), bool)
lost[600:604] = False
Label.valid_mask = lambda self: lost if self.info["path"] == "near.png" else np.ones((1024, 1024), bool)
pngs["near.png"] = disk(208, (40.0, -30.0)).copy()
pngs["near.png"][600:604] = 0   # the lost lines read as 0
_, merged_l, n, valid_l = stacking.load_hdr("far.png", valid=True)
col = merged_l[:, int(C - 40)]
assert n == 2 and valid_l.all() and np.abs(col[560:650] - 0.2).max() < 0.002, np.abs(col[560:650] - 0.2).max()
print("load_hdr ok")
print("ok")
