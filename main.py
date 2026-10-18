#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  4 17:50:45 2023

@author: sam
"""

import color_image as cd
import pandas as pd
import os
import traceback



def main():
    sequence_input = pd.read_csv("sequence_input.csv")

    for i in range(0,len(sequence_input)):
        sequence = sequence_input.iloc[i]

        target = sequence["target"]
        filters_formatted = sequence["filters"].replace(",","_")
        camera = sequence["camera"]
        folder = f"{camera}_{target}_{filters_formatted}"

        # an existing folder is reused: frames already in it are skipped (see export_sequence)
        os.makedirs(f"output/{folder}", exist_ok=True)
        try:
            print(sequence["filters"].split("_"))
            cd.export_sequence(camera,sequence["filters"].split("_"),target,sequence["delta"],folder, sequence["mosaic"], 0)
            print(sequence["filters"].split("_"))
        except Exception:
            print(f"Sequence {folder} failed:")
            traceback.print_exc()
            continue


# frames are built in parallel worker processes, which import this file again: the guard
# stops each of them from starting the whole run over
if __name__ == "__main__":
    main()
