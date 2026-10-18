# Cassini Project
 ## Overview

The Cassini project is my attempt at processing the data from NASA's Cassini mission into color images and videos. You can learn more about the Cassini mission [here](https://en.wikipedia.org/wiki/Cassini%E2%80%93Huygens). The TL;DR is that Cassini was a probe sent to explore Saturn and its moons. Over the course of the mission it took over 450,000 black and white images. These images are available to the public on [NASA's PDS website](https://pds-imaging.jpl.nasa.gov/search/?fq=-ATLAS_THUMBNAIL_URL%3Abrwsnotavail.jpg&fq=ATLAS_MISSION_NAME%3Acassini&q=*%3A*). My main goal with this project is to use the Cassini data to make videos of its encounters with various moons and planets.

 ### Iapetus in color
 ![Image](https://imgur.com/PAfwi0e.gif)

[Video of Jupiter](https://www.youtube.com/watch?v=r13RPdnDQAQ)

## What does it do?


 This program does 4 main things:
 * Search through all of Cassini's images for those of interest
 * Create color images from 3 filter B&W images (including aligning them)
 * Center the target body within the image frame
 * Create multi image mosaics

Below is a diagram which demonstrates this.

### Jupiter in false color
![Image](https://i.redd.it/emslqzuhnxh91.gif)

## How to use

1. Install required packages: `pip install -r requirements.txt`
### Required python packages
* Pandas
* Numpy
* Spiceypy
* OpenCV 2
* PIL (I know this is kind of redundant with opencv - will fix in a future update)
* Matplotlib

2. Download Cassini data [here](https://drive.google.com/file/d/1hrxyrGBIkVQfzReZ5hACr2lJZiHwxWBb/view?usp=share_link) Note: this ZIP file is quite large at 97 GB and will take a while to download. This data has been slightly preprocessed from the original NASA data to reduce file sizes and program complexity. This file in its original format would be nearly 1 TB!

3. Place data.zip in the main folder. There is no need to unzip it: images and labels are read straight out of the zip, and the SPICE kernels for the year being processed are extracted to a temporary spice_cache folder (deleted again when the program moves on to another year). To keep the zip somewhere else, set the CASSINI_DATA environment variable to its path. If the zip was made with Windows' built in zip tool and Python reports an unsupported compression method, install the zipfile-deflate64 package.

   You can still unzip the data and place the data folder into the main folder instead; a data folder takes priority over data.zip.

4. Only if you unzipped the data: run the create_spice_index() function located within index_maker.py - essentially this function updates the SPICE data indecies with correct file paths for your machine. This step isn't needed when reading from data.zip.

5. Open sequence_input.csv. This is the input used to tell the program which target bodies and images you are interested in. The fields in the CSV are as follows: 

### camera: ISSWA or ISSNA
Cassini carried 2 different cameras onboard, one with a narrow FOV and one with a wide FOV. Putting ISSNA into this field will tell the program to search for images from the narrow angle camera and ISSWA to search for the wide camera.
Example inputs:
* ISSWA
* ISSNA

### filters: 
Specify the filter(s) from which to create processed images. Cassini's cameras take pictures in B&W and use filter wheels to create color images. Between 1-3 filters can be inputted. If one filter is chosen all images will be outputted as B&W. Otherwise this the filters will correspond to red, green, then blue images. Filters are seperated by an underscore (_). Please refer to the [Cassini imaging user's guide page 149+](https://pds-imaging.jpl.nasa.gov/documentation/iss_data_user_guide_180916.pdf) for more information about filters, including which filters and filter combinations are availible. Since Cassini uses dual filter wheels the user can specify either one or two filters per channel. If only one is specified, the other filter wheel is ignored. Note: this can lead to some color differences between images. To specify a specific combination of filter wheels a comma (,) can be used between the names of the filters.
Example inputs:
* RED_GRN_BL1 - uses red, green and blue filters to create true color images. Ignores secondary filter wheel.
* CL1,RED_CL1,GRN_CL1,BL1 - creates true color images same as before but specifies a clear secondary filter to eliminate color changing. Note: this will result in fewer total images.
* CL1,CL2 - uses clear filters to create B&W images. The comma specifies the secondary filter.

### target:
The target body of interest, typed in all caps. 
Example inputs:
* SATURN
* TITAN
* JUPITER (this is valid since Cassini did a flyby of Jupiter on its way to Saturn)

### delta:
The maximum number of seconds between images taken with different filters to be considered 'part of the same image'. For example for Cassini to take a color image it actually takes 3 different images at 3 different times. There is a delay between each image due to the need to change filters and reset the camera. So if this field is set to 300, then the red, green, and blue channel images can be taken a maximum of 300 seconds apart. If this is confusing then just set this to around 300, which seems to work most of the time. If there is a short flyby where a sequence of images is taken faster than normal and this number is large the color channels of the images will not match.
Example inputs:
* 300 (use this number by default)
* 200

### mosaic: TRUE or FALSE
Whether or not to clear the image background for a new frame. When a target body does not fit within Cassini's FOV the spacecraft often took mosaic images. Enable this for large bodies such as Saturn or Jupiter, especially when using the narrow FOV camera. When enabled a processed image will be drawn on top of the previous images. If this explaination is confusing please refer to part [5] of the diagram below the what does it do?? section.
Example inputs:
* TRUE
* FALSE

Note: this is a spreadsheet and can accept multiple entries. Upon finishing one the program will move on to the next.

6. Processed images are placed in the output folder, one folder per sequence. If a run is stopped, running it again keeps the frames already made and carries on (mosaic sequences are always redrawn, since each frame is drawn on top of the ones before it).

7. Run main.py - note: it may take a while to finish. Data is place into an output folder. Frames are built in parallel by worker processes: one per 6 GB of memory, at most 4 (2 on a 16 GB machine). Each worker needs up to about 1 GB of memory: set the CASSINI_WORKERS environment variable to use more on a machine with memory to spare, or to 1 to build one frame at a time. The first run with data.zip saves an index of the zip in a zip_index folder (about 370 MB for the full dataset), which later runs and the workers reuse.


# Data Sources

[Processed data for use with this program](https://drive.google.com/file/d/1hrxyrGBIkVQfzReZ5hACr2lJZiHwxWBb/view?usp=share_link)

[Images from NASA's PDS website](https://pds-imaging.jpl.nasa.gov/search/?fq=-ATLAS_THUMBNAIL_URL%3Abrwsnotavail.jpg&fq=ATLAS_MISSION_NAME%3Acassini&q=*%3A*) Note: a wget script (included in this repository) is needed to download these images

[Attitude and instrument (SPICE) data needed for calculating where planetary bodies are located in each image](https://naif.jpl.nasa.gov/pub/naif/pds/data/co-s_j_e_v-spice-6-v1.0/cosp_1000/)

[Cassini imaging data user guide (basically my bible for writing this program)](https://pds-imaging.jpl.nasa.gov/documentation/iss_data_user_guide_180916.pdf)
