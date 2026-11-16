"""JPL's C-smithed pointing (*_ISS.bc, one segment per image) carried over to every frame of the same observation that
has none, so no observation mixes corrected and raw pointing (Sam 11-16: a sequence must never switch pointing
source). As make_neighbours_ck.py carries USGS's: E = C_iss(t0) C_raw(t0)^T at the observation's smithed frames,
applied to the raw attitude at the frame's own time: the median of the nearest smithed frames' corrections
(local_error), faded with time distance (HOLD, FADE). Frames USGS or its neighbours CK cover are left out.
Writes one CK (type 3, a second round each mid-exposure time) and its frame list (.lis).

    python spice_extra/iss_smithed/make_smith_neighbours_ck.py spice_extra/iss_smithed/ISS_smithed_neighbours_ck.bc [years]
"""
import collections, contextlib, io, os, sys, time, bisect
import numpy as np, pandas as pd, spiceypy as sp
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
os.environ["CASSINI_USGS_TITAN"] = "0"
os.environ["CASSINI_ISS_NEIGHBOURS"] = "0"   # the raw attitude, not this CK's own earlier answer
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


HOLD, FADE = 600.0, 10800.0   # s: a correction is carried whole this far from its C-smithed frame, then fades with this
#                              time constant (gone by ~3 h). Measured on 22,000 C-smithed frames of 2005/2008/2011/2015,
#                              one frame's correction applied to another of its observation at its pointing (raw: a
#                              median 20 NAC px off): carried whole, a median 6 px under a minute, 9 px to 10 min, 10 px
#                              to 1 h, 11 px to 6 h (raw 21), worse than raw for 16-28%; faded with 3 h, 13.5 px at 1-6
#                              h, worse than raw for 20% (the 30 min of an earlier trial gave back most of the gain)


def _toward(qa, qb, w):
    """slerp from quaternion qa to qb by w."""
    if qa @ qb < 0:
        qb = -qb
    om_ = np.arccos(np.clip(qa @ qb, -1.0, 1.0))
    if om_ < 1e-12:
        return qa
    q = (np.sin((1 - w) * om_) * qa + np.sin(w * om_) * qb) / np.sin(om_)
    return q / np.linalg.norm(q)


ONE = np.array([1.0, 0.0, 0.0, 0.0])
SAME_POINTING = np.radians(0.15)   # rad: and a correction is carried to any frame of the observation within this of its
#                                    frame's attitude (a pointing the observation comes back to)
POINTING_STEP = np.radians(0.1)   # rad: a turn this big or more between one frame of an observation and the next starts a
#                                   new pointing (a mosaic's next tile: a NAC frame is 0.35 deg, a WAC frame 3.5); a
#                                   correction is carried only within its pointing, however far the camera drifts along it
#                                   (a movie following its target, a ring movie creeping across the rings)


def _turn(a, b):
    """The angle (rad) between two attitude matrices."""
    r = np.asarray(a) @ np.asarray(b).T
    return float(np.arccos(np.clip((np.trace(r) - 1) / 2, -1.0, 1.0)))


def _faded(E, dt):
    """Correction E (a rotation) carried dt seconds from its frame: whole to HOLD, then faded towards none."""
    w = 1.0 if dt <= HOLD else float(np.exp(-(dt - HOLD) / FADE))
    return _toward(ONE, np.array(sp.m2q(E)), w)


NEAREST = 5   # a carried frame takes the median correction of this many C-smithed frames nearest it in time
AGREE_PX = 5.0   # and only where they agree: their median distance from that median at most this many of the frame's
#                  own pixels; where JPL's own corrections scatter more (ring mosaics: tens of px), no carried value is
#                  better than raw, and the frame keeps its raw pointing (the mosaic's joint solve places its tiles)
PIXEL = {"N": 6.0e-6, "W": 6.0e-5}   # rad per pixel, NAC and WAC


def _rotvec(E):
    axis, angle = sp.raxisa(np.asarray(E))
    return np.asarray(axis) * angle


def local_error(refs, t, pixel):
    """The error rotation at t from an observation's (time, E) list: the component-wise median of the NEAREST
    C-smithed frames' corrections (as rotation vectors), faded by the time to the nearest of them (_faded). JPL
    navigated each image on its own, and on a ring mosaic the corrections of one pointing's frames scatter by tens of
    pixels and sometimes hundreds (ISS_260RI_HIPHASEFA001: 2 to 76 px, one 482 px); a median of the nearby ones is
    what they agree on, where carrying the nearest one (or blending the two either side) copied its own error. None
    where they do not agree (AGREE_PX)."""
    near = sorted(refs, key=lambda r: abs(r[0] - t))[:NEAREST]
    vs = np.array([_rotvec(E) for _, E in near])
    v = np.median(vs, axis=0)
    if np.median(np.linalg.norm(vs - v, axis=1)) > AGREE_PX * pixel:
        return None
    a = float(np.linalg.norm(v))
    E = sp.axisar(v / a, a) if a > 0 else np.eye(3)
    return sp.q2m(_faded(E, abs(near[0][0] - t)))


