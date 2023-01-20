# -*- coding: utf-8 -*-
"""
Created on Sun Apr  3 01:57:31 2022

@author: Sam
"""

from PIL import Image, ImageEnhance
import label_handler as lh
import image_correction as ic
import index_maker as im
import numpy as np


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

triband_from_dualband = True
buffer = []

# BUG: Image order is incorrect sometimes
def build_mosaic(img):

    
    if len(buffer) > 4:
        buffer.pop(0)
    if len(buffer) >= 1:
        
        buffer.append(img)  
        composite = buffer[0]
        for image in buffer:

            composite = Image.alpha_composite(composite, image)
          
        return composite
    else:
        buffer.insert(0,img)
        return img

        

def export_sequence(camera, filters, target, delta, folder, mosaic, start_loc):
    mask = Image.open("mask.png").convert("L")
    index = im.get_images(camera, target, delta, filters, start_loc,make_csv=False)

    num_channels = len(filters)
    last = None
    for i in range(0, len(index)):
        imgs = []
        lbls = []
        
        
        
        try:
        
       
            
            
            if num_channels == 1:
                image = lh.label(index[filters[0]].iloc[i]).auto_center(border)
                image = Image.fromarray(image)
            
            else:
            
                for filter in filters:
                    
                    img = lh.label(index[filter].iloc[i], as_png = True)
            
                 
                    imgs.append(img)
                lbl = imgs[0]    
                for j in range(0, len(imgs)):
                    
                    
                    imgs[j] = imgs[j].resize_image()   
                                    
                try:   
                    
                                
                    imgs = ic.align_images(imgs)
                        
                            
                except:                     
                    print("Image alignment failure")
            
                for j in range(0, len(imgs)):
                    
                    imgs[j] = Image.fromarray(imgs[j]).convert('L')
                
                if num_channels == 3:
                    image = Image.merge("RGBA",(imgs[2],imgs[1],imgs[0], mask))
                    
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

        except Exception as e:
           print(e)
           continue
