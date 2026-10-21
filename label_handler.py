# -*- coding: utf-8 -*-
"""
Created on Tue Nov  2 12:33:42 2021

@author: Sam I
"""
import os
import gzip
import subprocess
import pandas as pd
import numpy as np
import cv2
import bootleg_autonav as ba
import image_correction as ic
import data_source as ds
import calibration as cal

#######################################################################################

#######################################################################################
#data = os.listdir(image_lib)

cur_year = 0
sequence_counts = {}
sequence_list = {}
cur_lbl = 1
wd = os.getcwd()
# transparent padding (pixels) added on every side of a frame before it is moved into place;
# raise it for close-up mosaics whose panels sit far from the target's center
canvas_border = 1024
#tot_lbl = len(data)/2
def rotation_matrix(image, angle):
    image_center = tuple((np.array(image.shape[1::-1]) - 1) / 2)
    return cv2.getRotationMatrix2D(image_center, angle, 1.0)

def rotate_image(image, angle):
    rot_mat = rotation_matrix(image, angle)
    result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
    return result


"""
Box (top, bottom, left, right) of a canvas of rows x cols that M moves the rectangle
(x0, y0)-(x1, y1) into, with a margin for interpolation
"""
def moved_box(M, x0, y0, x1, y1, rows, cols, margin=2):
    corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], float) @ np.asarray(M, float).T
    left, top = np.floor(corners.min(0)).astype(int) - margin
    right, bottom = np.ceil(corners.max(0)).astype(int) + margin
    return max(top, 0), min(bottom, rows), max(left, 0), min(right, cols)


