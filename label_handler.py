# -*- coding: utf-8 -*-
"""
Created on Tue Nov  2 12:33:42 2021

@author: Sam I
"""
import os
import subprocess
import pandas as pd
import numpy as np
import cv2
import bootleg_autonav as ba
import image_correction as ic

#######################################################################################

#######################################################################################
#data = os.listdir(image_lib)

cur_year = 0
sequence_counts = {}
sequence_list = {}
cur_lbl = 1
wd = os.getcwd()
#tot_lbl = len(data)/2
def rotate_image(image, angle):
    image_center = tuple(np.array(image.shape[1::-1]) / 2)
    rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
    result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
    return result

# definition of a label - contains essential information for... stuff
"""
Label class
Label objects represent an image and once loaded contain all image data for processing
"""
class label:
    
    def __init__(self, input_file, raw = False, as_png = False):
        info={}
        self.color = False
        self.color_img = None
        self.info = info
        if not raw:
            pointer = input_file.split('.')[0] + ".png"
        if as_png:
            self.path = input_file.split('.')[0] + ".lbl"
            self.info["path"] = self.path
        else:
            self.path = input_file
            
            self.info["path"] = pointer
        # read label file ans parse into self
        with open(self.path) as f_in:
            for line in f_in:
                if line:
                    line = line.strip()
                    if not line.find("=") == -1:
                        char = '\\'
                        values = line.replace(" ","").replace('"',"").replace(char[0],"").strip()
                    
                        values = values.split("=")
                        self.info[values[0]] = values[1]
                        
                            

                        
    def get_info(self):
        return self.info
     
            
    # Exports self as an image of format f_type    
    """
    Converts the label from .img format to a format of choice
    format = desired image output format - "png" or "jpg"
    output = output directory for converted image
    
    returns out - the new file path of the converted image
    """
    def export_raw(self,format,output):
        print(subprocess.check_output(f'cmd /k "{wd}/transform-1.11.1/bin/transform.bat -f {format} -o {output} -t {self.path}"'))
        out = output +"/" + self.info["^IMAGE_HEADER"].split(".")[0].replace("(","") + "." + format
        #img = cv2.imread(out)
        return out
    
    def export(self):
        return self.info["path"].split('.')[0] + ".png"
    
    def set_color(self, color_image):
        self.color = True
        self.color_img = color_image
        return self
        
        
    
    def export_img(self):
        out = self.export("png","image_output")
        return cv2.imread(out)
    
    def rotate_image(image, angle):
        image_center = tuple(np.array(image.shape[1::-1]) / 2)
        rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
        result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
        return result
    
    def resize_image(self):
        img = cv2.imread(self.info["path"].split('.')[0] + ".png")
        if int(self.info["LINES"]) < 1024:
            
            #scale_percent = 200
            #width = int(img.shape[1] * scale_percent / 100)
            #height = int(img.shape[0] * scale_percent / 100)
            dim = (1024,1024)
            img = cv2.resize(img, dim, interpolation = cv2.INTER_AREA)
            
        return img
    
    """
    Traslates image
    format = output format
    x = x pixels to move image by
    y = y pixels to move image by
    angle = angle to rotate image in degrees
    border = T/F add border or not
    """
    def translate(self,format, x,y,angle,border):
        
        if self.color:
            
            img = self.color_img
            lines =1024
        
           
        else:
            image = label.export(self)
            lines = int(self.info["LINES"])
            img = cv2.imread(image)
        M = np.float32([[1, 0, x], [0, 1, y]])
        
        print(f"number of lines {lines}")
        

        
        
        if border:
            
            max_bound = max(x,y)
            
            if max_bound > (lines*2):
                border = int(max_bound) + 1024
            else:
                border = lines     
            
            border = 1024
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
            img= cv2.copyMakeBorder(img,border,border,border,border,cv2.BORDER_CONSTANT,value=[0,0,0,0])   
        
        (rows, cols) = img.shape[:2]
        img = cv2.warpAffine(img, M, (cols, rows),borderMode=cv2.BORDER_TRANSPARENT)
  
        name = self.info["SPACECRAFT_CLOCK_START_COUNT".split('.')[0]]
        print(name)
        img = rotate_image(img,angle)

        return img
        
    
    """
    Automagically centers and rotates the image to align with its target
    border = True/False - should a border be added around the image (default is true since the border is pretty essential)
    """
    def auto_center(self, border=True):
        im_year = int(self.info["IMAGE_TIME"].split('-')[0])
        global cur_year
        
        if cur_year != im_year:
            ba.unload_kernels()
            ba.load_kernels(im_year,im_year)
            cur_year = im_year
            
        target_loc = ba.find_target(self, False, "graphs")    
        print(target_loc)
        return self.translate("png", target_loc[0],target_loc[1],target_loc[3],border)
    
    def is_mosaic(self):
        panels = self.info["OBSERVATION_ID"].split("X")
        if len(panels) > 1:
            return True
        else:
            return False
    

"""
Load all labels in the target directory
folder_path = path of labels to load
"""
def load_lbls(folder_path):
    data = os.listdir(folder_path)
    total = len(data) /2
    cur = 0
    labels = []
    for i in range(0,len(data)):
        file = data[i]
        if file.endswith(".LBL"):
            ticks = file.strip('W').strip('.LBL')
            ticks = ticks[:-2]
            cur+=1
            print(f"Label {cur} of {total} ")
            path = folder_path + "/" + file
           # print(path)
            labels.append(label(path))


def subset(dictionary, col_names):
    return {key: dictionary[key] for key in col_names}



def convert_image(image_path,output,format):
    print(subprocess.check_output(f'cmd /k "C:/Users/Sam/Desktop/Planetary_Data_Project/Programs-code/transform-1.11.1/bin/transform.bat -f {format} -o {output} -t {image_path}"'))
    



        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        





    
