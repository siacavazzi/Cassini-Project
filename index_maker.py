# -*- coding: utf-8 -*-
"""
Created on Tue Dec  7 23:22:08 2021

Cassini project file manager

@author: Sam Iacavazzi
"""

import label_handler as lh
import pandas as pd
import os
from tempfile import mkstemp
from shutil import move, copymode
from os import fdopen, remove
import datetime


import warnings
warnings.filterwarnings("ignore") 
# This section creates an index file for all image data for easy search later on
wd = os.getcwd()
                
image_folders = ["wac_data","nac_data"]

spice_index = wd + "/data/cosp_1000/index"
spice_data = wd + "/data/cosp_1000/data"


spice_path = "SPICE_PATH"

    
"""
Creates a CSV index file with all images. Converts the image date to seconds since Jan 01, 1970 for efficient comparisons later
NOTE: This will probably take a long tmime
"""    
def create_master_index():  
    rows = []
    # variables of interest to extract from image meta data 
    target_variables = ["path","IMAGE_MID_TIME","INSTRUMENT_ID","TARGET_NAME","TARGET_DESC","FILTER_NAME","OBSERVATION_ID","MISSING_LINES"]
 
    for camera in image_folders:
        for label in lh.load_lbls(camera):
            image_data = lh.subset(label.get_info(), target_variables)
            
            date = datetime.datetime.strptime(str(image_data['IMAGE_MID_TIME']).replace('Z',''),'%Y-%jT%H:%M:%S.%f')
            
            # add column which represents the image date in seconds since 1970 for efficiency later on
            image_data["seconds_1970"] = int((date-datetime.datetime(1970,1,1)).total_seconds())
            
            image_data["filter1"] = image_data["FILTER_NAME"].split(',')[0].replace(')',"").replace('(',"")
            image_data["filter2"] = image_data["FILTER_NAME"].split(',')[1].replace(')',"")
            
            
            image_data["year"] = int(image_data["IMAGE_MID_TIME"].split("-")[0])
            rows.append(image_data)
        print(f"Processing loaded labels: {len(rows)}")
    
    # get_images walks the index in time order
    output = pd.DataFrame(rows).sort_values("seconds_1970", kind="stable")
    # stored as floats like the original index, so frame names (e.g. 970413901.0_JUPITER.png) stay the same
    output[["seconds_1970","year"]] = output[["seconds_1970","year"]].astype(float)
    output.to_csv("Image_index.csv")
    
    
def replace(file_path, pattern, subst):
    #Create temp file
    fh, abs_path = mkstemp()
    with fdopen(fh,'w') as new_file:
        with open(file_path) as old_file:
            for line in old_file:
                new_file.write(line.replace(pattern, subst))
    #Copy the file permissions from the old file to the new file
    copymode(file_path, abs_path)
    #Remove original file
    remove(file_path)
    #Move new file
    move(abs_path, file_path)

"""
Replaces SPICE file location in SPICE indecies to make SPICE file location on the local machine
"""    
def create_spice_index():
    files = os.listdir(spice_index)
    print(files)
    for file in files:
        file = f"{spice_index}/{file}"
        replace(file, spice_path, spice_data)
        
        
"""
Reads Image_index.csv once and keeps it for later sequences
"""
_index = None

def load_index():
    global _index
    if _index is None:
        _index = pd.read_csv("Image_index.csv", usecols=["path","INSTRUMENT_ID","TARGET_NAME","FILTER_NAME","seconds_1970"])
    return _index


# helper function
def check_filters(color,filters):
    for filter in filters:
        if filter in color:
            return True
        
    return False
        
"""
Returns index of image sequences to create color images
camera = camera to pick images from - either "ISSWA" OR "ISSNA"
target = target body
delta = acceptable timeframe in seconds between images to be considered a sequence - a delta of 300 means that images taken within 5 mins of eachother are essentially the same image in different color bands
^ Longer deltas may result in more found color sequences but at the expense of potential misalignment between images
red/green/blue_filter = filter set (given "(CL1,CL2)") to assign to respective color
ex: red_filter = "(CL1,RED)" would assign images taken with the red filter to the red image index
"""
def get_images(camera,target,delta,filters,start_loc,make_csv=False):

    if len(filters) > 3 or len(filters) < 1:
        print("Only 1-3 filters per sequence are supported")
        return
   
    index = load_index()
    index = index[(index["INSTRUMENT_ID"] == camera) & (index["TARGET_NAME"] == target)]
    # plain lists and arrays: indexing a DataFrame row by row is very slow
    names = index["FILTER_NAME"].tolist()
    paths = index["path"].tolist()
    seconds = index["seconds_1970"].to_numpy()
    runlen = len(index) 
    num_channels = len(filters)
    rows = []
    
    i = start_loc
    while i < runlen:
        if num_channels == 1:
            if filters[0] in names[i]:
                rows.append({filters[0]: paths[i], "seconds_1970": seconds[i]})
            i = i + 1
            continue
            
        if check_filters(names[i],filters):
            # the sequence is image i plus every image taken less than delta seconds after it
            end = i + 1
            while end < runlen and seconds[end] - seconds[i] < delta:
                end = end + 1
            
            # colors are denoted by channels since there may be 1-3
            ch = {}
            if end > i + 1:
                for x in range(i, end):
                    for z in range(0, num_channels):
                        if filters[z] in names[x]:
                            ch[filters[z]] = "data/" + paths[x]
                            id = seconds[x]
                
            if len(ch) == num_channels:
                ch["seconds_1970"] = id
                rows.append(ch)
                # skip past the images used by this sequence
                i = end - 1
                     
        i = i + 1      
        
    print(f"Found {len(rows)} images in {runlen} {camera} images of {target}")
    output = pd.DataFrame(rows, columns=list(filters) + ["seconds_1970"])
        
    if make_csv is True:
        output.to_csv(f"{camera}_{target}_{num_channels}_index.csv")
    return output