"""
cv2.warpAffine of src onto an empty canvas of shape, worked out only inside box: the frame
covers a small part of the bordered canvas, and everywhere else stays empty anyway
"""
def warp_into(src, M, shape, box, **kwargs):
    out = np.zeros(shape, src.dtype)
    top, bottom, left, right = box
    if bottom > top and right > left:
        M = np.array(M, np.float64)
        M[0, 2] -= left
        M[1, 2] -= top
        # warped into zeros: BORDER_TRANSPARENT leaves pixels outside src as they were
        out[top:bottom, left:right] = cv2.warpAffine(src, M, (right - left, bottom - top), dst=out[top:bottom, left:right].copy(), **kwargs)
    return out

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
        for line in ds.read_text(self.path).splitlines():
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
        return ds.imread(out)
    
    def rotate_image(image, angle):
        image_center = tuple(np.array(image.shape[1::-1]) / 2)
        rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
        result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
        return result
    
    def resize_image(self):
        img = ds.imread(self.info["path"].split('.')[0] + ".png")
        if ds.lut8():
            # the lean archive stores camera codes; stretch them like the old PNGs
            img = cal.display_stretch(img, self.info)
        if int(self.info["LINES"]) < 1024:
            
            #scale_percent = 200
            #width = int(img.shape[1] * scale_percent / 100)
            #height = int(img.shape[0] * scale_percent / 100)
            dim = (1024,1024)
            img = cv2.resize(img, dim, interpolation = cv2.INTER_AREA)

        return img

    """
    Which pixels of the frame hold real data, sized like resize_image (True = valid).
    When the downlink lost packets, the ends of some lines never arrived and were filled
    with zeros; those show up as streaks in color composites. The binary line prefix
    (.prefix.gz, lean archive) gives each line's valid pixel count in bytes 2-3. Without
    it, a frame with MISSING_LINES has its trailing zero runs of 16+ pixels marked instead
    (packets hold whole multiples of 16 pixels).
    """
    def valid_mask(self):
        base = self.info["path"].split('.')[0]
        lines, samples = int(self.info["LINES"]), int(self.info["LINE_SAMPLES"])
        mask = np.ones((lines, samples), bool)
        if ds.exists(base + ".prefix.gz"):
            prefix = np.frombuffer(gzip.decompress(ds.read_bytes(base + ".prefix.gz")), np.uint8).reshape(lines, -1)
            valid = prefix[:, 2].astype(int) * 256 + prefix[:, 3]
            mask &= np.arange(samples) < valid[:, None]
        elif str(self.info.get("MISSING_LINES", "0")).isdigit() and int(self.info["MISSING_LINES"]) > 0:
            # some labels say MISSING_LINES = "N/A"; only a count of lines means anything is missing
            img = ds.imread(base + ".png", cv2.IMREAD_GRAYSCALE)
            if img is not None and img.shape == mask.shape:
                nonzero = img[:, ::-1] != 0
                tail = np.where(nonzero.any(1), np.argmax(nonzero, 1), samples)
                tail = np.where(tail >= 16, tail, 0)
                mask &= np.arange(samples) < (samples - tail)[:, None]
        if lines < 1024:
            mask = cv2.resize(mask.astype(np.uint8), (1024, 1024), interpolation=cv2.INTER_NEAREST) > 0
        return mask

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
            # find_target works in full resolution pixels, so bring summed (512/256
            # line) images up to 1024 lines before shifting them
            img = self.resize_image()
            lines = 1024
        print(f"number of lines {lines}")
        

        
        
        if border:
            border = canvas_border
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
        pad = border if border else 0
        h, w = img.shape[:2]
        rows, cols = h + 2 * pad, w + 2 * pad
        shape = (rows, cols) + img.shape[2:]

        # the frame shifted into the middle of the canvas, the same as warping the whole
        # bordered canvas but only where the frame lands (a few blank pixels around it, so its
        # edge blends with the border the same way). BORDER_TRANSPARENT leaves pixels the
        # shifted image doesn't cover blank
        edge = 2
        src = cv2.copyMakeBorder(img, edge, edge, edge, edge, cv2.BORDER_CONSTANT, value=[0, 0, 0, 0])
        M = np.float32([[1, 0, x + pad - edge], [0, 1, y + pad - edge]])
        frame_box = moved_box(M, 0, 0, w + 2 * edge, h + 2 * edge, rows, cols, 0)
        img = warp_into(src, M, shape, frame_box, borderMode=cv2.BORDER_TRANSPARENT)
  
        name = self.info["SPACECRAFT_CLOCK_START_COUNT".split('.')[0]]
        print(name)
        # rotate_image, again only where the frame is
        R = rotation_matrix(img, angle)
        top, bottom, left, right = frame_box
        img = warp_into(img, R, shape, moved_box(R, left, top, right, bottom, rows, cols), flags=cv2.INTER_LINEAR)

        # where each pixel of the original image ended up: shift (after the border) then
        # rotation, as a 3x3 matrix for reproject.py
        shift = np.array([[1, 0, x + pad], [0, 1, y + pad], [0, 0, 1]])
        self.placement = np.vstack([rotation_matrix(img, angle), [0, 0, 1]]) @ shift

        return img
        
    
    """
    Automagically centers and rotates the image to align with its target
    border = True/False - should a border be added around the image (default is true since the border is pretty essential)
    """
    def auto_center(self, border=True):
        im_year = int(self.info["IMAGE_TIME"].split('-')[0])

        def load_year():
            global cur_year
            if cur_year != im_year:
                ba.unload_kernels()
                # set first: a year whose kernels fail to load is not reloaded for every frame
                cur_year = im_year
                ba.load_kernels(im_year,im_year)

        # from the geometry cache when it is on (the frame server), so no kernels have to be loaded
        target_loc = ba.find_target_cached(self, load_year)
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
    data = ds.listdir(folder_path)
    total = len(data) /2
    cur = 0
    labels = []
    for i in range(0,len(data)):
        file = data[i]
        if file.upper().endswith(".LBL"):
            cur+=1
            if cur % 1000 == 0:
                print(f"Label {cur} of {total} ")
            path = folder_path + "/" + file
            labels.append(label(path))
    return labels


def subset(dictionary, col_names):
    return {key: dictionary[key] for key in col_names}



def convert_image(image_path,output,format):
    print(subprocess.check_output(f'cmd /k "C:/Users/Sam/Desktop/Planetary_Data_Project/Programs-code/transform-1.11.1/bin/transform.bat -f {format} -o {output} -t {image_path}"'))
    



        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        





    
