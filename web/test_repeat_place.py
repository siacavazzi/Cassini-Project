"""Repeat exposures are frames at one pointing (stacking.same_place, REPEAT_PLACE), not just frames close in time:
Phoebe 2004-06-11 goes back and forth between two pointings a minute apart, and every tile of its mosaics merged the
other pointing's frames (black blotches where the tile's own frame saturated and only the other one's shadow was
left). Checks the one rule where it is used: obs_mosaic.units keeps a frame at another pointing as a tile of its own,
stacking.find_repeats and load_hdr merge only the frames at the tile's pointing, and reel.shots makes the same
pictures. Fails on the code before it (units dropped every frame of a filter within 120 s, wherever it pointed).
Run: python web/test_repeat_place.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
import pandas as pd
import obs_mosaic as om
import reel
import stacking

A, B = (0.0, 0.0), (900.0, -120.0)   # two pointings 900 px apart, as Phoebe's
rows, geo = [], {}


def frame(obs, t, at, f=("CL1", "CL2"), cam="ISSNA"):
    fid = f"N{int(t)}_1"
    rows.append({"path": f"coiss_2004/{fid}.png", "id": fid, "filter1": f[0], "filter2": f[1],
                 "FILTER_NAME": f"{f[0]},{f[1]}", "seconds_1970": float(t), "TARGET_NAME": "PHOEBE",
                 "OBSERVATION_ID": obs, "INSTRUMENT_ID": cam, "set": -1})
    if at is not None:
        geo[fid] = (at[0], at[1], 30000.0)
    return fid


# Phoebe's pattern: A, B, A, B ... a frame every 60 s, ten frames
T0 = 1086980000
phoebe = [frame("ISS_000PH_HIRESA001_PRIME", T0 + 60 * i, A if i % 2 == 0 else B) for i in range(10)]
# a step-stare strip of 25 places 40 s apart (077RF_HIRESFRNG002's 25 frames merged into 7 tiles)
strip = [frame("ISS_077RF_HIRESFRNG002_PRIME", T0 + 20000 + 40 * i, (300.0 * i, 0.0)) for i in range(25)]
# a genuine bracket: three exposures 12 s apart within a few px, then the camera steps on; and one frame SPICE
# couldn't place, 20 s after the last, which stays a repeat as before (find_shift decides when it is merged)
bracket = [frame("ISS_045RH_REGGEOD001_PRIME", T0 + 40000 + 12 * i, (4.0 * i, -3.0 * i)) for i in range(3)]
step = frame("ISS_045RH_REGGEOD001_PRIME", T0 + 40050, (700.0, 0.0))
unplaced = frame("ISS_045RH_REGGEOD001_PRIME", T0 + 40070, None)

idx = pd.DataFrame(rows)
geo_of = lambda ids: {i: geo[i] for i in ids if i in geo}

# ---------- the rule ----------
assert stacking.same_place((0, 0, 1), (20, 0, 1)) and stacking.same_place((0, 0, 1), (0, 21, 1)) is False
assert stacking.same_place((0, 0, 1), None) is None and stacking.same_place((None, None, None), (0, 0, 1)) is None
kept = [(0, A, "a"), (60, B, "b")]
assert stacking.repeat_of(kept, 120, A, 120) == "a" and stacking.repeat_of(kept, 130, A, 120) is None
assert stacking.repeat_of(kept, 100, (905.0, -118.0), 120) == "b" and stacking.repeat_of(kept, 100, (450.0, 0.0), 120) is None
assert stacking.repeat_of(kept, 100, None, 120) == "b"   # no place: a repeat of the newest, as before
print("same_place, repeat_of ok")

# ---------- obs_mosaic.units ----------
groups = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
om._observations = lambda: (idx, groups)
om.reel.geometry = geo_of
om.reel.wavelength = lambda inst, f: 600
om._units.clear()
om._unit_of.clear()
stacking.places = geo_of


def tiles(obs):
    us = om.units("PHOEBE", obs, "N")
    return [fr[1] for u in us for fr in u["frames"]]


got = tiles("ISS_000PH_HIRESA001_PRIME")
# A at 0, B at 60; A at 120 and B at 180 are their repeats; A at 240 is over 120 s after the A tile, a new one, ...
assert got == [phoebe[i] for i in (0, 1, 4, 5, 8, 9)], got
assert {geo[i][:2] for i in got} == {A, B}
got = tiles("ISS_077RF_HIRESFRNG002_PRIME")
assert got == strip, len(got)
got = tiles("ISS_045RH_REGGEOD001_PRIME")
assert got == [bracket[0], step], got
print("units ok")

# ---------- stacking.find_repeats: only frames at the tile's pointing ----------
st = idx.assign(path=idx["path"]).set_index("path", drop=False)
stacking.index = st
stacking.groups = st.groupby(stacking.keys, sort=False).indices
stacking.columns = {k: st[k].to_numpy() for k in stacking.keys + ["path", "seconds_1970"]}
path = lambda fid: f"coiss_2004/{fid}.png"
for fid in tiles("ISS_000PH_HIRESA001_PRIME"):
    reps = [stacking.frame_id(p) for p in stacking.find_repeats(path(fid), 120, 50)]
    assert all(geo[r][:2] == geo[fid][:2] for r in reps), (fid, reps)
assert [stacking.frame_id(p) for p in stacking.find_repeats(path(phoebe[0]), 120, 50)] == [phoebe[0], phoebe[2]]
# the bracket's frames and the unplaced frame (SPICE can't say), not the step 700 px away
assert sorted(stacking.frame_id(p) for p in stacking.find_repeats(path(bracket[0]), 120, 50)) == sorted(bracket + [unplaced])
print("find_repeats ok")

# ---------- stacking.load_hdr: a repeat that doesn't line up is merged only where SPICE puts it at the pointing ----------
H = 32


class Label:
    def __init__(self, p):
        self.info = {"path": p, "EXPOSURE_DURATION": 100.0, "GAIN_MODE_ID": "12", "INSTRUMENT_MODE_ID": "FULL"}

    def get_info(self):
        return self.info

    def valid_mask(self):
        return np.ones((H, H), bool)

    def export(self):
        return self.info["path"]

    def resize_image(self):
        return np.full((H, H), 100, np.uint8)


import calibration as cal  # noqa: E402
stacking.lh.label = lambda p, as_png=True: Label(p)
stacking.ds.imread = lambda p, flags=None: np.full((H, H), 100, np.uint8)
stacking.cal.calibrate = lambda codes, info, image=None: codes.astype(np.float32) / 1000
stacking.cal.saturated = lambda codes, info, image=None: np.zeros(codes.shape, bool)
asked = {}
stacking.find_repeats = lambda p, window=120, max_frames=5: asked[p]
stacking.ic.find_shift = lambda a, b, r: None   # nothing lines up (faint frames of empty sky)
asked[path(bracket[0])] = [path(bracket[0]), path(bracket[1]), path(step), path(unplaced)]
_, _, n = stacking.load_hdr(path(bracket[0]))
assert n == 2, n   # the bracket's other exposure; not the step, nor the frame SPICE couldn't place
stacking.ic.find_shift = lambda a, b, r: (0.0, 0.0)   # everything lines up: still never the step's other pointing
_, _, n = stacking.load_hdr(path(bracket[0]))
assert n == 3, n
print("load_hdr ok")

# ---------- reel.shots: the same pictures ----------
ridx = idx.copy()
reel.load_index = lambda: (ridx, {})
reel.geometry = geo_of
reel._shots.clear()
shots = reel.shots("PHOEBE")
ph = [s for s in shots if s["obs"] == "ISS_000PH_HIRESA001_PRIME"]
assert [s["ids"][0] for s in ph] == [phoebe[i] for i in (0, 1, 4, 5, 8, 9)], [s["ids"] for s in ph]
assert ph[0]["also"] == [phoebe[2]] and ph[1]["also"] == [phoebe[3]], (ph[0].get("also"), ph[1].get("also"))
assert len([s for s in shots if s["obs"] == "ISS_077RF_HIRESFRNG002_PRIME"]) == 25
print("reel.shots ok")
print("ok")
