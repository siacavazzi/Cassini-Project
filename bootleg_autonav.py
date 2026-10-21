# -*- coding: utf-8 -*-
"""
Created on Fri Nov 19 22:25:30 2021
https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/inrypl_c.html
@author: Sam Iacavazzi
"""
import spiceypy as sp
import numpy as np
import math
import matplotlib.pyplot as plt
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
    data = ds.listdir(Kernel_index_path)
    for kernel_index in data:
        year = int(kernel_index.split("_")[1])
        if (year >= start_year) and (year <= end_year):
            print(f"Loading {year} kernels...")       
            ds.furnsh_metakernel(f"{Kernel_index_path}/{kernel_index}")
            
 
            
    print("Done!")

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
    exposure = float(info.get("EXPOSURE_DURATION", 0)) / 1000  # ms -> s
    return sp.str2et(info["IMAGE_TIME"]) - exposure / 2

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
    cam = sp.pxform("J2000", frame, et)
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


def _geometry_db():
    db = getattr(_geometry_local, "db", None)
    if db is None:
        import sqlite3
        db = sqlite3.connect(GEOMETRY_CACHE, timeout=60, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS target (frame TEXT PRIMARY KEY, version INTEGER, x REAL, y REAL, "
                   "z REAL, angle REAL, et REAL, camera TEXT, target TEXT, scale REAL, error TEXT)")
        _geometry_local.db = db
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
    row = _geometry_db().execute("SELECT x, y, z, angle, et, camera, target, scale, error FROM target "
                                 "WHERE frame = ? AND version = ?", (frame_id(label), GEOMETRY_VERSION)).fetchone()
    if row is None:
        return None
    if row[8] is not None:
        raise ValueError(row[8])
    label.geometry = {"et": row[4], "camera": row[5], "target": row[6], "center": CCD_CENTER, "scale": row[7]}
    return list(row[:4])


def _store_rows(rows):
    db = _geometry_db()
    db.execute("BEGIN")
    db.executemany("INSERT OR REPLACE INTO target VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.execute("COMMIT")


def _row(frame, target_loc=None, geometry=None, error=None):
    if error is not None:
        return (frame, GEOMETRY_VERSION, None, None, None, None, None, None, None, None, str(error)[:300])
    return (frame, GEOMETRY_VERSION, *map(float, target_loc), float(geometry["et"]), geometry["camera"],
            geometry["target"], float(geometry["scale"]), None)


"""
find_target through the cache: the cached answer, or find_target's (kernels for the frame's
year must be loaded then; load_year is called first to load them) added to the cache
"""
def find_target_cached(label, load_year=None):
    target_loc = cached_target(label)
    if target_loc is not None:
        return target_loc
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
    return target_loc


"""
Fills the geometry cache for every frame in Image_index.csv, a year at a time: the year's
kernels are loaded once, then find_target runs on each of its frames from the index's
IMAGE_MID_TIME, camera and target (the same fields find_target reads from a label).
Frames already cached are skipped, so it can be stopped and run again.
"""
def build_geometry_cache(years=None, target=None):
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
    done = {r[0] for r in _geometry_db().execute("SELECT frame FROM target WHERE version = ?", (GEOMETRY_VERSION,))}
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


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Fills the geometry cache (CASSINI_GEOMETRY_CACHE) from Image_index.csv")
    ap.add_argument("what", choices=["geometry"])
    ap.add_argument("--years", help="e.g. 2005 or 2004-2017 (default: every year)")
    ap.add_argument("--target", help="only frames of this target, e.g. ENCELADUS")
    args = ap.parse_args()
    if not GEOMETRY_CACHE:
        ap.error("set CASSINI_GEOMETRY_CACHE to the cache file, e.g. /Volumes/LaCie/claude_scratch_spk/geometry.sqlite")
    years = None
    if args.years:
        first, _, last = args.years.partition("-")
        years = set(range(int(first), int(last or first) + 1))
    build_geometry_cache(years, args.target)
