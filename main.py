#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  4 17:50:45 2023

@author: sam
"""

import color_image as cd
import pandas as pd
import os



sequence_input = pd.read_csv("sequence_input.csv")


for i in range(0,len(sequence_input)):
    sequence = sequence_input.iloc[i]           
    
    target = sequence["target"]
    filters_formatted = sequence["filters"].replace(",","_")
    camera = sequence["camera"]
    folder = f"{camera}_{target}_{filters_formatted}"
    
    os.mkdir(f"output/{folder}")
    try:
      

        print(sequence["filters"].split("_"))
        cd.export_sequence(camera,sequence["filters"].split("_"),target,sequence["delta"],folder, sequence["mosaic"], 0)
        print(sequence["filters"].split("_"))
    except:
        continue        
            