# pass 1: the error rotation at every smithed frame, by observation, over the whole mission (an observation can run
# across a new year: ISS_055RF_FMOVIE001_VIMS, 2007-2008)
errors_by_obs, smithed_frames, ets, raws = collections.defaultdict(list), set(), {}, {}
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
    for f in rows["frame"]:
        try: raws[f] = np.asarray(sp.pxform("J2000", BODY, ets[f]))
        except Exception: pass
    obs_of = dict(zip(rows["frame"], rows["OBSERVATION_ID"]))
    for f, g in good.items():
        if f in raws:
            errors_by_obs[obs_of[f]].append((ets[f], g @ raws[f].T, f))
# each observation's pointings: its frames in time order, a new pointing wherever the raw attitude turns POINTING_STEP
# or more from one frame to the next
pointing_of, cos_step = {}, 1 + 2 * np.cos(POINTING_STEP)
for o, g in index[index["OBSERVATION_ID"].isin(errors_by_obs)].groupby("OBSERVATION_ID"):
    fs = sorted((ets[f], f) for f in g["frame"] if f in raws)
    k, prev = 0, None
    for t, f in fs:
        if prev is not None and np.einsum("ij,ij->", raws[prev], raws[f]) < cos_step:
            k += 1
        pointing_of[f], prev = k, f
refs_by = collections.defaultdict(list)   # (observation, pointing) -> [(time, E)] in time order
for o, refs in errors_by_obs.items():
    for t, E, f in refs:
        if f in pointing_of:   # (a frame id the index lists twice keeps the pointing of its last row)
            refs_by[(o, pointing_of[f])].append((t, E))
for refs in refs_by.values():
    refs.sort(key=lambda r: r[0])
ref_list = {o: [(t, E) for t, E, f in refs] for o, refs in errors_by_obs.items()}
ref_raws = {o: np.array([raws[f] for t, E, f in refs]) for o, refs in errors_by_obs.items()}
cos_same = 1 + 2 * np.cos(SAME_POINTING)

# pass 2: every other frame of those observations takes the raw attitude turned by its observation's error
if os.path.exists(OUT): os.remove(OUT)
handle = sp.ckopn(OUT, "ISS smithed neighbours", 5000); written = []
for year, rows in index.groupby("year"):
    if YEARS and year not in YEARS: continue
    t0 = time.time()
    year_kernels(year)
    records, scattered = [], 0
    for f, o in zip(rows["frame"], rows["OBSERVATION_ID"]):
        if f in smithed_frames or f in skip or f not in pointing_of: continue
        # only from C-smithed frames of the same pointing: the attitude error changes with the attitude, so a mosaic's
        # tile at another pointing took a correction that did not fit it (the Grand Finale ring mosaic HIPHASEFA's
        # panels and ring steps, Earth Smiled's gray E-ring panel)
        # (and from those of a pointing the observation comes back to: a mosaic movie's laps, whose first lap may be
        # C-smithed and the next ones not; the 2004 approach movie 2X2MOVIEA001's raw laps sat 40 px off its own
        # C-smithed laps at the same pointings)
        near = dict(refs_by.get((o, pointing_of[f]), ()))
        same = np.einsum("nij,ij->n", ref_raws[o], raws[f]) >= cos_same
        near.update((t0, E) for (t0, E), ok in zip(ref_list[o], same) if ok)
        near = sorted(near.items())
        if not near: continue
        t = ets[f]
        E = local_error(near, t, PIXEL[f[0]])
        if E is None:
            scattered += 1
            continue
        try: cs = [E @ sp.pxform("J2000", BODY, t + d) for d in (-PAD, 0.0, PAD)]
        except Exception: continue
        records.append((f, t, cs))
    for f, t, cs in sorted(records, key=lambda r: r[1]):
        ticks = [sp.sce2c(-82, t + d) for d in (-PAD, 0.0, PAD)]
        sp.ckw03(handle, ticks[0], ticks[-1], -82000, "J2000", False, f, 3, ticks, np.array([sp.m2q(c) for c in cs]), np.zeros((3, 3)), 1, [ticks[0]])
        written.append(f)
    print(f"{year}: {len(records)} frames carried over, {scattered} left raw where JPL's corrections scatter ({time.time()-t0:.0f} s)", flush=True)
sp.ckcls(handle); ba.unload_kernels()
open(OUT[:-3] + ".lis", "w").writelines(f + "\n" for f in written)
# and the frames JPL's own per-image pointing covers (bootleg_autonav.own_pointing_frames)
open(os.path.join(os.path.dirname(OUT), "ISS_smithed_frames.lis"), "w").writelines(f + "\n" for f in sorted(smithed_frames))
