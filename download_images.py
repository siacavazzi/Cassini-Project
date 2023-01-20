# -*- coding: utf-8 -*-
"""
Spyder Editor
This is a wget script for downloading Cassini images from NASA's database. File paths should be modified 
for a given user's computer. Note: this script is not needed if the data is downloaded from my google drive link.
"""
import os
import subprocess
import wget
FILE_TYPE = "jpeg"
OUTPUT_DIR = r"C:\Users\Sam\Desktop\Planetary_Data_Project\Data\decode_buffer"
INPUT_DIR = r"C:\Users\Sam\Desktop\Planetary_Data_Project\Data\test2"

for f in os.listdir(OUTPUT_DIR):
    os.remove(os.path.join(OUTPUT_DIR, f))

SCRIPT = INPUT_DIR+r"\atlas_wget_script.bat"
with open(SCRIPT) as f:
    print("Reading file....")
    lines = f.readlines()
    
step=0
total = len(lines)
for line in lines:
    words = line.split(" ")
    url = words[4].replace("\n", "")
    step=step+1
    
    print(f"Downloading image {step} of {total} (----- {100*(step/total)}%")
    test = wget.download(f"{url}", out=OUTPUT_DIR)
   

data = os.listdir(OUTPUT_DIR)

labels = []


#for thing in data:
#    if ".LBL" in thing:
#        labels.extend(thing)
for i in range(0,len(data)):
    if data[i].find(".LBL") != -1:
        labels.append(data[i])
        target = OUTPUT_DIR + "/"+data[i]
        print(f"Converting image ({(i/len(data))*100})%")
        print(subprocess.check_output(f'cmd /k "C:/Users/Sam/Desktop/Planetary_Data_Project/transform-1.11.1/bin/transform -f {FILE_TYPE} -o {INPUT_DIR} -t {target}"'))









