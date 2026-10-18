# -*- coding: utf-8 -*-
"""
Created on Sun Apr  3 01:57:31 2022

@author: Sam Iacavazzi
"""

from PIL import Image, ImageEnhance
import label_handler as lh
import image_correction as ic
import index_maker as im
import stacking
import calibration as cal
import numpy as np
import mosaic as mo
import os
import traceback


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
stack_repeats = True # combine repeat exposures of each filter to cut noise
calibrate = True # put every filter on one brightness scale so colors are true (False = old per frame stretch)


def build_mosaic(img):
    return Image.fromarray(mo.add_frame(np.asarray(img)))

        

def export_sequence(camera, filters, target, delta, folder, mosaic, start_loc):
    mask = Image.open("mask.png").convert("L")
    index = im.get_images(camera, target, delta, filters, start_loc,make_csv=False)

    num_channels = len(filters)
    last = None
    mo.reset()
    skipped = 0
    for i in range(0, len(index)):
        imgs = []
        lbls = []
        
        id = index["seconds_1970"].iloc[i]
        title = f"{id}_{target}" 
        out_path = f"output/{folder}/{title}.png"
        # frames from an earlier run are kept. Mosaics are always redrawn since
        # each frame is drawn on top of the frames before it
        if not mosaic and os.path.exists(out_path):
            skipped += 1
            continue
        
        try:
        
       
            
            
            if num_channels == 1:
                lbl = lh.label(index[filters[0]].iloc[i], as_png = True)
                gray = Image.fromarray(lbl.resize_image()).convert('L')
                image = np.asarray(Image.merge("RGBA",(gray,gray,gray, mask)))
                image = Image.fromarray(lbl.set_color(image).auto_center(border))
                if mosaic:
                    image = build_mosaic(image)
            
            else:
            
                for filter in filters:
                    
                    lbl, img = stacking.load_stacked(index[filter].iloc[i], max_frames = 5 if stack_repeats else 1)
            
                    lbls.append(lbl)
                    imgs.append(img)
                if calibrate:
                    # puts every filter on the same brightness scale (see calibration.py)
                    imgs = cal.load_channels(lbls, imgs)
                
                # align to the middle frame in time so the largest offset is as small as possible
                order = sorted(range(len(lbls)), key=lambda j: lbls[j].info["IMAGE_TIME"])
                ref = order[len(order)//2]
                lbl = lbls[ref]
                                    
                try:   
                    
                                
                    imgs = ic.align_images(imgs, ref)
                        
                            
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
                        blank = Image.new('L', imgs[0].size, 0)
                        green = Image.merge("RGB",(imgs[0],blank,imgs[1])).convert('L')
                        image = Image.merge("RGB",(imgs[0],green,imgs[1]))
                    
                    else:
                        image = Image.merge("P",imgs[0],imgs[1])
            #image = Image.fromarray(image)
            
            
            enhancer = ImageEnhance.Sharpness(image)
            
            image =  enhancer.enhance(1.5)
            
            
            image.save(out_path)

        except Exception:
           print(f"Failed to make {title}:")
           traceback.print_exc()
           continue
    if skipped:
        print(f"Kept {skipped} frames already in output/{folder}")
