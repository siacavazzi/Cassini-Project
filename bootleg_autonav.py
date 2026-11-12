# -*- coding: utf-8 -*-
"""
Created on Fri Nov 19 22:25:30 2021
https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/inrypl_c.html
@author: Sam Iacavazzi
"""
import spiceypy as sp
import numpy as np
import math
import os
import threading
import data_source as ds


wd = os.getcwd()
Kernel_index_path = wd + "/data/cosp_1000/index"
       
loaded = False   
    
def check_kernels(start_year,end_year):
    global loaded
    if loaded == False:
        load_kernels(start_year,end_year)
        loaded = True

def date_to_clock(start,end):
    check_kernels()
    try:
        print(sp.str2et(start))
        start = sp.sce2c(-82,sp.str2et(start))
        end = sp.sce2c(-82,sp.str2et(end))
    except:
        print("Error converting image time to spacecraft clock time")
        raise 
        
    return [start, end]
    
"""
Loads all SPICE kernels from start_year to end_year
"""
def load_kernels(start_year, end_year):
    try:
        data = ds.listdir(Kernel_index_path)
    except (FileNotFoundError, KeyError) as e:
        data = []
    found = set()
    for kernel_index in data:
        year = int(kernel_index.split("_")[1])
        if (year >= start_year) and (year <= end_year):
            print(f"Loading {year} kernels...")       
            ds.furnsh_metakernel(f"{Kernel_index_path}/{kernel_index}")
            found.add(year)
    # every year asked for has its meta-kernel, or nothing is worked out without it (ds.KernelsMissing)
    lacking = [y for y in range(start_year, end_year + 1) if y not in found]
    if lacking:
        raise ds.KernelsMissing(f"no SPICE meta-kernel for {', '.join(map(str, lacking))} in {ds.get_kernel_source()} "
                                f"(cosp_1000/index; set CASSINI_KERNELS to the kernels archive)")
    # loaded after the year's kernels so their segments win over the mission (and c-smithed) ones
    for kernel in extra_kernels():
        sp.furnsh(kernel)
    print("Done!")

"""
USGS bundle-adjusted pointing for 6,896 Titan NAC frames (Weller, Karkoschka et al., USGS data release
2026, doi:10.5066/P14FAEKS; spice_extra/usgs_titan/README.md). A CK of Cassini's attitude (-82000) and
an SPK of Cassini relative to Titan, one segment per image covering only its exposure, so every other
moment of the mission keeps the mission kernels. Tie points fit to about 1.1 px. CASSINI_USGS_TITAN=0
leaves them out.
"""
USGS_TITAN_DIR = os.environ.get("CASSINI_USGS_TITAN_DIR") or \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "spice_extra", "usgs_titan")
# in load order: the correction carried over to the other frames of the same passes (make_neighbours_ck.py),
# then USGS's own CK and SPK, which win where they overlap
USGS_TITAN_KERNELS = ["Titan_neighbours_ck.bc", "Titan_CISS_2024_ck.bc", "Titan_CISS_2024_spk.bsp"]
# written next to a geometry cache answer worked out with these kernels loaded
USGS_TITAN_TAG = "usgs-titan-2024"
_usgs_frames = None


def usgs_titan_on():
    return os.environ.get("CASSINI_USGS_TITAN", "1").lower() not in ("0", "false", "no") and \
        os.path.exists(os.path.join(USGS_TITAN_DIR, "Titan_CISS_2024_ck.bc"))


def extra_kernels():
    if not usgs_titan_on():
        return []
    return [os.path.join(USGS_TITAN_DIR, k) for k in USGS_TITAN_KERNELS if os.path.exists(os.path.join(USGS_TITAN_DIR, k))]


"""
Frame ids (N1467471504_2) the USGS kernels change: the release's image list, and the WAC frames shuttered at the
same moment as one of its NAC frames (concurrent.lis), which take the corrected spacecraft attitude too, and the
other Titan frames of the same passes the correction is carried over to (neighbours.lis)
"""
def usgs_titan_frames():
    global _usgs_frames
    if _usgs_frames is None:
        _usgs_frames = set()
        if usgs_titan_on():
            for name in ("images.lis", "concurrent.lis", "neighbours.lis"):
                if not os.path.exists(os.path.join(USGS_TITAN_DIR, name)):
                    continue
                with open(os.path.join(USGS_TITAN_DIR, name)) as f:
                    _usgs_frames |= {line.strip() for line in f if line.strip()}
    return _usgs_frames

"""
Extracts the SPICE kernels for one year from the zip without loading them
(does nothing when the data is unzipped)
"""
def extract_kernels(year):
    if not ds.using_zip(ds.get_kernel_source()):
        return
    for kernel_index in ds.listdir(Kernel_index_path):
        if int(kernel_index.split("_")[1]) == year:
            ds.extract_metakernel(f"{Kernel_index_path}/{kernel_index}")

"""
Unloads all SPICE kernels
"""
def unload_kernels():
    print("Unloading all kernels...")
    sp.kclear()
    ds.clear_spice_cache()

