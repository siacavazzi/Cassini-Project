# -*- coding: utf-8 -*-
"""
Created on Sun Apr  3 01:57:31 2022

@author: Sam
"""
import pandas as pd
from PIL import Image, ImageEnhance
import label_handler as lh
import image_correction as ic
import index_maker as im
import os
import numpy as np
import cv2

output = "output"
format = "jpg"
border = True
last = None

folder = "test"
"""
ORDER OF COLORS ***

1 ch: B&W
2 ch: red, blue *** fake green may be inserted into the middle
3 ch: red, green, blue



"""
filters = ["RED","GRN","BL"]
triband_from_dualband = True
target = "SATURN"
buffer = []







#index = pd.read_csv("ISSNA_JUPITER_3_index.csv")



# BUG: Image order is incorrect
def build_mosaic(img):
    #img = np.asarray(img)
    
    #img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    
    if len(buffer) > 4:
        buffer.pop(0)
    if len(buffer) >= 1:
        
        buffer.append(img)  
        composite = buffer[0]
        for image in buffer:
            #image = image.resize([3072,3072])
            #composite = Image.fromarray(composite)
            composite = Image.alpha_composite(composite, image)
          
        return composite
    else:
        buffer.insert(0,img)
        return img
        #return img
        

def export_sequence(camera, filters, target, delta, folder, mosaic, start_loc):
    mask = Image.open("mask.png").convert("L")
    index = im.get_images(camera, target, delta, filters, start_loc,make_csv=False)

    num_channels = len(filters)
    last = None
    for i in range(0, len(index)):
        imgs = []
        lbls = []
        
        
        
        #try:
        if True:
       
            
            
            if num_channels == 1:
                image = lh.label(index[filters[0]].iloc[i]).auto_center(border)
                image = Image.fromarray(image)
            
            else:
                
                #lbl = lh.label(index[filters[0]].iloc[i], as_png = True)
                for filter in filters:
                    
                    img = lh.label(index[filter].iloc[i], as_png = True)
                    
                    
                    #mosaic = lbl.is_mosaic()
            
                    
                 
                    imgs.append(img)
                lbl = imgs[0]    
                for j in range(0, len(imgs)):
                    
                    
                    imgs[j] = imgs[j].resize_image()   
                   
                    
                try:   
                    
                                
                    imgs = ic.align_images(imgs)
                        
                            
                except:                     
                    print("Image alignment failure")
            
            
            
               # mask = Image.fromarray(imgs[0]).split()[3]
                for j in range(0, len(imgs)):
                    
                    imgs[j] = Image.fromarray(imgs[j]).convert('L')
                
                if num_channels == 3:
                    image = Image.merge("RGBA",(imgs[2],imgs[1],imgs[0], mask))
                    #image = image.convert("RGBA")
                   
                    image = np.asarray(image)
                    
                    image = lbl.set_color(image).auto_center()
                    
                    image = Image.fromarray(image)
                    
                    if mosaic:
        
                        
                        image = build_mosaic(image)
                        
                        """
                        if last is None:
                            last = image
                        else:
                            #image = ic.match_hist(last, image)
                            ###
                            #image = np.asarray(image)
                            last = np.asarray(last)
                            
                            r,g,b,a = image.split()
                            a = a.filter(ImageFilter.BLUR)
                            #alpha = np.asarray(alpha)
                            image = Image.merge("RGBA", (r,g,b,a))
                            
                            image = np.asarray(image)
                            image = ic.imgAlign(last, image, True)
                            img = Image.fromarray(image)
                     
                            last = Image.fromarray(last)
                            ###
                            image = Image.alpha_composite(last, image)
                            last = image
                            """
                
                else:
                    if triband_from_dualband:
                        blank = Image.open("blank2.jpg").convert('L')
                        green = Image.merge("RGB",(imgs[0],blank,imgs[1])).convert('L')
                        image = Image.merge("RGB",(imgs[0],green,imgs[1]))
                    
                    else:
                        image = Image.merge("P",imgs[0],imgs[1])
            id = index["seconds_1970"].iloc[i]
            title = f"{id}_{target}" 
        
            
            
            #image = Image.fromarray(image)
            
            
            enhancer = ImageEnhance.Sharpness(image)
            
            image =  enhancer.enhance(1.5)
            
            
            image.save(f"output/{folder}/{title}.png")
"""
        except Exception as e:
           print(e)
           continue
 """




        












"""

#index = index[index["TARGET_NAME"] == "SATURN"]
folder = "saturn_true_color"
for j in range(0,len(index)):
    #try:
    data =  lh.label(index["red"].iloc[j])
    r = data.auto_center(border)
    g =  lh.label(index["grn"].iloc[j]).auto_center(border)
    b =  lh.label(index["blu"].iloc[j]).auto_center(border)

    if last is not None:
        r = ic.rotationAlign(last,r)
        last = r
        
    else:
        last = r 
       
    try:
        green = ic.rotationAlign(r, g)
        blue = ic.rotationAlign(r, b)
        
    except:
        print("align fail")
        green = g
        blue = b
    

    green = Image.fromarray(green).convert('L')
    red = Image.fromarray(r).convert('L')
    blue = Image.fromarray(blue).convert('L')
    #except:
        #print("poop")


    target = index["TARGET_NAME"].iloc[j]
    name = index["rt"].iloc[j]
    try:
       
       title = data.info["^IMAGE_HEADER"].split(".")[0].replace("(","")
       image = Image.merge("RGB",(red,green,blue))
       image.save(f"output/{folder}/{title}.png")
    except:
        print("#####FAILED######")
    
    
    print(f"{j} of {len(index)}")




# Read in the three images downloaded from here:
#rgb_default = make_lupton_rgb(i, r, g, filename="ngc6976-default.jpeg")

"""
