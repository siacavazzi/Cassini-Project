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
