# Cassini Project
 ## Overview

The Cassini project is my attempt at processing the data from NASA's Cassini mission into color images and videos. You can learn more about the Cassini mission [here](https://en.wikipedia.org/wiki/Cassini%E2%80%93Huygens). The TL;DR is that Cassini was a probe sent to explore Saturn and its moons. Over the course of the mission it took over 450,000 black and white images. These images are available to the public on [NASA's PDS website](https://pds-imaging.jpl.nasa.gov/search/?fq=-ATLAS_THUMBNAIL_URL%3Abrwsnotavail.jpg&fq=ATLAS_MISSION_NAME%3Acassini&q=*%3A*). My main goal with this project is to use the Cassini data to make videos of its encounters with various moons and planets.

 ### Iapetus in color
 ![Image](https://imgur.com/PAfwi0e.gif)


## What does it do??


 This program does 4 main things:
 * Search through all of Cassini's images for those of interest
 * Create color images from 3 filter B&W images (including aligning them)
 * Center the target body within the image frame
 * Create multi image mosaics

Below is a diagram which demonstrates this.

### Jupiter in false color
![Image](https://i.redd.it/emslqzuhnxh91.gif)

## How to use

1. Install required packages
### Required python packages
* Pandas
* Numpy
* SPICEYPY
* OpenCV 2
* PIL (I know this is kind of redundant with opencv - will fix in a future update)
* Matplotlib

2. Download Cassini data [here]() Note: this ZIP file is quite large and will take a while to download. This data has been slightly preprocessed from the original NASA data to reduce file sizes and program complexity.

3. Unzip cassini data and place the data folder into the main folder.

4. Run the create_spice_index() function located within index_maker.py - essentially this function updates the SPICE data indecies with correct file paths for your machine. 

5. Open sequence_input.csv. This is the input used to tell the program which target bodies and images you are interested in. The fields in the CSV are as follows: 

### camera: ISSWA or ISSNA
Cassini carried 2 different cameras onboard, one with a narrow FOV and one with a wide FOV. Putting ISSNA into this field will tell the program to search for images from the narrow angle camera and ISSWA is for the wide camera.
Example inputs:
* ISSWA
* ISSNA

### filters: 
Specify the filter(s) from which to create processed images. Cassini's cameras take pictures in B&W and use filter wheels to create color images. Between 1-3 filters can be inputted. If one filter is chosen all images will be outputted as B&W. Otherwise this the filters will correspond to red, green, then blue images. Filters are seperated by an underscore (_). Please refer to the [Cassini imaging user's guide](https://pds-imaging.jpl.nasa.gov/documentation/iss_data_user_guide_180916.pdf) for more information about filters including which filters are availible. Since Cassini uses dual filter wheels the user can specify either one or two filters. If only one is specified, the other filter wheel is ignored. Note: this can lead to some color differences between images. To specify a specific combination of filter wheels a comma (,) can be used between the names of the filters.
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

6. Run main.py - note: it may take a while to finish.


# Data Sources

[Processed data for use with this program]()

[Images from NASA's PDS website](https://pds-imaging.jpl.nasa.gov/search/?fq=-ATLAS_THUMBNAIL_URL%3Abrwsnotavail.jpg&fq=ATLAS_MISSION_NAME%3Acassini&q=*%3A*) Note: a wget script (included in this repository) is needed to download these images

[Attitude and instrument (SPICE) data needed for calculating where planetary bodies are located in each image](https://naif.jpl.nasa.gov/pub/naif/pds/data/co-s_j_e_v-spice-6-v1.0/cosp_1000/)

[Cassini imaging data user guide (basically my bible for writing this program)](https://pds-imaging.jpl.nasa.gov/documentation/iss_data_user_guide_180916.pdf)
