"""Repeat exposures are frames at one pointing (stacking.same_place, REPEAT_PLACE), not just frames close in time:
Phoebe 2004-06-11 goes back and forth between two pointings a minute apart, and every tile of its mosaics merged the
other pointing's frames (black blotches where the tile's own frame saturated and only the other one's shadow was
left). Checks the one rule where it is used: obs_mosaic.units keeps a frame at another pointing as a tile of its own,
stacking.find_repeats and load_hdr merge only the frames at the tile's pointing, and reel.shots makes the same
pictures. Fails on the code before it (units dropped every frame of a filter within 120 s, wherever it pointed).
Also obs_mosaic._judge: with every frame of a dense scan a picture of its own, a creep that adds up to a jump over
one repeat window counts as a jump (013RI_AZSCNHIPH001 stays a mosaic), while a slowly drifting stare stays a movie.
Range too (REPEAT_GROW): on a close flyby (Phoebe's closest approach, 2004-06-11) frames 18 s apart at one pointing
were taken 100 km nearer, the body 4% bigger, and merged as one picture with crater shadows three edges deep; a frame
taken nearer or further is a picture of its own, and never merged as taken when it doesn't line up.
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
# a dense scan, each frame a picture of its own: 0.1 of a frame on every 73 s, and every fourth step 0.16, 30 frames
# (013RI_AZSCNHIPH001's ring scan); a stare drifting 0.03 of a frame every 30 s; a stare that jumps to a second field halfway and creeps
# on there a little (00BDI_GLOCOL001)
scan = [frame("ISS_013RI_AZSCNHIPH001_PRIME", T0 + 60000 + 73 * i,
              (-102.4 * i - 61.4 * ((i + 3) // 4), 0.0)) for i in range(30)]
drift = [frame("ISS_099RI_SPOKEMOVIE001_PRIME", T0 + 70000 + 30 * i, (31.0 * i, 0.0)) for i in range(30)]
hop = [frame("ISS_00BDI_GLOCOL001_PRIME", T0 + 80000 + 30 * i, ((0.0 if i < 15 else 800.0) + 31.0 * (i % 15), 0.0))
       for i in range(30)]
# creeping frame to frame but no mosaic: a ring survey stepping as the scan above, 200 frames, too wide
# for one
# (241RI_PROPSURVY001); a propeller retarget's view, 5 frames 0.1 of a frame apart, under a frame in all (277RI)
survey = [frame("ISS_241RI_PROPSURVY001_PIE", T0 + 90000 + 73 * i, (102.4 * i + 61.4 * ((i + 3) // 4), 0.0))
          for i in range(200)]
view = [frame("ISS_277RI_PROPRETRG001_PRIME", T0 + 100000 + 104 * i, (0.0, 102.4 * i)) for i in range(5)]

idx = pd.DataFrame(rows)
geo_of = lambda ids, reach=False: {i: geo[i] for i in ids if i in geo}

# ---------- the rule ----------
assert stacking.same_place((0, 0, 1), (20, 0, 1)) and stacking.same_place((0, 0, 1), (0, 21, 1)) is False
assert stacking.same_place((0, 0, 1), None) is None and stacking.same_place((None, None, None), (0, 0, 1)) is None
kept = [(0, A, "a"), (60, B, "b")]
assert stacking.repeat_of(kept, 120, A, 120) == "a" and stacking.repeat_of(kept, 130, A, 120) is None
assert stacking.repeat_of(kept, 100, (905.0, -118.0), 120) == "b" and stacking.repeat_of(kept, 100, (450.0, 0.0), 120) is None
assert stacking.repeat_of(kept, 100, None, 120) == "b"   # no place: a repeat of the newest, as before
# range: a body reaching 700 px from its centre, 0.1% nearer, moves its limb 0.7 px (a repeat); 4% nearer, 28 px
assert stacking.grown((0, 0, 2400.0, 700.0), (0, 0, 2397.6, 700.7)) < 1
assert stacking.same_place((0, 0, 2400.0, 700.0), (0, 0, 2397.6, 700.7))
assert stacking.same_place((0, 0, 2400.0, 724.0), (0, 0, 2300.0, 724.0)) is False
# ... a small body far off grows by a fraction of a pixel (a repeat however its range changes), and without a reach
# (a body of no known size, or places without reach) the range is not asked, as before
assert stacking.same_place((0, 0, 1.0e6, 20.0), (0, 0, 0.97e6, 20.6))
assert stacking.same_place((0, 0, 2400.0), (0, 0, 2300.0)) and stacking.same_place((0, 0, 2400.0, None), (0, 0, 2300.0, None))
kept = [(0, (0, 0, 2400.0, 724.0), "a")]
assert stacking.repeat_of(kept, 18, (0, 0, 2300.0, 724.0), 120) is None and stacking.repeat_of(kept, 18, (2, 1, 2399.0, 724.0), 120) == "a"
# reach: the body's radius in px (km over the range, at the camera's scale), no further than the frame's farthest
# corner from its centre, 0 when it is wholly off the frame, None for a body of no known size
stacking._radii.update({"PHOEBE": 107.0, "NOWHERE": None})
NAC = 1 / 6.0e-6
assert abs(stacking._reach("PHOEBE", (0, 0, 1.0e5), NAC) - 107 / 1e5 * NAC) < 1e-6   # 178 px, all in the frame
assert abs(stacking._reach("PHOEBE", (0, 0, 2400.0), NAC) - 512 * 2 ** 0.5) < 1e-6   # 7431 px: the corners
assert stacking._reach("PHOEBE", (5000.0, 0, 1.0e5), NAC) == 0.0
assert stacking._reach("NOWHERE", (0, 0, 1.0e5), NAC) is None
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
# a close flyby (Phoebe's closest approach, ISS_000PH_HIRESC001: a 2 s frame and two 0.82 s ones 18 and 35 s later
# from 100 and 200 km nearer, at one pointing): three pictures; and a bracket at a steady range stays one
reach_of = {}
flyby = []
for i, (dt, z) in enumerate(((0, 2420.0), (18, 2320.0), (35, 2220.0))):
    flyby.append(frame("ISS_000PH_HIRESC001_PRIME", T0 + 120000 + dt, (3.0 * i, 0.0)))
    geo[flyby[-1]] = (3.0 * i, 0.0, z)
    reach_of[flyby[-1]] = 724.0
steady = []
for i in range(3):
    steady.append(frame("ISS_000PH_HIRESC002_PRIME", T0 + 130000 + 12 * i, (3.0 * i, 0.0)))
    geo[steady[-1]] = (3.0 * i, 0.0, 9.0e4 - 2.0 * i)
    reach_of[steady[-1]] = 200.0
idx = pd.DataFrame(rows)
groups = idx.groupby(["TARGET_NAME", "OBSERVATION_ID", "INSTRUMENT_ID"], sort=False).indices
om._observations = lambda: (idx, groups)
geo_reach = lambda ids, reach=False: {i: geo[i] + ((reach_of.get(i),) if reach else ()) for i in ids if i in geo}
om.reel.geometry = geo_reach
assert tiles("ISS_000PH_HIRESC001_PRIME") == flyby
assert tiles("ISS_000PH_HIRESC002_PRIME") == steady[:1]
# (the frames' own tuples keep (x, y, z): the reach is only the repeat rule's)
assert all(len(fr) == 8 for u in om.units("PHOEBE", "ISS_000PH_HIRESC001_PRIME", "N") for fr in u["frames"])
om.reel.geometry = geo_of
print("units ok")

# ---------- obs_mosaic._judge: a creep that adds up to a jump within a repeat window is a jump ----------
u = om.units("PHOEBE", "ISS_013RI_AZSCNHIPH001_PRIME", "N")[0]
# one step in four jumps (mosaic.min_step) frame to frame, a movie's share (MOVIE_JUMPS), but every step does over
# the repeat window: a mosaic, as when each window's frames made one tile
assert len(u["frames"]) == 30 and u["jump_frac"] > 0.7 and not u["movie"], (len(u["frames"]), u["jump_frac"])
u = om.units("PHOEBE", "ISS_099RI_SPOKEMOVIE001_PRIME", "N")[0]
assert len(u["frames"]) == 30 and u["jump_frac"] == 0 and u["movie"], (len(u["frames"]), u["jump_frac"])
u = om.units("PHOEBE", "ISS_00BDI_GLOCOL001_PRIME", "N")[0]
# one jump: the creep is counted from the second field, not from the first
assert u["jump_frac"] == 1 / 29 and u["movie"], u["jump_frac"]
u = om.units("PHOEBE", "ISS_000PH_HIRESA001_PRIME", "N")[0]
assert u["jump_frac"] == 1 and not u["movie"], u["jump_frac"]   # A, B, A, B: every step a jump
for obs in ("ISS_241RI_PROPSURVY001_PIE", "ISS_277RI_PROPRETRG001_PRIME"):   # ... stay the movies they play as
    u = om.units("PHOEBE", obs, "N")[0]
    assert u["kind"] == "movie" and u["movie"], (obs, u["kind"], u["jump_frac"])
print("_judge ok")

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
# ... and the flyby's frames nearer and further are none of one another's
stacking.places = geo_reach
assert [stacking.frame_id(p) for p in stacking.find_repeats(path(flyby[0]), 120, 50)] == [flyby[0]]
assert sorted(stacking.frame_id(p) for p in stacking.find_repeats(path(steady[0]), 120, 50)) == sorted(steady)
stacking.places = geo_of
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

# ---------- a mosaic tile that can't be calibrated (8LSB) among calibrated ones is left out ----------
import tempfile  # noqa: E402
import color_image  # noqa: E402
made = {}


def processed(paths, hdr=False, scale=None, repeat_window=120, around=None, turn=0.0):
    side = 2 * om.HALF
    return np.full((side, side, 4), 200, np.uint8), None, {"calibrated": made[paths[0]], "stacked": [1],
                                                          "frame_offset": [0.0, 0.0]}


color_image.processed_frame = processed
om._register = lambda *a, **k: None
om._keep_made = lambda *a, **k: None
u = {"frames": [("x/a.png", "a", "CL1/CL2", 0.0, 600, 0.0, 0.0, 3e4)], "z": 3e4, "mosaic": True, "key": ("PHOEBE", "O", "N", 0)}
scale = {"blacks": {"CL1/CL2": 0.01}, "white": 0.2, "gamma": 1.5}
with tempfile.TemporaryDirectory() as there:
    made["x/a.png"] = True
    rep = om._tile_made(u, 0, there, scale, os.path.join(there, "ok"))
    assert "box" in rep and os.path.exists(os.path.join(there, "ok.png")), rep
    made["x/a.png"] = False
    rep = om._tile_made(u, 0, there, scale, os.path.join(there, "lsb"))
    assert "box" not in rep and "calibrated" in rep["why"] and not os.path.exists(os.path.join(there, "lsb.png")), rep
    # ... but drawn when no frame of its filter calibrates (the pass has no black for it), or in a movie
    rep = om._tile_made(u, 0, there, {**scale, "blacks": {}}, os.path.join(there, "lsb_only"))
    assert "box" in rep, rep
    rep = om._tile_made({**u, "mosaic": False}, 0, there, scale, os.path.join(there, "lsb_movie"))
    assert "box" in rep, rep
print("uncalibrated tile ok")
print("ok")
