"""JPL's C-smithed pointing (*_ISS.bc, one segment per image) carried over to every frame of the same observation that
has none, so no observation mixes corrected and raw pointing (Sam 11-16: a sequence must never switch pointing
source). As make_neighbours_ck.py carries USGS's: E = C_iss(t0) C_raw(t0)^T at the observation's smithed frames,
applied to the raw attitude at the frame's own time; between two smithed frames E is interpolated (slerp) by time,
before the first or after the last the nearest one's is taken. Frames USGS or its neighbours CK cover are left out.
Writes one CK (type 3, a second round each mid-exposure time) and its frame list (.lis).

    python spice_extra/iss_smithed/make_smith_neighbours_ck.py spice_extra/iss_smithed/ISS_smithed_neighbours_ck.bc [years]
"""
import collections, contextlib, io, os, sys, time, bisect
import numpy as np, pandas as pd, spiceypy as sp
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
os.environ["CASSINI_USGS_TITAN"] = "0"
import bootleg_autonav as ba
OUT = sys.argv[1]; YEARS = {int(y) for y in sys.argv[2].split(",")} if len(sys.argv) > 2 else None
PAD, BODY = 0.5, "CASSINI_SC_COORD"
U = os.path.join(ROOT, "spice_extra", "usgs_titan")
skip = {l.strip() for f in ("images.lis", "neighbours.lis", "concurrent.lis") for l in open(os.path.join(U, f)) if l.strip()}
index = pd.read_csv(os.path.join(ROOT, "Image_index.csv"), usecols=["path", "IMAGE_MID_TIME", "OBSERVATION_ID"], low_memory=False)
index = index[index["path"].notna() & index["IMAGE_MID_TIME"].notna()]
index = index.assign(frame=index["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0], year=index["IMAGE_MID_TIME"].str[:4].astype(int))
def year_kernels(year):
    with contextlib.redirect_stdout(io.StringIO()):
        ba.unload_kernels(); ba.load_kernels(year, year)
    iss = [sp.kdata(i, "CK")[0] for i in range(sp.ktotal("CK"))]
    return [f for f in iss if f.lower().endswith("_iss.bc")]


def slerp_error(refs, t):
    """The error rotation at t from an observation's (time, E) list: interpolated between the two either side, else
    the nearest end's."""
    times = [a for a, b in refs]
    k = bisect.bisect_left(times, t)
    if k == 0 or k == len(refs):
        return refs[0 if k == 0 else -1][1]
    (ta, ea), (tb, eb) = refs[k - 1], refs[k]
    qa, qb = np.array(sp.m2q(ea)), np.array(sp.m2q(eb))
    if qa @ qb < 0:
        qb = -qb
    w = (t - ta) / (tb - ta)
    om_ = np.arccos(np.clip(qa @ qb, -1.0, 1.0))
    q = qa if om_ < 1e-12 else (np.sin((1 - w) * om_) * qa + np.sin(w * om_) * qb) / np.sin(om_)
    return sp.q2m(q / np.linalg.norm(q))


# pass 1: the error rotation at every smithed frame, by observation, over the whole mission (an observation can run
# across a new year: ISS_055RF_FMOVIE001_VIMS, 2007-2008)
errors_by_obs, smithed_frames, ets = collections.defaultdict(list), set(), {}
for year, rows in index.groupby("year"):
    if YEARS and year not in YEARS: continue
    iss = year_kernels(year)
    win = []
    for f in iss:
        c = sp.ckcov(f, -82000, False, "INTERVAL", 0.0, "TDB"); win += [sp.wnfetd(c, i) for i in range(sp.wncard(c))]
    win.sort(); st = [a for a, b in win]
    for f, t in zip(rows["frame"], rows["IMAGE_MID_TIME"]):
        ets[f] = sp.str2et(t)
    good = {}
    for f in rows["frame"]:
        k = bisect.bisect_right(st, ets[f]) - 1
        if k >= 0 and win[k][0] <= ets[f] <= win[k][1]:
            smithed_frames.add(f)
            try: good[f] = sp.pxform("J2000", BODY, ets[f])
            except Exception: pass
    for f in iss: sp.unload(f)
    obs_of = dict(zip(rows["frame"], rows["OBSERVATION_ID"]))
    for f, g in good.items():
        try: errors_by_obs[obs_of[f]].append((ets[f], g @ sp.pxform("J2000", BODY, ets[f]).T))
        except Exception: pass
for refs in errors_by_obs.values():
    refs.sort(key=lambda r: r[0])

# pass 2: every other frame of those observations takes the raw attitude turned by its observation's error
if os.path.exists(OUT): os.remove(OUT)
handle = sp.ckopn(OUT, "ISS smithed neighbours", 5000); written = []
for year, rows in index.groupby("year"):
    if YEARS and year not in YEARS: continue
    t0 = time.time()
    year_kernels(year)
    records = []
    for f, o in zip(rows["frame"], rows["OBSERVATION_ID"]):
        refs = errors_by_obs.get(o)
        if not refs or f in smithed_frames or f in skip: continue
        t = ets[f]; E = slerp_error(refs, t)
        try: cs = [E @ sp.pxform("J2000", BODY, t + d) for d in (-PAD, 0.0, PAD)]
        except Exception: continue
        records.append((f, t, cs))
    for f, t, cs in sorted(records, key=lambda r: r[1]):
        ticks = [sp.sce2c(-82, t + d) for d in (-PAD, 0.0, PAD)]
        sp.ckw03(handle, ticks[0], ticks[-1], -82000, "J2000", False, f, 3, ticks, np.array([sp.m2q(c) for c in cs]), np.zeros((3, 3)), 1, [ticks[0]])
        written.append(f)
    print(f"{year}: {len(records)} frames carried over ({time.time()-t0:.0f} s)", flush=True)
sp.ckcls(handle); ba.unload_kernels()
open(OUT[:-3] + ".lis", "w").writelines(f + "\n" for f in written)
