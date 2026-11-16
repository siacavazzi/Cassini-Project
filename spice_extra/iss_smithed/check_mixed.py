"""Lists the observations that mix pointing sources: frames with a corrected pointing (JPL's per-image C-smithed CK,
USGS's Titan CK, or one carried over from either) beside frames left on the raw reconstructed attitude. With the
carry-over CKs in place there should be none (Sam 11-16: a sequence never switches pointing source).

    python spice_extra/iss_smithed/check_mixed.py [--before] [--out mixed.json]
--before: as the frames stood without ISS_smithed_neighbours_ck (its frame list left out)."""
import argparse, bisect, collections, contextlib, io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
import pandas as pd, spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("--before", action="store_true"); ap.add_argument("--out"); args = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__)); U = os.path.join(ROOT, "spice_extra", "usgs_titan")
fixed = {l.strip() for f in ("images.lis", "neighbours.lis", "concurrent.lis") for l in open(os.path.join(U, f)) if l.strip()}
if not args.before:
    fixed |= {l.strip() for l in open(os.path.join(here, "ISS_smithed_neighbours_ck.lis")) if l.strip()}
idx = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), usecols=["path", "IMAGE_MID_TIME", "OBSERVATION_ID"], low_memory=False)
idx = idx[idx["path"].notna() & idx["IMAGE_MID_TIME"].notna() & idx["OBSERVATION_ID"].notna()]
idx = idx.assign(frame=idx["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0], year=idx["IMAGE_MID_TIME"].str[:4].astype(int))
corrected = {}
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
mixed = {}
for obs, g in idx.groupby("OBSERVATION_ID"):
    c = [corrected[f] for f in g["frame"]]
    if any(c) and not all(c):
        mixed[obs] = {"frames": len(c), "raw": len(c) - sum(c)}
print(f"{len(mixed)} observations mix pointing sources ({sum(v['raw'] for v in mixed.values())} raw frames in them)")
if args.out:
    json.dump(mixed, open(args.out, "w"), indent=0)
