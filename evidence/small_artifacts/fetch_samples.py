"""Copies the archive members of the small-artifact sample frames (group I of the picture fix plan) into one tar, so
the fixes can be tested away from the Mac Mini: each listed frame with every frame of its camera, observation and
filter within PAD seconds (its repeat exposures, stacking.find_repeats), and a run of each sample movie pass, with
every member of the archive that shares a frame's name (picture, label, line prefix) and the archive's FORMAT.txt.
Run from the repo with CASSINI_DATA set:  python evidence/small_artifacts/fetch_samples.py out.tar"""
import io
import sys
import tarfile

import pandas as pd

import data_source as ds

FRAMES = ["W1601346192_1", "N1800422096_8", "W1545335176_2", "N1463204038_1", "W1360287337_1"]
PAD = 300
# (observation, a frame in it, frames each side)
MOVIES = [("ISS_216SA_AURSTARE001_VIMS", "N1810754140_1", 15), ("ISS_202OT_KIVRES125_PRIME", None, 12),
          ("ISS_150RI_EG60PHASE001_VIMS", None, 14)]

idx = pd.read_csv("Image_index.csv", usecols=["path", "OBSERVATION_ID", "FILTER_NAME", "INSTRUMENT_ID", "seconds_1970"],
                  low_memory=False)
idx["id"] = idx.path.str.split("/").str[-1].str.split(".").str[0]
want = set()
for fid in FRAMES:
    r = idx[idx.id == fid].iloc[0]
    s = idx[(idx.OBSERVATION_ID == r.OBSERVATION_ID) & (idx.FILTER_NAME == r.FILTER_NAME)
            & (idx.INSTRUMENT_ID == r.INSTRUMENT_ID) & ((idx.seconds_1970 - r.seconds_1970).abs() <= PAD)]
    want |= set(s.path)
for obs, mid, side in MOVIES:
    s = idx[idx.OBSERVATION_ID == obs].sort_values("seconds_1970").reset_index(drop=True)
    at = int(s.index[s.id == mid][0]) if mid else len(s) // 2
    want |= set(s.path[max(0, at - side):at + side + 1])
stems = sorted({p.rsplit(".", 1)[0] for p in want})
print(len(stems), "frames")
with tarfile.open(sys.argv[1], "w") as tar:
    def put(rel):
        data = ds.read_bytes(rel)
        info = tarfile.TarInfo(rel)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    for rel in ("nac_data/FORMAT.txt", "wac_data/FORMAT.txt"):
        if ds.exists(rel):
            put(rel)
    for stem in stems:
        for ext in (".png", ".lbl", ".prefix.gz"):
            if ds.exists(stem + ext):
                put(stem + ext)