# NAIF frame names of the two ISS cameras (cas_v4x.tf). These include the in-flight
# boresight and twist calibration, so no hard coded camera vectors are needed.
CAMERA_FRAMES = {"NAC": "CASSINI_ISS_NAC", "WAC": "CASSINI_ISS_WAC"}

# Catalog TARGET_NAMEs that NAIF's built-in name table doesn't know: misspellings of a moon's
# name (HYROKKIN is Hyrrokkin) and the provisional designations moons had when Cassini took
# their pictures (K07S4 is S/2007 S4, named Anthe later; S12_2004 and S13_2004 are still unnamed
# and have only NAIF's provisional codes). Registered with boddef so find_target (bodn2c, spkpos)
# places them; the ephemerides are in the irregular-satellite SPK (140809BP_IRRE_00256_25017.bsp)
# and, for Anthe, the regular-moon one. Every code was checked against frames of its name: the
# body lands in the frame. S8_2004 (Fornjot, 642), S14_2004 (Hati, 643) and S18_2004 (Bestla, 639)
# are left out: in their 2007 frames the SPK puts the moon 1.4-2.6 frame widths off the CCD (the
# shots were aimed with the orbits known then), so centring on it would draw an empty frame.
CATALOG_NAMES = {"HYROKKIN": 644, "SKADI": 627, "THRYM": 630, "ERRIAPO": 628, "SUTTUNG": 623,
                 "K07S4": 649, "S12_2004": 65040, "S13_2004": 65041}
for _name, _code in CATALOG_NAMES.items():
    sp.boddef(_name, _code)
# a frame cached before its name was registered failed with this; it is worked out again
UNKNOWN_NAME = "Spice returns not found for function: bodn2c"

# Correct for light time and stellar aberration so we get where the body *appears* to
# Cassini, not where it geometrically is at the instant of the exposure
ABCORR = "LT+S"

# All pixel values are in full resolution (1024 x 1024) pixels, even for summed images
FULL_FRAME = 1024
CCD_CENTER = (FULL_FRAME - 1) / 2  # 511.5, the centre of the CCD in 0 based pixels

"""
Ephemeris time at the middle of the exposure.
IMAGE_TIME in Cassini ISS labels is shutter close, not the middle of the exposure
"""
def image_et(label):
    info = label.info
    if "IMAGE_MID_TIME" in info:
        return sp.str2et(info["IMAGE_MID_TIME"])
    return sp.str2et(info["IMAGE_TIME"]) - (exposure_s(label) or 0.0) / 2

def camera_frame(label):
    if label.info["INSTRUMENT_NAME"].find("WIDE") != -1:
        return CAMERA_FRAMES["WAC"]
    return CAMERA_FRAMES["NAC"]

"""
Pixels per unit of tan(angle) off the boresight, from the focal length (mm) and pixel
size (microns) in the instrument kernel (cas_iss_v10.ti)
"""
def pixel_scale(frame):
    camera = sp.namfrm(frame)
    focal_length = sp.gdpool(f"INS{camera}_FOCAL_LENGTH", 0, 1)[0]
    pixel_size = sp.gdpool(f"INS{camera}_PIXEL_SIZE", 0, 1)[0] / 1000
    return focal_length / pixel_size

"""
Projects a direction in the camera frame onto the CCD (pinhole model).
Per cas_iss_v10.ti, samples increase towards -X and lines towards -Y of the camera
frame. Returns (sample, line) in 0 based full resolution pixels.
"""
def project(vector, scale):
    sample = CCD_CENTER - vector[0] / vector[2] * scale
    line = CCD_CENTER - vector[1] / vector[2] * scale
    return sample, line

"""
Angle (degrees, counter clockwise like cv2.getRotationMatrix2D) to rotate the image by
so that celestial (J2000) north points up
"""
def north_angle(cam, vector, scale):
    north = sp.mxv(cam, [0.0, 0.0, 1.0])
    sample, line = project(vector, scale)
    step = sp.vadd(vector, sp.vscl(1e-4 * sp.vnorm(vector), north))
    north_sample, north_line = project(step, scale)
    return math.degrees(math.atan2(north_sample - sample, line - north_line))

"""
The exposure (seconds) of the frame label is, from its EXPOSURE_DURATION (ms), or None (the geometry cache's fill
works from index rows, which have none)
"""
def exposure_s(label):
    try:
        return float(label.info.get("EXPOSURE_DURATION")) / 1000
    except (AttributeError, TypeError, ValueError):
        return None

# how far (s) past half the exposure the image's pointing is looked for: past the rounding of IMAGE_MID_TIME to the
# millisecond (all the fill, which knows no exposures, looks past)
POINTING_SLACK = 0.002

