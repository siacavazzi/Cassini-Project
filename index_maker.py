# -*- coding: utf-8 -*-
"""
Created on Tue Dec  7 23:22:08 2021

Cassini project file manager

@author: Sam
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
                
image_folders = ["/data/wac_data","/data/nac_data"]

spice_index = wd + "/data/cosp_1000/index"
spice_data = wd + "/data/cosp_1000/data"


spice_path = "SPICE_PATH"

    
"""
Creates a CSV index file with all images. Converts the image date to seconds since Jan 01, 1970 for efficient comparisons later
NOTE: This will probably take a long tmime
"""    
def create_master_index():  
    output = pd.DataFrame()
 
    for camera in image_folders:
        labels = lh.load_lbls(camera)
        
        # variables of interest to extract from image meta data 
        target_variables = ["path","IMAGE_MID_TIME","INSTRUMENT_ID","TARGET_NAME","TARGET_DESC","FILTER_NAME","OBSERVATION_ID","MISSING_LINES"]

        for i in range(0, len(labels)):
            image_data = labels[i]
            image_data = lh.subset(image_data.get_info(), target_variables)
            
            date = datetime.datetime.strptime(str(image_data['IMAGE_MID_TIME']).replace('Z',''),'%Y-%jT%H:%M:%S.%f')
            
            # add column which represents the image date in seconds since 1970 for efficiency later on
            image_data["seconds_1970"] = int((date-datetime.datetime(1970,1,1)).total_seconds())
            
            image_data["filter1"] = image_data["FILTER_NAME"].split(',')[0].replace(')',"").replace('(',"")
            image_data["filter2"] = image_data["FILTER_NAME"].split(',')[1].replace(')',"")
            
            
            image_data["year"] = int(image_data["IMAGE_MID_TIME"].split("-")[0])
            output = output.append(image_data,ignore_index=True)
            print(f"Processing loaded labels: {len(output)}")
    
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
    output = pd.DataFrame()
   
    index = pd.read_csv("Image_index.csv")
    
    index = index[index["INSTRUMENT_ID"] == camera]
    index = index[index["TARGET_NAME"] == target]
    index["date"] = ""
    index["color"] = ""    
    index["SEQUENCE"] = ""
    runlen = len(index) 
    num_channels = len(filters)
    
    
    
    i = start_loc
    while i < runlen:
        color = index["FILTER_NAME"].iloc[i]
        ch = {}
        if len(filters) == 1:
            if filters[0] in index['FILTER_NAME'].iloc[i]:
                print("Image found")
                ch[filters[0]] = index['path'].iloc[i]
                id = index["seconds_1970"].iloc[i]
                ch["seconds_1970"] = id
                output = output.append(ch,ignore_index=True)
                index["SEQUENCE"].iloc[i] = len(output)
                print(f"{i} of {runlen}")
                i = i + 1
                continue
            
        if check_filters(color,filters):
            # colors are denoted by channels since there may be 1-3
            
            seq = pd.DataFrame()
            j = 1
            
            while((index["seconds_1970"].iloc[i+j] - index["seconds_1970"].iloc[i]) < delta):
                if j == 1:
                    seq = seq.append(index.iloc[i]) 
                    
                seq = seq.append(index.iloc[i+j])                             
                j = j + 1
            
                for x in range(0,len(seq)):
                
                    for z in range(0, num_channels):
                   
                        if filters[z] in seq['FILTER_NAME'].iloc[x]:
                            ch[filters[z]] = "data/" + seq["path"].iloc[x]
                            id = seq["seconds_1970"].iloc[x]
            
                  
              
                
            if len(ch) == num_channels:
                print("Image found")
                ch["seconds_1970"] = id
                output = output.append(ch,ignore_index=True)
                index["SEQUENCE"].iloc[i] = len(output)
                i = i + j - 1
                
            if i + j + 25 >= runlen:
                print(f"this error is dumb: {i+j}")
                break
                     
        i = i + 1      
        print(f"{i} of {runlen}")
        
    if num_channels == 3:
        output = output[[filters[0],filters[1],filters[2],'seconds_1970']]
        
        
    if make_csv is True:
        output.to_csv(f"{camera}_{target}_{num_channels}_index.csv")
    return output






