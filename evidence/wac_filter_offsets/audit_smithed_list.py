"""Audit: which frames have JPL's per-image (C-smithed) pointing, from the *_ISS.bc CK coverage of each year's kernels."""
import contextlib, io, os, sys, bisect
import pandas as pd, spiceypy as sp
sys.path.insert(0, ".")
os.environ["CASSINI_USGS_TITAN"] = "0"
import bootleg_autonav as ba
index = pd.read_csv("Image_index.csv", usecols=["path", "IMAGE_MID_TIME"], low_memory=False)
index = index[index["path"].notna() & index["IMAGE_MID_TIME"].notna()]
index = index.assign(frame=index["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0], year=index["IMAGE_MID_TIME"].str[:4].astype(int))
out = open(sys.argv[1], "w")
for year, rows in index.groupby("year"):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ba.unload_kernels(); ba.load_kernels(year, year)
    except BaseException as e:
        print(year, "no kernels", str(e)[:80], flush=True); continue
    iss = [sp.kdata(i, "CK")[0] for i in range(sp.ktotal("CK"))]
    iss = [f for f in iss if f.lower().endswith("_iss.bc")]
    win = []
    for f in iss:
        c = sp.ckcov(f, -82000, False, "INTERVAL", 0.0, "TDB"); win += [sp.wnfetd(c, i) for i in range(sp.wncard(c))]
    win.sort(); st = [a for a, b in win]; n = 0
    for f, t in zip(rows["frame"], rows["IMAGE_MID_TIME"]):
        et = sp.str2et(t); k = bisect.bisect_right(st, et) - 1
        if k >= 0 and win[k][0] <= et <= win[k][1]:
            out.write(f + "\n"); n += 1
    print(year, len(rows), "frames,", n, "with JPL per-image pointing", flush=True)
out.close(); ba.unload_kernels()