"""
(et, J2000 to camera matrix) of Cassini's pointing (-82000) during the exposure of exposure seconds (None: unknown)
whose middle is et, from the last loaded CK with pointing within half of it (plus POINTING_SLACK), or None. For a
frame SPICE cannot place at its middle (the target behind the camera, or no pointing there at all): the C-smithed ISS
CKs (*_ISS.bc) hold an image's own pointing in a segment that covers only its exposure, and IMAGE_MID_TIME can fall
just outside it. W1354495588_1 (5 ms, Jupiter, ISS_C23JU_18ATM2X2B139_PRIME) has its middle 0.9 ms before its segment
opens, where the reconstructed CK (00275_01001rc.bc) points 91 degrees from Jupiter, so its composite failed as
"JUPITER is behind the camera" (2026-11-09); N1354496161_2 (3.8 s) has its segment at the end of its exposure, 1.9 s
on. The matrix is ckgp's own pointing turned onto the camera (no second look-up at a time that, converted back and
forth, could fall a fraction of a tick outside the segment); et is the pointing's time.
"""
def exposure_pointing(et, frame, exposure):
    half = (exposure or 0.0) / 2 + POINTING_SLACK
    try:
        clock = sp.sce2c(-82, et)
        ticks = sp.sce2c(-82, et + half) - clock
        cmat, found = sp.ckgp(-82000, clock, ticks, "J2000")
        at = sp.sct2e(-82, found)
        return at, sp.mxm(sp.pxform("CASSINI_SC_COORD", frame, at), cmat)
    except Exception:   # noqa: BLE001  (no pointing during the exposure: the frame is as SPICE had it)
        return None

"""
label = image label object
plot = TRUE for plot generation
output = target output directory
"""
def find_target(label,plot,output):
    et = image_et(label)
    frame = camera_frame(label)
    target = label.info["TARGET_NAME"]
    try:
        sp.bodn2c(target) # make sure spice knows the target
    except:
        print("Target not found")
        raise

    # apparent position of the target seen from Cassini, in the camera frame
    position, light_time = sp.spkpos(target, et, "J2000", ABCORR, "CASSINI")
    try:
        cam = sp.pxform("J2000", frame, et)
    except Exception:   # noqa: BLE001  (no pointing at the middle: looked for through the exposure below)
        cam = None
    if cam is None or sp.mxv(cam, position)[2] <= 0:
        # the pointing at the middle of the exposure may not be the image's own (exposure_pointing). Then the frame is
        # worked out at the pointing's time, the target's place too, which label.geometry keeps, so reproject.py and
        # bodies_in_frame turn and place the frame as it is placed here
        found = exposure_pointing(et, frame, exposure_s(label))
        if found is not None:
            et, cam = found
            position, light_time = sp.spkpos(target, et, "J2000", ABCORR, "CASSINI")
        elif cam is None:
            cam = sp.pxform("J2000", frame, et)   # (SPICE's own error for no pointing)
    vector = sp.mxv(cam, position)
    if vector[2] <= 0:
        raise ValueError(f"{target} is behind the camera")

    scale = pixel_scale(frame)
    sample, line = project(vector, scale)
    z = sp.vnorm(position) # distance to target in km
    angle = north_angle(cam, vector, scale)
    print(f"Target location on image sensor sample:{sample} line:{line}")
    print(f"Twist: {angle}")

    if plot:
        # only for these plots: loaded here so the frame server never pays for matplotlib
        import matplotlib.pyplot as plt
        date = label.info["IMAGE_TIME"]
        targ = label.info["TARGET_NAME"]
        f = plt.figure(figsize = (10,10))
        ax = f.add_subplot(111)
        plt.xlim(0,FULL_FRAME)
        plt.ylim(FULL_FRAME,0) # line 0 is the top of the image
        plt.xlabel("Sample")
        plt.ylabel("Line")
        plt.title(f"Location of {targ.title()} on Cassini's {frame[-3:]} sensor")
        plt.text(0.5,0.9,f"Time: {date} | Target: {targ} | distance: {round(z,1)} km",horizontalalignment='center',
        verticalalignment='center',fontsize=14, transform = ax.transAxes)
        plt.plot(sample,line,marker='o', markerfacecolor='blue', markersize=18)
        plt.savefig(f'{output}/{label.info["PRODUCT_ID"]}.png')

    # what reproject.py needs to map this image's pixels onto the target's surface
    label.geometry = {"et": et, "camera": frame, "target": target, "center": CCD_CENTER, "scale": scale}

    # shift that moves the target to the centre of the image
    x = CCD_CENTER - sample
    y = CCD_CENTER - line

    """
    x = x shift (full resolution pixels) that centres the target
    y = y shift (full resolution pixels) that centres the target
    z = distance to target in km
    angle = rotation in degrees that puts celestial north up
    """
    return [x,y,z,angle]


"""
Geometry cache: find_target's answer for each frame, kept in a small SQLite file so the
frame server can centre a frame without loading its year of kernels. Loading a year reads
1.1-1.4 GB of kernels, 4-21 s from the USB disk on the Mac Mini, and the server would pay
that every time the frames it is asked for change year.

Off unless CASSINI_GEOMETRY_CACHE names the file. Every target find_target works out is
added to it (failures too, with their reason), and `python bootleg_autonav.py geometry`
fills it for the whole mission from Image_index.csv, one year of kernels at a time.
A frame centred from the cache has label.geometry, but no kernels are loaded for it, so
surface reprojection (reproject.py) still needs its year loaded; the batch pipeline
(color_image.export_sequence) leaves the cache off.
"""
GEOMETRY_CACHE = os.environ.get("CASSINI_GEOMETRY_CACHE")
# bumped whenever find_target's answer changes, so older answers are not used
GEOMETRY_VERSION = 1
_geometry_local = threading.local()


