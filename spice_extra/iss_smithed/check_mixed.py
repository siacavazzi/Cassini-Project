"""Lists the observations that still switch pointing source within one pointing: a frame left on the raw reconstructed
attitude in the same pointing of an observation (its frames in time order, a new pointing wherever the attitude turns
POINTING_STEP or more from one frame to the next, as make_smith_neighbours_ck.py has it) as a frame whose pointing is
corrected (JPL's per-image C-smithed CK, USGS's Titan CK, or one carried over from either). A mosaic's tiles at other
pointings may differ in source (a correction is carried only within a pointing: the attitude error changes with the
attitude). With the carry-over CKs in place there should be none (Sam 11-16: a sequence never switches pointing
source).

    python spice_extra/iss_smithed/check_mixed.py [--before] [--out mixed.json]
--before: as the frames stood without the carried-over corrections."""
import argparse, bisect, contextlib, io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
os.environ["CASSINI_ISS_NEIGHBOURS"] = "0"
os.environ["CASSINI_USGS_TITAN"] = "0"
import numpy as np, pandas as pd, spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("--before", action="store_true"); ap.add_argument("--out"); args = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__)); U = os.path.join(ROOT, "spice_extra", "usgs_titan")
STEP = np.radians(0.1)   # make_smith_neighbours_ck.POINTING_STEP
fixed = {l.strip() for l in open(os.path.join(U, "images.lis")) if l.strip()}
if not args.before:
    fixed |= {l.strip() for f in (os.path.join(U, "neighbours.lis"), os.path.join(U, "concurrent.lis"),
                                  os.path.join(here, "ISS_smithed_neighbours_ck.lis")) for l in open(f) if l.strip()}
idx = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), usecols=["path", "IMAGE_MID_TIME", "OBSERVATION_ID"], low_memory=False)
idx = idx[idx["path"].notna() & idx["IMAGE_MID_TIME"].notna() & idx["OBSERVATION_ID"].notna()]
idx = idx.assign(frame=idx["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0], year=idx["IMAGE_MID_TIME"].str[:4].astype(int))
corrected, attitude = {}, {}
for year, rows in idx.groupby("year"):
    with contextlib.redirect_stdout(io.StringIO()):
        ba.unload_kernels(); ba.load_kernels(year, year)
    win = []
    for f in (sp.kdata(i, "CK")[0] for i in range(sp.ktotal("CK"))):
        if f.lower().endswith("_iss.bc"):
            c = sp.ckcov(f, -82000, False, "INTERVAL", 0.0, "TDB"); win += [sp.wnfetd(c, i) for i in range(sp.wncard(c))]
    win.sort(); st = [a for a, b in win]
    for f, t in zip(rows["frame"], rows["IMAGE_MID_TIME"]):
        e = sp.str2et(t); k = bisect.bisect_right(st, e) - 1
        corrected[f] = (k >= 0 and win[k][0] <= e <= win[k][1]) or f in fixed
        try: attitude[f] = np.asarray(sp.pxform("J2000", "CASSINI_SC_COORD", e))
        except Exception: attitude[f] = None
mixed, labels = {}, 0
cos_step = 1 + 2 * np.cos(STEP)
cos_same = 1 + 2 * np.cos(np.radians(0.15))   # make_smith_neighbours_ck.SAME_POINTING: a pointing it comes back to
ets = dict(zip(idx["frame"], idx["IMAGE_MID_TIME"]))
for obs, g in idx.groupby("OBSERVATION_ID"):
    fs = sorted((ets[f], f) for f in g["frame"] if attitude.get(f) is not None)
    c = [corrected[f] for _, f in fs]
    if not (any(c) and not all(c)):
        continue
    labels += 1
    seg, k, prev = {}, 0, None
    for _, f in fs:
        if prev is not None and np.einsum("ij,ij->", attitude[prev], attitude[f]) < cos_step:
            k += 1
        seg[f], prev = k, f
    fixed_segs = {seg[f] for _, f in fs if corrected[f]}
    G = np.array([attitude[f] for _, f in fs if corrected[f]])
    raw = [f for _, f in fs if not corrected[f] and (seg[f] in fixed_segs or
                                                     (np.einsum("nij,ij->n", G, attitude[f]) >= cos_same).any())]
    if raw:
        mixed[obs] = {"frames": len(fs), "raw_in_a_corrected_pointing": len(raw)}
print(f"{labels} observations hold both corrected and raw frames; {len(mixed)} switch source within one pointing "
      f"({sum(v['raw_in_a_corrected_pointing'] for v in mixed.values())} raw frames in a pointing with a corrected frame)")
if args.out:
    json.dump(mixed, open(args.out, "w"), indent=0)
