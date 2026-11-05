"""
Makes Titan_neighbours_ck.bc and neighbours.lis: the USGS correction carried over to the Titan frames USGS did not
adjust. USGS controlled only the 938 nm (CL1,CB3) NAC frames. The other filters of the same pass, shot seconds to
minutes before or after at the same pointing, keep the mission pointing, so a colour set would mix corrected and
uncorrected frames tens of pixels apart. Mission attitude errors change slowly, so each such frame takes the error
rotation of the nearest USGS frame of its observation (within MAX_GAP seconds):

    E = C_usgs(t0) C_mission(t0)^T        C_new(t) = E C_mission(t)

C maps J2000 to Cassini's body frame (CASSINI_SC_COORD, -82000), the frame both CKs are written in. The result is a
CK like USGS's (one type 3 segment per frame, a second around its mid-exposure time), loaded before the USGS CK by
bootleg_autonav.load_kernels. Run once from the repo root with the kernels reachable (CASSINI_KERNELS); it loads
each year's kernels as the pipeline does:

    CASSINI_KERNELS=... CASSINI_KEEP_SPICE_CACHE=1 python spice_extra/usgs_titan/make_neighbours_ck.py
"""
import contextlib
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ["CASSINI_USGS_TITAN"] = "0"  # the mission kernels only; the USGS CK is loaded by hand below
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import spiceypy as sp  # noqa: E402
import bootleg_autonav as ba  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("NEIGHBOURS_OUT", HERE)  # another folder for a trial run
OUT_CK = os.path.join(OUT, "Titan_neighbours_ck.bc")
OUT_LIST = os.path.join(OUT, "neighbours.lis")
YEARS = {int(y) for y in os.environ.get("NEIGHBOURS_YEARS", "").split(",") if y}  # a trial run's years
USGS_CK = os.path.join(HERE, "Titan_CISS_2024_ck.bc")
MAX_GAP = 600.0  # seconds from the nearest USGS frame of the same observation
PAD = 0.5  # seconds either side of the mid-exposure time
BODY = "CASSINI_SC_COORD"

usgs = {line.strip() for line in open(os.path.join(HERE, "images.lis")) if line.strip()}
concurrent = {line.strip() for line in open(os.path.join(HERE, "concurrent.lis")) if line.strip()}
index = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), usecols=["path", "IMAGE_MID_TIME", "OBSERVATION_ID", "TARGET_NAME"],
                    low_memory=False)
index = index[(index["TARGET_NAME"] == "TITAN") & index["path"].notna() & index["IMAGE_MID_TIME"].notna()]
index = index.assign(frame=index["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0],
                     year=index["IMAGE_MID_TIME"].str[:4].astype(int))

if os.path.exists(OUT_CK):
    os.remove(OUT_CK)
handle = sp.ckopn(OUT_CK, "USGS Titan neighbours", 5000)
written = []
for year, rows in index.groupby("year"):
    if YEARS and year not in YEARS:
        continue
    ref = rows[rows["frame"].isin(usgs)]
    todo = rows[~rows["frame"].isin(usgs | concurrent)]
    if ref.empty or todo.empty:
        continue
    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        ba.unload_kernels()
        ba.load_kernels(year, year)
    ets = {f: sp.str2et(t) for f, t in zip(rows["frame"], rows["IMAGE_MID_TIME"])}
    # E at each USGS frame: the mission attitude, then the USGS one (loaded last, so its segment wins)
    mission = {f: sp.pxform("J2000", BODY, ets[f]) for f in ref["frame"]}
    sp.furnsh(USGS_CK)
    errors = {}
    for f in ref["frame"]:
        errors[f] = sp.pxform("J2000", BODY, ets[f]) @ mission[f].T
    sp.unload(USGS_CK)
    by_obs = {obs: sorted((ets[f], f) for f in g["frame"]) for obs, g in ref.groupby("OBSERVATION_ID")}
    records = []  # (frame, et, C_new at et - PAD, et, et + PAD)
    for f, obs in zip(todo["frame"], todo["OBSERVATION_ID"]):
        refs = by_obs.get(obs)
        if not refs:
            continue
        t = ets[f]
        gap, nearest = min((abs(t - t0), f0) for t0, f0 in refs)
        if gap > MAX_GAP:
            continue
        try:
            cs = [errors[nearest] @ sp.pxform("J2000", BODY, t + d) for d in (-PAD, 0.0, PAD)]
        except Exception as e:  # no mission attitude at that moment: left as it is
            print(f"{f}: {type(e).__name__}", flush=True)
            continue
        records.append((f, t, cs))
    # written while the year's SCLK kernel is loaded
    for f, t, cs in sorted(records, key=lambda r: r[1]):
        ticks = [sp.sce2c(-82, t + d) for d in (-PAD, 0.0, PAD)]
        quats = np.array([sp.m2q(c) for c in cs])
        sp.ckw03(handle, ticks[0], ticks[-1], -82000, "J2000", False, f, 3, ticks, quats, np.zeros((3, 3)), 1,
                 [ticks[0]])
        written.append(f)
    print(f"{year}: {len(records)} frames carried over from {len(ref)} USGS frames ({time.time() - start:.0f} s)", flush=True)
sp.ckcls(handle)
ba.unload_kernels()
with open(OUT_LIST, "w") as fh:
    fh.writelines(f + "\n" for f in written)
print(f"wrote {len(written)} frames to {OUT_CK}", flush=True)