class _CloseWithThread:
    """Closes a thread's geometry connection as the thread ends. The connection itself is only freed by the cycle
    collector (its statement cache points back at it), which can take hours in a long-running server: every request
    thread of the frame server left its connection (the .sqlite file and its -wal) open until the process hit its
    open-file limit and answered 404 to everything (the 8952 preview, 2026-11-11). This holder is in no cycle, so
    it goes, and closes the connection, as soon as the thread's locals do."""
    def __init__(self, db):
        self.db = db

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            pass


def _geometry_db():
    db = getattr(_geometry_local, "db", None)
    if db is None:
        import sqlite3
        # check_same_thread off only so the closer may run wherever the thread's locals are cleared: each connection
        # is still used by its own thread alone
        db = sqlite3.connect(GEOMETRY_CACHE, timeout=60, isolation_level=None, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS target (frame TEXT PRIMARY KEY, version INTEGER, x REAL, y REAL, "
                   "z REAL, angle REAL, et REAL, camera TEXT, target TEXT, scale REAL, error TEXT)")
        # frames whose answer came from extra pointing kernels (USGS_TITAN_TAG); a USGS frame without
        # its tag here was cached before those kernels were added and is worked out again
        db.execute("CREATE TABLE IF NOT EXISTS pointing (frame TEXT PRIMARY KEY, kernels TEXT)")
        _geometry_local.db = db
        _geometry_local.closer = _CloseWithThread(db)
    return db


def frame_id(label):
    return os.path.basename(label.info["path"]).split(".")[0]


"""
find_target's answer for label from the cache: [x, y, z, angle], with label.geometry set as
find_target sets it, or None if it isn't cached. Raises ValueError for a frame find_target
could not centre.
"""
def cached_target(label):
    if not GEOMETRY_CACHE:
        return None
    if _needs_usgs(frame_id(label)):
        return None
    row = _geometry_db().execute("SELECT x, y, z, angle, et, camera, target, scale, error FROM target "
                                 "WHERE frame = ? AND version = ?", (frame_id(label), GEOMETRY_VERSION)).fetchone()
    if row is None:
        return None
    if row[8] is not None:
        if UNKNOWN_NAME in row[8] and _known(label.info["TARGET_NAME"]):
            return None
        raise ValueError(row[8])
    label.geometry = {"et": row[4], "camera": row[5], "target": row[6], "center": CCD_CENTER, "scale": row[7]}
    hit = shown_targets().get(frame_id(label))
    if hit:
        # a frame that shows another body than its target (shown_targets): that body's place
        label.geometry["target"] = hit[0]
        return [hit[1], hit[2], hit[3], row[3]]
    return list(row[:4])


def _needs_usgs(frame):
    if frame not in usgs_titan_frames():
        return False
    return _geometry_db().execute("SELECT 1 FROM pointing WHERE frame = ? AND kernels = ?",
                                  (frame, USGS_TITAN_TAG)).fetchone() is None


def _known(target):
    try:
        sp.bodn2c(target)
        return True
    except Exception:
        return False


def _store_rows(rows):
    db = _geometry_db()
    db.execute("BEGIN")
    db.executemany("INSERT OR REPLACE INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    usgs = usgs_titan_frames()
    db.executemany("INSERT OR REPLACE INTO pointing VALUES (?, ?)",
                   [(row[0], USGS_TITAN_TAG) for row in rows if row[0] in usgs])
    db.execute("COMMIT")


def _row(frame, target_loc=None, geometry=None, error=None):
    if error is not None:
        return (frame, GEOMETRY_VERSION, None, None, None, None, None, None, None, None, str(error)[:300])
    return (frame, GEOMETRY_VERSION, *map(float, target_loc), float(geometry["et"]), geometry["camera"],
            geometry["target"], float(geometry["scale"]), None)


"""
How much a shift worked out at the scale scale (find_target's pixel_scale, SPICE's pinhole camera) grows on a frame
of camera (a NAIF frame name) as the pipeline draws it: a WAC frame corrected by CISSCAL's geometric correction
(geometric_correction.py, the "geom" step) is a pinhole camera of focal length F_LINEAR (200.956 mm) where the
instrument kernel has 200.77 mm, so its pixels are LINEAR_SCALE / scale of SPICE's. 1 for the NAC, and for a WAC frame
the request leaves uncorrected. info = the frame's label (its shutter state), or None to ask only the request's steps.
"""
def linear_ratio(camera, scale, info=None):
    if camera != CAMERA_FRAMES["WAC"] or not scale:
        return 1.0
    import geometric_correction as gc
    if info is not None:
        on = gc.active(info)
    else:
        import calibration as cal
        on = cal.step("calibrate") and cal.step("geom")
    return gc.LINEAR_SCALE / float(scale) if on else 1.0


"""
find_target's answer [x, y, z, angle] for label on the frame as the pipeline draws it (linear_ratio): the shift and
label.geometry's scale grown for a corrected WAC frame. The cache keeps SPICE's own answer, so it stays good with the
"geom" step on or off.
"""
def linearized(label, target_loc):
    g = getattr(label, "geometry", None)
    if target_loc is None or not g:
        return target_loc
    ratio = linear_ratio(g.get("camera"), g.get("scale"), label.info)
    if ratio == 1.0:
        return target_loc
    label.geometry = dict(g, scale=float(g["scale"]) * ratio)
    return [target_loc[0] * ratio, target_loc[1] * ratio, *target_loc[2:]]


"""
find_target through the cache: the cached answer, or find_target's (kernels for the frame's
year must be loaded then; load_year is called first to load them) added to the cache, on the frame
as the pipeline draws it (linearized)
"""
def find_target_cached(label, load_year=None):
    target_loc = cached_target(label)
    if target_loc is not None:
        return linearized(label, target_loc)
    if load_year:
        load_year()
    try:
        target_loc = find_target(label, False, "graphs")
    except Exception as e:
        if GEOMETRY_CACHE:
            _store_rows([_row(frame_id(label), error=f"{type(e).__name__}: {e}")])
        raise
    if GEOMETRY_CACHE:
        _store_rows([_row(frame_id(label), target_loc, label.geometry)])
    else:
        # no cache (the batch pipeline): the body the frame shows worked out here, as shown_targets reads it from the
        # cache's tables (kernels for the frame are loaded)
        target = label.geometry["target"]
        try:
            km = _radius_km(target)
            found = shown_body(km / target_loc[2] * label.geometry["scale"] if km else None,
                               bodies_in_frame(label.geometry["et"], label.geometry["camera"], target))
        except Exception:   # noqa: BLE001  (no other body worked out: the frame keeps its target)
            found = None
        if found:
            label.info.setdefault("ARCHIVE_TARGET_NAME", label.info.get("TARGET_NAME"))
            label.info["TARGET_NAME"] = found[0]
            label.geometry["target"] = found[0]
            target_loc = [-found[1], -found[2], found[4], target_loc[3]]
    return linearized(label, target_loc)


"""
Fills the geometry cache for every frame in Image_index.csv, a year at a time: the year's
kernels are loaded once, then find_target runs on each of its frames from the index's
IMAGE_MID_TIME, camera and target (the same fields find_target reads from a label).
Frames already cached are skipped, so it can be stopped and run again; frames the USGS Titan
kernels cover are worked out again once after those kernels are added (--usgs-titan does only them).
"""
def build_geometry_cache(years=None, target=None, usgs_only=False):
    import contextlib
    import io
    import time
    import types
    import pandas as pd
    index = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Image_index.csv"),
                        usecols=["path", "IMAGE_MID_TIME", "INSTRUMENT_ID", "TARGET_NAME"], low_memory=False)
    index = index[index["path"].notna() & index["IMAGE_MID_TIME"].notna()]
    if target:
        index = index[index["TARGET_NAME"] == target]
    index = index.assign(year=index["IMAGE_MID_TIME"].str[:4].astype(int), day=index["IMAGE_MID_TIME"].str[5:8].astype(int),
                         frame=index["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0])
    # label_handler.auto_center loads the kernels of the year of IMAGE_TIME (shutter close), which
    # can be the next year for a frame taken in the last seconds of a year; those are left to it
    index = index[~((index["day"] >= 365) & (index["IMAGE_MID_TIME"].str[9:11] == "23"))]
    cached = list(_geometry_db().execute("SELECT frame, error FROM target WHERE version = ?", (GEOMETRY_VERSION,)))
    # frames that failed because SPICE didn't know their target's name, which is registered now (CATALOG_NAMES)
    retry = set(index.loc[index["TARGET_NAME"].isin(CATALOG_NAMES), "frame"]) & {
        frame for frame, error in cached if error and UNKNOWN_NAME in error}
    # frames the USGS Titan kernels cover that were worked out before they were added
    usgs = usgs_titan_frames()
    retry |= usgs - {frame for frame, in _geometry_db().execute("SELECT frame FROM pointing WHERE kernels = ?",
                                                               (USGS_TITAN_TAG,))}
    if usgs_only:
        index = index[index["frame"].isin(usgs)]
    done = {frame for frame, _ in cached} - retry
    for year, rows in index.groupby("year"):
        if years and year not in years:
            continue
        rows = rows[~rows["frame"].isin(done)]
        if rows.empty:
            continue
        start = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            unload_kernels()
            load_kernels(year, year)
        loaded = time.time() - start
        out = []
        for frame, mid, camera, name in zip(rows["frame"], rows["IMAGE_MID_TIME"], rows["INSTRUMENT_ID"], rows["TARGET_NAME"]):
            label = types.SimpleNamespace(info={"path": frame + ".png", "IMAGE_MID_TIME": mid, "TARGET_NAME": name,
                                                "INSTRUMENT_NAME": "WIDE ANGLE CAMERA" if camera == "ISSWA" else "NARROW ANGLE CAMERA"})
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    out.append(_row(frame, find_target(label, False, "graphs"), label.geometry))
            except Exception as e:
                out.append(_row(frame, error=f"{type(e).__name__}: {e}"))
            if len(out) >= 5000:
                _store_rows(out)
                out = []
        _store_rows(out)
        print(f"{year}: {len(rows)} frames in {time.time() - start:.0f} s (kernels {loaded:.0f} s)", flush=True)
    unload_kernels()


"""
Works out again every frame the geometry cache holds as behind the camera, with its label's exposure: the fill knows
no exposures (it looks only POINTING_SLACK past the middle), and rows from before exposure_pointing never looked. A
frame whose pointing during its exposure has the target in front is stored placed; the rest keep their error. Run
once on a cache filled before 2026-11-09 (`python bootleg_autonav.py geometry --behind`); 247 rows, 2 placed.
"""
def recheck_behind():
    import contextlib
    import io
    import pandas as pd
    import label_handler
    rows = [f for f, in _geometry_db().execute("SELECT frame FROM target WHERE version = ? AND error LIKE ?",
                                               (GEOMETRY_VERSION, "%is behind the camera%"))]
    index = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Image_index.csv"),
                        usecols=["path"], low_memory=False)
    paths = {os.path.basename(p).split(".")[0]: p for p in index["path"].dropna()}
    out, placed, years = [], 0, {}
    for frame in rows:
        if frame not in paths:
            continue
        label = label_handler.label(paths[frame], as_png=True)
        years.setdefault(int(label.info["IMAGE_TIME"][:4]), []).append(label)
    for year, labels in sorted(years.items()):
        with contextlib.redirect_stdout(io.StringIO()):
            unload_kernels()
            load_kernels(year, year)
        for label in labels:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    out.append(_row(frame_id(label), find_target(label, False, "graphs"), label.geometry))
                placed += 1
                print(f"placed {frame_id(label)}", flush=True)
            except Exception as e:
                out.append(_row(frame_id(label), error=f"{type(e).__name__}: {e}"))
    _store_rows(out)
    unload_kernels()
    print(f"{len(out)} behind-the-camera frames worked out again, {placed} placed", flush=True)


"""
The other bodies in each frame, beside its target: where SPICE puts every Saturn moon (NAIF 601-653), Saturn and
Jupiter whose disk touches the frame, kept in the geometry cache's bodies table, so a movie's stabilization can be
held on its target when a second moon is in the picture (obs_mosaic.steady_chain: Sam 2026-11-04, a moon transiting
another pulled the stabilization off the target and back). One row per body in the frame: x, y where its centre is
from the CCD's centre (full resolution pixels, the camera's own axes, as find_target projects it), r its radius
(pixels, the PCK's mean radius over the distance) and km its distance, so which is in front is known; a frame worked out with no body in it but its target has one row
with body '' so it reads as done. Filled by `python bootleg_autonav.py bodies`, a year of kernels at a time, for the
frames the target table places.
"""
BODIES_VERSION = 1
BODY_CODES = [699, 599] + list(range(601, 654))
BODY_MARGIN = 0.1   # of a frame: a body this far past the frame's edge is listed too (a limb coming in)


def _bodies_db():
    db = _geometry_db()
    db.execute("CREATE TABLE IF NOT EXISTS bodies (frame TEXT, version INTEGER, body TEXT, x REAL, y REAL, r REAL, km REAL)")
    db.execute("CREATE INDEX IF NOT EXISTS bodies_frame ON bodies (frame)")
    return db


_radii = {}


def _mean_radius(code):
    if code not in _radii:
        try:
            _radii[code] = float(np.mean(sp.bodvcd(code, "RADII", 3)[1]))
        except Exception:
            _radii[code] = None
    return _radii[code]


def bodies_in_frame(et, frame, target):
    """[(body, x, y, r, km)] for every body of BODY_CODES but target whose disk touches the frame (BODY_MARGIN round
    it) at et seen by camera frame: x, y its centre from the CCD's centre (full resolution pixels, camera axes), r its
    radius in pixels, km its distance. Kernels for et must be loaded."""
    cam = sp.pxform("J2000", frame, et)
    scale = pixel_scale(frame)
    reach = FULL_FRAME / 2 * (1 + 2 * BODY_MARGIN)
    out = []
    for code in BODY_CODES:
        try:
            name = sp.bodc2n(code)
        except Exception:
            continue
        if name == target:
            continue
        radius = _mean_radius(code)
        if not radius:
            continue
        try:
            position, _ = sp.spkpos(str(code), et, "J2000", ABCORR, "CASSINI")
        except Exception:
            continue
        vector = sp.mxv(cam, position)
        if vector[2] <= 0:
            continue
        sample, line = project(vector, scale)
        r = radius / sp.vnorm(position) * scale
        x, y = sample - CCD_CENTER, line - CCD_CENTER
        if max(abs(x), abs(y)) - r <= reach:
            out.append((name, float(x), float(y), float(r), float(sp.vnorm(position))))
    return out


def bodies_of(ids):
    """{frame id: [(body, x, y, r, km)]} from the bodies table, for the frames ids that were worked out ([] for one
    with no other body in it): every body but the one the frame shows (its target, or shown_targets'); a frame not
    worked out is left out. On the frame as it is drawn, as stacking.places
    reads the target's shift: a WAC frame's x, y and r grown by its geometric correction (linear_ratio)."""
    if not GEOMETRY_CACHE or not os.path.exists(GEOMETRY_CACHE):
        return {}
    db, out = _bodies_db(), {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        for frame, body, x, y, r, km, camera, scale in db.execute(
                f"SELECT b.frame, b.body, b.x, b.y, b.r, b.km, t.camera, t.scale FROM bodies b LEFT JOIN target t "
                f"ON t.frame = b.frame AND t.version = ? WHERE b.version = ? AND b.frame IN ({','.join('?' * len(part))})",
                (GEOMETRY_VERSION, BODIES_VERSION, *part)):
            got = out.setdefault(frame, [])
            if body:
                k_ = linear_ratio(camera, scale)
                got.append((body, x * k_, y * k_, r * k_, km))
    shown = shown_targets()
    for frame in [f for f in out if f in shown]:
        # a frame that shows another body than its target (shown_targets) is drawn round that body: the archive's
        # target is one of the others
        row = db.execute("SELECT target, x, y, z, camera, scale FROM target WHERE frame = ? AND version = ?",
                         (frame, GEOMETRY_VERSION)).fetchone()
        target, x, y, z, camera, scale = row
        k_, km = linear_ratio(camera, scale), _radius_km(target)
        out[frame] = [b for b in out[frame] if b[0] != shown[frame][0]] + \
                     [(target, -x * k_, -y * k_, (km / z * scale if km else 0.0) * k_, z)]
    return out


"""
The body a frame shows, when it is not the archive's target (Sam 2026-11-12: a few clear filter frames of the Saturn
approach looked unprocessed, as if nothing centred them). A frame whose target's disk is SEEN_RADIUS px or less in
radius (a moon a pixel or two across: the satellite searches ISS_C42OT_SATELLORB001/002, the storm watches' RIDER frames
on a small moon, a mutual event's far moon) is a picture of the biggest body SPICE puts on it, when that body's disk is
SHOWN_RADIUS px or more and the frame has it whole (Saturn, a third of the frame wide). It is centred, turned, grouped
into passes and calibrated as one (label.TARGET_NAME, reel's index, stacking.places, cached_target, bodies_of), where
centring on the dot moved the picture a few pixels and left Saturn cut at its edge, and a storm watch's frame of Saturn
was not centred at all (its moon too small to centre on). A frame that cuts its biggest disk (Saturn's limb filling a
WAC frame, its centre at the edge; Saturn filling the frame behind a moon) keeps its target: centred on that body, most
of the view would be empty, and a smaller body is not what the frame shows. The archive's target is kept as the label's
ARCHIVE_TARGET_NAME. Read from the geometry cache's target and bodies tables (find_target's and bodies_in_frame's
answers, which stay SPICE's own for the archive's target), so it needs the bodies table filled. Over the mission
(2026-11-12) 717 of 407,795 placed frames: 461 on Saturn, the rest on Rhea, Dione, Enceladus, Mimas, Tethys and Titan.
"""
SEEN_RADIUS = 2.0     # px: a disk this small is a dot (a cosmic ray hit or a star is as big); nothing to centre on
SHOWN_RADIUS = 12.0   # px: a disk at least this big (24 px across) is a body the picture shows (an 8 px moon in a
                      # corner of a frame full of rings, N1480613061_1, is not what it shows)


def shown_body(radius, others):
    """The body (one of others, bodies_in_frame's (body, x, y, r, km)) a frame shows instead of its target, whose disk
    is radius px in radius (None: of no known size), or None when the frame shows its target."""
    if radius is None or radius > SEEN_RADIUS:
        return None
    seen = [b for b in others if b[0] and b[3] is not None and b[3] >= SHOWN_RADIUS]
    if not seen:
        return None
    biggest = max(seen, key=lambda b: b[3])
    # the biggest disk on the frame, when the frame has it whole (one it cuts, Saturn filling the frame behind a moon,
    # is what the frame shows, and no centring helps)
    return biggest if max(abs(biggest[1]), abs(biggest[2])) + biggest[3] <= FULL_FRAME / 2 else None


def _radius_km(target):
    """The target's mean radius (km): the frame server's table (obs_mosaic.RADIUS), else SPICE's, else None."""
    try:
        import obs_mosaic
        return obs_mosaic.RADIUS.get(target)
    except ImportError:
        try:
            return _mean_radius(sp.bodn2c(target))
        except Exception:   # noqa: BLE001  (no kernels loaded, or a target SPICE does not know: no size)
            return None


_shown = None
_shown_lock = threading.Lock()


def shown_targets():
    """{frame: (body, x, y, z)} for every frame of the geometry cache that shows another body than its target
    (shown_body): the body, the shift that centres it (find_target's x, y, SPICE's own pixels) and its distance (km).
    Read once (the bodies table is filled ahead, a frame's answer never changes)."""
    global _shown
    if _shown is not None:
        return _shown
    with _shown_lock:
        if _shown is None:
            out = {}
            if GEOMETRY_CACHE and os.path.exists(GEOMETRY_CACHE):
                db = _bodies_db()
                rows = {}
                for frame, target, z, scale, body, x, y, r, km in db.execute(
                        "SELECT t.frame, t.target, t.z, t.scale, b.body, b.x, b.y, b.r, b.km FROM bodies b JOIN target t "
                        "ON t.frame = b.frame AND t.version = ? WHERE b.version = ? AND t.error IS NULL AND b.r >= ?",
                        (GEOMETRY_VERSION, BODIES_VERSION, SHOWN_RADIUS)):
                    rows.setdefault(frame, [target, z, scale, []])[3].append((body, x, y, r, km))
                sizes = {}
                for frame, (target, z, scale, others) in rows.items():
                    if target not in sizes:
                        sizes[target] = _radius_km(target)
                    km = sizes[target]
                    found = shown_body(km / z * scale if km and z and scale else None, others)
                    if found:
                        out[frame] = (found[0], -found[1], -found[2], found[4])
            _shown = out
    return _shown


def relabel(label):
    """Makes label a picture of the body its frame shows (shown_targets): TARGET_NAME that body, the archive's
    target kept as ARCHIVE_TARGET_NAME. Nothing for a frame that shows its target."""
    if not GEOMETRY_CACHE or "TARGET_NAME" not in label.info:
        return
    hit = shown_targets().get(frame_id(label))
    if hit and label.info["TARGET_NAME"] != hit[0]:
        label.info.setdefault("ARCHIVE_TARGET_NAME", label.info["TARGET_NAME"])
        label.info["TARGET_NAME"] = hit[0]


def build_bodies_cache(years=None, observations=None):
    """Fills the bodies table for every frame the target table places (or only those of the observations named),
    a year of kernels at a time; frames already in it are skipped, so it can be stopped and run again."""
    import contextlib
    import io
    import time
    import pandas as pd
    index = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Image_index.csv"),
                        usecols=["path", "IMAGE_MID_TIME", "OBSERVATION_ID"], low_memory=False)
    index = index[index["path"].notna() & index["IMAGE_MID_TIME"].notna()]
    if observations:
        index = index[index["OBSERVATION_ID"].isin(observations)]
    index = index.assign(year=index["IMAGE_MID_TIME"].str[:4].astype(int),
                         frame=index["path"].str.rsplit("/", n=1).str[-1].str.split(".").str[0])
    db = _bodies_db()
    placed = {f: (et, cam, tgt) for f, et, cam, tgt in db.execute(
        "SELECT frame, et, camera, target FROM target WHERE version = ? AND error IS NULL", (GEOMETRY_VERSION,))}
    done = {f for (f,) in db.execute("SELECT DISTINCT frame FROM bodies WHERE version = ?", (BODIES_VERSION,))}
    for year, rows in index.groupby("year"):
        if years and year not in years:
            continue
        frames = [f for f in rows["frame"] if f in placed and f not in done]
        if not frames:
            continue
        start = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            unload_kernels()
            load_kernels(year, year)
        loaded = time.time() - start
        out = []
        for f in frames:
            et, cam, tgt = placed[f]
            try:
                found = bodies_in_frame(et, cam, tgt)
            except Exception:
                continue   # (no pointing for it this year's kernels hold: left for another run)
            out += [(f, BODIES_VERSION, *b) for b in found] or [(f, BODIES_VERSION, "", None, None, None, None)]
            if len(out) >= 5000:
                db.execute("BEGIN")
                db.executemany("INSERT INTO bodies VALUES (?, ?, ?, ?, ?, ?, ?)", out)
                db.execute("COMMIT")
                out = []
        db.execute("BEGIN")
        db.executemany("INSERT INTO bodies VALUES (?, ?, ?, ?, ?, ?, ?)", out)
        db.execute("COMMIT")
        print(f"{year}: {len(frames)} frames in {time.time() - start:.0f} s (kernels {loaded:.0f} s)", flush=True)
    unload_kernels()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Fills the geometry cache (CASSINI_GEOMETRY_CACHE) from Image_index.csv")
    ap.add_argument("what", choices=["geometry", "bodies"])
    ap.add_argument("--years", help="e.g. 2005 or 2004-2017 (default: every year)")
    ap.add_argument("--target", help="only frames of this target, e.g. ENCELADUS")
    ap.add_argument("--observations", nargs="*", help="bodies: only the frames of these OBSERVATION_IDs")
    ap.add_argument("--usgs-titan", action="store_true", help="only the frames the USGS Titan kernels cover")
    ap.add_argument("--behind", action="store_true", help="geometry: work out again the frames cached as behind the "
                    "camera, with their labels' exposures (recheck_behind)")
    args = ap.parse_args()
    if not GEOMETRY_CACHE:
        ap.error("set CASSINI_GEOMETRY_CACHE to the cache file, e.g. /Volumes/LaCie/claude_scratch_spk/geometry.sqlite")
    years = None
    if args.years:
        first, _, last = args.years.partition("-")
        years = set(range(int(first), int(last or first) + 1))
    if args.what == "bodies":
        build_bodies_cache(years, args.observations)
    else:
        if args.usgs_titan and not usgs_titan_frames():
            ap.error(f"no USGS Titan kernels in {USGS_TITAN_DIR} (or CASSINI_USGS_TITAN=0)")
        if args.behind:
            recheck_behind()
        else:
            build_geometry_cache(years, args.target, args.usgs_titan)
