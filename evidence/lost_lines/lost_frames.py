# The frames whose pictures change with the lost-lines fill: every frame whose label counts MISSING_LINES, and every
# frame stacked or merged with one (stacking.find_repeats within the 120 s window load_stacked, load_hdr and the
# mosaics use). Everything else comes out byte for byte as before. Also picks test frames for render.py.
# Run from the repo root with CASSINI_DATA set: python evidence/lost_lines/lost_frames.py OUTDIR
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd())
import stacking

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
idx = pd.read_csv("Image_index.csv", low_memory=False)
idx["ml"] = pd.to_numeric(idx["MISSING_LINES"], errors="coerce").fillna(0).astype(int)
idx["id"] = idx["path"].str.split("/").str[-1].str.split(".").str[0]
lost = idx[idx.ml > 0]
stacking.load_index()
own = set(lost.id)
affected = {}
repeats_of = {}
for p, i in zip(lost.path, lost.id):
    reps = stacking.find_repeats(p, 120, 50)
    repeats_of[i] = len(reps) - 1
    for r in reps:
        rid = r.split("/")[-1].split(".")[0]
        affected[rid] = affected.get(rid) or ("own" if rid in own else "repeat")
with open(os.path.join(out, "lost_lines_frames.txt"), "w") as f:
    f.write("# id, own = its label counts lost lines, repeat = stacked/merged with such a frame\n")
    for rid in sorted(affected):
        f.write(f"{rid},{affected[rid]}\n")
summary = (f"frames in the index: {len(idx)}\nframes with MISSING_LINES > 0: {len(own)}\n"
           f"frames stacked with one of them (120 s): {sum(v == 'repeat' for v in affected.values())}\n"
           f"frames whose pictures change: {len(affected)} ({100 * len(affected) / len(idx):.2f}%)\n"
           f"of the lost frames, with at least one repeat: {sum(v > 0 for v in repeats_of.values())}\n")
print(summary)
open(os.path.join(out, "summary.txt"), "w").write(summary)

# test frames: the Rhea frame Sam sent, then lost frames on a moon or Saturn, a spread of how many lines they lost,
# with and without repeats; and clean frames (none of the above) for the byte-for-byte check
rng = np.random.default_rng(1)
bodies = {"RHEA", "DIONE", "TETHYS", "ENCELADUS", "MIMAS", "TITAN", "IAPETUS", "HYPERION", "PHOEBE", "SATURN", "JANUS", "EPIMETHEUS"}
cand = lost[lost.TARGET_NAME.isin(bodies) & lost.ml.between(10, 600)]
picks = ["N1516200841_1"]
for has_rep in (True, False):
    c = cand[[(repeats_of[i] > 0) == has_rep for i in cand.id]]
    for t in rng.permutation(sorted(set(c.TARGET_NAME)))[:4]:
        picks.append(rng.choice(c[c.TARGET_NAME == t].id.to_numpy()))
clean = idx[~idx.id.isin(affected) & idx.TARGET_NAME.isin(bodies)]
clean_ids = list(rng.choice(clean.id.to_numpy(), 30, replace=False))
# clean color sets: RED, GRN, BL1 of one observation within five minutes, none of them affected
sets = []
nac = clean[clean.INSTRUMENT_ID == "ISSNA"].copy()
nac["f"] = nac["FILTER_NAME"].astype(str)
for obs, g in nac.groupby("OBSERVATION_ID"):
    by = {f: g[g.f.str.contains(f)] for f in ("RED", "GRN", "BL1")}
    if all(len(v) for v in by.values()):
        r = by["RED"].iloc[0]
        near = [by[f].iloc[(by[f].seconds_1970 - r.seconds_1970).abs().argmin()] for f in ("RED", "GRN", "BL1")]
        if max(abs(n.seconds_1970 - r.seconds_1970) for n in near) < 300:
            sets.append(",".join(n.id for n in near))
sets = list(rng.choice(sets, min(6, len(sets)), replace=False))
with open(os.path.join(out, "test_ids.txt"), "w") as f:
    for i in picks:
        f.write(f"lost {i}\n")
    for i in clean_ids:
        f.write(f"clean {i}\n")
    for s in sets:
        f.write(f"clean {s}\n")
print(open(os.path.join(out, "test_ids.txt")).read())
