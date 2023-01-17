# -*- coding: utf-8 -*-
"""
Created on Fri Nov 19 22:25:30 2021
https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/inrypl_c.html
@author: Sam
"""
import spiceypy as sp
import numpy as np
import math
import matplotlib.pyplot as plt
import os


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
    data = os.listdir(Kernel_index_path)
    for kernel_index in data:
        year = int(kernel_index.split("_")[1])
        if (year >= start_year) and (year <= end_year):
            print(f"Loading {year} kernels...")       
            sp.furnsh(f"{Kernel_index_path}/{kernel_index}")
            
 
            
    print("Done!")

"""
Unloads all SPICE kernels
"""
def unload_kernels():
    print("Unloading all kernels...")
    sp.kclear()

"""
label = image label object
plot = TRUE for plot generation
output = target output directory
"""
def find_target(label,plot,output):
    utctim = label.info["IMAGE_TIME"]
    et = sp.str2et( utctim )
    target = label.info["TARGET_NAME"]
    camera = label.info["INSTRUMENT_NAME"]
    if camera.find("WIDE") != -1:
        camera = 'CASSINI_ISS_WAC'
    else:
        camera = 'CASSINI_ISS_NAC'
    print(camera)
    camera = sp.bods2c(camera)
    print(camera)
    camera_data = sp.getfov(camera,4)
    fov = camera_data[4]
    
    if camera == "CASSINI_ISS_NAC":
        nac = [0.0057600,-0.99999982,-0.00017100]
        
        #nac = [-0.99999982,0.0057600,-0.00017100]
        
    else:
        nac = [0.0,0.0,1.0]
    
    try:
        target = int(sp.bodn2c(target)) # try to find spice id code of target
    except:
        print("Target not found")
        raise

    # get target pos vector and 1 way light time in seconds
    print(f"camera: {camera}")
    xyzd = sp.spkez(target,et,sp.bodc2n(camera),"NONE",-82)
    print(xyzd)
    #RAY = xyzd[0][3:6]
    RAY = [0,0,0]
    VTARG = xyzd[0][0:3] # target 3d vector
    DTARG = xyzd[1] * sp.clight() # distance to target in km 
    
    # figure out twist angle
    cam_vec = [math.radians(-90),math.radians(0),math.radians(90)] # camera matrix
    cam_vec = sp.eul2m(cam_vec[0],cam_vec[1],cam_vec[2],1,2,3)
    angle = sp.pxform("CASSINI_SC_COORD","J2000",et) # convert camera matrix to j2000
    angle = sp.mxm(angle,cam_vec)
    angle = sp.m2eul(angle,3,1,3)
    angle = math.degrees(angle[2])
    print(f"Twist: {angle}")
    
    
    
    im_space = sp.nvc2pl(nac,DTARG) # make spice plane normal to pointing vector
    
    targ_loc = sp.inrypl(RAY,VTARG,im_space) # check to see where camera ray intersects target plane
    
    targ_loc = targ_loc[1][0:2]  
    fov_intersects = []
    
    for vector in fov:
        # check where rays intersect target plane
        fov_intersects.append(sp.inrypl(RAY,vector,im_space)[1])  
        x_ints = []
        y_ints = []
        
    for intersect in fov_intersects:
        x_ints.append(intersect[0])
        y_ints.append(intersect[1] )
            
    max_x = max(x_ints)
    max_y = max(y_ints)
    min_x = min(x_ints)     
    min_y = min(y_ints)   
    
    # set z to target distance
    z = DTARG
         
    lines = 1024 # get image resolution 
    
    x_bound = 0
    y_bound = 0
    
    """
    if targ_loc[0] > max_x:
        range = max_x - min_x 
        min_x = min_x + range
        max_x = max_x + range
        x_bound = -lines
        
    if targ_loc[0] < min_x:
        range = max_x - min_x
        min_x = min_x - range        
        max_x = max_x - range
        x_bound = lines
        
    if targ_loc[1] > max_y:
        range = max_y - min_y
        max_y = max_y + range
        min_y = min_y + range
        y_bound = lines
        
    if targ_loc[1] < min_y:
        range = max_y - min_y
        min_y = min_y - range
        max_y = max_y - range
        y_bound = -lines
     """   
    i=0

    while targ_loc[0] > max_x:
        i = i + 1
        range = max_x - min_x 
        min_x = min_x + range
        max_x = max_x + range
        x_bound = lines * i
        print(1)
        
        
    i = 0
     
    while targ_loc[0] < min_x:
        i = i + 1
        range = max_x - min_x 
        min_x = min_x - range
        max_x = max_x - range
        x_bound = -lines * i
        print(2)
        
        
    i = 0
    while targ_loc[1] > max_y:
        i = i + 1
        range = max_y - min_y 
        min_y = min_y + range
        max_y = max_y + range
        y_bound = -lines * i
        print(3)
        
        
    i = 0
    while targ_loc[1] < min_y:
        i = i + 1
        range = max_y - min_y 
        min_y = min_y - range
        max_y = max_y - range
        y_bound = lines * i
        

    
    x = np.interp(targ_loc[0],[min_x,max_x],[1,lines])
    x = lines - x
    y = np.interp(targ_loc[1],[min_y,max_y],[1,lines])
    print(f"Target location on image sensor x:{x} y:{y}")
    
    # if the target is out of camera bounds stop
  
    x = x + x_bound
    y = y + y_bound

    
            
    if plot:
        date = label.info["IMAGE_TIME"] 
        targ = label.info["TARGET_NAME"]           
        f = plt.figure(figsize = (10,10))
        ax = f.add_subplot(111)
        plt.ylim(1,lines)
        plt.xlim(1,lines)
        plt.xlabel("X pixels")
        plt.ylabel("Y pixels")
        plt.title(f"Location of {targ.title()} on Cassini's wide angle camera sensor")
        plt.text(0.5,0.9,f"Time: {date} | Target: {targ} | distance: {round(z,1)} km",horizontalalignment='center',
        verticalalignment='center',fontsize=14, transform = ax.transAxes)
        plt.plot(x,y,marker='o', markerfacecolor='blue', markersize=18)
        plt.savefig(f'{output}/{label.info["PRODUCT_ID"]}.png')
        
    x = (lines/2) - x
    y = y - (lines/2)
        
        
    """
    x = x pos of target in camera in pixels
    y = y pos of target in camera in pixels
    z = distance to target in km
    angle = optical twist angle relative to J2000 frame in degrees
    """    
    return [x,y,z,angle]
            




    




